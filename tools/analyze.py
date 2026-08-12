#!/usr/bin/env python3
"""
Join the three evidence streams into the tables the paper reports.

  1. build outcomes        results.jsonl written by every generation attempt
  2. reachability          reachability_audit.py over the built scenarios
  3. historical fidelity   fidelity_judge.py rubric scores

Each stream is keyed on the scenario output path, so a row is one (episode,
cell) pair and every metric for it lines up.

    python tools/analyze.py --root output/factorial \
        --reachability output/reachability.jsonl \
        --fidelity output/fidelity.jsonl,output/fidelity_v2_rev2.jsonl,output/fidelity_v2_1.jsonl \
        --latex output/tables.tex

Fidelity rows carry both the rubric version they were scored under and the hash
of the exact grading text, and every distinct (version, hash) pair is rendered
as its own table - never pooled. v1 scores five dimensions and means all five;
v2 scores combatants/setting/events/objective/pedagogy and means the first four;
v3 splits `setting` into `civilization` and `terrain` and means five. A `.1`
version is a point revision that reworded one anchor without changing the
dimension set, so it shares its parent's columns but still gets its own table -
scores either side of a reworded anchor are different measurements.

Rows written before the version field existed are v1 by definition.
"""

import argparse
import glob
import json
import math
import os
import re
from collections import defaultdict

CELL_LABEL = {
    "reach_on__templated": ("on", "templated"),
    "reach_off__templated": ("off", "templated"),
    "reach_on__freeform": ("on", "freeform"),
    "reach_off__freeform": ("off", "freeform"),
    # Fidelity arms. The style column carries the fidelity block's version, so
    # the two-column labelling still identifies the cell exactly.
    "rubric_on__freeform": ("off", "freeform/v1"),
    "fidelity_on__freeform": ("off", "freeform/v2"),
    "fidelity_on__reach_on__freeform": ("on", "freeform/v2"),
    "fidelity_v3__freeform": ("off", "freeform/v3"),
}

# The judge's dimension set changed with the rubric. Rows carry the version they
# were scored under; rows predating the field are v1 by definition, since v2 has
# never been written without it. Every version is rendered as its own table and
# they are never averaged together: v2 drops `anachronism`, renames `material`
# to `setting`, adds `objective`, and means four dimensions rather than five;
# v3 splits `setting` into `civilization` and `terrain` and means five.
#
# A `.1` suffix is a point revision that changed one anchor's wording and
# nothing structural, so it shares its parent's dimensions, mean and headers -
# but NOT its table. Scores either side of a reworded anchor are different
# measurements, which is what the rubric hash exists to keep apart.
FAMILY = {"v1": "v1", "v2": "v2", "v2.1": "v2", "v3": "v3", "v3.1": "v3"}

DIMS_BY_FAMILY = {
    "v1": ["combatants", "material", "events", "anachronism", "pedagogy"],
    "v2": ["combatants", "setting", "events", "objective", "pedagogy"],
    "v3": ["combatants", "civilization", "terrain", "events", "objective",
           "pedagogy"],
}
# Reported but excluded from the overall mean, per family.
UNSCORED_BY_FAMILY = {"v1": set(), "v2": {"pedagogy"}, "v3": {"pedagogy"}}
MEAN_LABEL = {"v1": "MEAN", "v2": "MEAN4", "v3": "MEAN5"}


def family(version):
    """Which dimension set a rubric version belongs to.

    Unknown versions raise rather than defaulting to v1. A silent fallback
    would print a v1 column header over v3 numbers and label it a mean over
    five dimensions that are not the five being shown - a wrong table that
    looks right, which is worse than no table.
    """
    try:
        return FAMILY[version]
    except KeyError:
        raise SystemExit(
            f"ERROR: unknown rubric version {version!r} in a fidelity log. Add it "
            f"to FAMILY/DIMS_BY_FAMILY in {os.path.basename(__file__)} before "
            f"rendering it; known versions: {', '.join(sorted(FAMILY))}")


def norm(path):
    return os.path.normpath(str(path)).replace("\\", "/").lower()


def load_attempts(root):
    """Every attempt line, grouped into (run_id, candidate) units per scenario."""
    rows = []
    for log in glob.glob(os.path.join(root, "*", "results.jsonl")):
        cell = os.path.basename(os.path.dirname(log))
        with open(log, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                r["cell"] = cell
                rows.append(r)
    return rows


def terminal_units(rows):
    """Collapse attempt lines to one terminal record per (run_id, candidate)."""
    groups = defaultdict(list)
    for r in rows:
        groups[(r["run_id"], r.get("candidate", 1))].append(r)
    units = []
    for _key, attempts in groups.items():
        attempts.sort(key=lambda r: r["attempt"])
        last = dict(attempts[-1])
        last["n_attempts"] = len(attempts)
        last["repaired"] = len(attempts) > 1 and last["outcome"] == "success"
        last["error_chain"] = [a.get("stderr") or "" for a in attempts[:-1]]
        last["introspection_chain"] = [a.get("introspection") for a in attempts]
        units.append(last)
    return units


def load_jsonl_by_path(path, key="scenario", dedupe_on=None):
    """Group JSONL rows by scenario path.

    dedupe_on names the fields that, with the scenario, identify one logical
    record. Concurrent judging processes can append the same judgement twice,
    which would silently double-weight those scenarios in every cell mean, so
    repeats are collapsed to the first occurrence rather than trusted.
    """
    out = defaultdict(list)
    if not path or not os.path.exists(path):
        return out
    seen = set()
    dropped = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if dedupe_on:
                ident = (norm(r[key]),) + tuple(r.get(k) for k in dedupe_on)
                if ident in seen:
                    dropped += 1
                    continue
                seen.add(ident)
            out[norm(r[key])].append(r)
    if dropped:
        print(f"note: dropped {dropped} duplicate row(s) from {path}")
    return out


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else float("nan")


def wilson(k, n, z=1.96):
    """Wilson score interval - honest for the small n these experiments have."""
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def fmt_pct(k, n):
    if n == 0:
        return "  -  "
    lo, hi = wilson(k, n)
    return f"{100*k/n:5.1f}% [{100*lo:4.1f},{100*hi:5.1f}]"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="output/factorial")
    ap.add_argument("--reachability", default="output/reachability.jsonl")
    ap.add_argument("--fidelity", action="append", default=None,
                    help="Fidelity score log. Repeatable, or comma-separated: pass several "
                         "logs together to render every instrument side by side. Each "
                         "distinct (rubric version, rubric text hash) gets its own table and "
                         "they are never pooled (default: output/fidelity.jsonl)")
    ap.add_argument("--latex", default=None)
    args = ap.parse_args()

    attempts = load_attempts(args.root)
    units = terminal_units(attempts)
    reach = load_jsonl_by_path(args.reachability)

    # One or more score logs, merged. The rubric version AND its text hash are
    # part of the dedupe identity. Without the hash, a re-score of the same
    # scenario+repeat under revised anchors collides with the old judgement and
    # is silently dropped as a duplicate - which is exactly the comparison the
    # re-score exists to make.
    fidelity_logs = []
    for item in (args.fidelity or ["output/fidelity.jsonl"]):
        fidelity_logs += [p.strip() for p in item.split(",") if p.strip()]
    # A log path that does not exist loads as silence, which reads downstream as
    # "that rubric was never run" rather than "you mistyped the path". Say so.
    missing_logs = [p for p in fidelity_logs if not os.path.exists(p)]
    if missing_logs and args.fidelity:
        for p in missing_logs:
            print(f"ERROR: fidelity log not found: {p}")
        raise SystemExit(2)
    fid = defaultdict(list)
    seen_ids = set()
    for path in fidelity_logs:
        for scenario, rows in load_jsonl_by_path(
                path, dedupe_on=("repeat", "mismatch_control", "rubric_version",
                                 "rubric_hash")).items():
            for r in rows:
                # Dedupe across files too, so passing the same log twice - or two
                # logs that overlap - cannot double-weight a scenario in a mean.
                ident = (scenario, r.get("repeat"), bool(r.get("mismatch_control")),
                         r.get("rubric_version", "v1"), r.get("rubric_hash") or "unstamped")
                if ident in seen_ids:
                    continue
                seen_ids.add(ident)
                fid[scenario].append(r)

    # Split the score log by rubric IDENTITY before anything else - version AND
    # the hash of the exact grading text. A v1 mean over five dimensions and a v2
    # mean over four are different measurements; so are two v2 means taken
    # against different revisions of the v2 anchors, which carry the same version
    # label. Pooling either pair produces a number that is not either one, so the
    # analysis refuses to and reports the cells separately.
    #
    # Rows written before stamping existed have no hash. They are kept in their
    # own "unstamped" cell rather than merged into a stamped one: their grading
    # text is not recoverable from the record, so they are not known to match.
    def identity(r):
        return (r.get("rubric_version", "v1"), r.get("rubric_hash") or "unstamped")

    fid_identities = sorted({identity(r) for rs in fid.values() for r in rs}) \
        or [("v1", "unstamped")]

    by_label = defaultdict(list)
    for ident in fid_identities:
        by_label[ident[0]].append(ident[1])
    for version, hashes in sorted(by_label.items()):
        if len(hashes) > 1:
            print(f"WARNING: rubric '{version}' appears under {len(hashes)} different "
                  f"grading texts: {', '.join(sorted(hashes))}")
            print("         These are NOT pooled - each is reported as its own cell. "
                  "Scores taken against different anchors are not comparable.")

    def by_identity(ident, want_mismatch):
        return {p: [r for r in rs
                    if identity(r) == ident
                    and bool(r.get("mismatch_control")) == want_mismatch]
                for p, rs in fid.items()}

    by_cell = defaultdict(list)
    for u in units:
        by_cell[u["cell"]].append(u)

    order = ["reach_on__templated", "reach_off__templated",
             "reach_on__freeform", "reach_off__freeform"]
    cells = [c for c in order if c in by_cell] + \
            [c for c in sorted(by_cell) if c not in order]

    print("=" * 108)
    print("TABLE 1  Build outcomes by prompt condition (one row per cell; n = episodes)")
    print("=" * 108)
    print(f"{'reach':<7}{'style':<11}{'n':>3}{'built':>22}{'1st-try':>22}"
          f"{'mean att':>10}{'triggers':>10}")
    print("-" * 108)
    t1 = []
    for cell in cells:
        us = by_cell[cell]
        reach_arm, style = CELL_LABEL.get(cell, (cell, ""))
        n = len(us)
        built = sum(1 for u in us if u["outcome"] == "success")
        first = sum(1 for u in us if u["outcome"] == "success" and u["n_attempts"] == 1)
        att = mean([u["n_attempts"] for u in us])
        trig = mean([u["trigger_count"] for u in us if u["outcome"] == "success"])
        print(f"{reach_arm:<7}{style:<11}{n:>3}{fmt_pct(built,n):>22}{fmt_pct(first,n):>22}"
              f"{att:>10.2f}{trig:>10.1f}")
        t1.append((reach_arm, style, n, built, first, att, trig))

    print()
    print("=" * 108)
    print("TABLE 2  Static reachability audit of BUILT scenarios (deterministic, no API)")
    print("=" * 108)
    print(f"{'reach':<7}{'style':<11}{'n':>3}{'win+lose':>22}{'at risk':>22}"
          f"{'redundant frag':>22}{'degen timer':>22}{'clean':>8}{'paths':>7}")
    print("-" * 108)
    t2 = []
    for cell in cells:
        rs = [reach[norm(u["output_path"])][0]
              for u in by_cell[cell]
              if u["outcome"] == "success" and reach.get(norm(u["output_path"]))]
        rs = [r for r in rs if r.get("ok")]
        n = len(rs)
        reach_arm, style = CELL_LABEL.get(cell, (cell, ""))
        both = sum(1 for r in rs if r["has_victory"] and r["has_defeat"])
        risk = sum(1 for r in rs if r["at_risk_victory"])
        frag = sum(1 for r in rs if r["redundant_fragile"])
        timer = sum(1 for r in rs if r["degenerate_timer"])
        clean = sum(1 for r in rs if r["clean"])
        paths = mean([r["n_victory_paths"] for r in rs])
        print(f"{reach_arm:<7}{style:<11}{n:>3}{fmt_pct(both,n):>22}{fmt_pct(risk,n):>22}"
              f"{fmt_pct(frag,n):>22}{fmt_pct(timer,n):>22}"
              f"{fmt_pct(clean,n).split('%')[0].strip()+'%':>8}{paths:>7.2f}")
        t2.append((reach_arm, style, n, both, risk, frag, timer, clean, paths))

    # The four modes the reachability block actually names. Measuring the
    # treatment against its own taxonomy, rather than against victory-condition
    # shape, is what makes the comparison fair to it.
    MODES = ("resource_dead_end", "composition_imbalance",
             "positional_trap", "timing_collapse")
    has_modes = any("failure_modes" in r for rs in reach.values() for r in rs)
    t2b = []
    if has_modes:
        print()
        print("=" * 108)
        print("TABLE 2b  Failure-mode taxonomy: the four modes the reachability block targets")
        print("=" * 108)
        print(f"{'reach':<7}{'style':<11}{'n':>3}" + "".join(f"{m[:13]:>15}" for m in MODES)
              + f"{'ANY':>16}")
        print("-" * 108)
        for cell in cells:
            rs = [reach[norm(u["output_path"])][0]
                  for u in by_cell[cell]
                  if u["outcome"] == "success" and reach.get(norm(u["output_path"]))]
            rs = [r for r in rs if r.get("ok") and "failure_modes" in r]
            if not rs:
                continue
            n = len(rs)
            reach_arm, style = CELL_LABEL.get(cell, (cell, ""))
            counts = [sum(1 for r in rs if r["failure_modes"][m]["fired"]) for m in MODES]
            anyf = sum(1 for r in rs if r.get("any_failure_mode"))
            print(f"{reach_arm:<7}{style:<11}{n:>3}" + "".join(f"{c:>15}" for c in counts)
                  + f"{fmt_pct(anyf, n):>16}")
            t2b.append((reach_arm, style, n, counts, anyf))
        for arm in ("on", "off"):
            rows = [r for r in t2b if r[0] == arm]
            k = sum(r[4] for r in rows)
            n = sum(r[2] for r in rows)
            if n:
                print(f"  reachability {arm:<4} pooled: {k}/{n} scenarios with >=1 "
                      f"failure mode ({100*k/n:.1f}%)")

    t3_by_version = []
    for ident in fid_identities:
        version, rhash = ident
        label = version if len(by_label[version]) == 1 else f"{version}@{rhash[:8]}"
        matched = by_identity(ident, False)
        mismatched = by_identity(ident, True)
        fam = family(version)
        dims = DIMS_BY_FAMILY[fam]
        unscored = UNSCORED_BY_FAMILY[fam]
        scored_dims = [d for d in dims if d not in unscored]

        print()
        print("=" * 108)
        print(f"TABLE 3 [{label}]  Historical fidelity, LLM judge (1-5 per dimension)")
        print(f"          rubric text {rhash}")
        if unscored:
            print(f"          mean is over {len(scored_dims)} dimension(s): "
                  f"{', '.join(scored_dims)}; "
                  f"{', '.join(sorted(unscored))} scored and reported but excluded")
        print("=" * 108)
        print(f"{'reach':<7}{'style':<11}{'n':>3}"
              + "".join(f"{d[:11] + ('*' if d in unscored else ''):>13}" for d in dims)
              + f"{MEAN_LABEL[fam]:>9}")
        print("-" * 108)
        t3 = []
        for cell in cells:
            rows = []
            for u in by_cell[cell]:
                if u["outcome"] != "success":
                    continue
                rows += [r for r in matched.get(norm(u["output_path"]), []) if r.get("ok")]
            reach_arm, style = CELL_LABEL.get(cell, (cell, ""))
            n = len(rows)
            vals = [mean([r.get(d) for r in rows]) for d in dims]
            overall = mean([r["mean"] for r in rows])
            print(f"{reach_arm:<7}{style:<11}{n:>3}" + "".join(f"{v:>13.2f}" for v in vals)
                  + f"{overall:>9.2f}")
            t3.append((reach_arm, style, n, vals, overall))
        if unscored:
            print("  * reported, not in the mean")
        t3_by_version.append((version, label, t3))

        # Fidelity coverage is uneven when a judging sweep is cut short, and cell
        # means over different episode subsets are not comparable. Restrict to
        # episodes judged in BOTH styles and pair them by title.
        print()
        print("=" * 108)
        print(f"TABLE 3b [{label}]  Fidelity, matched pairs only "
              "(episodes judged under BOTH styles, same reach arm)")
        print("=" * 108)
        per_cell_title = defaultdict(dict)
        for cell in cells:
            for u in by_cell[cell]:
                if u["outcome"] != "success":
                    continue
                rows = [r for r in matched.get(norm(u["output_path"]), []) if r.get("ok")]
                if rows:
                    per_cell_title[cell][u["title"]] = mean([r["mean"] for r in rows])
        for reach_arm in ("on", "off"):
            tcell = f"reach_{reach_arm}__templated"
            fcell = f"reach_{reach_arm}__freeform"
            shared = sorted(set(per_cell_title.get(tcell, {})) & set(per_cell_title.get(fcell, {})))
            if not shared:
                print(f"  reach {reach_arm}: no episode judged under both styles - not comparable")
                continue
            print(f"  reach {reach_arm}: {len(shared)} paired episode(s)")
            print(f"    {'episode':<34}{'templated':>11}{'freeform':>11}{'delta':>9}")
            deltas = []
            for title in shared:
                a, b = per_cell_title[tcell][title], per_cell_title[fcell][title]
                deltas.append(b - a)
                print(f"    {title[:33]:<34}{a:>11.2f}{b:>11.2f}{b-a:>+9.2f}")
            wins = sum(1 for d in deltas if d > 0)
            print(f"    {'MEAN':<34}{mean([per_cell_title[tcell][t] for t in shared]):>11.2f}"
                  f"{mean([per_cell_title[fcell][t] for t in shared]):>11.2f}"
                  f"{mean(deltas):>+9.2f}   freeform higher on {wins}/{len(shared)}")

        # Judge validation: matched vs mismatched briefs, and repeat-to-repeat spread.
        m_all = [r["mean"] for rs in matched.values() for r in rs if r.get("ok")]
        x_all = [r["mean"] for rs in mismatched.values() for r in rs if r.get("ok")]
        print()
        print("=" * 108)
        print(f"TABLE 4 [{label}]  Judge validation")
        print("=" * 108)
        if m_all:
            print(f"  matched brief      n={len(m_all):<4} mean={mean(m_all):.2f}")
        if x_all:
            print(f"  mismatched brief   n={len(x_all):<4} mean={mean(x_all):.2f}   "
                  f"separation = {mean(m_all)-mean(x_all):+.2f}")
        else:
            print("  mismatched brief   (not run)")

        spreads = []
        for rs in matched.values():
            good = [r for r in rs if r.get("ok")]
            if len(good) > 1:
                spreads.append(max(r["mean"] for r in good) - min(r["mean"] for r in good))
        if spreads:
            print(f"  self-consistency   {len(spreads)} scenario(s) judged >1x, "
                  f"mean within-scenario range = {mean(spreads):.2f} "
                  f"(max {max(spreads):.2f}) on the 1-5 scale")
        else:
            print("  self-consistency   (single judgement per scenario)")

        # The static checks that run before the judge. Only v2 rows carry them.
        pre = [r for rs in matched.values() for r in rs
               if "combatants_precondition" in r]
        if pre:
            seen_paths = {}
            for r in pre:
                seen_paths[norm(r["scenario"])] = r
            npre = len(seen_paths)
            comb = sum(1 for r in seen_paths.values()
                       if r["combatants_precondition"]["passed"])
            sett = sum(1 for r in seen_paths.values()
                       if r["setting_precondition"]["passed"])
            print(f"  static preconditions  combatants {comb}/{npre} pass, "
                  f"setting {sett}/{npre} pass")

    # Repair behaviour, pooled: what the introspection channel actually saw.
    print()
    print("=" * 108)
    print("TABLE 5  Self-repair behaviour (pooled over cells)")
    print("=" * 108)
    needing = [u for u in units if u["n_attempts"] > 1]
    rescued = [u for u in needing if u["outcome"] == "success"]
    print(f"  episodes needing >=1 repair : {len(needing)}/{len(units)}")
    print(f"  of those, rescued by repair : {len(rescued)}/{len(needing)}"
          + (f"  ({100*len(rescued)/len(needing):.0f}%)" if needing else ""))
    kinds = defaultdict(int)
    for u in units:
        for k in u["introspection_chain"]:
            if k:
                kinds[k] += 1
    if kinds:
        print("  introspection kinds fired   : "
              + ", ".join(f"{k}={v}" for k, v in sorted(kinds.items())))
    else:
        print("  introspection kinds fired   : none (no repair needed, or disabled)")

    if args.latex:
        with open(args.latex, "w", encoding="utf-8") as f:
            f.write(latex_tables(t1, t2, t3_by_version, t2b))
        print(f"\nwrote {args.latex}")


# Column headers per family, matching DIMS_BY_FAMILY order.
LATEX_DIM_HEADERS = {
    "v1": ["Comb.", "Mat.", "Events", "Anach.", "Ped."],
    "v2": ["Comb.", "Setting", "Events", "Obj.", "Ped."],
    "v3": ["Comb.", "Civ.", "Terrain", "Events", "Obj.", "Ped."],
}
LATEX_MEAN_HEADER = {"v1": "Mean", "v2": "Mean$_4$", "v3": "Mean$_5$"}

# Trailing caption note per family.
LATEX_FAMILY_NOTE = {
    "v1": "",
    "v2": (r" Under the v2 rubric the overall score is the unweighted mean of "
           r"combatants, setting, events and objective; pedagogy is scored and "
           r"reported but excluded. \emph{Obj.}\ is scored from the victory and "
           r"defeat conditions extracted from the trigger graph, not from the "
           r"scenario's objectives text. v2 scores are not comparable to v1 scores."),
    "v3": (r" Under the v3 rubric the overall score is the unweighted mean of "
           r"combatants, civilization, terrain, events and objective; pedagogy is "
           r"scored and reported but excluded. v3 splits v2's \emph{setting} into "
           r"\emph{Civ.}\ and \emph{Terrain}, so its mean is over five dimensions "
           r"and is not comparable to the v2 or v1 series."),
}

# Appended on top of the family note when the version is a point revision.
LATEX_REVISION_NOTE = (
    r" This is the revised \textsc{objective} anchor: a victory condition's "
    r"\emph{parameters} --- a survival timer's duration, the target a kill is keyed "
    r"to --- are judged as part of the goal it encodes, so a one-second timer or a "
    r"hunt for an arbitrary unit can no longer score as the historical objective. "
    r"Only that anchor differs from the parent rubric, and scores are not pooled "
    r"across the revision.")


def latex_tables(t1, t2, t3_by_version, t2b=()):
    def pct(k, n):
        return f"{100*k/n:.0f}" if n else "--"
    out = []
    out.append("% Auto-generated by tools/analyze.py -- do not hand-edit.\n")

    out.append(r"\begin{table}[t]")
    out.append(r"\caption{Build outcomes by prompt condition. $n$ is episodes per cell; "
               r"\emph{built} and \emph{1st try} are percentages of $n$, \emph{att.}\ the mean "
               r"generation calls per episode, and \emph{trig.}\ the mean trigger count of the "
               r"scenarios that built.}")
    out.append(r"\label{tab:build}")
    out.append(r"\small\centering")
    out.append(r"\begin{tabular}{llrrrrr}")
    out.append(r"\toprule")
    out.append(r"Reach & Style & $n$ & Built & 1st try & Att. & Trig. \\")
    out.append(r"\midrule")
    for reach_arm, style, n, built, first, att, trig in t1:
        out.append(f"{reach_arm} & {style} & {n} & {pct(built,n)}\\% & {pct(first,n)}\\% & "
                   f"{att:.2f} & {trig:.0f} \\\\")
    out.append(r"\bottomrule")
    out.append(r"\end{tabular}")
    out.append(r"\end{table}")
    out.append("")

    out.append(r"\begin{table}[t]")
    out.append(r"\caption{Static reachability audit of built scenarios. All 31 had both a "
               r"victory and a defeat path, so that column is omitted. A victory path is "
               r"\emph{fragile} when gated on \texttt{OBJECTS\_IN\_AREA}$\,\leq 0$; "
               r"\emph{at risk} means every path is fragile, \emph{redun.} that a robust path "
               r"survives alongside one. \emph{Degen.} is a win gated on a timer alone (not "
               r"counted for \texttt{defense}, where surviving a deadline is the point). "
               r"\emph{Paths} is the mean number of victory paths.}")
    out.append(r"\label{tab:reach}")
    out.append(r"\footnotesize\centering")
    out.append(r"\begin{tabular}{llrrrrrr}")
    out.append(r"\toprule")
    out.append(r"Reach & Style & $n$ & At risk & Redun. & Degen. & Clean & Paths \\")
    out.append(r"\midrule")
    for reach_arm, style, n, both, risk, frag, timer, clean, paths in t2:
        out.append(f"{reach_arm} & {style} & {n} & {pct(risk,n)}\\% & "
                   f"{pct(frag,n)}\\% & {pct(timer,n)}\\% & {pct(clean,n)}\\% & "
                   f"{paths:.2f} \\\\")
    out.append(r"\bottomrule")
    out.append(r"\end{tabular}")
    out.append(r"\end{table}")
    out.append("")

    if t2b:
        out.append(r"\begin{table}[t]")
        out.append(r"\caption{The four failure modes named by the reachability block, "
                   r"detected statically on the built scenarios. Counts are scenarios "
                   r"out of $n$. Measuring the treatment against its own taxonomy "
                   r"rather than against victory-condition shape.}")
        out.append(r"\label{tab:modes}")
        out.append(r"\footnotesize\centering")
        out.append(r"\begin{tabular}{llrrrrrr}")
        out.append(r"\toprule")
        out.append(r"Reach & Style & $n$ & Resrc. & Comp. & Posn. & Timing & Any \\")
        out.append(r"\midrule")
        for reach_arm, style, n, counts, anyf in t2b:
            cells_txt = " & ".join(str(c) for c in counts)
            out.append(f"{reach_arm} & {style} & {n} & {cells_txt} & {anyf} \\\\")
        out.append(r"\bottomrule")
        out.append(r"\end{tabular}")
        out.append(r"\end{table}")
        out.append("")

    def num(v):
        return "--" if v != v else f"{v:.2f}"   # NaN when a cell went unscored

    # One fidelity table per rubric identity present. Different versions are
    # different instruments over different dimension sets, and a point revision
    # is a different measurement of the same set, so none of them ever share a
    # table and their means are never averaged together.
    for version, label, t3 in t3_by_version:
        scored = [row for row in t3 if row[2] > 0]
        if not scored:
            continue
        fam = family(version)
        headers = LATEX_DIM_HEADERS[fam]
        # The Reach column only earns its width if more than one arm was scored.
        show_reach = len({row[0] for row in scored}) > 1
        note = ("" if show_reach else
                r" Only the reachability-\emph{off} cells were scored before the API budget was "
                r"exhausted, so that factor is held constant here and omitted from the table; "
                r"see Section~\ref{sec:eval-fidelity}.")
        note += LATEX_FAMILY_NOTE[fam]
        if version != fam:
            note += LATEX_REVISION_NOTE

        out.append(r"\begin{table}[t]")
        out.append(r"\caption{Historical fidelity scored by an LLM judge (Opus~5) against the "
                   + label.replace("_", r"\_") + r" rubric, 1--5 per dimension. $n$ counts judgements, not "
                   r"scenarios (up to three independent scorings each)." + note + "}")
        out.append(r"\label{tab:fidelity" + ("" if label == "v1" else
                   re.sub(r"[^A-Za-z0-9]", "", label)) + "}")
        out.append(r"\footnotesize\centering")
        # Style, n, one column per dimension, then the mean. Derived rather than
        # hardcoded: v3 has six dimensions, and a spec that is one column short
        # makes LaTeX drop the mean off the right edge of the table.
        out.append(r"\begin{tabular}{" + ("l" if show_reach else "")
                   + "l" + "r" * (len(headers) + 2) + "}")
        out.append(r"\toprule")
        out.append(("Reach & " if show_reach else "")
                   + "Style & $n$ & " + " & ".join(headers) + " & "
                   + LATEX_MEAN_HEADER[fam] + r" \\")
        out.append(r"\midrule")
        for reach_arm, style, n, vals, overall in scored:
            cells = " & ".join(num(v) for v in vals)
            prefix = f"{reach_arm} & " if show_reach else ""
            out.append(f"{prefix}{style} & {n} & {cells} & {num(overall)} \\\\")
        out.append(r"\bottomrule")
        out.append(r"\end{tabular}")
        out.append(r"\end{table}")
        out.append("")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    main()
