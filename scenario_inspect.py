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


# ---------------------------------------------------------------------------
# Terrain classification, for the v3 `terrain` dimension.
#
# Nothing in this pipeline perceived space before this: the generator writes
# code blind and the digest carried rosters, triggers and text but no layout.
# A terrain score was therefore unaskable. These map the parser's ~130 terrain
# ids onto the small legend rubric_v3.render_terrain_grid expects.
#
# Matched by NAME rather than by id number, so a library that adds or renumbers
# terrains keeps classifying correctly; order matters because several names
# match more than one pattern (FOREST_AUTUMN_SNOW is forest, not snow).
# ---------------------------------------------------------------------------
_TERRAIN_PATTERNS = (
    ("water", r"^(WATER|OCEAN)"),
    ("forest", r"FOREST|JUNGLE|BAMBOO|PALM|MANGROVE"),
    ("shallow", r"^BEACH|SHALLOW"),
    ("snow", r"SNOW|ICE"),
    ("road", r"^ROAD"),
    ("rock", r"ROCK|CLIFF|QUICKSAND"),
    ("sand", r"SAND|DESERT|GRAVEL_DESERT"),
    ("dirt", r"^DIRT|^FARM|MUD|SAVANNAH"),
    ("grass", r"GRASS|LEAVES|SHRUB|MOORLAND"),
)

_TERRAIN_CLASS_CACHE = None


def _terrain_classes():
    """{terrain id: legend key}, built once from the installed dataset."""
    global _TERRAIN_CLASS_CACHE
    if _TERRAIN_CLASS_CACHE is not None:
        return _TERRAIN_CLASS_CACHE
    import re as _re
    from AoE2ScenarioParser.datasets.terrains import TerrainId
    table = {}
    for terrain in TerrainId:
        name = terrain.name
        key = "unknown"
        for candidate, pattern in _TERRAIN_PATTERNS:
            if _re.search(pattern, name):
                key = candidate
                break
        table.setdefault(int(terrain.value), key)
    _TERRAIN_CLASS_CACHE = table
    return table


def classify_terrain(terrain_id):
    """Legend key for one terrain id (see rubric_v3._DEFAULT_LEGEND)."""
    return _terrain_classes().get(int(terrain_id), "unknown")


def terrain_class_counts(summary):
    """{legend key: tile count} over the whole map, for the static check."""
    counts = {}
    for row in summary.get("terrain_grid") or []:
        for value in row:
            key = classify_terrain(value)
            counts[key] = counts.get(key, 0) + 1
    return counts


def _player_civilizations(scenario):
    """{player_id: civilization name} for ACTIVE, non-GAIA players.

    The `setting` precondition of the v2 rubric turns on whether a scenario
    assigns civilizations at all, so the name is reported verbatim - including
    the parser's default "RANDOM", which is exactly the case the check is
    looking for. Best-effort: a library shape change yields {} rather than
    breaking every consumer of the summary.
    """
    civs = {}
    try:
        for player in scenario.player_manager.players:
            pid = int(getattr(player, "player_id", -1))
            if pid <= 0:                      # 0 is GAIA, -1 is unreadable
                continue
            if not getattr(player, "active", False):
                continue
            civ = getattr(player, "civilization", None)
            civs[pid] = getattr(civ, "name", None) if civ is not None else None
    except Exception:
        return {}
    return civs


def summarize(path, include_map=False):
    """Return a structured dict describing a built scenario.

    Keys: path, map_size, players (unit rosters per player),
    player_civilizations (active players only), triggers (name, enabled,
    conditions, effects, dialogue), plus rolled-up counts. Raises on an
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

        player_civilizations = _player_civilizations(scenario)

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
        terrain_grid = None
        elevation_grid = None
        if include_map:
            # Row-major grid indexed [y * map_size + x], built from each tile's
            # own coordinates rather than trusting the parser's iteration order.
            terrain = [0] * (map_size * map_size)
            # The same data as 2D rows, plus elevation: what the terrain digest
            # renders. Built in the same pass so the map is walked once.
            terrain_grid = [[0] * map_size for _ in range(map_size)]
            elevation_grid = [[0] * map_size for _ in range(map_size)]
            for tile in map_manager.terrain:
                tx, ty = int(tile.x), int(tile.y)
                if 0 <= tx < map_size and 0 <= ty < map_size:
                    terrain[ty * map_size + tx] = int(tile.terrain_id)
                    terrain_grid[ty][tx] = int(tile.terrain_id)
                    elevation_grid[ty][tx] = int(getattr(tile, "elevation", 0) or 0)

    dialogue = [e["message"] for t in triggers for e in t["effects"]
                if e["message"] and e["type"] in
                ("DISPLAY_INSTRUCTIONS", "SEND_CHAT", "DISPLAY_TIMER")]

    summary = {
        "path": path,
        "filename": os.path.basename(path),
        "map_size": map_size,
        "players": players,
        "player_civilizations": player_civilizations,
        "triggers": triggers,
        "trigger_count": len(triggers),
        "unit_total": sum(e["count"] for r in players.values() for e in r.values()),
        "dialogue": dialogue,
    }
    if include_map:
        summary["all_units"] = all_units
        summary["terrain"] = terrain
        summary["terrain_grid"] = terrain_grid
        summary["elevation_grid"] = elevation_grid
    return summary


def placed_hero_names(summary):
    """Every named hero constant placed in the scenario, deduplicated.

    The v2 `combatants` precondition asks whether each of these is named in the
    episode brief, so it needs the constants themselves (JOAN_OF_ARC, ...)
    rather than the roster counts.
    """
    names = []
    for roster in summary.get("players", {}).values():
        for name, entry in roster.items():
            if entry.get("category") == "hero" and name not in names:
                names.append(name)
    return sorted(names)


def terrain_digest(summary, size=32):
    """The ASCII terrain map + elevation panel the v3 `terrain` dimension needs.

    Rendering lives in rubric_v3 (it is part of the instrument, versioned with
    the rubric text); this supplies the grid and the id->legend classifier.
    Returns "" when the summary was built without include_map, so a caller that
    forgets simply gets no panel rather than a wrong one.
    """
    grid = summary.get("terrain_grid")
    if not grid:
        return ""
    from rubric_v3 import render_terrain_grid
    return render_terrain_grid(grid, classify_terrain, size=size,
                               elevation=summary.get("elevation_grid"))


def to_digest(summary, max_dialogue=28, max_triggers=40, include_civilizations=False,
              include_terrain=False):
    """Render a summary as compact prose for an LLM judge.

    Deliberately content-only: no filename, no model, no prompt condition, so a
    judge cannot infer which arm produced the scenario.

    include_civilizations adds the per-player civilization assignment, which the
    v2 rubric's `setting` dimension scores directly. include_terrain adds the
    ASCII terrain map the v3 `terrain` dimension is scored from. Both are opt-in
    for the same reason: the digest is the judge's whole view of the artifact,
    so adding a panel silently changes what an older rubric was measuring. The
    rubric hash on each score row covers the rubric TEXT, not the digest, so
    nothing downstream would catch that drift - keeping the older digests
    byte-identical is what prevents it.
    """
    lines = [f"MAP: {summary['map_size']}x{summary['map_size']} tiles",
             f"TOTAL PLACED OBJECTS: {summary['unit_total']}", ""]

    if include_civilizations:
        civs = summary.get("player_civilizations") or {}
        lines.append("CIVILIZATION ASSIGNED PER ACTIVE PLAYER")
        if civs:
            for pid in sorted(civs):
                lines.append(f"  Player {pid}: {civs[pid] or 'unset'}")
        else:
            lines.append("  (none readable)")
        lines.append("")

    if include_terrain:
        panel = terrain_digest(summary)
        if panel:
            lines.append(panel)
            lines.append("")

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
