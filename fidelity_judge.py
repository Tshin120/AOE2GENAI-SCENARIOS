"""
LLM fidelity judge.

Build success and playability preconditions are machine-checked elsewhere in
this pipeline. Historical fidelity is the dimension that would normally require
expert annotation; this module scores it with an LLM against a fixed rubric so
the whole evaluation can be rerun as models and prompts change.

What the judge sees is a *content digest* of the built ``.aoe2scenario``
(rosters, trigger structure, in-game text) produced by ``scenario_inspect`` -
never the generating code, the model name, or the prompt condition. The arm is
therefore not recoverable from the judge's input, so scores cannot be biased by
knowing which condition produced a scenario.

Rubric (each 1-5, integer; see RUBRIC below for anchors):

    combatants     the right sides, led by the right people
    material       terrain / architecture / rosters fit the place and century
    events         objective sequence tracks what actually happened
    anachronism    freedom from out-of-period, out-of-region content
    pedagogy       a player would come away with an accurate impression

Usage:

    # score every scenario under a directory tree
    python fidelity_judge.py --scan output/factorial --out output/fidelity.jsonl

    # judge reliability: same scenarios, repeated independent scorings
    python fidelity_judge.py --scan output/factorial --repeats 3

    # discriminant validity: score each scenario against the WRONG brief
    python fidelity_judge.py --scan output/factorial --mismatch-control

Every row is appended to a JSONL log; with --update-sidecars the aggregate score
is merged into each scenario's existing .meta.json next to outcome and
trigger_count.
"""

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

import api_config
from provenance import utc_now_iso, sidecar_path
from scenario_inspect import summarize, to_digest

# A capable model by default: the judge is the measuring instrument, so it
# should not be the cheapest thing available.
DEFAULT_JUDGE_MODEL = "opus-5"
JUDGE_TEMPERATURE = 0.0
JUDGE_MAX_TOKENS = 4000

DIMENSIONS = ["combatants", "material", "events", "anachronism", "pedagogy"]

RUBRIC = """\
Score each dimension 1-5 (integers only).

combatants - Are the two sides the actual historical belligerents, with
  leaders/heroes who were really present at this event?
    5 both sides correct, named leaders historically present
    3 sides roughly right but leaders generic, absent, or misattributed
    1 wrong belligerents entirely

material - Do terrain, architecture, and unit rosters match the region and
  century of the event?
    5 rosters and buildings plausible for both cultures at this date
    3 broadly regional but with generic or mismatched elements
    1 material culture belongs to another part of the world

events - Does the sequence of objectives and scripted beats track the actual
  course of the event?
    5 recognisable as this event's real narrative arc, correct outcome logic
    3 generic battle/journey shape with a few real details attached
    1 unrelated to what happened

anachronism - Freedom from content that could not exist at this time and place.
  Judge specific placed content, not the engine's inherent limits.
    5 nothing out of period or out of region
    3 one or two noticeable intrusions
    1 pervasive anachronism (wrong-century heroes, wrong-culture architecture)

pedagogy - Would a student who played this come away with an accurate
  impression of the event?
    5 accurate and instructive
    3 harmless but uninformative
    1 actively misleading
"""

SYSTEM_PROMPT = """\
You are a military historian evaluating whether a game scenario faithfully \
represents a specific historical event. You are rigorous and specific: you name \
the exact units, buildings, or characters that are wrong, and you do not give \
credit for surface-level references in text when the placed content contradicts \
them.

Important: the scenario is built in Age of Empires II, whose unit and building \
catalogue is finite and medieval-European-centric. Do not penalise the scenario \
for the engine lacking an exact unit; penalise it only for choices that were \
avoidable given what the engine does offer. Placing a named hero from the wrong \
century IS avoidable and should be penalised.

Respond with a single JSON object and nothing else."""

USER_TEMPLATE = """\
HISTORICAL EVENT THE SCENARIO CLAIMS TO DEPICT
Title: {title}
Brief: {description}
{extra}

SCENARIO CONTENT AS BUILT
{digest}

{rubric}
Return exactly this JSON shape:

{{
  "combatants": <1-5>,
  "material": <1-5>,
  "events": <1-5>,
  "anachronism": <1-5>,
  "pedagogy": <1-5>,
  "anachronisms_found": ["specific item and why it is wrong", ...],
  "strengths": ["specific accurate detail", ...],
  "justification": "2-4 sentences citing specific content"
}}"""


def _extract_json(text):
    """Pull the JSON object out of a model reply that may be fenced or padded."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"no JSON object in reply: {text[:200]}")
    return json.loads(text[start:end + 1])


def call_judge(api_key, prompt, model, timeout=api_config.REQUEST_TIMEOUT,
               retries=4):
    """POST one judging request, retrying transient rate/credit/server errors.

    Bursts of concurrent requests can trip 402/429 even with credit remaining,
    so those back off and retry rather than losing the judgement.
    """
    delay = 5.0
    last = None
    for attempt in range(retries):
        try:
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}",
                         "Content-Type": "application/json",
                         "HTTP-Referer": "https://aoe2scenario-generator.com",
                         "X-Title": "AoE2 Scenario Fidelity Judge"},
                json={"model": api_config.resolve_model(model),
                      "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                                   {"role": "user", "content": prompt}],
                      "temperature": JUDGE_TEMPERATURE,
                      "max_tokens": JUDGE_MAX_TOKENS},
                timeout=timeout)
            if resp.status_code in (402, 408, 429, 500, 502, 503, 504):
                last = f"{resp.status_code}: {resp.text[:160]}"
                if attempt < retries - 1:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise RuntimeError(last)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except requests.RequestException as e:
            last = str(e)
            if attempt == retries - 1:
                raise
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(last or "judge call failed")


def score_scenario(api_key, scenario_path, title, description, model,
                   extra_context="", repeat_index=1):
    """Score one scenario against one historical brief. Returns a result row."""
    row = {
        "scenario": scenario_path,
        "title": title,
        "judge_model": api_config.resolve_model(model),
        "repeat": repeat_index,
        "timestamp_utc": utc_now_iso(),
    }
    try:
        summary = summarize(scenario_path)
    except Exception as e:
        return {**row, "ok": False, "error": f"parse_failed: {e}"}

    prompt = USER_TEMPLATE.format(
        title=title, description=description,
        extra=extra_context, digest=to_digest(summary), rubric=RUBRIC)

    # A reply occasionally omits a dimension or returns null for one; re-ask
    # once, naming the offender, before giving up on the judgement.
    scores, verdict, err = {}, None, None
    for attempt in range(2):
        ask = prompt if attempt == 0 else (
            prompt + f"\n\nYour previous reply left {err} missing or null. "
                     "Every one of the five dimensions must be an integer 1-5.")
        try:
            verdict = _extract_json(call_judge(api_key, ask, model))
        except Exception as e:
            return {**row, "ok": False, "error": f"judge_failed: {e}"}
        scores, missing = {}, []
        for dim in DIMENSIONS:
            try:
                scores[dim] = max(1, min(5, int(verdict[dim])))
            except Exception:
                missing.append(dim)
        if not missing:
            break
        err = ", ".join(missing)
    else:
        return {**row, "ok": False, "error": f"missing scores after retry: {err}"}

    return {
        **row,
        "ok": True,
        **scores,
        "mean": round(sum(scores.values()) / len(scores), 3),
        "anachronisms_found": verdict.get("anachronisms_found") or [],
        "strengths": verdict.get("strengths") or [],
        "justification": verdict.get("justification", ""),
        "trigger_count": summary["trigger_count"],
        "unit_total": summary["unit_total"],
    }


def find_scenarios(root):
    """Every .aoe2scenario under root that has a readable .meta.json sidecar.

    The sidecar supplies the historical brief the scenario was generated from,
    which is exactly what the judge scores against.
    """
    found = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in sorted(filenames):
            if not name.endswith(".aoe2scenario"):
                continue
            path = os.path.join(dirpath, name)
            meta = sidecar_path(path)
            if not os.path.exists(meta):
                continue
            try:
                with open(meta, encoding="utf-8") as f:
                    found.append((path, json.load(f)))
            except Exception:
                continue
    return found


def update_sidecar(scenario_path, aggregate):
    """Merge fidelity scores into the scenario's existing metadata sidecar."""
    path = sidecar_path(scenario_path)
    try:
        with open(path, encoding="utf-8") as f:
            meta = json.load(f)
    except Exception:
        return False
    meta["fidelity"] = aggregate
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    return True


def main():
    ap = argparse.ArgumentParser(description="Score generated scenarios for historical fidelity.")
    ap.add_argument("--scan", default="output",
                    help="Directory tree to scan for .aoe2scenario + sidecar pairs")
    ap.add_argument("--scenario", help="Score a single scenario file instead of scanning")
    ap.add_argument("--title", help="Override the historical title (single-scenario mode)")
    ap.add_argument("--description", help="Override the brief (single-scenario mode)")
    ap.add_argument("--model", default=DEFAULT_JUDGE_MODEL, help="Judge model")
    ap.add_argument("--out", default="output/fidelity.jsonl", help="Append-only results log")
    ap.add_argument("--repeats", type=int, default=1,
                    help="Independent scorings per scenario (judge self-consistency)")
    ap.add_argument("--mismatch-control", action="store_true",
                    help="Score each scenario against a DIFFERENT scenario's brief. "
                         "A judge with discriminant validity should score these far lower.")
    ap.add_argument("--workers", type=int, default=3,
                    help="Concurrent judge calls. Keep low: bursts trip 402/429.")
    ap.add_argument("--resume", action="store_true",
                    help="Skip (scenario, repeat) pairs already scored OK in --out, "
                         "so an interrupted or partly-failed sweep is topped up "
                         "instead of paid for twice")
    ap.add_argument("--update-sidecars", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("OPENROUTER_API_KEY is not set", file=sys.stderr)
        return 1

    if args.scenario:
        meta = {}
        try:
            with open(sidecar_path(args.scenario), encoding="utf-8") as f:
                meta = json.load(f)
        except Exception:
            pass
        targets = [(args.scenario, {
            "title": args.title or meta.get("title") or os.path.basename(args.scenario),
            "description": args.description or meta.get("description", ""),
        })]
    else:
        targets = find_scenarios(args.scan)
    if args.limit:
        targets = targets[:args.limit]
    if not targets:
        print(f"No scenario+sidecar pairs found under {args.scan}", file=sys.stderr)
        return 1

    # Already-successful (scenario, repeat, mode) triples, so --resume can skip
    # them instead of paying for the same judgement twice.
    done = set()
    if args.resume and os.path.exists(args.out):
        with open(args.out, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("ok"):
                    done.add((os.path.normpath(r["scenario"]), r.get("repeat", 1),
                              bool(r.get("mismatch_control"))))

    # In mismatch mode each scenario is paired with the next distinct title's
    # brief, so every pairing is a genuine mismatch.
    jobs = []
    for i, (path, meta) in enumerate(targets):
        for rep in range(1, args.repeats + 1):
            if (os.path.normpath(path), rep, bool(args.mismatch_control)) in done:
                continue
            if args.mismatch_control:
                others = [m for _p, m in targets if m.get("title") != meta.get("title")]
                if not others:
                    continue
                brief = others[i % len(others)]
                jobs.append((path, brief.get("title", ""), brief.get("description", ""), rep, True))
            else:
                jobs.append((path, meta.get("title", ""), meta.get("description", ""), rep, False))

    mode = "MISMATCH CONTROL" if args.mismatch_control else "matched"
    print(f"Judging {len(targets)} scenario(s) x {args.repeats} repeat(s) = {len(jobs)} calls "
          f"[{mode}]  judge={api_config.resolve_model(args.model)}", flush=True)

    # Append each judgement as it lands rather than buffering to the end: a
    # sweep that dies partway (rate limit, interrupt) then keeps everything it
    # already paid for, and --resume can pick up from exactly there.
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    rows = []
    t0 = time.time()
    with open(args.out, "a", encoding="utf-8") as out_f, \
            ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(score_scenario, api_key, path, title, desc, args.model,
                          "", rep): (path, mismatch)
                for path, title, desc, rep, mismatch in jobs}
        for n, fut in enumerate(as_completed(futs), 1):
            path, mismatch = futs[fut]
            row = fut.result()
            row["mismatch_control"] = mismatch
            rows.append(row)
            out_f.write(json.dumps(row, ensure_ascii=False) + "\n")
            out_f.flush()
            label = os.path.basename(os.path.dirname(path)) + "/" + os.path.basename(path)
            if row.get("ok"):
                print(f"[{n}/{len(jobs)}] mean={row['mean']:.2f}  {label}", flush=True)
            else:
                print(f"[{n}/{len(jobs)}] ERROR {row.get('error','')[:90]}  {label}", flush=True)

    good = [r for r in rows if r.get("ok")]
    print(f"\n{len(good)}/{len(rows)} scored in {(time.time()-t0)/60:.1f} min -> {args.out}")
    if good:
        for dim in DIMENSIONS + ["mean"]:
            vals = [r[dim] for r in good]
            print(f"  {dim:<14} {sum(vals)/len(vals):.2f}")

    if args.update_sidecars and not args.mismatch_control:
        by_path = {}
        for r in good:
            by_path.setdefault(r["scenario"], []).append(r)
        for path, group in by_path.items():
            aggregate = {"judge_model": group[0]["judge_model"], "n_judgements": len(group)}
            for dim in DIMENSIONS + ["mean"]:
                aggregate[dim] = round(sum(g[dim] for g in group) / len(group), 3)
            aggregate["anachronisms_found"] = group[0]["anachronisms_found"]
            update_sidecar(path, aggregate)
        print(f"  updated {len(by_path)} sidecar(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
