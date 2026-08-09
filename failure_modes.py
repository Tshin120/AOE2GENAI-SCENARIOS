"""
Static detectors for the four ways a scenario becomes unwinnable.

The reachability prompt block names a taxonomy --- resource dead end,
composition imbalance, positional trap, timing collapse --- and asks the model
to rule each one out before emitting code. ``reachability_audit`` checks the
*shape* of the victory conditions; this module checks the taxonomy itself, so
the treatment can be measured against what it actually targets rather than
against a proxy.

Every check reads the built artefact and runs offline. None of them simulate the
game, so each is a screen rather than a proof: they are tuned to fire on the
clear-cut case and stay quiet when the evidence is ambiguous, because a
false alarm on 31 scenarios is more expensive than a miss.

    resource_dead_end     the player is given an economy but the map lacks a
                          resource class needed to run it
    composition_imbalance an enemy force class has no counter available to the
                          player, in units or in production buildings
    positional_trap       the victory objective is not reachable on foot from
                          the player's starting position (flood fill over
                          terrain, buildings, and gates the player cannot open)
    timing_collapse       the first scripted hostile action lands before the
                          player has anything to answer it with

Each detector returns (fired: bool, detail: str).
"""

from collections import deque

# --- Terrain passability ---------------------------------------------------
# Deep and medium water block land movement; shallows, fords and beaches do not.
_WATER_SUBSTRINGS = ("WATER", "OCEAN")
_PASSABLE_WATER_SUBSTRINGS = ("SHALLOW", "FORD", "BEACH", "BRIDGE")

# --- Object classes --------------------------------------------------------
_FOOD_SOURCES = {"FORAGE_BUSH", "DEER", "BOAR", "SHEEP", "GOAT", "TURKEY", "COW",
                 "LLAMA", "WATER_BUFFALO", "ZEBRA", "OSTRICH", "ELEPHANT",
                 "JAVELINA", "IBEX", "GAZELLE", "FISH"}
_WOOD_SOURCES = ("TREE",)
_GOLD_SOURCES = {"GOLD_MINE"}
_STONE_SOURCES = {"STONE_MINE"}

_ECONOMY_UNITS = ("VILLAGER", "TOWN_CENTER", "TRADE_CART", "FISHING_SHIP")

# Coarse combat classes. Deliberately broad: the point is to catch a scenario
# that fields massed siege against an infantry-only player, not to model
# matchups precisely.
_CLASS_MEMBERS = {
    "cavalry": ("KNIGHT", "CAVALIER", "PALADIN", "SCOUT_CAVALRY", "LIGHT_CAVALRY",
                "HUSSAR", "CAMEL", "CATAPHRACT", "WAR_ELEPHANT", "TARKAN",
                "MAGYAR_HUSZAR", "BOYAR", "KESHIK", "LEITIS", "KONNIK",
                "MAMELUKE", "SHRIVAMSHA", "SAVAR"),
    "archer": ("ARCHER", "CROSSBOWMAN", "ARBALESTER", "CAVALRY_ARCHER",
               "HAND_CANNONEER", "SKIRMISHER", "LONGBOWMAN", "CHU_KO_NU",
               "MANGUDAI", "WAR_WAGON", "PLUMED_ARCHER", "RATTAN_ARCHER",
               "GENITOUR", "CONQUISTADOR", "SLINGER", "ARAMBAI"),
    "infantry": ("MILITIA", "MAN_AT_ARMS", "LONG_SWORDSMAN", "TWO_HANDED_SWORDSMAN",
                 "CHAMPION", "SPEARMAN", "PIKEMAN", "HALBERDIER", "EAGLE",
                 "HUSKARL", "SAMURAI", "TEUTONIC_KNIGHT", "WOAD_RAIDER",
                 "BERSERK", "JAGUAR", "THROWING_AXEMAN", "CONDOTTIERO",
                 "KAMAYUK", "SHOTEL", "GBETO", "URUMI", "LEGIONARY"),
    "siege": ("BATTERING_RAM", "CAPPED_RAM", "SIEGE_RAM", "MANGONEL", "ONAGER",
              "SIEGE_ONAGER", "SCORPION", "BOMBARD_CANNON", "TREBUCHET",
              "HOUFNICE", "SIEGE_TOWER"),
    "fortification": ("CASTLE", "WATCH_TOWER", "GUARD_TOWER", "KEEP",
                      "BOMBARD_TOWER", "DONJON", "FORTIFIED_WALL", "STONE_WALL"),
}

# Which of the player's own force classes can meaningfully engage each enemy
# class, plus buildings that train one. Deliberately generous: the intro's
# example is an enemy the player has *no effective answer to at all* (massed
# bombard cannons against infantry with no siege or ranged), not a missing hard
# counter. Knights against light cavalry is an even fight, not an imbalance, so
# a narrow spearmen-only table would flag ordinary scenarios as broken.
_COUNTERS = {
    "cavalry": (("cavalry", "archer", "infantry", "siege"),
                ("BARRACKS", "STABLE", "ARCHERY_RANGE", "CASTLE", "MONASTERY")),
    "archer": (("cavalry", "archer", "infantry", "siege"),
               ("STABLE", "ARCHERY_RANGE", "BARRACKS", "SIEGE_WORKSHOP")),
    "infantry": (("cavalry", "archer", "infantry", "siege"),
                 ("ARCHERY_RANGE", "STABLE", "BARRACKS", "SIEGE_WORKSHOP")),
    "siege": (("cavalry", "archer", "infantry"),
              ("STABLE", "ARCHERY_RANGE", "BARRACKS")),
}

# Monks convert almost anything, so they answer any class on their own.
_UNIVERSAL_ANSWERS = ("MONK", "MISSIONARY", "WARRIOR_PRIEST")

# Force classes that can march at the player. Fortifications are structures and
# are handled by the positional check instead.
_MOBILE_CLASSES = ("cavalry", "archer", "infantry", "siege")

# Anything that can knock a structure down at reasonable speed.
_SIEGE_CAPABLE = ("BATTERING_RAM", "CAPPED_RAM", "SIEGE_RAM", "MANGONEL", "ONAGER",
                  "SIEGE_ONAGER", "TREBUCHET", "BOMBARD_CANNON", "HOUFNICE",
                  "PETARD", "SCORPION")
_SIEGE_PRODUCERS = ("SIEGE_WORKSHOP", "CASTLE")

# An enemy class must reach this many units before its lack of a counter counts
# as an imbalance; one stray knight is not a composition problem.
MASSED_THRESHOLD = 4
# A hostile event this early, with nothing to answer it, is a timing collapse.
EARLY_THREAT_SECONDS = 90

HUMAN = 1


def _is_water(terrain_name):
    if not any(k in terrain_name for k in _WATER_SUBSTRINGS):
        return False
    return not any(k in terrain_name for k in _PASSABLE_WATER_SUBSTRINGS)


def _terrain_names():
    from AoE2ScenarioParser.datasets.terrains import TerrainId
    return {int(t.value): t.name for t in TerrainId}


def _blocked_terrain_ids():
    return {tid for tid, name in _terrain_names().items() if _is_water(name)}


def _classify(unit_name):
    for klass, members in _CLASS_MEMBERS.items():
        for m in members:
            if m in unit_name:
                return klass
    return None


def _player_units(summary, player_id):
    return [u for u in summary.get("all_units", []) if u["player_id"] == player_id]


def _names_of(units):
    return {u["name"] for u in units}


# --- 1. Resource dead end --------------------------------------------------

def resource_dead_end(summary):
    """An economy the map cannot feed.

    Only meaningful when the scenario actually gives the player an economy: a
    pure-combat set piece with no villagers needs no resources, and flagging it
    would be noise. When there is an economy, a resource class that is entirely
    absent from the map is a hard dead end for anything requiring it.
    """
    mine = _player_units(summary, HUMAN)
    if not mine:
        return False, "player has no units"
    my_names = _names_of(mine)
    has_economy = any(any(e in n for e in _ECONOMY_UNITS) for n in my_names)
    if not has_economy:
        return False, "no economy given (combat set piece); resources not required"

    gaia = [u for u in summary.get("all_units", []) if u["player"] == "GAIA"]
    gaia_names = [u["name"] for u in gaia]
    have = {
        "food": any(n in _FOOD_SOURCES or any(f in n for f in ("FISH", "FORAGE"))
                    for n in gaia_names),
        "wood": any(any(w in n for w in _WOOD_SOURCES) for n in gaia_names),
        "gold": any(n in _GOLD_SOURCES for n in gaia_names),
        "stone": any(n in _STONE_SOURCES for n in gaia_names),
    }
    # Food and wood sustain any economy at all; gold and stone gate only some
    # victory paths, so their absence alone is not called a dead end.
    missing = [k for k in ("food", "wood") if not have[k]]
    if missing:
        return True, ("economy present but map has no " + " or ".join(missing)
                      + f" source (gold={have['gold']}, stone={have['stone']})")
    return False, ("economy supported: " +
                   ", ".join(k for k, v in have.items() if v))


# --- 2. Composition imbalance ---------------------------------------------

def composition_imbalance(summary):
    """A massed enemy class the player cannot answer.

    Counts an answer as available if the player already fields a counter unit or
    owns a building that trains one, since a scenario with production is not
    stuck with its opening army.
    """
    mine = _player_units(summary, HUMAN)
    if not mine:
        return False, "player has no units"
    enemies = [u for u in summary.get("all_units", [])
               if u["player"] not in ("GAIA", "ONE") and u["player_id"] != HUMAN]
    if not enemies:
        return False, "no enemy units"

    # Mobile force classes only. Fortifications are excluded deliberately: a
    # walled base is 100+ separate wall objects, which would swamp any unit
    # count, and being unable to knock a wall down is a positional problem, not
    # a composition one.
    enemy_force = {}
    for u in enemies:
        klass = _classify(u["name"])
        if klass in _MOBILE_CLASSES:
            enemy_force[klass] = enemy_force.get(klass, 0) + 1

    my_names = _names_of(mine)
    my_classes = {_classify(n) for n in my_names} - {None}
    has_universal = any(any(u in n for u in _UNIVERSAL_ANSWERS) for n in my_names)

    unanswered = []
    for klass, count in sorted(enemy_force.items()):
        if count < MASSED_THRESHOLD:
            continue
        answering_classes, building_counters = _COUNTERS.get(klass, ((), ()))
        has_unit = bool(my_classes & set(answering_classes))
        has_building = any(any(b in n for b in building_counters) for n in my_names)
        if not (has_unit or has_building or has_universal):
            unanswered.append(f"{klass} x{count}")

    mine_txt = ", ".join(sorted(my_classes)) or "no military class"
    if unanswered:
        return True, (f"player fields {mine_txt} with no production; "
                      "nothing answers " + "; ".join(unanswered))
    summary_txt = ", ".join(f"{k} x{v}" for k, v in sorted(enemy_force.items()))
    return False, (f"enemy force ({summary_txt or 'none classified'}) "
                   f"answered by player {mine_txt}")


# --- 3. Positional trap ----------------------------------------------------

def _walkable_grid(summary, include_structures):
    """Boolean grid of tiles a land unit can occupy.

    Two settings, because the obstacles differ in kind. Deep water and cliffs
    are *permanent*: no unit composition removes them. Enemy buildings --- walls,
    gates, towers --- are destructible, so they delay rather than forbid. Passing
    include_structures=False gives the permanent-barrier map, which is what
    decides whether a scenario is genuinely unwinnable.
    """
    size = summary["map_size"]
    terrain = summary.get("terrain") or []
    blocked_ids = _blocked_terrain_ids()
    walk = [True] * (size * size)
    for i, tid in enumerate(terrain):
        if tid in blocked_ids:
            walk[i] = False
    for u in summary.get("all_units", []):
        name = u["name"]
        permanent = "CLIFF" in name
        destructible = u["category"] == "building" and u["player_id"] != HUMAN
        if not (permanent or (include_structures and destructible)):
            continue
        x, y = u["x"], u["y"]
        if 0 <= x < size and 0 <= y < size:
            walk[y * size + x] = False
    return walk, size


def _can_breach(summary):
    """Whether the player can remove a structure blocking the way."""
    my_names = _names_of(_player_units(summary, HUMAN))
    has_siege = any(any(s in n for s in _SIEGE_CAPABLE) for n in my_names)
    has_producer = any(any(b in n for b in _SIEGE_PRODUCERS) for n in my_names)
    return has_siege or has_producer


def _reachable_from(starts, walk, size):
    """Flood fill (8-connected) from the starting tiles over walkable ground."""
    seen = bytearray(size * size)
    q = deque()
    for x, y in starts:
        if 0 <= x < size and 0 <= y < size and not seen[y * size + x]:
            seen[y * size + x] = 1
            q.append((x, y))
    while q:
        x, y = q.popleft()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = x + dx, y + dy
                if not (0 <= nx < size and 0 <= ny < size):
                    continue
                idx = ny * size + nx
                if seen[idx] or not walk[idx]:
                    continue
                seen[idx] = 1
                q.append((nx, ny))
    return seen


def victory_targets(summary):
    """Tiles the player must physically reach to win.

    Resolves each victory condition's unit_object reference to a placed object,
    and takes area-based conditions at their area centre.
    """
    by_ref = {u["reference_id"]: u for u in summary.get("all_units", [])}
    targets = []
    for trig in summary["triggers"]:
        wins = [e for e in trig["effects"]
                if e["type"] == "DECLARE_VICTORY" and e.get("source_player") == HUMAN]
        if not wins:
            continue
        for cond in trig["conditions"]:
            ref = cond.get("unit_object")
            if isinstance(ref, int) and ref in by_ref:
                u = by_ref[ref]
                targets.append((trig["name"], u["name"], u["x"], u["y"]))
                continue
            area = cond.get("area") or []
            if len(area) == 4 and all(isinstance(v, int) and v >= 0 for v in area):
                x1, y1, x2, y2 = area
                targets.append((trig["name"], "area", (x1 + x2) // 2, (y1 + y2) // 2))
    return targets


def _unreached(targets, seen, size):
    """Targets with no reachable tile within one step (units attack adjacent)."""
    out = []
    for name, target_name, tx, ty in targets:
        ok = any(seen[(ty + dy) * size + (tx + dx)]
                 for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                 if 0 <= tx + dx < size and 0 <= ty + dy < size)
        if not ok:
            out.append(f"{name} -> {target_name} @({tx},{ty})")
    return out


def positional_trap(summary):
    """Victory objectives the player cannot get to.

    Fires only when *every* objective is cut off by a permanent barrier ---
    water or cliffs --- which no unit composition can undo. A base sealed behind
    walls is reported but not flagged, unless the player also has no way to
    breach: walls are destructible, so treating them as terrain would call
    almost every siege scenario broken.
    """
    if "terrain" not in summary:
        return False, "map data not loaded"
    mine = _player_units(summary, HUMAN)
    if not mine:
        return False, "player has no units"
    targets = victory_targets(summary)
    if not targets:
        return False, "no positional victory objective"

    starts = [(u["x"], u["y"]) for u in mine]

    hard_walk, size = _walkable_grid(summary, include_structures=False)
    hard_unreached = _unreached(targets, _reachable_from(starts, hard_walk, size), size)
    if hard_unreached and len(hard_unreached) == len(targets):
        return (True,
                "no victory objective reachable: permanent terrain barrier "
                "(water/cliff) blocks " + "; ".join(hard_unreached),
                {"reason": "terrain_barrier"})

    soft_walk, _ = _walkable_grid(summary, include_structures=True)
    soft_unreached = _unreached(targets, _reachable_from(starts, soft_walk, size), size)
    if soft_unreached and len(soft_unreached) == len(targets):
        if not _can_breach(summary):
            return (True,
                    "every objective is sealed behind enemy structures and the "
                    "player has no siege unit or siege-producing building "
                    "(melee can still chip walls, so this is a severe impediment "
                    "rather than strict unwinnability): " + "; ".join(soft_unreached),
                    {"reason": "sealed_no_siege"})
        return (False,
                f"{len(soft_unreached)} objective(s) behind enemy structures, "
                "but the player can breach (siege available)",
                {"reason": "sealed_can_breach"})
    if hard_unreached:
        return (False,
                f"{len(hard_unreached)}/{len(targets)} objective(s) behind a "
                "permanent barrier, but a reachable objective remains",
                {"reason": "partial_barrier"})
    return (False, f"all {len(targets)} victory objective(s) reachable on foot",
            {"reason": "clear"})


# --- 4. Timing collapse ----------------------------------------------------

_HOSTILE_EFFECTS = {"CREATE_OBJECT", "TASK_OBJECT", "PATROL", "DAMAGE_OBJECT",
                    "KILL_OBJECT", "CHANGE_OWNERSHIP"}
_MILITARY_CLASSES = ("cavalry", "archer", "infantry", "siege")


def timing_collapse(summary):
    """A scripted attack lands before the player can answer it.

    Looks for the earliest timer-gated trigger that creates or tasks hostile
    units, and asks whether the player has any military asset at t=0 --- units,
    fortifications, or a military production building.
    """
    earliest = None
    for trig in summary["triggers"]:
        timers = [c.get("timer") for c in trig["conditions"]
                  if c["type"] == "TIMER" and isinstance(c.get("timer"), int)
                  and c["timer"] >= 0]
        if not timers:
            continue
        hostile = any(e["type"] in _HOSTILE_EFFECTS
                      and isinstance(e.get("source_player"), int)
                      and e["source_player"] not in (HUMAN, -1)
                      for e in trig["effects"])
        if hostile:
            t = min(timers)
            if earliest is None or t < earliest:
                earliest = t

    if earliest is None:
        return False, "no timer-gated hostile action"

    mine = _player_units(summary, HUMAN)
    my_names = _names_of(mine)
    has_military = any(_classify(n) in _MILITARY_CLASSES for n in my_names)
    has_defence = any(any(f in n for f in _CLASS_MEMBERS["fortification"])
                      for n in my_names)
    has_production = any(any(b in n for b in ("BARRACKS", "ARCHERY_RANGE", "STABLE",
                                              "SIEGE_WORKSHOP", "CASTLE"))
                         for n in my_names)

    if earliest <= EARLY_THREAT_SECONDS and not (has_military or has_defence):
        return True, (f"first hostile action at t={earliest}s with no starting "
                      f"military or fortification (production={has_production})")
    return False, (f"first hostile action at t={earliest}s; "
                   f"military={has_military}, fortification={has_defence}")


# --- Entry point -----------------------------------------------------------

DETECTORS = (
    ("resource_dead_end", resource_dead_end),
    ("composition_imbalance", composition_imbalance),
    ("positional_trap", positional_trap),
    ("timing_collapse", timing_collapse),
)


def detect_all(summary):
    """Run every detector. Returns {name: {fired, detail, ...}} plus a rollup.

    A detector may return (fired, detail) or (fired, detail, extra); extra is
    merged into that detector's entry, which is how positional_trap reports
    whether the barrier was permanent terrain or a structure it cannot breach.
    """
    out = {}
    fired = []
    for name, fn in DETECTORS:
        extra = {}
        try:
            result = fn(summary)
            if len(result) == 3:
                hit, detail, extra = result
            else:
                hit, detail = result
        except Exception as e:                      # a detector must never
            hit, detail = False, f"detector error: {e}"   # break the audit
        out[name] = {"fired": bool(hit), "detail": detail, **(extra or {})}
        if hit:
            fired.append(name)
    out["any_failure_mode"] = bool(fired)
    out["failure_modes_fired"] = fired
    out["n_failure_modes"] = len(fired)
    return out
