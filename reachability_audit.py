"""
Static reachability audit of a built scenario.

Executing successfully proves a scenario *loads*; it says nothing about whether
the scenario can be *won*. This module inspects the trigger graph of a built
``.aoe2scenario`` and reports the structural defects that make a scenario
unwinnable or degenerate. No game simulation and no LLM: every check is a
deterministic property of the trigger table, so it is free to rerun and cannot
drift between runs.

Checks
------
Every DECLARE_VICTORY trigger for the human player is one *victory path*, and
each path is classified by the conditions gating it:

  robust     gated on a specific object or place (DESTROY_OBJECT,
             BRING_OBJECT_TO_AREA, ...) - cannot silently become unsatisfiable
  fragile    gated on OBJECTS_IN_AREA with quantity <= 0 - the failure mode
             reachability prompting targets: one enemy that garrisons,
             converts, or flees the area strands the player forever
  timer      gated on nothing but a TIMER - satisfied by waiting

Whether a fragile path *matters* depends on whether anything else can win the
scenario, so the findings separate the two cases:

unwinnable         no victory path at all
at_risk_victory    EVERY victory path is fragile, so the scenario really can
                   become uncompletable
redundant_fragile  some path is fragile but a robust path survives - a wart,
                   not a defect
degenerate_timer   some victory path is timer-only, so the player wins by
                   waiting regardless of play. Suppressed for `defense`
                   scenarios, where surviving to a deadline IS the historical
                   win condition (pass --scenario-type, or let the audit read
                   it from the .meta.json sidecar)
missing_defeat     no way to lose; the scenario has no stakes
orphan_triggers    triggers shipped disabled that no ACTIVATE_TRIGGER effect
                   ever enables - content that can never fire

A scenario is `clean` when it has a victory path that is not at risk, has a
defeat path, has no degenerate timer win, and has no orphan triggers.

    python reachability_audit.py output/factorial            # audit a tree
    python reachability_audit.py path/to/one.aoe2scenario    # audit one file
    python reachability_audit.py output/factorial --json out.jsonl
"""

import argparse
import json
import os
import sys

from scenario_inspect import summarize

HUMAN_PLAYER = 1

# Conditions that pin victory to a specific object or place, which is what makes
# a victory condition robust rather than a standing area query.
ROBUST_CONDITIONS = {"DESTROY_OBJECT", "BRING_OBJECT_TO_AREA", "CAPTURE_OBJECT",
                     "OWN_OBJECTS", "OWN_FEWER_OBJECTS", "RESEARCH_TECHNOLOGY",
                     "ACCUMULATE_ATTRIBUTE", "OBJECT_IN_AREA"}


def classify_path(trigger):
    """Classify one victory trigger as 'fragile', 'timer' or 'robust'.

    Conditions on a trigger are conjunctive, so a single unsatisfiable conjunct
    is enough to make the whole path fragile - it is checked before the others.
    """
    conditions = trigger["conditions"]
    if not conditions:
        return "timer"
    if any(c["type"] == "OBJECTS_IN_AREA" and isinstance(c.get("quantity"), int)
           and c["quantity"] <= 0 for c in conditions):
        return "fragile"
    kinds = {c["type"] for c in conditions}
    if kinds <= {"TIMER"}:
        return "timer"
    if kinds & ROBUST_CONDITIONS:
        return "robust"
    return "other"


def audit(summary, scenario_type=None):
    """Return a dict of reachability findings for one scenario summary.

    scenario_type (from the sidecar) only affects whether a timer-gated win is
    treated as degenerate: for `defense`, surviving to a deadline is the point.
    """
    triggers = summary["triggers"]

    victory_triggers, defeat_triggers = [], []
    for index, trigger in enumerate(triggers):
        for effect in trigger["effects"]:
            if effect["type"] != "DECLARE_VICTORY":
                continue
            if effect.get("source_player") == HUMAN_PLAYER:
                victory_triggers.append((index, trigger))
            else:
                defeat_triggers.append((index, trigger))

    # Which trigger indices are switched on at runtime by another trigger.
    activated = set()
    for trigger in triggers:
        for effect in trigger["effects"]:
            if effect["type"] == "ACTIVATE_TRIGGER":
                tid = effect.get("trigger_id")
                if isinstance(tid, int) and tid >= 0:
                    activated.add(tid)

    orphans = [t["name"] for i, t in enumerate(triggers)
               if not t["enabled"] and i not in activated]

    fragile, timer_only, robust = [], [], []
    for _index, trigger in victory_triggers:
        kind = classify_path(trigger)
        if kind == "fragile":
            fragile.append(trigger["name"])
        elif kind == "timer":
            timer_only.append(trigger["name"])
        elif kind == "robust":
            robust.append(trigger["name"])

    has_victory = bool(victory_triggers)
    has_defeat = bool(defeat_triggers)

    # A fragile path only endangers the scenario if nothing else can win it.
    at_risk = has_victory and len(fragile) == len(victory_triggers)
    redundant_fragile = bool(fragile) and not at_risk
    # Surviving to a deadline is the canonical defense-scenario win, not a bug.
    degenerate_timer = bool(timer_only) and (scenario_type != "defense")

    clean = (has_victory and has_defeat and not at_risk
             and not degenerate_timer and not orphans)

    return {
        "scenario_type": scenario_type,
        "trigger_count": summary["trigger_count"],
        "unit_total": summary["unit_total"],
        "has_victory": has_victory,
        "has_defeat": has_defeat,
        "missing_defeat": has_victory and not has_defeat,
        "n_victory_paths": len(victory_triggers),
        "n_defeat_triggers": len(defeat_triggers),
        "n_fragile_paths": len(fragile),
        "n_timer_paths": len(timer_only),
        "n_robust_paths": len(robust),
        "any_fragile": bool(fragile),
        "at_risk_victory": at_risk,
        "redundant_fragile": redundant_fragile,
        "timer_only_victory": bool(timer_only),
        "degenerate_timer": degenerate_timer,
        "robust_victory": bool(robust),
        "fragile_victory_triggers": fragile,
        "timer_only_victory_triggers": timer_only,
        "orphan_triggers": orphans,
        "n_orphan_triggers": len(orphans),
        "unwinnable": not has_victory,
        "clean": clean,
    }


def _sidecar_scenario_type(path):
    """Read scenario_type from the scenario's .meta.json, if one exists."""
    meta_path = str(path) + ".meta.json"
    try:
        with open(meta_path, encoding="utf-8") as f:
            return json.load(f).get("scenario_type")
    except Exception:
        return None


def audit_path(path, scenario_type=None):
    try:
        stype = scenario_type or _sidecar_scenario_type(path)
        return {"scenario": path, "ok": True, **audit(summarize(path), stype)}
    except Exception as e:
        return {"scenario": path, "ok": False, "error": str(e)}


def collect(root):
    if os.path.isfile(root):
        return [root]
    out = []
    for dirpath, _dirs, files in os.walk(root):
        for name in sorted(files):
            if name.endswith(".aoe2scenario"):
                out.append(os.path.join(dirpath, name))
    return out


def main():
    ap = argparse.ArgumentParser(description="Static reachability audit of built scenarios.")
    ap.add_argument("target", help="A .aoe2scenario file or a directory tree")
    ap.add_argument("--json", dest="json_out", help="Write one JSON row per scenario here")
    ap.add_argument("--quiet", action="store_true", help="Summary table only")
    ap.add_argument("--scenario-type", default=None,
                    help="Override the type (else read from each .meta.json sidecar)")
    args = ap.parse_args()

    paths = collect(args.target)
    if not paths:
        print(f"No .aoe2scenario files under {args.target}", file=sys.stderr)
        return 1

    rows = [audit_path(p, args.scenario_type) for p in paths]
    good = [r for r in rows if r["ok"]]

    if not args.quiet:
        print(f"{'scenario':<50}{'type':<10}{'trig':>5}{'paths':>6}{'risk':>6}"
              f"{'redun':>6}{'timer':>6}{'orph':>5}{'clean':>7}")
        print("-" * 101)
        for r in rows:
            if not r["ok"]:
                print(f"{os.path.basename(r['scenario'])[:51]:<52}  PARSE ERROR: {r['error'][:40]}")
                continue
            label = os.path.join(os.path.basename(os.path.dirname(r["scenario"])),
                                 os.path.basename(r["scenario"]).replace(".aoe2scenario", ""))
            print(f"{label[:49]:<50}{str(r['scenario_type'])[:9]:<10}{r['trigger_count']:>5}"
                  f"{r['n_victory_paths']:>6}"
                  f"{'YES' if r['at_risk_victory'] else '.':>6}"
                  f"{'yes' if r['redundant_fragile'] else '.':>6}"
                  f"{'YES' if r['degenerate_timer'] else ('(ok)' if r['timer_only_victory'] else '.'):>6}"
                  f"{r['n_orphan_triggers']:>5}"
                  f"{'ok' if r['clean'] else 'NO':>7}")

    if good:
        n = len(good)
        def pct(k):
            c = sum(1 for r in good if r[k])
            return f"{c}/{n} ({100.0 * c / n:.1f}%)"
        print(f"\nAudited {n} scenario(s)"
              + (f"  [{len(rows) - n} unparseable]" if len(rows) != n else ""))
        print(f"  has victory path:        {pct('has_victory')}")
        print(f"  has defeat path:         {pct('has_defeat')}")
        print(f"  AT RISK (all paths frag) {pct('at_risk_victory')}")
        print(f"  redundant fragile path:  {pct('redundant_fragile')}")
        print(f"  degenerate timer win:    {pct('degenerate_timer')}")
        print(f"    (timer win, any type)  {pct('timer_only_victory')}")
        print(f"  robust victory path:     {pct('robust_victory')}")
        print(f"  has orphan triggers:     {pct('n_orphan_triggers')}")
        print(f"  fully clean:             {pct('clean')}")

    if args.json_out:
        os.makedirs(os.path.dirname(args.json_out) or ".", exist_ok=True)
        with open(args.json_out, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"\nwrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
