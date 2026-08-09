"""
Read a built .aoe2scenario back into a structured summary.

This is the shared front-end for post-hoc analysis of generated scenarios. It
inspects the *artefact* rather than the code that produced it, so the same
summary works for hand-authored scenarios, official campaign scenarios, and
generated ones.

Two consumers:

* ``fidelity_judge.py``  - turns the summary into a prose digest for the LLM
  fidelity rubric.
* ``reachability_audit.py`` - checks victory/defeat structure statically.

Loading a scenario prints a banner and progress lines from the parser; every
entry point here suppresses that so callers get clean stdout.
"""

import contextlib
import io
import os
import sys
import threading

_UNIT_NAME_CACHE = None

# sys.stdout is process-global, so two threads swapping it concurrently can
# restore the real console mid-parse and let the parser's banner (which contains
# non-ASCII glyphs) hit a legacy code page. Serialise the swap.
_QUIET_LOCK = threading.RLock()


@contextlib.contextmanager
def _quiet():
    """Silence the parser's load banner / progress output (stdout + stderr).

    Thread-safe: holds a re-entrant lock for the duration, so concurrent callers
    take turns rather than clobbering each other's saved streams.
    """
    with _QUIET_LOCK:
        buf_out, buf_err = io.StringIO(), io.StringIO()
        old_out, old_err = sys.stdout, sys.stderr
        try:
            sys.stdout, sys.stderr = buf_out, buf_err
            yield
        finally:
            sys.stdout, sys.stderr = old_out, old_err


def _unit_names():
    """id -> (name, category) over every dataset, built once."""
    global _UNIT_NAME_CACHE
    if _UNIT_NAME_CACHE is not None:
        return _UNIT_NAME_CACHE
    from AoE2ScenarioParser.datasets.units import UnitInfo
    from AoE2ScenarioParser.datasets.buildings import BuildingInfo
    from AoE2ScenarioParser.datasets.heroes import HeroInfo
    from AoE2ScenarioParser.datasets.other import OtherInfo

    table = {}
    for dataset, category in ((UnitInfo, "unit"), (BuildingInfo, "building"),
                              (HeroInfo, "hero"), (OtherInfo, "other")):
        for item in dataset:
            try:
                table.setdefault(item.ID, (item.name, category))
            except Exception:
                continue
    _UNIT_NAME_CACHE = table
    return table


def _enum_name(value, enum_cls):
    """Effect/condition types come back from a parsed file as plain ints, so map
    them through the dataset enum; fall back to the raw value if unrecognized."""
    if hasattr(value, "name"):
        return value.name
    try:
        return enum_cls(int(value)).name
    except Exception:
        return str(value)


def _effect_message(effect):
    """Player-visible text carried by an effect, if any."""
    text = getattr(effect, "message", None)
    if text:
        text = str(text).strip()
        if text:
            return text
    return None


def load(path):
    """Parse a scenario file, returning the AoE2DEScenario object."""
    from AoE2ScenarioParser.scenarios.aoe2_de_scenario import AoE2DEScenario
    with _quiet():
        return AoE2DEScenario.from_file(path)


def summarize(path, include_map=False):
    """Return a structured dict describing a built scenario.

    Keys: path, map_size, players (unit rosters per player), triggers (name,
    enabled, conditions, effects, dialogue), plus rolled-up counts. Raises on an
    unparseable file so callers can record that as its own outcome.

    include_map=True additionally returns the data the failure-mode detectors
    need and the fidelity digest does not: ``terrain`` (a flat row-major grid of
    terrain ids) and ``all_units`` (every object with its reference_id, owner and
    tile, so a victory condition's unit_object can be resolved to a position).
    It roughly triples parse cost on a 120x120 map, so it is opt-in.
    """
    from AoE2ScenarioParser.datasets.players import PlayerId
    from AoE2ScenarioParser.datasets.effects import EffectId
    from AoE2ScenarioParser.datasets.conditions import ConditionId

    scenario = load(path)
    with _quiet():
        unit_manager = scenario.unit_manager
        trigger_manager = scenario.trigger_manager
        map_manager = scenario.map_manager
        map_size = map_manager.map_size

        names = _unit_names()
        players = {}
        all_units = []
        for player_id in PlayerId:
            try:
                units = unit_manager.get_player_units(player_id)
            except Exception:
                continue
            if not units:
                continue
            roster = {}
            for unit in units:
                name, category = names.get(unit.unit_const,
                                           (f"UnknownID_{unit.unit_const}", "unknown"))
                if include_map:
                    all_units.append({
                        "reference_id": int(getattr(unit, "reference_id", -1)),
                        "player": player_id.name,
                        "player_id": int(player_id.value),
                        "unit_const": int(unit.unit_const),
                        "name": name,
                        "category": category,
                        "x": int(unit.x),
                        "y": int(unit.y),
                    })
                entry = roster.setdefault(name, {"count": 0, "category": category,
                                                 "positions": []})
                entry["count"] += 1
                if len(entry["positions"]) < 4:
                    entry["positions"].append((int(unit.x), int(unit.y)))
            players[player_id.name] = roster

        triggers = []
        for trigger in trigger_manager.triggers:
            conditions = []
            for cond in trigger.conditions:
                conditions.append({
                    "type": _enum_name(cond.condition_type, ConditionId),
                    "quantity": getattr(cond, "quantity", None),
                    "source_player": getattr(cond, "source_player", None),
                    "unit_object": getattr(cond, "unit_object", None),
                    "area": [getattr(cond, k, None)
                             for k in ("area_x1", "area_y1", "area_x2", "area_y2")],
                    "timer": getattr(cond, "timer", None),
                })
            effects = []
            for eff in trigger.effects:
                effects.append({
                    "type": _enum_name(eff.effect_type, EffectId),
                    "message": _effect_message(eff),
                    "source_player": getattr(eff, "source_player", None),
                    "trigger_id": getattr(eff, "trigger_id", None),
                })
            triggers.append({
                "name": str(trigger.name),
                "enabled": bool(trigger.enabled),
                "looping": bool(getattr(trigger, "looping", False)),
                "conditions": conditions,
                "effects": effects,
            })

        terrain = None
        if include_map:
            # Row-major grid indexed [y * map_size + x], built from each tile's
            # own coordinates rather than trusting the parser's iteration order.
            terrain = [0] * (map_size * map_size)
            for tile in map_manager.terrain:
                tx, ty = int(tile.x), int(tile.y)
                if 0 <= tx < map_size and 0 <= ty < map_size:
                    terrain[ty * map_size + tx] = int(tile.terrain_id)

    dialogue = [e["message"] for t in triggers for e in t["effects"]
                if e["message"] and e["type"] in
                ("DISPLAY_INSTRUCTIONS", "SEND_CHAT", "DISPLAY_TIMER")]

    summary = {
        "path": path,
        "filename": os.path.basename(path),
        "map_size": map_size,
        "players": players,
        "triggers": triggers,
        "trigger_count": len(triggers),
        "unit_total": sum(e["count"] for r in players.values() for e in r.values()),
        "dialogue": dialogue,
    }
    if include_map:
        summary["all_units"] = all_units
        summary["terrain"] = terrain
    return summary


def to_digest(summary, max_dialogue=28, max_triggers=40):
    """Render a summary as compact prose for an LLM judge.

    Deliberately content-only: no filename, no model, no prompt condition, so a
    judge cannot infer which arm produced the scenario.
    """
    lines = [f"MAP: {summary['map_size']}x{summary['map_size']} tiles",
             f"TOTAL PLACED OBJECTS: {summary['unit_total']}", ""]

    lines.append("ROSTERS BY PLAYER")
    for player, roster in summary["players"].items():
        if not roster:
            continue
        by_cat = {}
        for name, entry in roster.items():
            by_cat.setdefault(entry["category"], []).append(f"{name} x{entry['count']}")
        lines.append(f"  {player}:")
        for category in ("hero", "unit", "building", "other", "unknown"):
            if by_cat.get(category):
                items = ", ".join(sorted(by_cat[category]))
                lines.append(f"    {category}: {items}")
    lines.append("")

    lines.append(f"TRIGGERS ({summary['trigger_count']} total)")
    for trigger in summary["triggers"][:max_triggers]:
        conds = ", ".join(c["type"] for c in trigger["conditions"]) or "none"
        effs = ", ".join(e["type"] for e in trigger["effects"]) or "none"
        lines.append(f"  - {trigger['name']} | when: {conds} | then: {effs}")
    if summary["trigger_count"] > max_triggers:
        lines.append(f"  ... and {summary['trigger_count'] - max_triggers} more")
    lines.append("")

    if summary["dialogue"]:
        lines.append("IN-GAME TEXT (narration, objectives, dialogue)")
        for text in summary["dialogue"][:max_dialogue]:
            flat = " ".join(str(text).split())
            lines.append(f"  - {flat[:300]}")
        if len(summary["dialogue"]) > max_dialogue:
            lines.append(f"  ... and {len(summary['dialogue']) - max_dialogue} more")

    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scenario_inspect.py <scenario.aoe2scenario>")
        raise SystemExit(1)
    print(to_digest(summarize(sys.argv[1])))
