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
        --fidelity output/fidelity.jsonl \
        --latex output/tables.tex
"""

import argparse
import glob
import json
import math
import os
from collections import defaultdict

CELL_LABEL = {
    "reach_on__templated": ("on", "templated"),
    "reach_off__templated": ("off", "templated"),
    "reach_on__freeform": ("on", "freeform"),
    "reach_off__freeform": ("off", "freeform"),
}


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
    ap.add_argument("--fidelity", default="output/fidelity.jsonl")
    ap.add_argument("--latex", default=None)
    args = ap.parse_args()

    attempts = load_attempts(args.root)
    units = terminal_units(attempts)
    reach = load_jsonl_by_path(args.reachability)
    fid = load_jsonl_by_path(args.fidelity,
                             dedupe_on=("repeat", "mismatch_control"))

    matched = {p: [r for r in rs if not r.get("mismatch_control")] for p, rs in fid.items()}
    mismatched = {p: [r for r in rs if r.get("mismatch_control")] for p, rs in fid.items()}

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

    print()
    print("=" * 108)
    print("TABLE 3  Historical fidelity, LLM judge (1-5 per dimension)")
    print("=" * 108)
    dims = ["combatants", "material", "events", "anachronism", "pedagogy"]
    print(f"{'reach':<7}{'style':<11}{'n':>3}" + "".join(f"{d[:11]:>13}" for d in dims)
          + f"{'MEAN':>9}")
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
        vals = [mean([r[d] for r in rows]) for d in dims]
        overall = mean([r["mean"] for r in rows])
        print(f"{reach_arm:<7}{style:<11}{n:>3}" + "".join(f"{v:>13.2f}" for v in vals)
              + f"{overall:>9.2f}")
        t3.append((reach_arm, style, n, vals, overall))

    # Fidelity coverage is uneven when a judging sweep is cut short, and cell
    # means over different episode subsets are not comparable. Restrict to
    # episodes judged in BOTH styles and pair them by title.
    print()
    print("=" * 108)
    print("TABLE 3b  Fidelity, matched pairs only (episodes judged under BOTH styles, same reach arm)")
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
    print("TABLE 4  Judge validation")
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
            f.write(latex_tables(t1, t2, t3, m_all, x_all, spreads))
        print(f"\nwrote {args.latex}")


def latex_tables(t1, t2, t3, m_all, x_all, spreads):
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

    out.append(r"\begin{table}[t]")
    def num(v):
        return "--" if v != v else f"{v:.2f}"   # NaN when a cell went unscored

    scored = [row for row in t3 if row[2] > 0]
    # The Reach column only earns its width if more than one arm was scored.
    show_reach = len({row[0] for row in scored}) > 1
    note = ("" if show_reach else
            r" Only the reachability-\emph{off} cells were scored before the API budget was "
            r"exhausted, so that factor is held constant here and omitted from the table; "
            r"see Section~\ref{sec:eval-fidelity}.")

    out.append(r"\caption{Historical fidelity scored by an LLM judge (Opus~5) against a fixed "
               r"rubric, 1--5 per dimension. $n$ counts judgements, not scenarios (up to three "
               r"independent scorings each)." + note + "}")
    out.append(r"\label{tab:fidelity}")
    out.append(r"\footnotesize\centering")
    out.append(r"\begin{tabular}{" + ("l" if show_reach else "") + r"lrrrrrrr}")
    out.append(r"\toprule")
    out.append(("Reach & " if show_reach else "")
               + r"Style & $n$ & Comb. & Mat. & Events & Anach. & Ped. & Mean \\")
    out.append(r"\midrule")
    for reach_arm, style, n, vals, overall in scored:
        cells = " & ".join(num(v) for v in vals)
        prefix = f"{reach_arm} & " if show_reach else ""
        out.append(f"{prefix}{style} & {n} & {cells} & {num(overall)} \\\\")
    out.append(r"\bottomrule")
    out.append(r"\end{tabular}")
    out.append(r"\end{table}")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    main()
