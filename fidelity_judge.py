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

Several rubric versions ship, selected with --rubric (default v2). v2.1 and
v3.1 are point revisions of v2 and v3 that touch only the `objective` anchor
(see rubric_v2_1.py); every other section is spliced through byte-identical, so
a vN -> vN.1 comparison isolates that one dimension.

v2 (rubric_v2.py, the current instrument; each 1-5, integer):

    combatants     the right sides and leaders, with a plausible roster
    setting        civilization / architecture / terrain fit the place and period
    events         the scenario reproduces what actually happened
    objective      the encoded victory and defeat conditions are the goal the
                   history posed
    pedagogy       a player would come away with an accurate impression

    The overall score is the unweighted mean of the FIRST FOUR. Pedagogy is
    scored and reported but excluded, being largely predicted by the others.
    v2 scores are NOT comparable to v1 scores: different dimension set,
    different mean.

v1 (RUBRIC below) is retained verbatim behind --rubric v1. It is the instrument
that produced the published scores, so its text is frozen.

`objective` is scored from the victory and defeat conditions EXTRACTED from the
trigger graph by reachability_audit, not from the scenario's objectives text -
that separation is what stops it collapsing into a second narration score. Two
static preconditions run before the judge and are reported next to the scores
without being shown to it: every placed named hero must appear in the brief
(combatants), and every active player must have a civilization assigned
(setting).

Usage:

    # score every scenario under a directory tree (v2 rubric)
    python fidelity_judge.py --scan output/factorial --out output/fidelity_v2.jsonl

    # re-run the frozen v1 instrument
    python fidelity_judge.py --scan output/factorial --rubric v1

    # judge reliability: same scenarios, repeated independent scorings
    python fidelity_judge.py --scan output/factorial --repeats 3

    # discriminant validity: score each scenario against the WRONG brief
    python fidelity_judge.py --scan output/factorial --mismatch-control

Every row is appended to a JSONL log; with --update-sidecars the aggregate score
is merged into each scenario's existing .meta.json next to outcome and
trigger_count.
"""

import argparse
import collections
import hashlib
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

import api_config
import rubric_v2
import rubric_v2_1
import rubric_v3
from provenance import utc_now_iso, sidecar_path
from reachability_audit import extract_objective_conditions
from scenario_inspect import (summarize, to_digest, placed_hero_names,
                              terrain_class_counts)

# A capable model by default: the judge is the measuring instrument, so it
# should not be the cheapest thing available.
DEFAULT_JUDGE_MODEL = "opus-5"
JUDGE_TEMPERATURE = 0.0
# Raised from 4000 when re-scoring under v2.1/v3.1: at 4000 roughly a quarter of
# replies were cut off mid-JSON and discarded as `judge_failed`, which is paid-for
# judgements thrown away. The cap only bounds how long a reply may be, so it
# cannot change a score that already fit under it - it only stops well-formed
# verdicts being lost. Billing is on tokens emitted, not on the cap.
JUDGE_MAX_TOKENS = 12000

DEFAULT_RUBRIC_VERSION = "v2"

# v1 dimension set. Frozen: this is what the published scores were computed over.
DIMENSIONS = ["combatants", "material", "events", "anachronism", "pedagogy"]

# v2 dimension set, from the single source of truth both sides of the pipeline
# import. All five are scored; only SCORED_DIMENSIONS enter the mean.
DIMENSIONS_V2 = list(rubric_v2.DIMENSIONS_V2)

# v3 splits v2's `setting` into `civilization` and `terrain`, and means five.
DIMENSIONS_V3 = list(rubric_v3.DIMENSIONS_V3)

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

# v2 template. The one structural difference from v1 is the objective-facts
# block: the victory and defeat conditions arrive already extracted from the
# trigger graph, and the rubric tells the judge to score `objective` from those
# and nothing else. The digest still carries the objectives text, which is what
# `pedagogy` is scored on - so the two dimensions are reading different evidence
# by construction rather than by the judge's discretion.
USER_TEMPLATE_V2 = """\
HISTORICAL EVENT THE SCENARIO CLAIMS TO DEPICT
Title: {title}
Brief: {description}
{extra}

SCENARIO CONTENT AS BUILT
{digest}

{objective_facts}

{rubric}
Return exactly this JSON shape:

{{
  "combatants": <1-5>,
  "setting": <1-5>,
  "events": <1-5>,
  "objective": <1-5>,
  "pedagogy": <1-5>,
  "issues_found": ["specific item and why it is wrong", ...],
  "strengths": ["specific accurate detail", ...],
  "justification": "2-4 sentences citing specific content"
}}"""

# v3 template. Adds the terrain digest, which is the whole reason a `terrain`
# dimension is scoreable at all: before it the judge saw rosters, triggers and
# text but no layout, so it could not have judged geography if asked.
USER_TEMPLATE_V3 = """HISTORICAL EVENT THE SCENARIO CLAIMS TO DEPICT
Title: {title}
Brief: {description}
{extra}

SCENARIO CONTENT AS BUILT
{digest}

{objective_facts}

{rubric}
Return exactly this JSON shape:

{{
  "combatants": <1-5>,
  "civilization": <1-5>,
  "terrain": <1-5>,
  "events": <1-5>,
  "objective": <1-5>,
  "pedagogy": <1-5>,
  "issues_found": ["specific item and why it is wrong", ...],
  "strengths": ["specific accurate detail", ...],
  "justification": "2-4 sentences citing specific content"
}}"""


# Everything that differs between the two instruments, in one place.
RUBRIC_VERSIONS = {
    "v1": {
        "dimensions": DIMENSIONS,
        "rubric": RUBRIC,
        "template": USER_TEMPLATE,
        "issues_key": "anachronisms_found",
        "wants_objective_facts": False,
    },
    "v2": {
        "dimensions": DIMENSIONS_V2,
        "rubric": rubric_v2.JUDGE_RUBRIC_V2,
        "template": USER_TEMPLATE_V2,
        "issues_key": "issues_found",
        "wants_objective_facts": True,
        "wants_terrain": False,
    },
    "v3": {
        "dimensions": DIMENSIONS_V3,
        "rubric": rubric_v3.JUDGE_RUBRIC_V3,
        "template": USER_TEMPLATE_V3,
        "issues_key": "issues_found",
        "wants_objective_facts": True,
        "wants_terrain": True,
    },
    # v2.1 / v3.1 revise ONE section - the objective anchor, which said
    # nothing about a victory condition's parameters and so could not tell a
    # one-second win from a thirty-minute siege hold. Everything else is
    # spliced through byte-identical from the frozen text, so the dimension
    # sets, templates and means are shared with the version they revise and
    # only the rubric string (and hence the rubric_hash) differs.
    "v2.1": {
        "dimensions": DIMENSIONS_V2,
        "rubric": rubric_v2_1.JUDGE_RUBRIC_V2_1,
        "template": USER_TEMPLATE_V2,
        "issues_key": "issues_found",
        "wants_objective_facts": True,
        "wants_terrain": False,
    },
    "v3.1": {
        "dimensions": DIMENSIONS_V3,
        "rubric": rubric_v2_1.JUDGE_RUBRIC_V3_1,
        "template": USER_TEMPLATE_V3,
        "issues_key": "issues_found",
        "wants_objective_facts": True,
        "wants_terrain": True,
    },
}

# Which mean each instrument reports, and which sidecar slot it owns. Keeping
# these keyed off the version rather than off `== "v2"` tests is what stops a
# new instrument silently inheriting v2's mean or overwriting v2's scores.
_MEAN_FAMILY = {"v1": "v1", "v2": "v2", "v2.1": "v2", "v3": "v3", "v3.1": "v3"}


def sidecar_key(version):
    """Sidecar slot for one instrument, so re-scoring never clobbers another.

    v1 keeps the historical `fidelity` key; every later version gets its own,
    `fidelity_v2`, `fidelity_v2_1`, `fidelity_v3`, ...
    """
    if version == "v1":
        return "fidelity"
    return "fidelity_" + version.replace(".", "_")


# ---------------------------------------------------------------------------
# Rubric identity.
#
# A bare version LABEL ("v2") is not enough to attribute a score: the v2 rubric
# text was revised in place - the hero anchors went from a binary rule to a
# graded one, and pedagogy stopped re-penalizing substitutions - and every row
# written before and after carries the same "v2". Nothing in those rows says
# which text produced them, so the scores could only be dated by an indirect
# fingerprint. Stamping the exact text ends that: two rows are comparable when
# their hashes match, and the analysis refuses to average across a mismatch.
#
# The hash covers the rubric text pasted into the judge prompt, because that is
# what determines a score. rubric_module_hash additionally covers the whole
# rubric_v2 source, so a change to the static preconditions recorded alongside
# the scores is visible too; it is informational and not a pooling key, since it
# moves on comment edits that cannot affect a judgement.
# ---------------------------------------------------------------------------
def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _module_hash():
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "rubric_v2.py"), encoding="utf-8") as f:
            return _sha(f.read())
    except Exception:
        return None


# Rubric versions whose text has never been revised, so a row written before
# hash stamping existed is unambiguously attributable to the current text.
# ONLY v1 qualifies, and only because it is frozen by policy - the v2 text was
# revised in place, which is the whole reason the hash was introduced, so an
# unstamped v2 row cannot be told apart from a pre-revision one.
UNSTAMPED_IS_UNAMBIGUOUS = frozenset({"v1"})


def rubric_matches(row, version, current_hash):
    """Is `row` a judgement against the exact rubric text this run is using?"""
    if row.get("rubric_version", "v1") != version:
        return False
    if row.get("rubric_hash") == current_hash:
        return True
    return row.get("rubric_hash") is None and version in UNSTAMPED_IS_UNAMBIGUOUS


def _mean_for(version, scores):
    """Overall score under one instrument.

    v1 averages all five dimensions. v2 averages only the four scored ones -
    pedagogy is reported but deliberately excluded - via rubric_v2.overall_score,
    so the definition of the headline number lives with the rubric text it
    belongs to.
    """
    family = _MEAN_FAMILY.get(version, version)
    if family == "v3":
        return round(rubric_v3.overall_score_v3(scores), 3)
    if family == "v2":
        return round(rubric_v2.overall_score(scores), 3)
    return round(sum(scores.values()) / len(scores), 3)


def static_preconditions(summary, title, description):
    """The two pass/fail checks that run BEFORE the judge and need no model.

    Reported alongside the scores but never shown to the judge: they are an
    independent signal, and feeding them in would just be telling the judge what
    to think about two of the dimensions it is meant to score for itself.
    """
    heroes = placed_hero_names(summary)
    brief = f"{title}\n{description}"
    comb_ok, unsupported = rubric_v2.check_combatants_precondition(heroes, brief)
    civs = summary.get("player_civilizations") or {}
    set_ok, unassigned = rubric_v2.check_setting_precondition(civs)
    return {
        "combatants_precondition": {
            "passed": comb_ok,
            "placed_heroes": heroes,
            "unsupported_heroes": unsupported,
        },
        "setting_precondition": {
            "passed": set_ok,
            "player_civilizations": {str(k): v for k, v in civs.items()},
            "unassigned_players": unassigned,
        },
    }


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
                   extra_context="", repeat_index=1,
                   rubric_version=DEFAULT_RUBRIC_VERSION):
    """Score one scenario against one historical brief. Returns a result row."""
    spec = RUBRIC_VERSIONS[rubric_version]
    dimensions = spec["dimensions"]
    row = {
        "scenario": scenario_path,
        "title": title,
        "judge_model": api_config.resolve_model(model),
        "rubric_version": rubric_version,
        # Identity of the exact grading text, so this row can never be pooled
        # with one graded against different anchors.
        "rubric_hash": _sha(spec["rubric"]),
        "rubric_module_hash": _module_hash(),
        "repeat": repeat_index,
        "timestamp_utc": utc_now_iso(),
    }
    try:
        # v2 resolves a victory condition's unit_object to the unit it names, so
        # it needs the placed-object table that include_map carries.
        summary = summarize(scenario_path,
                            include_map=spec["wants_objective_facts"])
    except Exception as e:
        return {**row, "ok": False, "error": f"parse_failed: {e}"}

    extras = {}
    if spec.get("wants_terrain"):
        counts = terrain_class_counts(summary)
        passed, distinct = rubric_v3.check_terrain_precondition(counts)
        row["terrain_precondition"] = {
            "passed": passed,
            "distinct_classes": distinct,
            "tile_counts": counts,
            # All-zero elevation is invisible in the class counts but is exactly
            # the "flat ground where it turned on elevation" the rubric anchors
            # a 1 on, so it is recorded separately.
            "uses_elevation": any(v for row_ in (summary.get("elevation_grid") or [])
                                  for v in row_),
        }
    if spec["wants_objective_facts"]:
        victory, defeat = extract_objective_conditions(summary)
        extras["objective_facts"] = rubric_v2.format_objective_facts(victory, defeat)
        row["objective_facts"] = extras["objective_facts"]
        # Computed here, reported in the row, and deliberately NOT in the prompt.
        row.update(static_preconditions(summary, title, description))

    prompt = spec["template"].format(
        title=title, description=description, extra=extra_context,
        digest=to_digest(summary,
                         include_civilizations=spec["wants_objective_facts"],
                         include_terrain=spec.get("wants_terrain", False)),
        rubric=spec["rubric"], **extras)

    # A reply occasionally omits a dimension or returns null for one; re-ask
    # once, naming the offender, before giving up on the judgement.
    scores, verdict, err = {}, None, None
    for attempt in range(2):
        ask = prompt if attempt == 0 else (
            prompt + f"\n\nYour previous reply left {err} missing or null. "
                     f"Every one of the {len(dimensions)} dimensions must be "
                     "an integer 1-5.")
        try:
            verdict = _extract_json(call_judge(api_key, ask, model))
        except Exception as e:
            return {**row, "ok": False, "error": f"judge_failed: {e}"}
        scores, missing = {}, []
        for dim in dimensions:
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
        "mean": _mean_for(rubric_version, scores),
        # v3 splits `setting` in two, so its raw mean is not on the v2 scale.
        # The bridge recombines the halves into a v2-shaped MEAN4 so the
        # longitudinal series survives; reported alongside, never instead of.
        **({"bridge_mean_v2": round(rubric_v3.bridge_score_v2(scores), 3)}
           if _MEAN_FAMILY.get(rubric_version) == "v3" else {}),
        spec["issues_key"]: verdict.get(spec["issues_key"]) or [],
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


def read_log(path):
    """Every successfully-judged row in a results log, skipping junk lines.

    Both --resume and the sidecar aggregation read the log back rather than
    relying on what the current invocation produced, since a sweep is normally
    made of several passes.
    """
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if row.get("ok"):
                rows.append(row)
    return rows


def update_sidecar(scenario_path, aggregate, key="fidelity"):
    """Merge fidelity scores into the scenario's existing metadata sidecar.

    key separates the instruments: v1 keeps `fidelity`, v2 writes `fidelity_v2`,
    so a scenario can carry both and neither clobbers the other.
    """
    path = sidecar_path(scenario_path)
    try:
        with open(path, encoding="utf-8") as f:
            meta = json.load(f)
    except Exception:
        return False
    meta[key] = aggregate
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
    ap.add_argument("--rubric", choices=sorted(RUBRIC_VERSIONS),
                    default=DEFAULT_RUBRIC_VERSION,
                    help="Rubric version. v1 is the frozen published instrument; v2 "
                         "(default) means four dimensions with pedagogy reported but "
                         "excluded; v3 splits `setting` and means five; v2.1/v3.1 revise "
                         "only the `objective` anchor of v2/v3. Scores from different "
                         "versions are NOT comparable, and --resume keys on the rubric "
                         "hash, so a revision re-scores rather than reusing stale rows")
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

    current_hash = _sha(RUBRIC_VERSIONS[args.rubric]["rubric"])

    # Already-successful (scenario, repeat, mode) tuples, so --resume can skip
    # them instead of paying for the same judgement twice. Only rows graded
    # against THIS run's exact rubric text get in, so a log holding several
    # instruments resumes each of them independently.
    done = set()
    if args.resume:
        for r in read_log(args.out):
            # The rubric hash is part of the key: a row graded against an older
            # revision of the same version does NOT satisfy a request under the
            # current text, so --resume re-scores it instead of silently keeping
            # a stale judgement.
            if rubric_matches(r, args.rubric, current_hash):
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
          f"[{mode}]  rubric={args.rubric} ({current_hash})  "
          f"judge={api_config.resolve_model(args.model)}", flush=True)

    # Append each judgement as it lands rather than buffering to the end: a
    # sweep that dies partway (rate limit, interrupt) then keeps everything it
    # already paid for, and --resume can pick up from exactly there.
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    rows = []
    t0 = time.time()
    with open(args.out, "a", encoding="utf-8") as out_f, \
            ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(score_scenario, api_key, path, title, desc, args.model,
                          "", rep, args.rubric): (path, mismatch)
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

    spec = RUBRIC_VERSIONS[args.rubric]
    dimensions = spec["dimensions"]
    good = [r for r in rows if r.get("ok")]
    print(f"\n{len(good)}/{len(rows)} scored in {(time.time()-t0)/60:.1f} min -> {args.out}")
    if good:
        for dim in dimensions:
            vals = [r[dim] for r in good]
            excluded = (_MEAN_FAMILY.get(args.rubric) == "v2"
                        and dim not in rubric_v2.SCORED_DIMENSIONS)
            note = "   (reported, not in the mean)" if excluded else ""
            print(f"  {dim:<14} {sum(vals)/len(vals):.2f}{note}")
        means = [r["mean"] for r in good]
        label = ("mean (4 dims)" if _MEAN_FAMILY.get(args.rubric) == "v2"
                 else "mean")
        print(f"  {label:<14} {sum(means)/len(means):.2f}")

    # The static checks are the part of the evaluation that does not depend on
    # the judge at all, so they get reported whether or not the judging landed.
    with_pre = [r for r in rows if "combatants_precondition" in r]
    if with_pre:
        by_scenario = {}
        for r in with_pre:
            by_scenario[os.path.normpath(r["scenario"])] = r
        n = len(by_scenario)
        comb = sum(1 for r in by_scenario.values()
                   if r["combatants_precondition"]["passed"])
        sett = sum(1 for r in by_scenario.values()
                   if r["setting_precondition"]["passed"])
        heroes = sum(len(r["combatants_precondition"]["placed_heroes"])
                     for r in by_scenario.values())
        flagged = sum(len(r["combatants_precondition"]["unsupported_heroes"])
                      for r in by_scenario.values())
        print(f"\n  Static preconditions over {n} scenario(s)")
        print(f"    combatants (every placed hero named in the brief): "
              f"{comb}/{n} pass   [{flagged}/{heroes} placed heroes unsupported]")
        print(f"    setting (civilization set for every active player): "
              f"{sett}/{n} pass")

    if args.update_sidecars and not args.mismatch_control:
        # Aggregate from the whole log, not from what THIS invocation happened
        # to score. A sweep is routinely run in several passes - one per
        # directory, then a --resume top-up for the failures - and aggregating
        # per-invocation made each pass overwrite the sidecar with only its own
        # batch, so a scenario scored 3x ended up recorded as n_judgements: 1
        # with the mean of whichever single repeat came last. Reading the log
        # back makes the sidecar reflect every judgement under this exact
        # rubric text, and makes `--update-sidecars --resume` with nothing left
        # to score a cheap way to repair sidecars written by the old behaviour.
        by_path = collections.defaultdict(list)
        for r in read_log(args.out):
            if (rubric_matches(r, args.rubric, current_hash)
                    and not r.get("mismatch_control")):
                by_path[r["scenario"]].append(r)
        for path, group in by_path.items():
            # Deterministic despite append order, so re-running is a no-op.
            group.sort(key=lambda r: (r.get("repeat", 1), r.get("timestamp_utc", "")))
            aggregate = {"judge_model": group[0]["judge_model"],
                         "rubric_version": args.rubric,
                         "rubric_hash": current_hash,
                         "n_judgements": len(group)}
            for dim in dimensions + ["mean"]:
                aggregate[dim] = round(sum(g[dim] for g in group) / len(group), 3)
            aggregate[spec["issues_key"]] = group[0][spec["issues_key"]]
            for key in ("combatants_precondition", "setting_precondition"):
                if key in group[0]:
                    aggregate[key] = group[0][key]
            # v1 wrote its scores at meta["fidelity"]; keep that slot for the
            # published instrument and give every later instrument its own, so
            # re-scoring with one never silently overwrites another.
            update_sidecar(path, aggregate, key=sidecar_key(args.rubric))
        print(f"  updated {len(by_path)} sidecar(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
