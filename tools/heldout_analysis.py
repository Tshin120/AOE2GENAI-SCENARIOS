#!/usr/bin/env python3
"""Held-out generalization test for the API-facts result.

The API facts were extracted from the ORIGINAL eight episodes' failures, so the
standing objection is that they are eight specific patches rather than a general
fix. This compares the same base -> base+rubric+API contrast on eight held-out
episodes against the original corpus.

The held-out episodes are deliberately DIFFERENT (scenario types, regions, and
civilizations the original never used; figures with no AoE2 hero unit; polities
with no clean `Civilization` enum match), not deliberately hard. A lower
absolute score on this set therefore does not refute generalization. The DELTA
is the measurement, and both corpora are measured the same way here: paired
per-episode, same CI method, same rubric hash.

    python tools/heldout_analysis.py --rubric-hash c51d48535325f97f
"""

import argparse
import collections
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import rubric_v2

DIMS = list(rubric_v2.DIMENSIONS_V2)
SCORED = list(rubric_v2.SCORED_DIMENSIONS)
T95 = {5: 2.776, 6: 2.571, 7: 2.447, 8: 2.365, 9: 2.306, 10: 2.262}  # df -> t(.975)


def load_scores(path, rubric_hash, version):
    """scenario path -> per-dimension mean over that scenario's repeats."""
    acc = collections.defaultdict(lambda: collections.defaultdict(list))
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if not r.get("ok") or r.get("mismatch_control"):
                continue
            if r.get("rubric_version") != version or r.get("rubric_hash") != rubric_hash:
                continue
            key = os.path.normpath(r["scenario"]).replace("\\", "/")
            for d in DIMS:
                acc[key][d].append(r[d])
    return {k: {d: sum(v) / len(v) for d, v in dd.items()} for k, dd in acc.items()}


def episode(path):
    return os.path.basename(path).replace(".aoe2scenario", "")


def under(scores, root):
    """Restrict a score table to one cell directory, keyed by episode."""
    root = root.replace("\\", "/").rstrip("/") + "/"
    return {episode(k): v for k, v in scores.items() if k.startswith(root)}


def paired(a, b, dim):
    """(episodes, per-episode deltas) for episodes present in BOTH conditions."""
    keys = sorted(set(a) & set(b))
    return keys, [b[k][dim] - a[k][dim] for k in keys]


def ci95(xs):
    """Mean and t-based 95% CI of paired deltas. Returns (mean, lo, hi, sd)."""
    n = len(xs)
    m = sum(xs) / n
    if n < 2:
        return m, float("nan"), float("nan"), float("nan")
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))
    h = T95.get(n - 1, 2.365) * sd / math.sqrt(n)
    return m, m - h, m + h, sd


def mean4(row):
    return sum(row[d] for d in SCORED) / len(SCORED)


def build_stats(results_log):
    """First-attempt rate and repair attempts from a cell's results.jsonl.

    Two things this has to get right, both of which bite:

    `api_error` is a TRANSPORT failure, not a code failure. It is retried under
    the same (candidate, attempt) key and does not mean the generated code was
    wrong, so it must not count against the build rate or inflate the attempt
    count. One original-arm episode logs `c1a1:api_error | c1a1:success` and
    reads as a build failure if you take the last row by attempt number.

    Terminal outcome is therefore the last row in FILE order, and the attempt
    count is taken from the code-bearing rows only.
    """
    if not os.path.exists(results_log):
        return None
    runs = collections.defaultdict(list)
    with open(results_log, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            runs[r.get("title")].append(r)
    per_ep = {}
    for title, rows in runs.items():
        terminal = rows[-1]                                   # file order
        code_rows = [r for r in rows if r.get("outcome") != "api_error"]
        attempts = max((r.get("attempt", 1) for r in code_rows), default=1)
        cand = max((r.get("candidate", 1) for r in code_rows), default=1)
        per_ep[title] = {"candidate": cand, "attempts": attempts,
                         "outcome": terminal.get("outcome"),
                         "api_errors": len(rows) - len(code_rows)}
    n = len(per_ep)
    built = sum(1 for v in per_ep.values() if v["outcome"] == "success")
    first = sum(1 for v in per_ep.values()
                if v["outcome"] == "success" and v["attempts"] == 1 and v["candidate"] == 1)
    att = [v["attempts"] for v in per_ep.values()]
    return {"n": n, "built": built, "first_attempt": first,
            "mean_attempts": round(sum(att) / n, 2) if n else float("nan"),
            "per_episode": per_ep}


def preconditions(score_log, rubric_hash, version, root):
    """combatants / setting precondition pass counts, from the judge's rows."""
    root = root.replace("\\", "/").rstrip("/") + "/"
    seen = {}
    with open(score_log, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if not r.get("ok") or r.get("mismatch_control"):
                continue
            if r.get("rubric_version") != version or r.get("rubric_hash") != rubric_hash:
                continue
            k = os.path.normpath(r["scenario"]).replace("\\", "/")
            if not k.startswith(root) or "combatants_precondition" not in r:
                continue
            seen[episode(k)] = (r["combatants_precondition"]["passed"],
                                r["setting_precondition"]["passed"],
                                r["setting_precondition"].get("unassigned_players") or [],
                                r["combatants_precondition"].get("unsupported_heroes") or [])
    return seen


def repair_vs_civ(build, precon):
    """Trap 2: did self-repair strip the civilization assignments?

    Self-repair is fidelity-blind - it removes instructions it cannot execute,
    and in the pre-API arm it deleted civilization assignments in 5 of 7
    scenarios. The generating code is not retained per attempt, so the strip
    cannot be observed directly; what IS observable is its consequence. This
    cross-tabs "needed repair" against "failed the civilization precondition".
    A strip shows up as failures concentrated in the repaired rows.
    """
    rows = []
    for title, v in (build or {}).get("per_episode", {}).items():
        key = None
        for ep in precon:
            if ep.replace("_", " ").lower() in title.lower().replace("'", "") or \
               title.lower().replace("'", "").replace(" ", "_").strip("_").endswith(ep):
                key = ep
                break
        p = precon.get(key) if key else None
        rows.append({"title": title, "attempts": v["attempts"],
                     "repaired": v["attempts"] > 1, "outcome": v["outcome"],
                     "setting_ok": (p[1] if p else None),
                     "unassigned": (p[2] if p else None)})
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--rubric-hash", default="c51d48535325f97f")
    ap.add_argument("--rubric-version", default="v2.1")
    ap.add_argument("--heldout-scores", default="output/fidelity_heldout.jsonl")
    ap.add_argument("--orig-scores", default="output/fidelity_v2_1.jsonl")
    ap.add_argument("--base-root", default="output/heldout_base/reach_off__freeform")
    ap.add_argument("--api-root", default="output/heldout_api/fidelity_on__freeform")
    ap.add_argument("--orig-base-root", default="output/factorial/reach_off__freeform")
    ap.add_argument("--orig-api-root", default="output/fidelity_v2_arm_api/fidelity_on__freeform")
    args = ap.parse_args()

    ho = load_scores(args.heldout_scores, args.rubric_hash, args.rubric_version)
    og = load_scores(args.orig_scores, args.rubric_hash, args.rubric_version)
    sets = {
        "held-out 8": (under(ho, args.base_root), under(ho, args.api_root)),
        "original 8": (under(og, args.orig_base_root), under(og, args.orig_api_root)),
    }

    out = {}
    for label, (A, B) in sets.items():
        keys = sorted(set(A) & set(B))
        print(f"\n{'='*78}\n{label}  -  {len(keys)} paired episode(s), rubric {args.rubric_version} "
              f"({args.rubric_hash})\n{'='*78}")
        if not keys:
            print("  no paired scores yet")
            continue
        print(f"{'dimension':<14}{'A base':>9}{'B base+rubric+API':>20}{'delta':>9}"
              f"{'95% CI':>20}")
        print("-" * 72)
        res = {}
        for dim in DIMS + ["MEAN4"]:
            if dim == "MEAN4":
                da = {k: {"MEAN4": mean4(A[k])} for k in keys}
                db = {k: {"MEAN4": mean4(B[k])} for k in keys}
                _k, d = paired(da, db, "MEAN4")
                ma = sum(mean4(A[k]) for k in keys) / len(keys)
                mb = sum(mean4(B[k]) for k in keys) / len(keys)
            else:
                _k, d = paired(A, B, dim)
                ma = sum(A[k][dim] for k in keys) / len(keys)
                mb = sum(B[k][dim] for k in keys) / len(keys)
            m, lo, hi, sd = ci95(d)
            star = "  *" if dim == "pedagogy" else ""
            print(f"{dim:<14}{ma:>9.2f}{mb:>20.2f}{m:>+9.2f}"
                  f"{f'[{lo:+.2f}, {hi:+.2f}]':>20}{star}")
            res[dim] = {"A": round(ma, 3), "B": round(mb, 3), "delta": round(m, 3),
                        "ci": [round(lo, 3), round(hi, 3)], "sd": round(sd, 3)}
        print("  * pedagogy is reported but excluded from MEAN4")
        print(f"\n  per-episode MEAN4 deltas: "
              + ", ".join(f"{k.split('_')[-1][:12]}={mean4(B[k])-mean4(A[k]):+.2f}" for k in keys))
        out[label] = res
    return out


if __name__ == "__main__":
    main()
