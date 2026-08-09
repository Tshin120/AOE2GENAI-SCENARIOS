import os
import re
import ast
import sys
import json
import uuid
import inspect
import difflib
import importlib
import subprocess
import requests
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
import logging
from pathlib import Path

import api_config
from provenance import write_sidecar, append_result, new_run_id, utc_now_iso

# AoE2ScenarioParser imports
from AoE2ScenarioParser.scenarios.aoe2_de_scenario import AoE2DEScenario
from AoE2ScenarioParser.datasets.players import PlayerId
from AoE2ScenarioParser.datasets.units import UnitInfo
from AoE2ScenarioParser.datasets.trigger_lists import *
from AoE2ScenarioParser.datasets.buildings import BuildingInfo
from AoE2ScenarioParser.datasets.other import OtherInfo
from AoE2ScenarioParser.datasets.techs import TechInfo
from AoE2ScenarioParser.datasets.heroes import HeroInfo

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Reachability-analysis guidance (the "treatment" prompt).
#
# Appended to the system prompt when ScenarioConfig.reachability_prompting is
# True (the default). Set the flag False to reproduce the original "control"
# prompt. This block is the merged form of reachability_research/
# generator_reachability.py's added guidance PLUS the explicit
# destroy_object-over-objects_in_area trigger guidance (decision D1-B): a
# win/lose condition built on objects_in_area(quantity=0) is a classic source
# of permanently-unwinnable scenarios, so it is called out directly here.
# ---------------------------------------------------------------------------
REACHABILITY_ANALYSIS_BLOCK = """

                    REACHABILITY ANALYSIS - CRITICAL FOR SCENARIO QUALITY:

                    Before finalizing your scenario, verify reachability - that both
                    victory and defeat are achievable from every reachable game state.

                    A scenario is BROKEN if:
                    1. The player cannot win (no path to victory exists)
                    2. The player cannot lose (no challenge, no defeat path)
                    3. The player can reach a state where victory becomes permanently
                       impossible, regardless of skill

                    THE FOUR WAYS SCENARIOS BREAK:

                    1. RESOURCE DEAD END: The total resources on the map (mines + starting
                       stockpile) are insufficient to accomplish the victory condition, and
                       no alternative income sources (market, trade route, relics) are
                       provided. Ensure the player has enough total resources to build the
                       units and structures needed to win.

                    2. COMPOSITION IMBALANCE: The enemy has a unit composition that the
                       player has no effective counter for, given the units and buildings
                       available to them. For example, giving the enemy massed bombard
                       cannons but only providing the player with infantry and no siege
                       workshop or ranged units. Ensure the player has access to units or
                       buildings that can counter every enemy unit type present.

                    3. POSITIONAL TRAP: The player cannot physically reach objectives or
                       enemies. For example, objectives placed across water with no dock
                       or transport ship provided, or enemies behind terrain barriers with
                       no siege units available. Ensure physical paths exist or provide the
                       tools to create them.

                    4. TIMING COLLAPSE: The gap between the first enemy threat and the
                       player's first possible military response is too large, and the
                       player's existing assets cannot survive that gap. The enemy destroys
                       win-critical assets (town center, hero unit, key buildings) before
                       the player can mount any defense. Ensure the player has enough
                       starting units or defenses to survive until they can respond.

                    TRIGGER CONDITIONS FOR WIN/LOSE - PREFER destroy_object OVER objects_in_area:
                    - For any VICTORY or DEFEAT condition, prefer destroy_object on a stored
                      unit reference (enemy leader, castle, hero, or a key building) over
                      objects_in_area(quantity=0, ...).
                    - objects_in_area(quantity=0) is a FRAGILE win/lose check: a single enemy
                      unit that garrisons inside a building, gets converted, flees to an
                      unreachable corner, or spawns outside the checked area leaves the count
                      above 0 forever - making victory permanently unreachable (failure mode
                      3, POSITIONAL TRAP). destroy_object targets one specific object by its
                      reference_id and fires deterministically when that object dies.
                    - CORRECT (deterministic): store the reference and destroy it -
                        enemy_leader = unit_manager.add_unit(PlayerId.TWO, unit_const=HeroInfo.XXX.ID, ...)
                        vc = trigger_manager.add_trigger("VC")
                        vc.new_condition.destroy_object(unit_object=enemy_leader.reference_id)
                        vc.new_effect.declare_victory(source_player=PlayerId.ONE, enabled=1)
                    - Reserve objects_in_area for NON-TERMINAL detection (is the player near a
                      zone, has a wave been thinned) - not as the sole path to victory. If you
                      must gate victory on clearing an area, ALSO provide a destroy_object
                      victory path on the enemy leader/castle so the scenario is still winnable.
                    - Every scenario MUST contain at least one declare_victory effect reachable
                      through a destroy_object (or bring_object_to_area) condition.

                    REACHABILITY CHECKLIST (verify before generating code):
                    - [ ] Victory trigger exists and is reachable through player actions
                    - [ ] Victory is driven by destroy_object / bring_object_to_area, not by a
                          lone objects_in_area(quantity=0) check
                    - [ ] Defeat is possible (enemy can actually threaten the player)
                    - [ ] Total resources on the map are sufficient to reach the victory
                          condition
                    - [ ] Player has access to units that can counter the enemy composition
                    - [ ] Player can physically reach all objectives on the map
                    - [ ] If timed waves exist, the player has enough starting
                          units/buildings to survive the first wave
                    - [ ] No trigger deadlocks (triggers that disable each other creating
                          an unwinnable state)

                    After verifying, add a comment block at the top of your generated code:
                    # REACHABILITY ANALYSIS:
                    # Victory path: [brief description]
                    # Defeat path: [brief description]
                    # Resource sufficiency: [yes/no + why]
                    # Counter availability: [yes/no + why]
                    # Physical access: [yes/no + why]
                    # Timing viability: [yes/no + why]
"""

# --- Prompt-style ablation --------------------------------------------------
# The scenario-type templates in ScenarioGenerator._load_templates() prescribe a
# rigid trigger count and per-section structure. prompt_style="freeform" skips
# that template and sends a short generic instruction instead, letting the model
# choose its own trigger structure/count for the episode. Everything else - the
# system prompt (base + reachability block), the region/civ templates and every
# parser-usage rule - is identical across modes, so the ablation isolates the
# scenario-type template only.
TEMPLATED_MIN_TRIGGERS = 20   # soft warning floor for the templated (default) prompt
FREEFORM_MIN_TRIGGERS = 4     # soft floor for freeform: setup + narrative + objectives + win/loss

FREEFORM_PROMPT_TEMPLATE = """Create a complete, playable Age of Empires 2 scenario for this historical episode:
- Title: {title}
- Description: {description}
- Map size: {map_size}x{map_size}
- Players: {players}
- Difficulty: {difficulty}

Build a COMPLETE, PLAYABLE scenario:
- Set up the map, the players, and their starting units and buildings, then express the game logic as triggers.
- Tell the story of this episode through in-game dialogue, using the color convention <YELLOW> for the narrator, <BLUE> for allies, and <RED> for enemies.
- Give the player clear objectives, displayed in-game.
- Provide BOTH a reachable victory condition AND a reachable defeat condition: the player must be able to actually win, and to actually lose.

YOU decide the trigger structure and the number of triggers that best fit THIS
episode - there is NO fixed or required trigger count. As a soft minimum, create
enough triggers to cover: initial setup, the narrative/dialogue beats, the
objectives, and the win/loss conditions. Choose whatever design makes the
scenario the most historically faithful and the most playable for this episode."""


@dataclass
class ScenarioConfig:
    """Configuration for scenario generation

    Scenario types (based on real AoE2 campaign analysis):
    - battle: Direct combat between armies (Saladin 6 pattern)
    - escort: Protect hero/units traveling to destination (Joan 1, 5 pattern)
    - diplomacy: Multiple factions to ally with through quests (Genghis 1 pattern)
    - defense: Survive waves of attackers (Saladin 5 pattern)
    - conquest: Capture enemy bases/objectives progressively (Genghis 3 pattern)
    - story: Narrative-driven with multiple acts (combined patterns)

    Geographic regions for terrain/building selection:
    - mediterranean: Coastlines, olive groves, palm trees, dry grass
    - steppe: Open grassland, minimal trees, rolling hills
    - northern_europe: Dense forests, rivers, marshes, oak trees
    - desert: Sand dunes, oases, palm trees, rocky outcrops
    - east_asia: Rice paddies, bamboo, rivers, mountains
    - middle_east: Arid terrain, date palms, mud brick architecture

    Civilization styles for building appearance:
    - western_european: Franks, Britons, Teutons (castles, monasteries, pavilions)
    - eastern_european: Slavs, Byzantines (orthodox churches, stone forts)
    - middle_eastern: Saracens, Persians, Berbers (mosques, pavilions, desert camps)
    - central_asian: Mongols, Cumans, Tatars (yurts, nomadic camps)
    - east_asian: Chinese, Japanese, Koreans (pagodas, bamboo)
    - african: Malians, Ethiopians (unique architecture, savanna)
    """
    title: str
    description: str
    map_size: int = 120
    players: int = 2
    difficulty: str = "medium"
    scenario_type: str = "story"  # battle, escort, diplomacy, defense, conquest, story
    output_path: str = "generated_scenario.aoe2scenario"
    wikipedia_url: str = None  # Optional Wikipedia URL for historical context
    region: str = None  # Geographic region: mediterranean, steppe, northern_europe, desert, east_asia, middle_east
    player_civ: str = None  # Player civilization style: western_european, eastern_european, middle_eastern, central_asian, east_asian
    enemy_civ: str = None  # Enemy civilization style

    # --- Generation parameters (per-run, recorded into the metadata sidecar) ---
    model: str = None  # MODEL_REGISTRY key or raw OpenRouter slug; None -> api_config.DEFAULT_MODEL
    temperature: float = 0.7  # sampling temperature (default unchanged)
    max_tokens: int = 32000  # completion cap (raised default so large scenarios are not truncated)

    # --- Quality levers ---
    reachability_prompting: bool = True  # append the reachability-analysis guidance to the system prompt
    best_of: int = 1  # generate N candidates, keep the first that builds successfully (>=1)
    max_repair_attempts: int = 3  # self-repair retries after a validation_failure / execution_error

    # --- Ablation lever ---
    prompt_style: str = "templated"  # "templated" (per-type template, default) | "freeform" (generic instruction)

# Bumped when the generation pipeline changes in a way that affects outputs.
GENERATOR_VERSION = "2.0"


@dataclass
class ExecutionOutcome:
    """Structured result of executing generated scenario code as a subprocess."""
    ok: bool
    returncode: int
    stdout: str
    stderr: str


@dataclass
class GenerationResult:
    """Terminal result of one generate() call.

    outcome is exactly one of: success | validation_failure | execution_error |
    api_error. For best-of-N this is the first successful candidate, else the
    last candidate's terminal attempt.
    """
    outcome: str
    title: str
    scenario_type: str
    model: str
    temperature: float
    max_tokens: int
    reachability_prompting: bool
    output_path: str
    run_id: str = ""
    candidate: int = 1
    attempts: int = 0
    trigger_count: int = 0
    code: str = ""
    stderr: str = ""
    validation_detail: str = ""
    error: str = ""
    prompt_style: str = "templated"
    # Which introspection fired to produce this attempt's code (importerror |
    # attributeerror | typeerror | nameerror), else None. Lets us later query how
    # often introspection-augmented repairs fired and whether they converge
    # faster than plain stderr-echo repairs.
    introspection: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.outcome == "success"


def _extract_python_code(text: str) -> str:
    """Extract Python source from a model response, stripping markdown fences."""
    if "```python" in text:
        start = text.find("```python") + len("```python")
        end = text.find("```", start)
        return text[start:end].strip() if end != -1 else text[start:].strip()
    if "```" in text:
        start = text.find("```") + 3
        end = text.find("```", start)
        return text[start:end].strip() if end != -1 else text[start:].strip()
    return text.strip()


# ---------------------------------------------------------------------------
# Repair introspection.
#
# When a generated program fails on a parser API call, the repair loop otherwise
# sees only the traceback text and tends to *guess* another wrong name (we saw
# defense scenarios burn all 4 attempts cycling ResourceId -> Resource ->
# modify_attribute(attribute=...), none of which exist). These helpers pull the
# GROUND TRUTH out of the INSTALLED AoE2ScenarioParser - the real importable
# names, the real object attributes, the real call signatures - and hand it to
# the repair model so "guess again" becomes "pick a valid option".
#
# Everything here is best-effort and defensive: _introspect_error never raises
# into the generation pipeline, and any library-shape change simply yields no
# block instead of a crash. Output is hard-capped at _MAX_INTROSPECTION_LINES.
# ---------------------------------------------------------------------------
_MAX_INTROSPECTION_LINES = 30

# Dataset modules the generated code imports via `from ...datasets.X import *`.
_DATASET_MODULES = [
    "AoE2ScenarioParser.datasets.trigger_lists",
    "AoE2ScenarioParser.datasets.players",
    "AoE2ScenarioParser.datasets.units",
    "AoE2ScenarioParser.datasets.buildings",
    "AoE2ScenarioParser.datasets.techs",
    "AoE2ScenarioParser.datasets.heroes",
    "AoE2ScenarioParser.datasets.other",
    "AoE2ScenarioParser.datasets.terrains",
]


def _public_names(obj, limit=60):
    return [n for n in dir(obj) if not n.startswith("_")][:limit]


def _closest(target, candidates, n=5):
    """Best-effort 'did you mean' over a name list (fuzzy, then substring)."""
    close = difflib.get_close_matches(target, candidates, n=n, cutoff=0.6)
    if not close:
        low = target.lower()
        close = [c for c in candidates if low in c.lower() or c.lower() in low][:n]
    return close


def _clean_sig(func) -> str:
    """inspect.signature() as a string with the bound 'self' dropped."""
    s = str(inspect.signature(func))
    return s.replace("(self, ", "(").replace("(self)", "()")


def _effect_condition_classes():
    """The NewEffectSupport / NewConditionSupport classes (importable without a
    scenario instance, so no from_default() parse / no emoji-print). (None, None)
    if the library moved them."""
    try:
        from AoE2ScenarioParser.objects.support.new_effect import NewEffectSupport
        from AoE2ScenarioParser.objects.support.new_condition import NewConditionSupport
        return NewEffectSupport, NewConditionSupport
    except Exception:
        return None, None


def _introspect_callable(func):
    """TypeError on a call: show the real signature of the effect/condition
    method, plus the sibling modify_* when a resource/attribute mix-up is
    likely (e.g. modify_attribute(attribute=...) instead of modify_resource)."""
    eff, con = _effect_condition_classes()
    out = []
    for cls, label in ((eff, "new_effect"), (con, "new_condition")):
        if cls is not None and hasattr(cls, func):
            try:
                out.append(f"{label}.{func}{_clean_sig(getattr(cls, func))}")
            except (TypeError, ValueError):
                pass
    if func in ("modify_attribute", "modify_resource") and eff is not None:
        sibling = "modify_resource" if func == "modify_attribute" else "modify_attribute"
        if hasattr(eff, sibling):
            try:
                out.append(f"new_effect.{sibling}{_clean_sig(getattr(eff, sibling))}")
            except (TypeError, ValueError):
                pass
        out.append("For PLAYER resources (food/wood/stone/gold) use modify_resource with "
                   "tribute_list=Attribute.GOLD_STORAGE (or FOOD_/WOOD_/STONE_STORAGE) and "
                   "operation=Operation.SET/ADD/SUBTRACT - NOT modify_attribute.")
    if not out and eff is not None:
        close = _closest(func, _public_names(eff, limit=200))
        if close:
            out.append(f"No new_effect/new_condition method named '{func}'. "
                       f"Closest: {', '.join(close)}")
    return out


def _resolve_owner(owner):
    """Resolve the object named in an AttributeError to a module or class."""
    try:
        return importlib.import_module(owner)
    except Exception:
        pass
    simple = owner.split(".")[-1]
    eff, con = _effect_condition_classes()
    for cls in (eff, con):
        if cls is not None and cls.__name__ == simple:
            return cls
    for modname in _DATASET_MODULES:
        try:
            m = importlib.import_module(modname)
        except Exception:
            continue
        cand = getattr(m, simple, None)
        if isinstance(cand, type):
            return cand
    return None


def _introspect_attribute(owner, missing):
    """AttributeError: list the real public attributes/methods of the object."""
    obj = _resolve_owner(owner)
    if obj is None:
        return []
    names = _public_names(obj, limit=60)
    out = [f"'{owner}' has no attribute '{missing}'. Valid attributes/methods:"]
    close = _closest(missing, names)
    if close:
        out.append("  closest: " + ", ".join(close))
    out.append("  " + ", ".join(names[:40]))
    return out


def _introspect_import(name, module):
    """ImportError 'cannot import name': list what the module really exports."""
    try:
        m = importlib.import_module(module)
    except Exception:
        return []
    public = _public_names(m, limit=200)
    classes = [n for n in public if isinstance(getattr(m, n, None), type)]
    out = [f"Cannot import '{name}' from {module} - it does not exist."]
    close = _closest(name, public)
    if close:
        out.append("  closest names: " + ", ".join(close))
    if classes:
        out.append("  importable classes: " + ", ".join(classes[:25]))
    if "trigger_lists" in module and any(k in name.lower()
                                         for k in ("resource", "tribute", "attribute")):
        out.append("  For player resources use enum 'Attribute' (FOOD_STORAGE, WOOD_STORAGE, "
                   "STONE_STORAGE, GOLD_STORAGE) with 'Operation' (SET/ADD/SUBTRACT) via "
                   "new_effect.modify_resource(...).")
    return out


def _introspect_missing_module(module):
    """ModuleNotFoundError: point at the real dataset module list."""
    return [f"No module named '{module}'. Valid dataset modules are:",
            "  " + ", ".join(_DATASET_MODULES)]


def _introspect_name(name):
    """NameError: a bare undefined symbol - say where it actually lives (the
    datasets use `import *`), or the closest real name if it doesn't exist."""
    found_in = []
    for modname in _DATASET_MODULES:
        try:
            m = importlib.import_module(modname)
        except Exception:
            continue
        if hasattr(m, name):
            found_in.append(modname.split(".")[-1])
    if found_in:
        return [f"'{name}' is not defined here but exists in datasets: "
                f"{', '.join(found_in)} (imported via `import *`) - just use it directly."]
    out = [f"'{name}' is not defined and does not exist in the datasets."]
    try:
        tl = importlib.import_module("AoE2ScenarioParser.datasets.trigger_lists")
        close = _closest(name, _public_names(tl, limit=200))
    except Exception:
        close = []
    if close:
        out.append("  did you mean: " + ", ".join(close))
    if any(k in name.lower() for k in ("resource", "tribute")):
        out.append("  For player resources: new_effect.modify_resource(quantity=..., "
                   "tribute_list=Attribute.GOLD_STORAGE, source_player=PlayerId.ONE, "
                   "operation=Operation.SET).")
    return out


def _introspect_error(error_text):
    """Return (ground_truth_block, kind) for a failing program's error text.

    kind is one of 'importerror' | 'attributeerror' | 'typeerror' | 'nameerror'
    when a parser API error is recognized and ground truth was pulled from the
    installed library, else ('', None). Scans the traceback bottom-up so the
    actual raised exception (last line) wins over any chained context. Never
    raises - introspection failures degrade to no block."""
    try:
        if not error_text:
            return "", None
        lines = [ln.rstrip() for ln in error_text.splitlines() if ln.strip()]
        kind, body = None, []
        for ln in reversed(lines):
            m = re.search(r"TypeError:\s+(\w+)\(\)", ln)
            if m and re.search(r"unexpected keyword argument|missing \d+ required|"
                               r"takes \d+|positional argument", ln):
                kind, body = "typeerror", _introspect_callable(m.group(1))
                break
            m = re.search(r"AttributeError:\s+(?:'([\w.]+)' object|module '([\w.]+)'|"
                          r"type object '([\w.]+)') has no attribute '([^']+)'", ln)
            if m:
                owner = m.group(1) or m.group(2) or m.group(3)
                kind, body = "attributeerror", _introspect_attribute(owner, m.group(4))
                break
            m = re.search(r"(?:ImportError|ModuleNotFoundError):\s+cannot import name "
                          r"'([^']+)' from '([\w.]+)'", ln)
            if m:
                kind, body = "importerror", _introspect_import(m.group(1), m.group(2))
                break
            m = re.search(r"ModuleNotFoundError:\s+No module named '([\w.]+)'", ln)
            if m:
                kind, body = "importerror", _introspect_missing_module(m.group(1))
                break
            m = re.search(r"NameError:\s+name '([^']+)' is not defined", ln)
            if m:
                kind, body = "nameerror", _introspect_name(m.group(1))
                break
        if not kind or not body:
            return "", None
        header = ("=== GROUND TRUTH FROM INSTALLED AoE2ScenarioParser "
                  "(use ONLY the names/signatures below; do not invent others) ===")
        block_lines = ([header] + body)[:_MAX_INTROSPECTION_LINES]
        return "\n\n" + "\n".join(block_lines) + "\n", kind
    except Exception:
        return "", None


class OpenRouterAPI:
    """Handles communication with OpenRouter API"""
    
    def __init__(self, api_key: str, base_url: str = "https://openrouter.ai/api/v1"):
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://aoe2scenario-generator.com",
            "X-Title": "AoE2 Scenario Generator"
        }
    
    def generate_scenario_code(self, prompt: str, model: str = None,
                               temperature: float = None, max_tokens: int = None,
                               reachability_prompting: bool = True) -> str:
        """Generate scenario code using OpenRouter API.

        model / temperature / max_tokens fall back to the api_config defaults
        when not supplied. reachability_prompting toggles the reachability
        guidance appended to the system prompt (REACHABILITY_ANALYSIS_BLOCK).
        """
        model = api_config.resolve_model(model)
        if temperature is None:
            temperature = api_config.DEFAULT_TEMPERATURE
        if max_tokens is None:
            max_tokens = api_config.DEFAULT_MAX_TOKENS

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": """You are an expert Age of Empires 2 scenario creator using the AoE2ScenarioParser library.

                    Generate complete, runnable Python code that creates an Age of Empires 2 scenario.

                    IMPORTANT - Start your code with this EXACT header:
                    ```python
                    import sys
                    import io
                    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
                    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

                    from AoE2ScenarioParser.scenarios.aoe2_de_scenario import AoE2DEScenario
                    from AoE2ScenarioParser.datasets.players import PlayerId
                    from AoE2ScenarioParser.datasets.units import UnitInfo
                    from AoE2ScenarioParser.datasets.buildings import BuildingInfo
                    from AoE2ScenarioParser.datasets.trigger_lists import *
                    from AoE2ScenarioParser.datasets.techs import TechInfo
                    from AoE2ScenarioParser.datasets.heroes import HeroInfo
                    from AoE2ScenarioParser.datasets.other import OtherInfo
                    from AoE2ScenarioParser.datasets.terrains import TerrainId
                    ```

                    IMPORTANT API USAGE - Follow this exact pattern:
                    ```python
                    # Create a new blank scenario
                    scenario = AoE2DEScenario.from_default()

                    # Get managers
                    unit_manager = scenario.unit_manager
                    trigger_manager = scenario.trigger_manager
                    map_manager = scenario.map_manager

                    # FIRST: Get map size - default is 120x120, use this for ALL coordinate calculations
                    map_size = map_manager.map_size  # Returns 120 for default map
                    # To CHANGE the map size, ASSIGN the property (there is NO set_size / set_map_size method):
                    #   map_manager.map_size = 100   # resizes to 100x100; re-read map_size afterward
                    map_size = map_manager.map_size

                    # Calculate safe zones based on map_size (NEVER use hardcoded coordinates!)
                    center = map_size // 2
                    quarter = map_size // 4
                    three_quarter = (map_size * 3) // 4

                    # Add units - use .ID property and map_size-relative coordinates
                    unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.MILITIA.ID, x=center, y=center)
                    unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.ARCHER.ID, x=three_quarter, y=three_quarter)
                    unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.BARRACKS.ID, x=quarter, y=quarter)
                    unit_manager.add_unit(PlayerId.ONE, unit_const=HeroInfo.JOAN_OF_ARC.ID, x=center-5, y=center-5)
                    unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.GOLD_MINE.ID, x=quarter+5, y=quarter+5)

                    # MANDATORY: Add GAIA resources for player economy (using map_size-relative positions)
                    # Gold mines cluster near player start
                    for i in range(5):
                        unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.GOLD_MINE.ID, x=quarter+i, y=center)
                    # Stone mines cluster
                    for i in range(4):
                        unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.STONE_MINE.ID, x=quarter+i, y=center+5)
                    # Forage bushes
                    for i in range(8):
                        unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.FORAGE_BUSH.ID, x=quarter-5+i, y=center-5)
                    # Huntable animals
                    for i in range(4):
                        unit_manager.add_unit(PlayerId.GAIA, unit_const=UnitInfo.DEER.ID, x=quarter+10+i, y=center+10)
                    # Herdable animals
                    for i in range(6):
                        unit_manager.add_unit(PlayerId.GAIA, unit_const=UnitInfo.SHEEP.ID, x=quarter+5+i, y=center-10)

                    # Paint terrain tiles (water, grass, beach, etc.)
                    # ALWAYS use pre-calculated variables: center, quarter, three_quarter, map_size
                    # NEVER use hardcoded numbers like 50, 80, 100 - they may exceed map boundaries!

                    # Example: Create sea on left portion of map (first 25% = 0 to quarter)
                    for x in range(0, quarter):
                        for y in range(0, map_size):
                            tile = map_manager.get_tile(x=x, y=y)
                            tile.terrain_id = TerrainId.WATER_DEEP.value

                    # Create beach transition (3 tiles after water: quarter to quarter+3)
                    beach_end = min(quarter + 3, map_size)
                    for x in range(quarter, beach_end):
                        for y in range(0, map_size):
                            tile = map_manager.get_tile(x=x, y=y)
                            tile.terrain_id = TerrainId.BEACH.value

                    # Land area starts after beach (quarter+3 to map_size)
                    # This is where you place units, buildings, resources

                    # Create triggers - ONLY use these conditions (exact parameter names!):
                    trigger = trigger_manager.add_trigger("My Trigger")
                    trigger.new_condition.timer(timer=10)
                    trigger.new_condition.bring_object_to_area(unit_object=unit.reference_id, area_x1=10, area_y1=10, area_x2=20, area_y2=20)
                    trigger.new_condition.destroy_object(unit_object=enemy.reference_id)
                    trigger.new_condition.objects_in_area(quantity=5, object_list=UnitInfo.SPEARMAN.ID, source_player=PlayerId.ONE, area_x1=10, area_y1=20, area_x2=30, area_y2=30)
                    trigger.new_condition.accumulate_attribute(quantity=200, attribute=2, source_player=PlayerId.ONE)
                    trigger.new_condition.difficulty_level(quantity=3)  # 0=Easiest,1=Standard,2=Moderate,3=Hard,4=Hardest

                    # Create triggers - ONLY use these effects (exact parameter names!):
                    trigger.new_effect.display_instructions(display_time=10, message="Hello!")
                    trigger.new_effect.declare_victory(source_player=PlayerId.ONE, enabled=1)
                    trigger.new_effect.create_object(object_list_unit_id=UnitInfo.ARCHER.ID, source_player=PlayerId.ONE, location_x=50, location_y=50)
                    trigger.new_effect.kill_object(source_player=PlayerId.TWO, area_x1=0, area_y1=0, area_x2=100, area_y2=100)
                    trigger.new_effect.kill_object(object_list_unit_id=BuildingInfo.PALISADE_WALL.ID, source_player=PlayerId.TWO, area_x1=0, area_y1=0, area_x2=50, area_y2=50)
                    trigger.new_effect.change_ownership(source_player=PlayerId.TWO, target_player=PlayerId.ONE, area_x1=10, area_y1=10, area_x2=20, area_y2=20)
                    trigger.new_effect.research_technology(source_player=PlayerId.ONE, technology=TechInfo.FORGING.ID)

                    # Grant/set PLAYER RESOURCES (food/wood/stone/gold) - use modify_resource (verified against the installed parser):
                    trigger.new_effect.modify_resource(quantity=500, tribute_list=Attribute.GOLD_STORAGE, source_player=PlayerId.ONE, operation=Operation.ADD)   # +500 gold
                    trigger.new_effect.modify_resource(quantity=1000, tribute_list=Attribute.FOOD_STORAGE, source_player=PlayerId.ONE, operation=Operation.SET)  # set food to 1000
                    #   tribute_list must be: Attribute.FOOD_STORAGE / WOOD_STORAGE / STONE_STORAGE / GOLD_STORAGE
                    #   operation must be:    Operation.SET / ADD / SUBTRACT / MULTIPLY / DIVIDE
                    #   Attribute and Operation come from datasets.trigger_lists (already imported via `import *`).
                    #   There is NO ResourceId and NO Resource class; do NOT use modify_attribute(attribute=...) for player resources.

                    # WALLS AND GATES - AI must own gates to pass through them!
                    # Enemy AI base with walls - AI owns its own gate so units can exit
                    enemy_base_x, enemy_base_y = three_quarter, three_quarter
                    # Walls around enemy base (owned by enemy)
                    for i in range(10):
                        unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.STONE_WALL.ID, x=enemy_base_x-5+i, y=enemy_base_y-5)
                        unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.STONE_WALL.ID, x=enemy_base_x-5+i, y=enemy_base_y+5)
                    # Gate owned by AI player so their units can exit to attack
                    enemy_gate = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GATE_NORTH_TO_SOUTH.ID, x=enemy_base_x, y=enemy_base_y-5)

                    # Trigger to make AI units patrol out through their gate
                    attack_trigger = trigger_manager.add_trigger("AI Attack")
                    attack_trigger.new_condition.timer(timer=60)
                    attack_trigger.new_effect.patrol(
                        object_list_unit_id=UnitInfo.KNIGHT.ID,
                        source_player=PlayerId.TWO,
                        location_x=quarter,  # Patrol toward player base
                        location_y=quarter
                    )

                    # Trigger to "breach" gate (delete it) when player attacks
                    breach_trigger = trigger_manager.add_trigger("Gate Breached")
                    breach_trigger.new_condition.destroy_object(unit_object=enemy_gate.reference_id)
                    breach_trigger.new_effect.display_instructions(display_time=10, message="The gate has fallen!")

                    # Save scenario
                    scenario.write_to_file("output.aoe2scenario")
                    ```

                    ALWAYS use from_default() to create new scenarios:
                    - scenario = AoE2DEScenario.from_default()
                    - Do NOT use from_file() as template files may not exist

                    CRITICAL RULES:
                    - Do NOT use scenario_metadata - it doesn't exist
                    - Always use .ID when adding units (e.g., UnitInfo.MILITIA.ID)
                    - Use unit_manager.add_unit() for units AND buildings
                    - Use PlayerId.ONE, PlayerId.TWO, PlayerId.GAIA for players
                    - For trigger conditions/effects, ALWAYS use source_player (NOT player)
                    - Do NOT use these methods: own_fewer_objects, victory(), own_objects with player param
                    - PLAYER RESOURCES: grant/set with new_effect.modify_resource(quantity=, tribute_list=Attribute.*_STORAGE, source_player=, operation=Operation.*). Do NOT use modify_attribute for this, and do NOT reference ResourceId/Resource - they do not exist in this parser.
                    - VARIABLE NAMING - NEVER shadow Python builtins! These cause cryptic crashes:
                      * NEVER use these as variable names: range, map, list, type, id, set, dict, min, max, sum, filter, input, open, print, len, int, str, float, bool, object, round, zip, next, iter, hash, tuple, bytes, super, enumerate, reversed, sorted, abs, pow
                      * WRONG: range = unit_manager.add_unit(...)  # Overwrites Python's range() - crashes ALL subsequent for-loops!
                      * WRONG: map = map_manager  # Overwrites Python's map() function!
                      * RIGHT: archer_range_bld = unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.ARCHERY_RANGE.ID, ...)
                      * RIGHT: patrol_range = 20
                      * Use descriptive names: firing_range, attack_range, bow_range, archer_range_bld, mountain_range_start
                    - TYPE ERRORS CAUSE CRASHES - Never pass strings where integers/enums are expected:
                      * WRONG: source_player="PlayerId.ONE" or source_player="1"
                      * RIGHT: source_player=PlayerId.ONE
                      * WRONG: unit_const="UnitInfo.MILITIA.ID" or unit_const="74"
                      * RIGHT: unit_const=UnitInfo.MILITIA.ID
                      * WRONG: x="50", y="50"
                      * RIGHT: x=50, y=50 (integers, not strings!)
                      * All coordinates (x, y, area_x1, area_y1, etc.) must be integers
                      * All player references must be PlayerId enums, not strings
                    - UNIT POSITION ACCESS: Units returned by add_unit() have .x and .y directly
                      * RIGHT: unit.x, unit.y
                      * WRONG: unit.position.x, unit.position.y (Unit has NO .position attribute!)
                    - CRITICAL: All units AND terrain tiles must be within map boundaries (0 to map_size-1)
                      * ALWAYS get map_size first: map_size = map_manager.map_size
                      * For a 120x120 map, valid coordinates are 0-119
                      * For an 80x80 map, valid coordinates are 0-79
                      * NEVER use hardcoded values like range(0, 80) - use range(0, map_size) instead
                      * Use map_size-relative calculations: map_size // 4, map_size // 2, etc.
                      * Units/tiles placed outside boundaries cause ValueError crash!
                    - CRITICAL: No two objects can share the same coordinates!
                      * Every unit, building, and GAIA object MUST have unique (x, y) coordinates
                      * Buildings are larger than 1 tile - leave space around them (2-4 tiles depending on size)
                      * When placing multiple units, offset each one: x+0, x+1, x+2 or use loops with different positions
                      * WRONG: placing 5 archers all at (50, 50)
                      * RIGHT: placing archers at (50,50), (51,50), (52,50), (50,51), (51,51)
                      * Use loops with offsets: for i in range(5): add_unit(..., x=base_x+i, y=base_y)
                    - CRITICAL: Never place units on top of impassable terrain or GAIA objects!
                      * Do NOT place units on WATER_DEEP, WATER_MEDIUM terrain (they will drown/be stuck)
                      * Do NOT place units where you placed trees, cliffs, mountains, or rocks
                      * Do NOT place units on top of GOLD_MINE, STONE_MINE, or other resources
                      * Plan your map layout FIRST: define zones for water, terrain features, resources, THEN place units in clear areas
                      * Leave buffer space (2-3 tiles) between terrain features and unit spawn points
                      * Example layout order: 1) Paint water/terrain 2) Place cliffs/trees 3) Place resources 4) Place units in remaining clear land
                    - MANDATORY: Every scenario MUST include GAIA resources for all human players:
                      * GOLD_MINE: At least 2 clusters of 4-5 mines near each player start
                      * STONE_MINE: At least 1 cluster of 3-4 mines near each player start
                      * FORAGE_BUSH or FRUIT_BUSH: At least 6-8 bushes near each player start
                      * Huntables (DEER, WILD_BOAR) or herdables (SHEEP, GOAT): 4-8 animals
                      * If water exists: SHORE_FISH along coastlines

                    - MANDATORY: Military buildings based on scenario type (see template for specifics):
                      * BATTLE scenarios: Both sides need production buildings near their bases
                        - Player: BARRACKS, ARCHERY_RANGE, STABLE (1-2 each), BLACKSMITH
                        - Enemy: BARRACKS, ARCHERY_RANGE, STABLE, CASTLE or GUARD_TOWERs
                      * DEFENSE scenarios: Defender has full base, attackers spawn from edges
                        - Defender: TOWN_CENTER, CASTLE, BARRACKS, ARCHERY_RANGE, STABLE, BLACKSMITH, UNIVERSITY
                        - Walls: 20+ STONE_WALL or PALISADE_WALL segments with GATE
                        - Towers: 4-6 GUARD_TOWER or KEEP at strategic positions
                      * ESCORT scenarios: Minimal buildings, focus on journey
                        - Enemy camps: BARRACKS or ARCHERY_RANGE at ambush points
                        - Friendly camps: TOWN_CENTER or PAVILION clusters for recruitment
                      * DIPLOMACY scenarios: Each faction has a distinct camp
                        - Faction camps: PAVILION_A/B/C, YURT_A-H, or TENT_A-E based on culture
                        - Military: 1-2 production buildings (STABLE for nomads, BARRACKS for settled)
                        - Decorations: BONFIRE, TORCH_A, FLAG_B/D for camp atmosphere
                      * CONQUEST scenarios: Enemy has layered fortifications
                        - Outer defenses: PALISADE_WALL, WATCH_TOWER
                        - Inner fortress: STONE_WALL, FORTIFIED_WALL, GATE, GUARD_TOWER, KEEP
                        - Core: CASTLE, TOWN_CENTER
                      * Building placement: Leave 3-4 tiles between buildings, place production buildings near unit rally points

                    - CRITICAL: WALLS AND GATES FOR AI PLAYERS
                      AI players can ONLY pass through gates they own. Follow these rules:
                      * GATE OWNERSHIP: Always assign gates to the player whose units need to pass through
                        - WRONG: Player ONE owns gate, but Player TWO units need to exit their base
                        - RIGHT: Player TWO owns gate for their own base, Player ONE owns gates for player base
                      * AI BASE DESIGN: Enemy AI bases with walls MUST have gates owned by that AI player
                        - Example: If Player TWO has a walled base, Player TWO must own the GATE
                        - unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GATE_NORTH_TO_SOUTH.ID, x=50, y=50)
                      * GATE TRIGGERS: Use triggers to control gate access at specific times:
                        - Store gate reference: gate = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GATE_NORTH_TO_SOUTH.ID, ...)
                        - Delete gate to "breach" walls: trigger.new_effect.remove_object(object_list_unit_id=gate.reference_id, source_player=PlayerId.TWO)
                        - Change ownership to capture: trigger.new_effect.change_ownership(area_x1=..., source_player=PlayerId.TWO, target_player=PlayerId.ONE)
                      * PATROL THROUGH GATES: Use patrol/attack-move to make AI units path through their own gates
                        - trigger.new_effect.patrol(unit_object=unit.reference_id, source_player=PlayerId.TWO, location_x=target_x, location_y=target_y)
                      * WALL GAPS FOR SCRIPTED EXITS: For enemy AI that needs to attack:
                        - Option 1: Leave intentional gaps in walls (no gate needed)
                        - Option 2: AI-owned gates at exit points
                        - Option 3: Trigger to delete wall/gate section when attack begins
                      * COMMON MISTAKE: Surrounding enemy base entirely with player-owned walls/gates = AI trapped forever
                      * DEFENSE SCENARIOS: Defender (Player ONE) owns gates in their walls; attackers spawn OUTSIDE walls

                    TRIGGER DESIGN - TIMERS VS AREA TRIGGERS:
                    - AVOID timer conditions for main objectives and story progression
                    - Players move at their own pace - timer-based objectives feel artificial
                    - Use bring_object_to_area for location-based events (arrival, discovery, ambush)
                    - Use destroy_object for combat milestones (enemy defeated, gate breached)
                    - Use objects_in_area to detect unit presence in zones
                    - ONLY use timers for:
                      * Opening narration (first 5-10 seconds)
                      * Ambient/flavor dialogue that doesn't affect gameplay
                      * Historical time pressure when part of the actual narrative (siege countdown, dawn attack)
                      * Defense scenario wave spawns (these ARE time-based by design)

                    TRIGGER STRUCTURE - CRITICAL REQUIREMENT:
                    *** YOU MUST CREATE THE EXACT NUMBER OF TRIGGERS SPECIFIED IN THE TEMPLATE ***
                    - The template specifies MINIMUM trigger counts for each section - MEET OR EXCEED THEM
                    - Scenarios with insufficient triggers are INCOMPLETE and will be REJECTED
                    - Count your triggers before finishing - if below the minimum, ADD MORE

                    Follow the detailed trigger counts and patterns in the scenario template provided.
                    Key rules:
                    - Store unit references: hero = unit_manager.add_unit(...), then use hero.reference_id in triggers
                    - Victory: declare_victory(source_player=PlayerId.ONE, enabled=1) for player win
                    - Defeat: declare_victory(source_player=PlayerId.TWO, enabled=1) to make enemy win = player loses
                    - Dialogue colors: <BLUE> allies, <RED> enemies, <YELLOW> narrator
                    - Naming: "[D0] Intro", "[D1] Scout", "[Obj] Objective 1", "VC", "Defeat"
                    - CREATE EVERY TRIGGER LISTED IN THE TEMPLATE - do not skip any

                    COMMON MISTAKES TO AVOID:
                    - KING and QUEEN are in UnitInfo, NOT HeroInfo! Use UnitInfo.KING.ID
                    - difficulty_level only takes: quantity (0-4) and inverted (0/1). NO "compare" parameter!
                    - Use object_list_unit_id for effects, object_list for conditions
                    - All heroes use HeroInfo except: KING, QUEEN (UnitInfo), KHAN (both exist - use HeroInfo.KHAN for Genghis)

                    ESSENTIAL DATASETS - ONLY use names listed here! Inventing unit names causes AttributeError crashes:
                    UnitInfo: MILITIA, MAN_AT_ARMS, SPEARMAN, PIKEMAN, ARCHER, CROSSBOWMAN, SKIRMISHER,
                              KNIGHT, CAVALIER, SCOUT_CAVALRY, LIGHT_CAVALRY, CAVALRY_ARCHER, CAMEL_RIDER,
                              CHAMPION, BERSERK, SAMURAI, IMMORTAL_MELEE, IMMORTAL_RANGED, WAR_ELEPHANT,
                              BATTERING_RAM, MANGONEL, ONAGER, TREBUCHET, SCORPION, BOMBARD_CANNON,
                              VILLAGER_MALE, VILLAGER_FEMALE, SHEEP, DEER, WILD_BOAR, KING, QUEEN
                    *** WARNING: UnitInfo.IMMORTAL does NOT exist! Use UnitInfo.IMMORTAL_MELEE or UnitInfo.IMMORTAL_RANGED ***
                    *** WARNING: Do NOT invent unit names. If a unit is not listed above, it will crash! ***
                    BuildingInfo: TOWN_CENTER, BARRACKS, ARCHERY_RANGE, STABLE, CASTLE, SIEGE_WORKSHOP,
                                  HOUSE, MILL, MARKET, BLACKSMITH, MONASTERY, UNIVERSITY,
                                  PALISADE_WALL, STONE_WALL, GATE_NORTH_TO_SOUTH, GUARD_TOWER, KEEP
                    HeroInfo: JOAN_OF_ARC, WILLIAM_THE_CONQUEROR, SALADIN, GENGHIS_KHAN, RICHARD_THE_LIONHEART,
                              EL_CID, FREDERICK_BARBAROSSA, ATTILA_THE_HUN, ALEXANDER, LEONIDAS, DARIUS
                    OtherInfo: GOLD_MINE, STONE_MINE, FORAGE_BUSH, TREE_OAK, TREE_PALM_FOREST,
                               CLIFF_DEFAULT_2, CLIFF_DEFAULT_3, ROCK_FORMATION_1, FLAG_A, FLAG_B,
                               ROMAN_RUINS, CASTLE_RUINS, TEMPLE_RUIN, SKELETON, TORCH_A, BONFIRE
                    TerrainId: WATER_DEEP, WATER_SHALLOW, BEACH, GRASS_1, GRASS_2, DIRT_1,
                               DESERT_SAND, ROAD, FOREST_OAK (use .value property)""" + (REACHABILITY_ANALYSIS_BLOCK if reachability_prompting else "") + """

                    Return ONLY the Python code, no explanations or markdown formatting."""
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=payload,
                timeout=api_config.REQUEST_TIMEOUT
            )
            response.raise_for_status()
            
            result = response.json()
            generated_code = result["choices"][0]["message"]["content"]
            
            # Clean up the response to extract only Python code
            if "```python" in generated_code:
                start = generated_code.find("```python") + 9
                end = generated_code.find("```", start)
                generated_code = generated_code[start:end].strip()
            elif "```" in generated_code:
                start = generated_code.find("```") + 3
                end = generated_code.find("```", start)
                generated_code = generated_code[start:end].strip()
            
            return generated_code
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            raise
        except KeyError as e:
            logger.error(f"Unexpected API response format: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise

    def repair_scenario_code(self, failing_code: str, error_detail: str,
                             model: str = None, temperature: float = None,
                             max_tokens: int = None,
                             reachability_prompting: bool = True) -> str:
        """Ask the model to fix code that failed validation or execution.

        Sends the failing program plus the captured stderr / validation detail
        back to the model and returns a corrected full program. Uses the same
        model/temperature/max_tokens so the repaired attempt is comparable to
        the original.
        """
        model = api_config.resolve_model(model)
        if temperature is None:
            temperature = api_config.DEFAULT_TEMPERATURE
        if max_tokens is None:
            max_tokens = api_config.DEFAULT_MAX_TOKENS

        repair_system = (
            "You are fixing a Python program that uses the AoE2ScenarioParser "
            "library to build an Age of Empires 2 scenario. The program failed. "
            "Return the COMPLETE corrected program and nothing else - no prose, "
            "no markdown fences.\n"
            "Hard rules you must keep:\n"
            "- Start with the exact sys.stdout/sys.stderr UTF-8 wrapper header and "
            "the AoE2ScenarioParser imports.\n"
            "- Use AoE2DEScenario.from_default(); keep scenario.write_to_file(...) at the end.\n"
            "- Use .ID on unit/building/hero constants; PlayerId enums (not strings); "
            "integer coordinates within 0..map_size-1; source_player (not player).\n"
            "- Do NOT invent unit/building names; do NOT shadow Python builtins "
            "(range, map, list, id, ...).\n"
            "- Preserve the existing scenario design: keep the same triggers, units, "
            "objectives and victory/defeat conditions. Change ONLY what is needed to "
            "fix the error."
        )
        if reachability_prompting:
            repair_system += "\n" + REACHABILITY_ANALYSIS_BLOCK

        user_msg = (
            "The following AoE2 scenario program failed.\n\n"
            "=== ERROR / FAILURE DETAIL ===\n"
            f"{error_detail}\n\n"
            "=== FAILING PROGRAM ===\n"
            f"{failing_code}\n\n"
            "Return the complete corrected program only."
        )

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": repair_system},
                {"role": "user", "content": user_msg},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=self.headers,
            json=payload,
            timeout=api_config.REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        result = response.json()
        generated_code = result["choices"][0]["message"]["content"]
        return _extract_python_code(generated_code)


class ScenarioGenerator:
    """Main class for generating AoE2 scenarios using AI"""
    
    def __init__(self, api_key: str):
        self.api = OpenRouterAPI(api_key)
        self.scenario_templates = self._load_templates()
    
    def _load_templates(self) -> Dict[str, str]:
        """Load scenario generation templates based on real AoE2 campaign patterns"""
        return {
            "battle": """Create an Age of Empires 2 BATTLE scenario based on Saladin Campaign (cam3) patterns:
            - Title: {title}
            - Description: {description}
            - Map size: {map_size}x{map_size}
            - Players: {players}
            - Difficulty: {difficulty}

            ===== MANDATORY TRIGGER REQUIREMENTS =====
            YOU MUST CREATE EXACTLY 25-30 TRIGGERS. This is NON-NEGOTIABLE.
            Scenarios with fewer than 25 triggers are INCOMPLETE and UNACCEPTABLE.

            Count your triggers as you create them. Do not stop until you have at least 25.

            REQUIRED TRIGGER BREAKDOWN (minimum counts - you MUST meet or exceed these):
            - Setup triggers: 4-5 MINIMUM (Techs, Walls, Easy Difficulty, Hardmode, Close Gates)
            - Dialogue triggers: 10-12 MINIMUM using "[D#] Name" pattern (numbered [D0] through [D11])
            - Objective triggers: 3-4 MINIMUM using "[Obj] Name" or "[O] Name" pattern
            - Victory/Defeat triggers: 3-4 MINIMUM (VC, VC2, Defeat, DEFEAT)
            - Special triggers: 2-3 MINIMUM (Resign player, unit behavior, reinforcements)
            ==========================================

            TRIGGER STRUCTURE (from Saladin cam3 - 28 triggers) - CREATE ALL OF THESE:
            1. --- Setup Section (CREATE ALL 5 triggers) ---
               YOU MUST CREATE ALL OF THESE SETUP TRIGGERS:
               - "Techs": timer(1), research_technology for 2-3 starting techs (FORGING, SCALE_MAIL, etc.)
               - "Walls": timer(1), setup initial wall/gate states
               - "Easy Difficulty": condition=difficulty_level(quantity=0), kill_object to reduce enemies
               - "Hardmode": condition=difficulty_level(quantity=3), create_object to spawn extra enemies
               - "Close Gates": timer(1), task_object to close all gates at scenario start

            2. --- Dialogue Section (CREATE ALL 12 triggers with "[D#]" prefix) ---
               YOU MUST CREATE ALL OF THESE DIALOGUE TRIGGERS:
               - "[D0] Intro": timer(5), opening narration - "<YELLOW>Narrator: [Set the scene]"
               - "[D1] Scout Report": timer(15), scout provides intel - "<BLUE>Scout: [Enemy positions]"
               - "[D2] Commander Speech": timer(30), ally commander speaks - "<BLUE>Commander: [Battle plan]"
               - "[D3] Enemy Taunt 1": timer(60), enemy leader boasts - "<RED>Enemy: [Taunt message]"
               - "[D4] Enemy Taunt 2": timer(120), second enemy taunt - "<RED>Enemy: [Second taunt]"
               - "[D5] At Location 1": bring_object_to_area, reach first key position
               - "[D6] At Location 2": bring_object_to_area, reach second key position
               - "[D7] Battle Begins": timer(180), major combat starts - "<YELLOW>Narrator: [Battle description]"
               - "[D8] Midpoint Update": timer(300), battle progress update
               - "[D9] Enemy Weakening": objects_in_area (enemy count low), enemy morale breaks
               - "[D10] Final Push": timer(420), climactic moment dialogue
               - "[D11] Hero Falls": destroy_object on hero, death message before defeat trigger

            3. --- Objective Section (CREATE ALL 4 triggers with "[Obj]" prefix) ---
               YOU MUST CREATE ALL OF THESE OBJECTIVE TRIGGERS:
               - "[O] Main Objectives": timer(1), display ALL objectives at start
               - "[Obj] Primary Goal": main victory condition tracking
               - "[Obj] Secondary Goal": optional/bonus objective
               - "[Obj] Survival": hero must survive notification

            4. --- Victory/Defeat Section (CREATE ALL 4 triggers) ---
               YOU MUST CREATE ALL OF THESE VICTORY/DEFEAT TRIGGERS:
               - "VC": destroy enemy leader/castle, declare_victory(source_player=PlayerId.ONE, enabled=1)
               - "VC2": alternative victory (e.g., timer survival), declare_victory player 1
               - "Defeat": hero dies, declare_victory(source_player=PlayerId.TWO, enabled=1)
               - "DEFEAT": all key buildings lost, backup defeat trigger

            PLAYER SETUP AND BUILDINGS:

            Player ONE (Human):
            Store hero reference!
            - hero = unit_manager.add_unit(PlayerId.ONE, unit_const=HeroInfo.XXX.ID, ...)
            - 15-25 military units in formation
            - Base buildings: TOWN_CENTER, 2-3 HOUSE, MILL, BLACKSMITH
            - Military production: BARRACKS, ARCHERY_RANGE, STABLE (1-2 each)
            - Place buildings in a cluster with 3-4 tile spacing
            - If player has walls: Player ONE owns their own gates

            Player TWO+ (Enemy AI):
            Store enemy leader reference!
            - enemy_leader = unit_manager.add_unit(PlayerId.TWO, unit_const=HeroInfo.XXX.ID, ...)
            - 30-50 military units in defensive positions
            - Fortifications: CASTLE or 4-6 GUARD_TOWER/KEEP
            - Walls: 15-30 STONE_WALL segments with 1-2 GATE
            - Production: BARRACKS, ARCHERY_RANGE, STABLE behind walls
            - Support: TOWN_CENTER, BLACKSMITH, MONASTERY

            CRITICAL - ENEMY GATE OWNERSHIP:
            - ALL gates in enemy base owned by ENEMY (PlayerId.TWO)
            - enemy_gate = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GATE_NORTH_TO_SOUTH.ID, ...)
            - This allows enemy to patrol/sortie through their own gates
            - Player must destroy gates to breach enemy base

            GAIA:
            - 500+ trees forming forests/boundaries
            - Resources near player start
            - Decorations: ROMAN_RUINS, SKELETON, FLAG_A for atmosphere

            UNIT PLACEMENT:
            - Military units in formation groups (infantry front, archers behind)
            - Guard towers protecting key positions (corners, gates, hills)
            - Walls and gates around enemy bases (enemy-owned!)
            - Hero unit with 3-5 bodyguard units

            AI BEHAVIOR TRIGGERS:
            - "Enemy Patrol": timer(1), task_object for enemy patrols THROUGH THEIR GATES
            - "Enemy Sortie": objects_in_area (player near base), task enemy units to attack
            - "Gate Defense": enemy archers/towers positioned to defend gate approaches

            HISTORICAL BATTLEFIELD CONSTRUCTION (CRITICAL - build the location FIRST):
            Step 1: Define the battlefield geography using map_size-relative zones
               map_size = map_manager.map_size
               # Divide map into logical zones based on historical layout

            Step 2: Paint terrain to match historical geography
               - Rivers/water: WATER_DEEP, WATER_SHALLOW with BEACH transitions
               - Hills/ridges: Use elevation via CLIFF objects in lines
               - Forests: Dense TREE placement (100-300 trees) to block movement
               - Roads: ROAD terrain connecting key positions
               - Open fields: GRASS_1, GRASS_2 for battle areas

            Step 3: Add GAIA objects to define the battlefield
               - CLIFF_DEFAULT_2/3: Create ridges, hills, impassable terrain
               - ROCK_FORMATION_1/2: Rocky outcrops, defensive positions
               - Trees (TREE_OAK, TREE_A-F): Forest boundaries, flanking protection
               - Decorations: FLAGS for objectives, ROMAN_RUINS for atmosphere

            EXAMPLE - Battle of Hastings (1066):
               # Senlac Hill where Saxons defended
               hill_y = map_size // 3  # Hill in upper third
               # Create ridge with cliffs
               for x in range(quarter, three_quarter):
                   unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.CLIFF_DEFAULT_2.ID, x=x, y=hill_y)
               # Saxon shield wall position ON the hill
               for i in range(15):
                   unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.MAN_AT_ARMS.ID, x=center-7+i, y=hill_y-3)
               # Norman starting position at bottom (open field)
               norman_y = three_quarter
               # Forests on flanks to prevent encirclement
               for x in range(0, quarter):
                   for y in range(hill_y-10, hill_y+10):
                       unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.TREE_OAK.ID, x=x, y=y)

            EXAMPLE - Thermopylae (480 BC):
               # Sea on right side (east)
               for x in range(three_quarter, map_size):
                   for y in range(0, map_size):
                       tile = map_manager.get_tile(x=x, y=y)
                       tile.terrain_id = TerrainId.WATER_DEEP.value
               # Mountains on left (west) - dense cliffs
               for x in range(0, quarter):
                   for y in range(0, map_size):
                       unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.CLIFF_DEFAULT_3.ID, x=x, y=y)
               # Narrow pass in middle (the Hot Gates) - only 8-10 tiles wide
               pass_width = 10
               pass_x_start = quarter
               pass_x_end = three_quarter
               # Greeks defend the narrowest point

            EXAMPLE - River Crossing Battle:
               # River running north-south through center
               river_x = center
               for y in range(0, map_size):
                   for dx in range(-2, 3):  # 5-tile wide river
                       tile = map_manager.get_tile(x=river_x+dx, y=y)
                       tile.terrain_id = TerrainId.WATER_SHALLOW.value
               # Ford/bridge at specific point
               bridge_y = center
               # Place BRIDGE objects or shallow crossing

            MANDATORY RESOURCES AND BOUNDARIES:
            - Place GAIA resources (gold, stone, forage, huntables) near player starting positions
            - ALWAYS get map_size = map_manager.map_size FIRST
            - All coordinates must be within 0 to map_size-1
            - Build terrain BEFORE placing units (so units aren't on water/cliffs)

            ===== FINAL TRIGGER CHECKLIST - VERIFY BEFORE FINISHING =====
            Count your triggers. You MUST have created AT LEAST:
            [ ] 5 Setup triggers (Techs, Walls, Easy Difficulty, Hardmode, Close Gates)
            [ ] 12 Dialogue triggers ([D0] through [D11])
            [ ] 4 Objective triggers ([O] Main, [Obj] Primary, Secondary, Survival)
            [ ] 4 Victory/Defeat triggers (VC, VC2, Defeat, DEFEAT)
            ---------------------------------------------------------
            TOTAL: 25 triggers MINIMUM. If you have fewer, GO BACK AND ADD MORE.
            ==============================================================""",

            "escort": """ESCORT SCENARIO - CREATE EXACTLY 17 TRIGGERS
Title: {title} | Description: {description} | Map: {map_size}x{map_size} | Players: {players}

=== COORDINATES ===
map_size = map_manager.map_size
start_x, start_y = 20, map_size//2
mid_x, mid_y = map_size//2, map_size//2
enemy_camp_x, enemy_camp_y = map_size*2//3, map_size//2
dest_x, dest_y = map_size-15, map_size//2
pursuit_spawn_x = 10

=== CREATE THESE 18 TRIGGERS ===

# SETUP (3 triggers)
1. "Init" - timer(1), display opening narrative and objectives
2. "Easy Mode" - difficulty_level(0), kill_object removes some enemies
3. "Hard Mode" - difficulty_level(3), create extra enemy units at enemy_camp

# PURSUIT (3 triggers) - Creates urgency via timed cavalry spawns
4. "Pursuit Wave 1" - timer(120), spawn 4 LIGHT_CAVALRY at pursuit_spawn, task_object toward mid_x
5. "Pursuit Wave 2" - timer(240), spawn 6 LIGHT_CAVALRY at pursuit_spawn, task toward enemy_camp
6. "Pursuit Arrives" - bring_object_to_area(hero near mid_x), display "The pursuit draws near!"

# JOURNEY (5 triggers) - Key story beats using bring_object_to_area
7. "[D1] Departure" - bring_object_to_area(hero leaves start+15), display "We must reach [destination] before nightfall."
8. "[D2] Midpoint" - bring_object_to_area(hero at mid_x), display "Halfway there. Stay vigilant."
9. "[D3] Enemy Territory" - bring_object_to_area(hero near enemy_camp), display "Enemy camp ahead! Fight through or find another way."
10. "[D4] Approaching Goal" - bring_object_to_area(hero at dest-20), display "Almost there! The [destination] is in sight!"
11. "[D5] Ambush" - bring_object_to_area(hero at enemy_camp+10), spawn ambush enemies, task attack

# RECRUITMENT (2 triggers) - Must earn allies
12. "Find Allies" - bring_object_to_area(hero at allied_camp), display "Warriors: Defeat the raider chief and we join you."
13. "Allies Join" - destroy_object(raider_chief), change_ownership allied units to player

# VICTORY/DEFEAT (4 triggers)
14. "Victory" - bring_object_to_area(hero at dest), display victory, declare_victory(PlayerId.ONE)
15. "Defeat Hero" - destroy_object(hero), display defeat message, declare_victory(PlayerId.TWO)
16. "Companion Falls" - destroy_object(companion), display mourning message (no defeat)
17. "Gate Breached" - destroy_object(enemy_gate), display "The way is open!"

=== COMPLETE CODE EXAMPLE ===

```python
scenario = AoE2DEScenario.from_default()
unit_manager = scenario.unit_manager
trigger_manager = scenario.trigger_manager
map_manager = scenario.map_manager

map_size = map_manager.map_size
start_x, start_y = 20, map_size//2
mid_x, mid_y = map_size//2, map_size//2
enemy_camp_x, enemy_camp_y = map_size*2//3, map_size//2
allied_camp_x, allied_camp_y = map_size//2 - 10, map_size//2 + 20
dest_x, dest_y = map_size-15, map_size//2
pursuit_spawn_x = 10

# === UNITS ===
# Player ONE - Escort party
hero = unit_manager.add_unit(PlayerId.ONE, unit_const=HeroInfo.JOAN_OF_ARC.ID, x=start_x, y=start_y)
companion = unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.CAVALIER.ID, x=start_x+2, y=start_y)
for i in range(5):
    unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.KNIGHT.ID, x=start_x+i, y=start_y+3)
    unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.CROSSBOWMAN.ID, x=start_x+i, y=start_y+5)

# Player TWO - Enemy
enemy_gate = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GATE_SOUTHWEST_TO_NORTHEAST.ID, x=enemy_camp_x, y=enemy_camp_y)
for i in range(8):
    unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.PALISADE_WALL.ID, x=enemy_camp_x-4+i, y=enemy_camp_y-3)
    unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.CROSSBOWMAN.ID, x=enemy_camp_x-2+i//2, y=enemy_camp_y+2)
unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.WATCH_TOWER.ID, x=enemy_camp_x-5, y=enemy_camp_y)

# Player THREE - Raiders (enemy of player, has chief to kill for recruitment)
raider_chief = unit_manager.add_unit(PlayerId.THREE, unit_const=UnitInfo.BERSERK.ID, x=allied_camp_x+15, y=allied_camp_y)
for i in range(5):
    unit_manager.add_unit(PlayerId.THREE, unit_const=UnitInfo.MILITIA.ID, x=allied_camp_x+14+i, y=allied_camp_y+1)

# Player FOUR - Potential allies (join after killing raider chief)
for i in range(6):
    unit_manager.add_unit(PlayerId.FOUR, unit_const=UnitInfo.PIKEMAN.ID, x=allied_camp_x+i, y=allied_camp_y)

# GAIA resources
for i in range(4):
    unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.GOLD_MINE.ID, x=start_x+10+i, y=start_y+10)

# === TRIGGERS ===

# 1. Init
t = trigger_manager.add_trigger("Init")
t.new_condition.timer(timer=1)
t.new_effect.display_instructions(source_player=PlayerId.ONE, display_time=15,
    message="<YELLOW>Escort the hero safely to the destination. Beware - enemy cavalry pursue you!")

# 2. Easy Mode
t = trigger_manager.add_trigger("Easy Mode")
t.new_condition.difficulty_level(quantity=0)
t.new_effect.kill_object(object_list_unit_id=UnitInfo.CROSSBOWMAN.ID, source_player=PlayerId.TWO,
    area_x1=enemy_camp_x-10, area_y1=enemy_camp_y-10, area_x2=enemy_camp_x+10, area_y2=enemy_camp_y+10)

# 3. Hard Mode
t = trigger_manager.add_trigger("Hard Mode")
t.new_condition.difficulty_level(quantity=3)
for i in range(3):
    t.new_effect.create_object(object_list_unit_id=UnitInfo.KNIGHT.ID, source_player=PlayerId.TWO,
        location_x=enemy_camp_x+i, location_y=enemy_camp_y+5)

# 4. Pursuit Wave 1
t = trigger_manager.add_trigger("Pursuit Wave 1")
t.new_condition.timer(timer=120)
for i in range(4):
    t.new_effect.create_object(object_list_unit_id=UnitInfo.LIGHT_CAVALRY.ID, source_player=PlayerId.TWO,
        location_x=pursuit_spawn_x+i, location_y=start_y)
t.new_effect.task_object(object_list_unit_id=UnitInfo.LIGHT_CAVALRY.ID, source_player=PlayerId.TWO,
    location_x=mid_x, location_y=mid_y)

# 5. Pursuit Wave 2
t = trigger_manager.add_trigger("Pursuit Wave 2")
t.new_condition.timer(timer=240)
for i in range(6):
    t.new_effect.create_object(object_list_unit_id=UnitInfo.LIGHT_CAVALRY.ID, source_player=PlayerId.TWO,
        location_x=pursuit_spawn_x+i, location_y=start_y)

# 6. Pursuit Arrives
t = trigger_manager.add_trigger("Pursuit Arrives")
t.new_condition.bring_object_to_area(unit_object=hero.reference_id,
    area_x1=mid_x-10, area_y1=mid_y-10, area_x2=mid_x+10, area_y2=mid_y+10)
t.new_effect.display_instructions(source_player=PlayerId.ONE, display_time=8,
    message="<RED>The pursuit draws near! Keep moving!")

# 7. [D1] Departure
t = trigger_manager.add_trigger("[D1] Departure")
t.new_condition.bring_object_to_area(unit_object=hero.reference_id,
    area_x1=start_x+10, area_y1=start_y-15, area_x2=start_x+25, area_y2=start_y+15)
t.new_effect.display_instructions(source_player=PlayerId.ONE, display_time=10,
    message="<BLUE>Companion: We must reach safety before the enemy catches us.")

# 8. [D2] Midpoint
t = trigger_manager.add_trigger("[D2] Midpoint")
t.new_condition.bring_object_to_area(unit_object=hero.reference_id,
    area_x1=mid_x-5, area_y1=mid_y-10, area_x2=mid_x+5, area_y2=mid_y+10)
t.new_effect.display_instructions(source_player=PlayerId.ONE, display_time=10,
    message="<YELLOW>Halfway there. Stay vigilant - enemies lurk ahead.")

# 9. [D3] Enemy Territory
t = trigger_manager.add_trigger("[D3] Enemy Territory")
t.new_condition.bring_object_to_area(unit_object=hero.reference_id,
    area_x1=enemy_camp_x-15, area_y1=enemy_camp_y-15, area_x2=enemy_camp_x, area_y2=enemy_camp_y+15)
t.new_effect.display_instructions(source_player=PlayerId.ONE, display_time=10,
    message="<RED>Enemy camp ahead! We must fight through their defenses.")

# 10. [D4] Approaching Goal
t = trigger_manager.add_trigger("[D4] Approaching Goal")
t.new_condition.bring_object_to_area(unit_object=hero.reference_id,
    area_x1=dest_x-25, area_y1=dest_y-15, area_x2=dest_x-10, area_y2=dest_y+15)
t.new_effect.display_instructions(source_player=PlayerId.ONE, display_time=10,
    message="<GREEN>Almost there! The destination is in sight!")

# 11. [D5] Ambush
t = trigger_manager.add_trigger("[D5] Ambush")
t.new_condition.bring_object_to_area(unit_object=hero.reference_id,
    area_x1=enemy_camp_x+5, area_y1=enemy_camp_y-10, area_x2=enemy_camp_x+20, area_y2=enemy_camp_y+10)
for i in range(4):
    t.new_effect.create_object(object_list_unit_id=UnitInfo.PIKEMAN.ID, source_player=PlayerId.TWO,
        location_x=enemy_camp_x+15, location_y=enemy_camp_y-3+i)
t.new_effect.display_instructions(source_player=PlayerId.ONE, display_time=8,
    message="<RED>Ambush! They were waiting for us!")

# 12. Find Allies
t = trigger_manager.add_trigger("Find Allies")
t.new_condition.bring_object_to_area(unit_object=hero.reference_id,
    area_x1=allied_camp_x-5, area_y1=allied_camp_y-5, area_x2=allied_camp_x+10, area_y2=allied_camp_y+5)
t.new_effect.display_instructions(source_player=PlayerId.ONE, display_time=12,
    message="<CYAN>Warriors: Raiders plague our village. Kill their chief and we will join your cause.")

# 13. Allies Join
t = trigger_manager.add_trigger("Allies Join")
t.new_condition.destroy_object(unit_object=raider_chief.reference_id)
t.new_effect.display_instructions(source_player=PlayerId.ONE, display_time=10,
    message="<CYAN>Warriors: The chief is dead! We ride with you now.")
t.new_effect.change_ownership(source_player=PlayerId.FOUR, target_player=PlayerId.ONE,
    area_x1=allied_camp_x-5, area_y1=allied_camp_y-5, area_x2=allied_camp_x+15, area_y2=allied_camp_y+10)

# 14. Victory
t = trigger_manager.add_trigger("Victory")
t.new_condition.bring_object_to_area(unit_object=hero.reference_id,
    area_x1=dest_x-5, area_y1=dest_y-10, area_x2=dest_x+5, area_y2=dest_y+10)
t.new_effect.display_instructions(source_player=PlayerId.ONE, display_time=15,
    message="<GREEN>Victory! The hero has reached safety!")
t.new_effect.declare_victory(source_player=PlayerId.ONE, enabled=1)

# 15. Defeat Hero
t = trigger_manager.add_trigger("Defeat Hero")
t.new_condition.destroy_object(unit_object=hero.reference_id)
t.new_effect.display_instructions(source_player=PlayerId.ONE, display_time=10,
    message="<RED>The hero has fallen. All is lost.")
t.new_effect.declare_victory(source_player=PlayerId.TWO, enabled=1)

# 16. Defeat Army (optional - hero death is main defeat, this is backup)
# Skip this trigger - checking all military units is complex
# The hero death trigger (15) handles the main defeat condition

# 16. Companion Falls
t = trigger_manager.add_trigger("Companion Falls")
t.new_condition.destroy_object(unit_object=companion.reference_id)
t.new_effect.display_instructions(source_player=PlayerId.ONE, display_time=10,
    message="<ORANGE>Your companion has fallen! Honor their sacrifice - press on!")

# 17. Gate Breached
t = trigger_manager.add_trigger("Gate Breached")
t.new_condition.destroy_object(unit_object=enemy_gate.reference_id)
t.new_effect.display_instructions(source_player=PlayerId.ONE, display_time=8,
    message="<GREEN>The gate is down! Push through!")

scenario.write_to_file("OUTPUT_SCENARIO.aoe2scenario")  # Replace with actual output path
```

=== KEY DESIGN ELEMENTS ===
1. PURSUIT creates urgency (timer-spawned cavalry chasing from behind)
2. EARNED RECRUITMENT (kill raider chief to get allies)
3. JOURNEY BEATS (5 location-triggered story moments)
4. CLEAR VICTORY/DEFEAT (hero reaches destination or dies)

=== RULES ===
- Store hero, companion, enemy_gate, raider_chief references at creation
- Use bring_object_to_area for location triggers, NOT timers
- Enemy gates owned by PlayerId.TWO
- Spawn multiple units with loops, not quantity parameter""",

            "diplomacy": """Create an Age of Empires 2 DIPLOMACY scenario based on Genghis Khan Campaign (cam4) patterns:
            - Title: {title}
            - Description: {description}
            - Map size: {map_size}x{map_size}
            - Players: {players} (recommend 6-8 for diplomacy)
            - Difficulty: {difficulty}

            ===== MANDATORY TRIGGER REQUIREMENTS =====
            YOU MUST CREATE EXACTLY 50-65 TRIGGERS. This is NON-NEGOTIABLE.

            REQUIRED TRIGGER BREAKDOWN (minimum counts):
            - Setup triggers: 5-6 (Techs, diplomacy, difficulty, AI behavior)
            - Faction Request triggers: 5-8 (one per neutral faction)
            - Faction Joins triggers: 5-8 (completion triggers per faction)
            - Story Dialogue triggers: 10-12 using "[D#] Name" pattern
            - Victory/Defeat triggers: 5-6 (tiered victory, defeat conditions)
            - Utility triggers: 8-10 (loops, patrols, faction death checks)
            ==========================================

            TRIGGER STRUCTURE (CREATE ALL OF THESE):

            1. --- Setup Section (CREATE ALL 6 triggers) ---
               - "Techs": timer(1), research_technology for starting techs
               - "Set Diplomacy": timer(1), set initial diplomatic stances
                 All neutral factions start NEUTRAL to player (not allied, not enemy)
               - "Easy Difficulty": difficulty_level(quantity=0), reduce main enemy forces
               - "Hard Difficulty": difficulty_level(quantity=3), add extra enemy patrols
               - "Enemy Patrols": timer(1), task_object to start enemy (Player TWO) patrols
                 IMPORTANT: Enemy patrols through THEIR OWN gates
               - "Faction AI Setup": timer(1), set neutral faction unit stances to defensive

            2. --- Faction Request Section (CREATE ONE PER FACTION - 5-8 triggers) ---
               Each neutral faction presents their quest when hero visits their camp.
               ALL requests use bring_object_to_area - player visits camp to receive quest.

               Store hero reference: hero = unit_manager.add_unit(PlayerId.ONE, unit_const=HeroInfo.XXX.ID, ...)

               - "[D1] Faction 3 Request": bring_object_to_area (hero enters Faction 3 camp)
                 "<CYAN>Faction 3 Leader: Greetings, traveler. We need [TRIBUTE TYPE]."
                 Quest types: tribute (food/gold), combat (defeat enemy), fetch (kill beast)

               - "[D1] Faction 4 Request": bring_object_to_area (hero enters Faction 4 camp)
                 "<PURPLE>Faction 4 Leader: Prove your worth by defeating the [enemy]."

               - "[D1] Faction 5 Request": bring_object_to_area (hero enters Faction 5 camp)
                 "<GREEN>Faction 5 Leader: We require [resource] to survive the winter."

               - "[D1] Faction 6 Request": bring_object_to_area (hero enters Faction 6 camp)
                 "<ORANGE>Faction 6 Leader: A great beast terrorizes our lands..."

               - "[D1] Faction 7 Request": bring_object_to_area (hero enters Faction 7 camp)
                 "<GREY>Faction 7 Leader: Our enemies must be destroyed before we join you."

               Quest Type Examples:
               - TRIBUTE: "Bring us 500 food/gold" - accumulate_attribute condition
               - COMBAT: "Defeat the [enemy faction]" - destroy_object on enemy leader
               - FETCH: "Kill the great wolf/boar" - destroy_object on GAIA beast

            3. --- Faction Joins Section (CREATE ONE PER FACTION - 5-8 triggers) ---
               Each faction joins when their quest is complete.

               - "[Obj] Faction 3 Joins": condition based on quest type
                 Tribute: accumulate_attribute(quantity=500, attribute=0, source_player=PlayerId.ONE)
                 Effects:
                   1. display_instructions: "<CYAN>Faction 3: You have honored your word. We join you!"
                   2. change_ownership: transfer faction units to player
                      change_ownership(source_player=PlayerId.THREE, target_player=PlayerId.ONE, area_x1=..., area_y1=..., area_x2=..., area_y2=...)
                   3. change_diplomacy (optional): set faction to ally

               - "[Obj] Faction 4 Joins": destroy_object (enemy leader killed)
                 Effects: display message, change_ownership of faction units

               - "[Obj] Faction 5 Joins": accumulate_attribute (gold tribute)
                 Effects: display message, change_ownership of faction units

               - "[Obj] Faction 6 Joins": destroy_object (beast killed)
                 Store beast: beast = unit_manager.add_unit(PlayerId.GAIA, unit_const=UnitInfo.WILD_BOAR.ID, ...)
                 Condition: destroy_object(unit_object=beast.reference_id)
                 Effects: display message, change_ownership

               - "[Obj] Faction 7 Joins": destroy_object (enemy defeated)
                 Effects: display message, change_ownership

            4. --- Story Dialogue Section (CREATE ALL 12 triggers) ---
               Opening and story progression:
               - "[D0] Intro": timer(5), narrator sets scene
                 "<YELLOW>Narrator: The land is divided among many tribes..."
               - "[D1] Hero Speaks": timer(15), hero's goal stated
                 "<BLUE>Hero: I will unite these peoples under one banner."
               - "[D2] Advisor Counsel": timer(30), companion advice
                 "<BLUE>Advisor: Visit each tribe's camp to learn their needs."

               Faction-specific dialogue (triggered by bring_object_to_area):
               - "[D3] Approach Enemy": bring_object_to_area (near enemy base)
                 "<RED>Enemy Lord: You dare approach my domain?"
               - "[D4] Enemy Taunt": timer(120), enemy provocation
                 "<RED>Enemy Lord: The tribes will never follow a weakling like you!"

               Progress updates:
               - "[D5] First Faction Joined": triggered after first join trigger
                 "<YELLOW>Narrator: Word spreads of your growing alliance..."
               - "[D6] Halfway Point": triggered after 2-3 factions join
                 "<BLUE>Advisor: Our strength grows. Continue gathering allies."
               - "[D7] Enemy Worried": triggered after 3+ factions
                 "<RED>Enemy Lord: This alliance must be stopped!"

               Late game:
               - "[D8] Final Faction": bring_object_to_area (last faction camp)
               - "[D9] Alliance Complete": all factions joined
                 "<YELLOW>Narrator: The tribes are united at last!"
               - "[D10] March on Enemy": timer after alliance complete
               - "[D11] Victory Speech": triggered by victory condition

            5. --- Victory/Defeat Section (CREATE ALL 6 triggers) ---
               Tiered victory based on factions recruited:

               - "VC Minimum": objects_in_area OR custom tracking (2+ factions joined)
                 Effect: declare_victory(source_player=PlayerId.ONE, enabled=1)
                 Message: "You have forged a modest alliance."

               - "VC Standard": 3-4 factions joined
                 Effect: declare_victory with enhanced message
                 Message: "Your alliance is strong!"

               - "VC Ultimate": ALL factions joined + enemy defeated
                 Effect: declare_victory with ultimate message
                 Message: "You have united all the tribes and crushed your enemies!"

               - "Defeat - Hero Dies": destroy_object(unit_object=hero.reference_id)
                 Effect: declare_victory(source_player=PlayerId.TWO, enabled=1)

               - "Defeat - Enemy Wins": enemy destroys player base (optional)
                 Condition: destroy_object on player TOWN_CENTER

               - "[D_] Hero Death Msg": destroy_object on hero
                 Effect: display death message before defeat trigger fires

            6. --- Utility Triggers (CREATE ALL 8-10 triggers) ---
               - "Enemy Patrol Loop": looping=True, task_object to patrol enemy units
               - "Enemy Reinforcements": timer(300), create_object for enemy
               - "Faction 3 Death Check": destroy_object on faction leader, message
               - "Faction 4 Death Check": destroy_object on faction leader, message
               - "Faction 5 Death Check": destroy_object on faction leader, message
               - "Beast Spawned": timer(1), reveal beast location or create beast
               - "Resource Trickle": looping timer, give player small resource income
               - "Map Reveal": timer(1), reveal key locations

            PLAYER SETUP AND BUILDINGS:

            Player ONE (Hero/Protagonist - Human):
            - Hero unit (store reference for all triggers!)
            - 10-15 starting cavalry/soldiers
            - Small starting camp:
              * TOWN_CENTER or CASTLE as base
              * STABLE, BARRACKS for unit production
              * 2-3 HOUSE
            - Starting resources: moderate (player may need to collect tribute)

            Player TWO (Main Enemy - AI):
            - Enemy lord (store reference for triggers)
            - 30-50 military units in fortified base
            - Fortified base:
              * CASTLE as stronghold
              * STONE_WALL perimeter with GATE (enemy owns gate!)
              * GUARD_TOWER at key positions
              * BARRACKS, STABLE, ARCHERY_RANGE
            - Patrols that move THROUGH their own gates

            Players THREE-EIGHT (Neutral Factions - AI):
            Each faction has a distinct camp (spread across map):

            - Faction Camp Template:
              * Central structure: PAVILION_A/B/C, YURT_A-H, or TENT_A-E
              * Decorations: TORCH_A, BONFIRE, FLAG_B/D
              * 1-2 military buildings: STABLE (nomads) or BARRACKS (settled)
              * 15-25 military units (unique composition per faction)
              * Faction leader (store reference for death checks)

            - Faction Unit Variety:
              * Steppe faction: CAVALRY_ARCHER, LIGHT_CAVALRY, SCOUT_CAVALRY
              * Settled faction: MAN_AT_ARMS, SPEARMAN, CROSSBOWMAN
              * Forest faction: ARCHER, SKIRMISHER, SPEARMAN
              * Mountain faction: PIKEMAN, ONAGER, infantry

            GAIA:
            - Quest targets: WILD_BOAR, WOLF (for fetch quests) - store references!
            - Resources near player start and faction camps
            - Terrain features separating faction territories
            - ROMAN_RUINS, RELIC for exploration rewards

            MAP DESIGN:
            - Player starts in center or corner
            - Enemy base in opposite corner (final objective)
            - Neutral faction camps spread across map (one per quadrant/region)
            - Natural barriers (rivers, forests, cliffs) separating territories
            - Roads connecting camps for easy navigation
            - Each faction territory visually distinct (terrain, decorations)

            DIPLOMACY MECHANICS - CRITICAL RULES:

            1. Quest conditions by type:
               - TRIBUTE: accumulate_attribute(quantity=X, attribute=0/3, source_player=PlayerId.ONE)
                 * attribute=0 is Food, attribute=3 is Gold
               - COMBAT: destroy_object(unit_object=enemy_leader.reference_id)
               - FETCH: destroy_object(unit_object=beast.reference_id)

            2. Faction transfer uses change_ownership with area:
               - change_ownership(source_player=PlayerId.THREE, target_player=PlayerId.ONE, area_x1=..., area_y1=..., area_x2=..., area_y2=...)
               - Area should cover the entire faction camp

            3. Enemy gates owned by enemy:
               - Enemy patrols can exit through their own gates
               - Player must breach or destroy gates to attack

            4. Neutral factions start NEUTRAL:
               - Not hostile, not allied
               - Become allied after joining

            ===== FINAL TRIGGER CHECKLIST =====
            [ ] 6 Setup triggers
            [ ] 5-8 Faction Request triggers (one per faction)
            [ ] 5-8 Faction Joins triggers (one per faction)
            [ ] 12 Story Dialogue triggers ([D0] through [D11])
            [ ] 6 Victory/Defeat triggers (VC tiers + defeat)
            [ ] 8-10 Utility triggers (patrols, death checks, loops)
            ---------------------------------------------------------
            TOTAL: 50-65 triggers MINIMUM
            ===============================================""",

            "defense": """Create an Age of Empires 2 DEFENSE scenario based on Saladin Campaign (cam3) siege patterns:
            - Title: {title}
            - Description: {description}
            - Map size: {map_size}x{map_size}
            - Players: {players}
            - Difficulty: {difficulty}

            ===== MANDATORY TRIGGER REQUIREMENTS =====
            YOU MUST CREATE EXACTLY 35-45 TRIGGERS. This is NON-NEGOTIABLE.

            REQUIRED TRIGGER BREAKDOWN (minimum counts):
            - Setup triggers: 6-7 (Techs, walls, gates, difficulty, resources)
            - Wave spawn triggers: 12-16 (4-6 waves with 2-3 triggers each)
            - Dialogue triggers: 10-12 using "[D#] Name" pattern
            - Objective triggers: 4-5 using "[O] Name" pattern
            - Victory/Defeat triggers: 4-5 (survive, eliminate, defeat conditions)
            ==========================================

            TRIGGER STRUCTURE (CREATE ALL OF THESE):

            1. --- Setup Section (CREATE ALL 7 triggers) ---
               - "Techs": timer(1), research defensive technologies
                 research_technology: FORGING, SCALE_MAIL_ARMOR, FLETCHING, etc.
               - "Wall Setup": timer(1), ensure walls are properly configured
               - "Close Gates": timer(1), close all gates at start
                 IMPORTANT: Player ONE owns all defensive gates
               - "Easy Difficulty": difficulty_level(quantity=0)
                 Effect: kill_object to remove enemies from later waves
               - "Standard Difficulty": difficulty_level(quantity=1)
                 Effect: normal wave composition (no changes)
               - "Hard Difficulty": difficulty_level(quantity=3)
                 Effect: create_object to add extra enemies to each wave
               - "Starting Resources": timer(1), modify_resource to grant starting resources (tribute_list=Attribute.*_STORAGE, operation=Operation.SET)

            2. --- Wave Spawn Section (CREATE ALL 16 triggers - 4 waves × 4 triggers each) ---
               Defense scenarios USE TIMERS - waves are time-based by design!

               === WAVE 1 (60 seconds) - Probing Attack ===
               - "Wave 1 Announce": timer(55)
                 Effect: display_instructions "Scouts report enemies approaching from the [direction]!"
               - "Wave 1 Spawn": timer(60)
                 Effect: create_object at map edge (spawn_x, spawn_y based on direction)
                 Units: 8-12 infantry (MAN_AT_ARMS, SPEARMAN)
                        4-6 archers (ARCHER, CROSSBOWMAN)
               - "Wave 1 Attack": timer(65)
                 Effect: task_object with attack-move toward player base
                 task_object(object_list_unit_id=UnitInfo.MAN_AT_ARMS.ID, source_player=PlayerId.TWO, location_x=target_x, location_y=target_y)
               - "Wave 1 Cleared": objects_in_area(quantity=0, source_player=PlayerId.TWO, area around spawn)
                 Effect: display_instructions "The first wave has been repelled!"

               === WAVE 2 (180 seconds) - Cavalry Assault ===
               - "Wave 2 Announce": timer(175)
                 Effect: display "More enemies incoming! Cavalry spotted!"
               - "Wave 2 Spawn": timer(180)
                 Spawn from DIFFERENT direction than Wave 1
                 Units: 10-12 infantry, 6-8 archers, 6-8 cavalry (KNIGHT, LIGHT_CAVALRY)
               - "Wave 2 Attack": timer(185)
                 Effect: task_object to attack
               - "Wave 2 Cleared": objects_in_area check

               === WAVE 3 (320 seconds) - Siege Assault ===
               - "Wave 3 Announce": timer(315)
                 Effect: display "They bring siege weapons! Protect the walls!"
               - "Wave 3 Spawn": timer(320)
                 Spawn from DIFFERENT direction
                 Units: 12-15 infantry, 8-10 archers, 5 cavalry
                        3-4 siege (BATTERING_RAM, MANGONEL)
               - "Wave 3 Attack": timer(325)
                 Effect: task_object - siege targets gates/walls, troops protect siege
               - "Wave 3 Cleared": objects_in_area check

               === WAVE 4 (480 seconds) - Final Assault ===
               - "Wave 4 Announce": timer(475)
                 Effect: display "<RED>Enemy Commander: This ends now! ALL FORCES, ATTACK!"
               - "Wave 4 Spawn": timer(480)
                 Spawn from MULTIPLE directions simultaneously
                 Units: 15-20 elite infantry (CHAMPION, PIKEMAN)
                        10-12 elite archers (ARBALESTER)
                        8-10 cavalry (CAVALIER, PALADIN)
                        4-5 siege (TREBUCHET, BATTERING_RAM)
                        1 Enemy Hero/Commander (store reference for VC)
               - "Wave 4 Attack": timer(485)
                 Effect: all units attack
               - "Enemy Commander Dies": destroy_object(unit_object=enemy_commander.reference_id)
                 Effect: display "Their commander has fallen! The attack falters!"

            3. --- Dialogue Section (CREATE ALL 12 triggers) ---
               - "[D0] Intro": timer(5)
                 "<YELLOW>Narrator: The enemy army gathers outside your walls..."
               - "[D1] Defender Speech": timer(10)
                 "<BLUE>Commander: Men, hold the walls! Our lives depend on it!"
               - "[D2] Scout Report": timer(30)
                 "<BLUE>Scout: I count four assault groups preparing to attack."
               - "[D3] First Wave Warning": timer(55) - synced with wave announce
                 "<BLUE>Watchman: Movement on the horizon! Here they come!"
               - "[D4] Enemy Taunt 1": timer(90)
                 "<RED>Enemy Lord: Your walls will crumble before us!"
               - "[D5] Between Waves": timer(150)
                 "<BLUE>Commander: Repair what you can! More will come!"
               - "[D6] Enemy Taunt 2": timer(250)
                 "<RED>Enemy Lord: You cannot hold forever!"
               - "[D7] Siege Warning": timer(315) - synced with wave 3
                 "<BLUE>Scout: Siege engines! They mean to breach the walls!"
               - "[D8] Encouragement": timer(400)
                 "<BLUE>Commander: Hold fast! Victory is within reach!"
               - "[D9] Final Wave Warning": timer(475) - synced with wave 4
                 "<YELLOW>Narrator: The enemy commits their full strength..."
               - "[D10] Near Victory": timer(550) - if survival timer is 600
                 "<BLUE>Commander: Dawn approaches! Just a little longer!"
               - "[D11] Hero/Key Unit Death": destroy_object on key defender
                 "<BLUE>Soldier: [Name] has fallen!"

            4. --- Objective Section (CREATE ALL 5 triggers) ---
               - "[O] Main Objective": timer(1)
                 "Survive the enemy assault until dawn. (10:00)"
                 "Protect the [CASTLE/TOWN_CENTER] at all costs."
               - "[O] Optional - Kill Commander": timer(1)
                 "OPTIONAL: Slay the enemy commander."
               - "[Obj] Survival Progress 1": timer(200)
                 "You have survived 3 minutes. Keep holding!"
               - "[Obj] Survival Progress 2": timer(400)
                 "You have survived 6 minutes. Victory draws near!"
               - "[Obj] Commander Killed": destroy_object on enemy commander
                 "The enemy commander has been slain!"

            5. --- Victory/Defeat Section (CREATE ALL 5 triggers) ---
               - "VC Survive": timer(600) - primary victory
                 Effect: declare_victory(source_player=PlayerId.ONE, enabled=1)
                 Message: "Dawn breaks! You have survived the siege!"
               - "VC Eliminate": objects_in_area (all enemy players have 0 units)
                 Condition: Check all spawn areas and map for enemy units
                 Effect: declare_victory(source_player=PlayerId.ONE, enabled=1)
                 Message: "All attackers have been destroyed!"
               - "VC Commander + Survive": destroy_object(commander) AND timer(600)
                 Enhanced victory message
               - "Defeat - Castle Lost": destroy_object on CASTLE/key building
                 Effect: declare_victory(source_player=PlayerId.TWO, enabled=1)
                 Message: "Your stronghold has fallen!"
               - "Defeat - TC Lost": destroy_object on TOWN_CENTER (backup)
                 Effect: declare_victory(source_player=PlayerId.TWO, enabled=1)

            PLAYER SETUP AND BUILDINGS:

            Player ONE (Defender - Human):
            Store references for key buildings!

            Central Fortification:
            - castle = unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.CASTLE.ID, x=center, y=center)
            - OR 2x KEEP if no castle appropriate

            Walls (Player ONE owns all walls and gates):
            - 30-50 STONE_WALL segments forming complete perimeter
            - 2-4 GATE at cardinal entry points (N, S, E, W)
            - Gates owned by PLAYER ONE - enemies must destroy to enter
            - Leave NO GAPS - force enemies through gates

            Towers:
            - 6-8 GUARD_TOWER or KEEP at corners and flanking gates
            - Position towers to cover gate approaches

            Economy (inside walls):
            - TOWN_CENTER (store reference for defeat condition)
            - 4-6 HOUSE
            - MILL, LUMBER_CAMP, MINING_CAMP
            - Resource piles (gold, stone, wood) inside walls

            Military (inside walls):
            - BARRACKS, ARCHERY_RANGE, STABLE for reinforcements
            - BLACKSMITH, UNIVERSITY for upgrades
            - MONASTERY for healing

            Starting Units:
            - 15-20 military: CROSSBOWMAN on walls, MAN_AT_ARMS at gates
            - 8-12 VILLAGER for repairs and resource gathering
            - 1 Hero/Commander (optional, store reference)

            Player TWO-FOUR (Attackers - AI):
            - NO starting buildings (attackers spawn via triggers)
            - NO starting units (all created by wave triggers)
            - Define spawn points at map edges:
              * North: spawn_n_x = center, spawn_n_y = 5
              * South: spawn_s_x = center, spawn_s_y = map_size - 5
              * East: spawn_e_x = map_size - 5, spawn_e_y = center
              * West: spawn_w_x = 5, spawn_w_y = center

            GAIA:
            - Resources INSIDE defender's walls (gold, stone, wood, food)
            - Terrain features OUTSIDE channeling attackers toward gates:
              * Forests blocking flanking routes
              * Cliffs/water creating chokepoints
              * Roads leading from spawn points to gates

            GATE AND WALL MECHANICS - CRITICAL:

            1. DEFENDER owns all gates:
               - unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.GATE_NORTH_TO_SOUTH.ID, ...)
               - Enemies CANNOT pass through - must destroy gate

            2. Walls must form COMPLETE perimeter:
               - No gaps for enemies to exploit
               - Force all attackers through gate chokepoints

            3. Siege weapons target gates:
               - Wave 3+ includes BATTERING_RAM to break gates
               - Once gate destroyed, infantry floods through

            4. Tower placement:
               - Towers covering gate approaches maximize damage
               - Crossfire zones at gates

            WAVE SPAWN LOCATIONS:
            Use different edges for variety:
            - Wave 1: North edge
            - Wave 2: East edge
            - Wave 3: South edge
            - Wave 4: ALL edges simultaneously (surround)

            DIFFICULTY SCALING:
            | Difficulty | Wave Size | Siege | Final Wave |
            |------------|-----------|-------|------------|
            | Easy       | -30%      | -50%  | No hero    |
            | Standard   | Normal    | Normal| 1 hero     |
            | Hard       | +30%      | +50%  | 2 heroes   |

            ===== FINAL TRIGGER CHECKLIST =====
            [ ] 7 Setup triggers (Techs, Walls, Gates, Easy/Standard/Hard, Resources)
            [ ] 16 Wave triggers (4 waves × 4 triggers: announce, spawn, attack, cleared)
            [ ] 12 Dialogue triggers ([D0] through [D11])
            [ ] 5 Objective triggers ([O] Main, Optional, Progress x2, Commander)
            [ ] 5 Victory/Defeat triggers (Survive, Eliminate, Enhanced, Castle Lost, TC Lost)
            ---------------------------------------------------------
            TOTAL: 45 triggers MINIMUM
            ===============================================""",

            "conquest": """Create an Age of Empires 2 CONQUEST scenario based on Genghis Khan Campaign (cam4) patterns:
            - Title: {title}
            - Description: {description}
            - Map size: {map_size}x{map_size}
            - Players: {players}
            - Difficulty: {difficulty}

            ===== MANDATORY TRIGGER REQUIREMENTS =====
            YOU MUST CREATE EXACTLY 40-50 TRIGGERS. This is NON-NEGOTIABLE.

            REQUIRED TRIGGER BREAKDOWN (minimum counts):
            - Setup triggers: 5-6 (Techs, difficulty, AI behavior, map reveal)
            - Discovery triggers: 8-10 using "[D#] Name" pattern
            - Capture triggers: 6-8 (siege, buildings, areas)
            - Gate/Breach triggers: 4-6 (wall destruction, gate capture)
            - Progressive Victory triggers: 6-8 (V/1 through V/4, milestones)
            - Objective triggers: 4-5 using "[O] Name" pattern
            - Defeat triggers: 3-4
            ==========================================

            TRIGGER STRUCTURE (CREATE ALL OF THESE):

            1. --- Setup Section (CREATE ALL 6 triggers) ---
               - "Techs": timer(1), research siege technologies
                 research_technology: SIEGE_ENGINEERS, CHEMISTRY, etc.
               - "Easy Difficulty": difficulty_level(quantity=0)
                 Effect: kill_object to reduce garrison, weaken walls
               - "Hard Difficulty": difficulty_level(quantity=3)
                 Effect: create_object to add extra defenders, towers
               - "Enemy Patrol Setup": timer(1)
                 Effect: task_object for enemy patrols THROUGH THEIR OWN GATES
                 CRITICAL: Enemy must own gates so they can patrol/reinforce
               - "Map Reveal": timer(1)
                 Effect: Create MAP_REVEALER units or use reveal_map effect for key areas
               - "Starting Grant": timer(1)
                 Effect: modify_resource for starting resources (tribute_list=Attribute.*_STORAGE, operation=Operation.SET), create starting units

            2. --- Discovery Section (CREATE ALL 10 triggers) ---
               ALL discovery triggers use bring_object_to_area - player explores to find!
               Store hero reference: hero = unit_manager.add_unit(...)

               Outer Defenses Discovery:
               - "[D0] Intro": timer(5), opening narration
                 "<YELLOW>Narrator: Before you lies the enemy fortress..."
               - "[D1] Outer Wall Sighted": bring_object_to_area (approach outer wall)
                 "<BLUE>Scout: The outer defenses. Palisades and watchtowers."
               - "[D2] Find Weak Point": bring_object_to_area (specific wall section)
                 "<BLUE>Scout: This section looks weaker than the rest."
               - "[D3] Siege Equipment Found": bring_object_to_area (near GAIA siege)
                 "<BLUE>Scout: Abandoned siege weapons! We can use these!"

               Middle Defenses Discovery:
               - "[D4] Middle Wall Sighted": bring_object_to_area (after breaching outer)
                 "<BLUE>Scout: Stone walls ahead. This will be harder."
               - "[D5] Gate Spotted": bring_object_to_area (near enemy gate)
                 "<BLUE>Scout: A fortified gate. We'll need rams to break through."
               - "[D6] Defenders Rally": bring_object_to_area (approach middle defenses)
                 "<RED>Enemy Commander: Reinforce the inner walls! Hold them!"

               Inner Fortress Discovery:
               - "[D7] Inner Fortress Sighted": bring_object_to_area (see castle)
                 "<YELLOW>Narrator: The inner fortress looms before you..."
               - "[D8] Final Defenses": bring_object_to_area (approach castle)
                 "<RED>Enemy Lord: You will die at my gates!"
               - "[D9] Enemy Lord Spotted": bring_object_to_area (near castle)
                 "<BLUE>Scout: The enemy lord is there! Destroy him and victory is ours!"

            3. --- Capture Section (CREATE ALL 8 triggers) ---
               Store references for all capturable objects!

               Siege Equipment Capture:
               - "Capture Siege 1": bring_object_to_area (hero near GAIA trebuchet)
                 trebuchet = unit_manager.add_unit(PlayerId.GAIA, unit_const=UnitInfo.TREBUCHET.ID, ...)
                 Condition: bring_object_to_area(unit_object=hero.reference_id, area around trebuchet)
                 Effect: change_ownership(source_player=PlayerId.GAIA, target_player=PlayerId.ONE, area)
                 Message: "Trebuchet captured!"

               - "Capture Siege 2": bring_object_to_area (second siege weapon)
                 Effect: change_ownership of battering rams/mangonels

               - "Capture Siege 3": bring_object_to_area (third siege weapon)

               Building Capture:
               - "Capture Outpost": destroy_object (enemy watchtower) OR objects_in_area (clear area)
                 Effect: create_object friendly buildings, display message
                 Message: "The outpost is ours! Use it to reinforce."

               - "Capture Barracks": bring_object_to_area + objects_in_area (clear defenders)
                 Effect: change_ownership of enemy BARRACKS to player
                 Message: "Enemy barracks captured! Train reinforcements."

               Area Control:
               - "Control Outer Zone": objects_in_area (no enemies in outer zone)
                 Effect: display "Outer defenses secured!"

               - "Control Middle Zone": objects_in_area (no enemies in middle zone)
                 Effect: display "Middle defenses secured!"

               - "Control Inner Zone": objects_in_area (no enemies except castle)
                 Effect: display "Inner courtyard secured! Only the keep remains!"

            4. --- Gate/Breach Section (CREATE ALL 6 triggers) ---
               Store references for all gates and key wall segments!

               Outer Wall Breaches:
               - outer_gate = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GATE_NORTH_TO_SOUTH.ID, ...)
               - outer_wall_weak = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.PALISADE_WALL.ID, ...)

               - "Outer Gate Breached": destroy_object(unit_object=outer_gate.reference_id)
                 Effect: display_instructions "The outer gate has fallen!"
                 IMPORTANT: Enemy owned this gate - now destroyed, path is open

               - "Outer Wall Breached": destroy_object(unit_object=outer_wall_weak.reference_id)
                 Effect: display "A breach in the outer wall! Pour through!"

               Middle Wall Breaches:
               - middle_gate = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GATE_NORTH_TO_SOUTH.ID, ...)

               - "Middle Gate Breached": destroy_object(unit_object=middle_gate.reference_id)
                 Effect: display "The stone gate crumbles!"

               - "Middle Wall Section Down": destroy_object on wall segment
                 Effect: display message

               Inner Fortress:
               - inner_gate = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GATE_NORTH_TO_SOUTH.ID, ...)

               - "Inner Gate Breached": destroy_object(unit_object=inner_gate.reference_id)
                 Effect: display "<YELLOW>The final gate is down! Storm the keep!"

               - "Castle Under Siege": bring_object_to_area (units reach castle)
                 Effect: display "Attack the castle! End this!"

            5. --- Progressive Victory Section (CREATE ALL 8 triggers) ---
               Victory progresses through phases - each phase triggers next objective.

               - "V/1 Outer Cleared": objects_in_area (outer zone clear) OR destroy_object (outer gate)
                 Effect: display "Phase 1 complete: Outer defenses fallen!"
                 Unlocks: Access to middle zone

               - "V/2 Siege Captured": bring_object_to_area (captured 2+ siege weapons)
                 Effect: display "Siege equipment secured!"

               - "V/3 Middle Cleared": objects_in_area (middle zone clear) OR destroy_object (middle gate)
                 Effect: display "Phase 2 complete: Middle defenses breached!"
                 Unlocks: Access to inner fortress

               - "V/4 Inner Breached": destroy_object (inner gate)
                 Effect: display "Phase 3 complete: The keep is exposed!"

               - "V/5 Commander Killed": destroy_object(unit_object=enemy_lord.reference_id)
                 enemy_lord = unit_manager.add_unit(PlayerId.TWO, unit_const=HeroInfo.XXX.ID, ...)
                 Effect: display "<YELLOW>The enemy lord has fallen!"

               - "V/6 Castle Destroyed": destroy_object(unit_object=castle.reference_id)
                 castle = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.CASTLE.ID, ...)
                 Effect: display "The castle crumbles!"

               - "Victory Primary": destroy_object on castle OR enemy_lord
                 Effect: declare_victory(source_player=PlayerId.ONE, enabled=1)
                 Message: "The fortress has fallen! Victory is yours!"

               - "Victory Complete": destroy_object on castle AND enemy_lord
                 Effect: declare_victory with enhanced message
                 Message: "Total victory! The enemy is utterly defeated!"

            6. --- Objective Section (CREATE ALL 5 triggers) ---
               - "[O] Main Objectives": timer(1)
                 "Breach the enemy fortress and destroy their stronghold."
                 "1. Break through the outer defenses"
                 "2. Breach the middle walls"
                 "3. Storm the inner keep and destroy the castle"

               - "[Obj] Outer Cleared": triggered by V/1
                 "Outer defenses cleared! Press forward!"

               - "[Obj] Middle Cleared": triggered by V/3
                 "Middle defenses breached! The keep awaits!"

               - "[Obj] Optional - Capture All Siege": capture all 3 siege weapons
                 "OPTIONAL: All siege equipment captured!"

               - "[Obj] Optional - Minimal Losses": timer(victory) with unit count check
                 "OPTIONAL: Victory with minimal casualties!"

            7. --- Defeat Section (CREATE ALL 4 triggers) ---
               - "Defeat - Hero Dies": destroy_object(unit_object=hero.reference_id)
                 Effect: display death message
                 Effect: declare_victory(source_player=PlayerId.TWO, enabled=1)

               - "Defeat - Army Destroyed": objects_in_area (player military = 0)
                 Effect: declare_victory(source_player=PlayerId.TWO, enabled=1)
                 Message: "Your army has been annihilated!"

               - "Defeat - Siege Lost": destroy_object on all player siege weapons
                 Effect: display "All siege equipment lost! You cannot breach the walls!"
                 (Optional: Can continue if player has other options)

               - "[D_] Hero Death Message": destroy_object on hero
                 Effect: display "<YELLOW>Our leader has fallen..."

            PLAYER SETUP AND BUILDINGS:

            Player ONE (Attacker - Human):
            Store hero reference!
            - hero = unit_manager.add_unit(PlayerId.ONE, unit_const=HeroInfo.XXX.ID, ...)
            - 25-35 military units (infantry, archers, cavalry)
            - 3-5 starting siege: BATTERING_RAM, MANGONEL
            - Forward camp (optional):
              * BARRACKS, ARCHERY_RANGE for reinforcements
              * BLACKSMITH for upgrades
              * No walls (offensive scenario)

            Player TWO (Defender - AI):
            LAYERED FORTRESS DESIGN - Store references for all key objects!

            === Outer Defenses (First Line) ===
            - 25-35 PALISADE_WALL segments
            - 2-3 WATCH_TOWER
            - 1-2 GATE (Enemy owns! So defenders can patrol through)
            - Garrison: 10-15 infantry, 5-8 archers
            - outer_gate = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GATE_NORTH_TO_SOUTH.ID, ...)

            === Middle Defenses (Second Line) ===
            - 35-45 STONE_WALL segments
            - 4-5 GUARD_TOWER
            - 2-3 GATE (Enemy owns!)
            - BARRACKS, ARCHERY_RANGE behind walls
            - Garrison: 15-20 infantry, 10-12 archers, 5 cavalry
            - middle_gate = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GATE_NORTH_TO_SOUTH.ID, ...)

            === Inner Fortress (Final Objective) ===
            - castle = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.CASTLE.ID, ...)
            - TOWN_CENTER, BLACKSMITH, MONASTERY
            - 4-6 KEEP or BOMBARD_TOWER
            - 1-2 GATE (Enemy owns!)
            - enemy_lord = unit_manager.add_unit(PlayerId.TWO, unit_const=HeroInfo.XXX.ID, ...) - store reference!
            - Elite garrison: 15-20 elite troops

            Player THREE+ (Secondary Defenders - AI):
            - Outposts between defensive lines
            - WATCH_TOWER + 5-10 troops each
            - Reinforce main defender when attacked

            GAIA (Capturable Equipment):
            Store references for capture triggers!
            - trebuchet = unit_manager.add_unit(PlayerId.GAIA, unit_const=UnitInfo.TREBUCHET.ID, ...)
            - ram = unit_manager.add_unit(PlayerId.GAIA, unit_const=UnitInfo.BATTERING_RAM.ID, ...)
            - Place near walls but outside enemy reach
            - TRANSPORT_SHIP if water crossing needed

            GATE MECHANICS - CRITICAL:

            1. ALL gates owned by DEFENDER (PlayerId.TWO):
               - Defenders can patrol THROUGH their own gates
               - Reinforcements can move between defensive layers
               - Player must DESTROY gates to pass

            2. Wall weak points:
               - Mark certain wall segments as "weak" (store references)
               - These require fewer hits to destroy
               - Provides player with tactical choices

            3. Gate destruction sequence:
               - Outer gate → access to middle zone
               - Middle gate → access to inner fortress
               - Inner gate → access to castle

            4. Progressive unlocking:
               - Each gate breach triggers discovery of next layer
               - Enemies retreat to next defensive line when current falls

            MAP DESIGN:
            - Player starts at map edge
            - Three defensive layers blocking path:
              * Outer: Palisade + watchtowers (1/4 into map)
              * Middle: Stone walls + guard towers (1/2 into map)
              * Inner: Castle + keeps (3/4 into map or center)
            - GAIA siege equipment between layers (capturable)
            - Terrain channeling attacks toward gates
            - Optional flanking routes (harder but bypass some defenses)

            ===== FINAL TRIGGER CHECKLIST =====
            [ ] 6 Setup triggers (Techs, Easy/Hard, Enemy Patrols, Map Reveal, Starting Grant)
            [ ] 10 Discovery triggers ([D0] through [D9])
            [ ] 8 Capture triggers (Siege x3, Buildings x2, Zones x3)
            [ ] 6 Gate/Breach triggers (Outer, Middle, Inner gates + wall sections)
            [ ] 8 Progressive Victory triggers (V/1 through V/6, Victory, Victory Complete)
            [ ] 5 Objective triggers ([O] Main, Outer, Middle, Optional x2)
            [ ] 4 Defeat triggers (Hero Dies, Army Destroyed, Siege Lost, Death Message)
            ---------------------------------------------------------
            TOTAL: 47 triggers MINIMUM
            ===============================================""",

            "story": """Create an Age of Empires 2 STORY scenario combining patterns from all campaigns:
            - Title: {title}
            - Description: {description}
            - Map size: {map_size}x{map_size}
            - Players: {players}
            - Difficulty: {difficulty}

            ===== MANDATORY TRIGGER REQUIREMENTS =====
            YOU MUST CREATE EXACTLY 45-60 TRIGGERS. This is NON-NEGOTIABLE.

            REQUIRED TRIGGER BREAKDOWN (minimum counts):
            - Setup triggers: 5-6 (Techs, difficulty, AI behavior, initial state)
            - Act 1 triggers: 10-12 (introduction, meet characters, first quest)
            - Act 2 triggers: 12-15 (rising action, complications, recruitment)
            - Act 3 triggers: 10-12 (climax, final battle, resolution)
            - Objective triggers: 5-6 using "[O] Name" pattern
            - Victory/Defeat triggers: 5-6
            ==========================================

            TRIGGER DESIGN - CRITICAL RULES:

            1. STORY PROGRESSION uses bring_object_to_area, NOT timers!
               - Player controls pacing by moving through the world
               - Each story beat triggered by reaching a location
               - Timers ONLY for opening narration and ambient dialogue

            2. Store ALL important unit references:
               - hero = unit_manager.add_unit(...) - for area triggers
               - ally = unit_manager.add_unit(...) - for death checks
               - villain = unit_manager.add_unit(...) - for victory condition

            3. Gate ownership:
               - Enemy bases: Enemy owns gates (so they can patrol/exit)
               - Player captures gates via destroy_object or change_ownership

            TRIGGER STRUCTURE (CREATE ALL OF THESE):

            1. --- Setup Section (CREATE ALL 6 triggers) ---
               - "Techs": timer(1), research starting technologies
               - "Easy Difficulty": difficulty_level(quantity=0)
                 Effect: kill_object to reduce enemies, create_object for extra allies
               - "Hard Difficulty": difficulty_level(quantity=3)
                 Effect: create_object for extra enemies, stronger garrisons
               - "Enemy AI Setup": timer(1)
                 Effect: task_object for enemy patrols through THEIR OWN gates
               - "Initial State": timer(1)
                 Effect: Set diplomacy, reveal starting area, position camera
               - "Ally AI Setup": timer(1)
                 Effect: Set ally unit stances, patrol routes

            2. --- Act 1: Introduction (CREATE ALL 12 triggers) ---
               Opening - uses timer for first narration only:
               - "[D0] Intro": timer(5)
                 "<YELLOW>Narrator: In the year [DATE], [setting description]..."
                 "<YELLOW>Our story begins in [location]..."

               Character Introduction - ALL use bring_object_to_area:
               - "[D1] Hero Awakens": bring_object_to_area (hero in starting area)
                 "<BLUE>Hero: [Establishing character moment]"
               - "[D2] Meet Advisor": bring_object_to_area (hero reaches advisor)
                 "<BLUE>Advisor: My lord, troubling news from the [direction]..."
               - "[D3] Advisor Explains": timer(3) after D2 (immediate follow-up only)
                 "<BLUE>Advisor: [Exposition about the threat]"

               First Quest Setup:
               - "[D4] First Objective": bring_object_to_area (hero leaves camp)
                 Display objective: "Investigate the [location]"
               - "[D5] Encounter Scouts": bring_object_to_area (reach scout position)
                 "<BLUE>Scout: My lord! Enemy forces spotted to the [direction]!"
               - "[D6] First Enemy Contact": bring_object_to_area (reach enemy outpost)
                 "<RED>Enemy Captain: Intruders! Kill them!"
                 Effect: task_object to attack (small skirmish)

               First Victory:
               - "[D7] Outpost Cleared": destroy_object (enemy captain killed) OR objects_in_area (enemies cleared)
                 "<BLUE>Advisor: Well done, my lord. But this is only the beginning."
               - "[D8] Discover Clue": bring_object_to_area (find story item/location)
                 "<YELLOW>Narrator: Among the ruins, you discover [plot point]..."
               - "[D9] Return to Base": bring_object_to_area (hero returns to camp)
                 "<BLUE>Advisor: We must prepare for what lies ahead."

               Recruitment:
               - "[D10] Allies Arrive": bring_object_to_area (reach allied camp) OR timer after D9
                 "<BLUE>Allied Commander: I bring reinforcements!"
                 Effect: change_ownership to transfer allied units to player
               - "[D11] Act 1 Ends": bring_object_to_area (hero at map boundary/new area)
                 "<YELLOW>Narrator: And so [hero] set forth..."

            3. --- Act 2: Rising Action (CREATE ALL 15 triggers) ---
               Journey/Exploration:
               - "[D12] New Territory": bring_object_to_area (enter Act 2 zone)
                 "<YELLOW>Narrator: The land grew darker as they traveled..."
               - "[D13] Ambush!": bring_object_to_area (ambush zone)
                 "<RED>Enemy: You walked right into our trap!"
                 Effect: create_object to spawn ambush units
               - "[D14] Ambush Survived": objects_in_area (ambush enemies dead)
                 "<BLUE>Advisor: That was close. They knew we were coming."

               Story Complication:
               - "[D15] Discovery": bring_object_to_area (find important location)
                 "<YELLOW>Narrator: What they found changed everything..."
               - "[D16] Betrayal/Twist": bring_object_to_area OR destroy_object (trigger event)
                 "<RED>Traitor: Did you really think I was your ally?"
                 Effect: change_ownership or create_object for twist
               - "[D17] Reaction": timer(5) after D16 (immediate emotional beat)
                 "<BLUE>Hero: [Emotional response to twist]"

               Ally in Danger:
               - "[D18] Ally Distress": timer(60) after entering Act 2 OR bring_object_to_area
                 "<BLUE>Messenger: The [ally] is under attack! We must help!"
                 New objective: "Save [ally] before it's too late"
               - "[D19] Rescue Mission": bring_object_to_area (reach ally location)
                 "<BLUE>Ally: Thank the heavens you've come!"
               - "[D20] Ally Saved": destroy_object (enemies at ally location killed)
                 "<BLUE>Ally: I am in your debt. My forces are yours."
                 Effect: change_ownership for rescued ally troops

               Enemy Escalation:
               - "[D21] Enemy Taunt": bring_object_to_area (approach enemy territory)
                 "<RED>Villain: So, you've made it this far. Impressive."
               - "[D22] Major Battle": bring_object_to_area (reach battlefield)
                 "<YELLOW>Narrator: The two armies clashed..."
                 Effect: task_object for large battle
               - "[D23] Battle Aftermath": objects_in_area (battle area cleared)
                 "<BLUE>Advisor: Victory, but at great cost."

               Preparation for Climax:
               - "[D24] Final Ally": bring_object_to_area (reach final allied camp)
                 "<BLUE>Final Ally: Together, we can defeat [villain]!"
                 Effect: change_ownership for final reinforcements
               - "[D25] Path to Fortress": bring_object_to_area (reach Act 3 boundary)
                 "<YELLOW>Narrator: The enemy stronghold lay before them..."
               - "[D26] Act 2 Ends": bring_object_to_area (hero at fortress approach)
                 Display: "Breach the enemy fortress and defeat [villain]"

            4. --- Act 3: Climax (CREATE ALL 12 triggers) ---
               Approach:
               - "[D27] Fortress Gates": bring_object_to_area (reach outer wall)
                 "<BLUE>Advisor: The gates are heavily defended."
               - "[D28] Breach Begins": destroy_object (outer gate destroyed)
                 "<YELLOW>Narrator: The final assault began..."
               - "[D29] Inner Defenses": bring_object_to_area (reach inner area)
                 "<RED>Villain: Is that all you have? Pathetic!"

               Final Confrontation:
               - "[D30] Villain Confrontation": bring_object_to_area (reach throne room/keep)
                 "<RED>Villain: You've come far, [hero]. But this is where you die."
               - "[D31] Villain Speech": timer(5) after D30 (dramatic pause)
                 "<RED>Villain: [Monologue explaining motivation/threat]"
               - "[D32] Final Battle": timer(10) after D31
                 "<BLUE>Hero: [Defiant response]"
                 Effect: task_object for villain to attack

               Victory Sequence:
               - "[D33] Villain Weakened": villain HP low (use objects_in_area with quantity)
                 "<RED>Villain: No... this cannot be..."
               - "[D34] Villain Falls": destroy_object(unit_object=villain.reference_id)
                 "<YELLOW>Narrator: [Villain] fell, and with him, the darkness lifted."
               - "[D35] Victory Moment": timer(3) after D34
                 "<BLUE>Hero: It is done."

               Resolution:
               - "[D36] Aftermath": timer(10) after victory
                 "<YELLOW>Narrator: Peace returned to the land..."
               - "[D37] Epilogue": timer(20) after victory
                 "<YELLOW>Narrator: And [hero]'s name would be remembered forever."
               - "[D38] Final Scene": timer(30) after victory
                 "<YELLOW>Narrator: [Final story wrap-up]"

            5. --- Objective Section (CREATE ALL 6 triggers) ---
               - "[O] Main Objectives": timer(1)
                 "Act 1: Investigate the threat"
                 "Act 2: Build your forces and uncover the truth"
                 "Act 3: Defeat [villain] and restore peace"

               - "[Obj] Act 1 Complete": triggered by D11
                 "Act 1 Complete: The journey begins!"

               - "[Obj] Act 2 Complete": triggered by D26
                 "Act 2 Complete: The final battle awaits!"

               - "[Obj] Ally Rescued": triggered by D20
                 "[Ally] has been saved!"

               - "[Obj] Optional Discovery": bring_object_to_area (hidden area)
                 "You discovered [hidden item/location]!"

               - "[Obj] Victory": triggered by D34
                 "[Villain] has been defeated! Victory!"

            6. --- Victory/Defeat Section (CREATE ALL 6 triggers) ---
               - "VC Primary": destroy_object(unit_object=villain.reference_id)
                 Effect: declare_victory(source_player=PlayerId.ONE, enabled=1)

               - "VC Alternative": destroy_object on villain's castle/key building
                 Effect: declare_victory(source_player=PlayerId.ONE, enabled=1)
                 (Backup if villain dies to other causes)

               - "VC Complete": destroy villain AND all objectives complete
                 Effect: Enhanced victory message

               - "Defeat - Hero Dies": destroy_object(unit_object=hero.reference_id)
                 Effect: declare_victory(source_player=PlayerId.TWO, enabled=1)

               - "Defeat - Key Ally Dies": destroy_object on essential ally
                 Effect: declare_victory(source_player=PlayerId.TWO, enabled=1)
                 (Only if ally death = story failure)

               - "[D_] Hero Death Msg": destroy_object on hero
                 Effect: display "<YELLOW>And so ended the tale of [hero]..."

            PLAYER SETUP AND BUILDINGS:

            Player ONE (Protagonist - Human):
            Store hero reference!
            - hero = unit_manager.add_unit(PlayerId.ONE, unit_const=HeroInfo.XXX.ID, ...)
            - 10-15 starting units (grows through recruitment)
            - Starting camp:
              * TOWN_CENTER or small CASTLE
              * BARRACKS, STABLE, ARCHERY_RANGE
              * 2-3 HOUSE, BLACKSMITH
            - Resources for rebuilding losses

            Player TWO (Main Antagonist - AI):
            Store villain reference!
            - villain = unit_manager.add_unit(PlayerId.TWO, unit_const=HeroInfo.XXX.ID, ...)

            Act 1-2 Presence (enemy outposts):
            - WATCH_TOWER + 5-10 troops per outpost
            - PALISADE_WALL small camps
            - Patrols THROUGH THEIR OWN GATES

            Act 3 Fortress (final location):
            - CASTLE as final objective (store reference)
            - STONE_WALL perimeter with GATE (enemy owns gates!)
            - GUARD_TOWER, KEEP defenses
            - BARRACKS, ARCHERY_RANGE, STABLE
            - 30-50 elite troops

            Player THREE+ (Supporting Characters - AI):
            Store ally references for death checks!

            Allied Characters:
            - ally1 = unit_manager.add_unit(PlayerId.THREE, unit_const=HeroInfo.XXX.ID, ...)
            - Allied camps: TOWN_CENTER, PAVILION clusters
            - 10-20 troops to transfer via change_ownership

            Neutral Characters:
            - Neutral towns: MARKET, MONASTERY, HOUSE clusters
            - Can become allied through story triggers

            Enemy Outposts (can be Player FOUR):
            - Smaller enemy faction
            - BARRACKS, PALISADE_WALL camps

            GAIA (Story Props):
            - FLAG_A-D: Mark story locations (bring_object_to_area targets)
            - ROMAN_RUINS, CASTLE_RUINS: Past events, discoveries
            - SKELETON, GRAVE: Battlefield atmosphere
            - RELIC: Hidden rewards
            - TORCH_A, BONFIRE: Camp atmosphere

            MAP DESIGN - THREE ACT STRUCTURE:

            Act 1 Zone (Starting area - 1/3 of map):
            - Player starting camp
            - Nearby allied camp
            - Small enemy outpost (first conflict)
            - Story discovery location

            Act 2 Zone (Middle area - 1/3 of map):
            - Ambush locations
            - Ally in danger location
            - Major battlefield
            - Story twist location
            - Final allied camp

            Act 3 Zone (Enemy territory - 1/3 of map):
            - Enemy fortress with layered walls
            - Villain's keep
            - Final battle arena

            Terrain separating zones:
            - Rivers, forests, cliffs between acts
            - Roads connecting story locations
            - Natural funneling toward objectives

            STORYTELLING TECHNIQUES:

            1. Color-coded dialogue:
               - <YELLOW> Narrator (scene-setting, transitions)
               - <BLUE> Allies (hero, advisor, friendly characters)
               - <RED> Enemies (villain, enemy captains)
               - <CYAN> <PURPLE> <GREEN> Other characters

            2. Dialogue timing:
               - display_time=10-15 for important dialogue
               - display_time=5-8 for quick exchanges
               - Space major beats with travel (bring_object_to_area)

            3. Environmental storytelling:
               - ROMAN_RUINS show past battles
               - SKELETON marks dangerous areas
               - FLAGS mark objectives
               - Building styles indicate faction control

            ===== FINAL TRIGGER CHECKLIST =====
            [ ] 6 Setup triggers
            [ ] 12 Act 1 triggers ([D0] through [D11])
            [ ] 15 Act 2 triggers ([D12] through [D26])
            [ ] 12 Act 3 triggers ([D27] through [D38])
            [ ] 6 Objective triggers
            [ ] 6 Victory/Defeat triggers
            ---------------------------------------------------------
            TOTAL: 57 triggers MINIMUM
            ==============================================="""
        }
    
    def generate_scenario(self, config: ScenarioConfig, model: str = None,
                          temperature: float = None, max_tokens: int = None,
                          reachability_prompting: bool = None) -> str:
        """Generate a scenario based on the provided configuration.

        The optional model/temperature/max_tokens/reachability_prompting
        arguments override the values on `config` (used by the generate()
        orchestrator so it can log the exact resolved parameters). Calling
        generate_scenario(config) alone is unchanged - it uses config's values.
        """
        # Resolve effective parameters (explicit override > config value)
        model = model if model is not None else config.model
        temperature = temperature if temperature is not None else config.temperature
        max_tokens = max_tokens if max_tokens is not None else config.max_tokens
        reachability_prompting = (config.reachability_prompting
                                  if reachability_prompting is None else reachability_prompting)

        # Select the user-message prompt body. This is the ONLY thing the
        # prompt_style ablation changes; the system prompt (base + reachability),
        # the region/civ templates and all parser rules are identical in both modes.
        if config.prompt_style == "freeform":
            base_template = FREEFORM_PROMPT_TEMPLATE
        else:
            base_template = self.scenario_templates.get(
                config.scenario_type, self.scenario_templates["story"])

        # Format the prompt
        prompt = base_template.format(
            title=config.title,
            description=config.description,
            map_size=config.map_size,
            players=config.players,
            difficulty=config.difficulty
        )

        # Add geographic region for terrain accuracy
        if config.region:
            prompt += f"""

            GEOGRAPHIC REGION: {config.region}
            Build terrain to match this region using the patterns below:

            {self._get_region_template(config.region)}"""

        # Add civilization styles for building accuracy
        if config.player_civ or config.enemy_civ:
            prompt += f"""

            CIVILIZATION STYLES:
            Player civilization: {config.player_civ or 'default'}
            Enemy civilization: {config.enemy_civ or 'default'}

            {self._get_civ_template(config.player_civ, config.enemy_civ)}"""

        # Add Wikipedia URL for historical context if provided
        if config.wikipedia_url:
            prompt += f"""

            HISTORICAL REFERENCE:
            Use the following Wikipedia article for accurate historical details:
            {config.wikipedia_url}

            Incorporate historically accurate:
            - Key figures and their roles
            - Military units and tactics used
            - Geographic/terrain features
            - Timeline of events
            - Dialogue reflecting the era"""

        # Generate the scenario code
        logger.info(f"Generating scenario: {config.title}")
        generated_code = self.api.generate_scenario_code(
            prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            reachability_prompting=reachability_prompting,
        )

        return generated_code

    def _get_region_template(self, region: str) -> str:
        """Return terrain building instructions for a geographic region"""
        templates = {
            "mediterranean": """
            MEDITERRANEAN TERRAIN PATTERN:
            - Base terrain: TerrainId.GRASS_1, TerrainId.DIRT_1 for land
            - Coastline: TerrainId.BEACH transitioning to TerrainId.WATER_MEDIUM
            - Trees: OtherInfo.TREE_PALM_FOREST, OtherInfo.TREE_A (sparse, coastal)
            - Features: Rocky coastlines with CLIFF_DEFAULT_2, olive groves (sparse tree clusters)
            - Resources: GOLD_MINE in hills, SHORE_FISH along coast
            - Atmosphere: Bright, open terrain with sea views

            Example coast creation:
            # Create sea on one edge (e.g., south)
            for x in range(0, map_size):
                for y in range(map_size - quarter, map_size):
                    tile = map_manager.get_tile(x=x, y=y)
                    if y < map_size - quarter + 3:
                        tile.terrain_id = TerrainId.BEACH.value
                    else:
                        tile.terrain_id = TerrainId.WATER_MEDIUM.value
            """,

            "steppe": """
            STEPPE/PLAINS TERRAIN PATTERN:
            - Base terrain: TerrainId.GRASS_DRY, TerrainId.GRASS_1 (mix for variety)
            - Water: Minimal - occasional small lakes or rivers
            - Trees: VERY SPARSE - only along rivers or as isolated clusters
            - Features: Rolling hills using subtle terrain variation, ROCK_FORMATION_1 outcrops
            - Resources: Scattered GOLD_MINE, herds of SHEEP/HORSE near camps
            - Atmosphere: Open, windswept, vast horizons

            Example steppe creation:
            # Mostly dry grass with patches of regular grass
            for x in range(0, map_size):
                for y in range(0, map_size):
                    tile = map_manager.get_tile(x=x, y=y)
                    if (x + y) % 7 < 2:  # Scattered pattern
                        tile.terrain_id = TerrainId.GRASS_1.value
                    else:
                        tile.terrain_id = TerrainId.GRASS_DRY.value
            # Add sparse rock formations
            for i in range(15):
                rx, ry = random_position_in_bounds()
                unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.ROCK_FORMATION_1.ID, x=rx, y=ry)
            """,

            "northern_europe": """
            NORTHERN EUROPE TERRAIN PATTERN:
            - Base terrain: TerrainId.GRASS_1, TerrainId.GRASS_2, TerrainId.DIRT_1
            - Water: Rivers (TerrainId.WATER_SHALLOW), lakes, marshes (TerrainId.SHALLOW_WATER)
            - Trees: DENSE forests - OtherInfo.TREE_OAK, OtherInfo.TREE_B, OtherInfo.TREE_C
            - Features: Thick woodlands, river crossings, marshy areas
            - Resources: GOLD_MINE/STONE_MINE in forest clearings, DEER in woods
            - Atmosphere: Dark, enclosed by trees, mysterious

            Example forest creation:
            # Create dense forest blocks
            forest_zones = [(0, 0, quarter, map_size), (three_quarter, 0, map_size, map_size)]
            for fx1, fy1, fx2, fy2 in forest_zones:
                for x in range(fx1, fx2):
                    for y in range(fy1, fy2):
                        if (x + y) % 3 != 0:  # Leave some gaps
                            unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.TREE_OAK.ID, x=x, y=y)
            """,

            "desert": """
            DESERT TERRAIN PATTERN:
            - Base terrain: TerrainId.DESERT_SAND, TerrainId.DIRT_3
            - Water: Rare oases only - small TerrainId.WATER_SHALLOW pools
            - Trees: OtherInfo.TREE_PALM_FOREST only at oases
            - Features: Sand dunes (terrain variation), ROCK_FORMATION_1/2 outcrops, CLIFF_DEFAULT_2
            - Resources: GOLD_MINE near rocky areas, sparse FORAGE_BUSH at oases
            - Atmosphere: Harsh, exposed, limited cover

            Example desert with oasis:
            # Fill with desert
            for x in range(0, map_size):
                for y in range(0, map_size):
                    tile = map_manager.get_tile(x=x, y=y)
                    tile.terrain_id = TerrainId.DESERT_SAND.value
            # Create oasis at center
            oasis_x, oasis_y = center, center
            for dx in range(-5, 6):
                for dy in range(-5, 6):
                    if dx*dx + dy*dy < 25:  # Circular oasis
                        tile = map_manager.get_tile(x=oasis_x+dx, y=oasis_y+dy)
                        if dx*dx + dy*dy < 9:
                            tile.terrain_id = TerrainId.WATER_SHALLOW.value
                        else:
                            tile.terrain_id = TerrainId.GRASS_1.value
            # Palm trees around oasis
            for i in range(12):
                angle = i * 30
                px = oasis_x + int(6 * math.cos(math.radians(angle)))
                py = oasis_y + int(6 * math.sin(math.radians(angle)))
                unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.TREE_PALM_FOREST.ID, x=px, y=py)
            """,

            "east_asia": """
            EAST ASIA TERRAIN PATTERN:
            - Base terrain: TerrainId.GRASS_1, TerrainId.GRASS_2
            - Water: Rivers, rice paddies (if available), coastal areas
            - Trees: OtherInfo.TREE_BAMBOO (if available), OtherInfo.TREE_F, cherry trees
            - Features: Terraced hills, river valleys, mountain passes with CLIFF_DEFAULT_3
            - Resources: GOLD_MINE in mountains, SHORE_FISH in rivers
            - Atmosphere: Scenic, varied elevation, water features

            Example mountain pass:
            # Mountains on edges
            for x in range(0, quarter):
                for y in range(0, map_size):
                    unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.CLIFF_DEFAULT_3.ID, x=x, y=y)
            # River through center valley
            for y in range(0, map_size):
                for dx in range(-2, 3):
                    tile = map_manager.get_tile(x=center+dx, y=y)
                    tile.terrain_id = TerrainId.WATER_SHALLOW.value
            """,

            "middle_east": """
            MIDDLE EAST TERRAIN PATTERN:
            - Base terrain: TerrainId.DIRT_1, TerrainId.DIRT_3, TerrainId.DESERT_SAND (edges)
            - Water: Rivers (Tigris/Euphrates style), irrigation channels
            - Trees: OtherInfo.TREE_PALM_FOREST along rivers, date palm groves
            - Features: River valleys surrounded by arid land, ancient ruins
            - Resources: GOLD_MINE in hills, fertile river banks
            - Atmosphere: Ancient civilization, contrast between river valley and desert

            Example river valley:
            # Arid terrain as base
            for x in range(0, map_size):
                for y in range(0, map_size):
                    tile = map_manager.get_tile(x=x, y=y)
                    tile.terrain_id = TerrainId.DIRT_3.value
            # Fertile river valley through center
            river_x = center
            for y in range(0, map_size):
                for dx in range(-8, 9):
                    tile = map_manager.get_tile(x=river_x+dx, y=y)
                    if abs(dx) < 2:
                        tile.terrain_id = TerrainId.WATER_SHALLOW.value
                    elif abs(dx) < 6:
                        tile.terrain_id = TerrainId.GRASS_1.value  # Fertile banks
            """
        }
        return templates.get(region, "# Use default terrain (grass with scattered features)")

    def _get_civ_template(self, player_civ: str, enemy_civ: str) -> str:
        """Return building style instructions for civilizations"""
        civ_styles = {
            "western_european": """
            WESTERN EUROPEAN STYLE (Franks, Britons, Teutons):
            - Camps: BuildingInfo.PAVILION_A, BuildingInfo.TENT_A, BuildingInfo.TENT_B
            - Religious: BuildingInfo.MONASTERY (stone churches)
            - Decorations: OtherInfo.FLAG_A, OtherInfo.TORCH_A, OtherInfo.ROMAN_RUINS
            - Military: Stone CASTLE, GUARD_TOWER, FORTIFIED_WALL
            - Civilian: TOWN_CENTER with clustered HOUSE, MARKET
            - Heroes: HeroInfo.JOAN_OF_ARC, HeroInfo.WILLIAM_THE_CONQUEROR, HeroInfo.RICHARD_THE_LIONHEART
            """,

            "eastern_european": """
            EASTERN EUROPEAN STYLE (Slavs, Byzantines):
            - Camps: BuildingInfo.PAVILION_B, BuildingInfo.TENT_C
            - Religious: BuildingInfo.MONASTERY (orthodox style)
            - Decorations: OtherInfo.FLAG_B, OtherInfo.BONFIRE, OtherInfo.TORCH_A
            - Military: Stone fortifications, KEEP, thick walls
            - Civilian: Fortified TOWN_CENTER, walled compounds
            - Heroes: HeroInfo.CONSTANTINE_XI (if available)
            """,

            "middle_eastern": """
            MIDDLE EASTERN STYLE (Saracens, Persians, Berbers):
            - Camps: BuildingInfo.PAVILION_C, BuildingInfo.TENT_D, BuildingInfo.TENT_E
            - Religious: BuildingInfo.MOSQUE (if available) or MONASTERY
            - Decorations: OtherInfo.FLAG_D, OtherInfo.TORCH_A, OtherInfo.BONFIRE
            - Military: Curved walls, CASTLE with desert aesthetic
            - Civilian: Courtyard-style buildings, MARKET prominence
            - Heroes: HeroInfo.SALADIN, HeroInfo.YODIT (if available)
            - Units: CAMEL_RIDER, MAMELUKE, CAVALRY_ARCHER
            """,

            "central_asian": """
            CENTRAL ASIAN STYLE (Mongols, Cumans, Tatars):
            - Camps: BuildingInfo.YURT_A, BuildingInfo.YURT_B, BuildingInfo.YURT_C, BuildingInfo.YURT_D
            - NO permanent religious buildings (nomadic)
            - Decorations: OtherInfo.BONFIRE, OtherInfo.FLAG_B, animal pens
            - Military: Minimal fortifications, mobile camps
            - Civilian: Yurt clusters, no permanent towns
            - Heroes: HeroInfo.GENGHIS_KHAN, HeroInfo.SUBOTAI (if available)
            - Units: CAVALRY_ARCHER, MANGUDAI, LIGHT_CAVALRY, SCOUT_CAVALRY

            Example nomad camp:
            camp_x, camp_y = quarter, center
            # Central bonfire
            unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.BONFIRE.ID, x=camp_x, y=camp_y)
            # Ring of yurts
            for i in range(6):
                angle = i * 60
                yx = camp_x + int(5 * math.cos(math.radians(angle)))
                yy = camp_y + int(5 * math.sin(math.radians(angle)))
                yurt_type = [BuildingInfo.YURT_A, BuildingInfo.YURT_B, BuildingInfo.YURT_C][i % 3]
                unit_manager.add_unit(PlayerId.TWO, unit_const=yurt_type.ID, x=yx, y=yy)
            """,

            "east_asian": """
            EAST ASIAN STYLE (Chinese, Japanese, Koreans, Vietnamese):
            - Camps: BuildingInfo.PAVILION_A (pagoda-like), unique architecture
            - Religious: BuildingInfo.MONASTERY (temple style)
            - Decorations: OtherInfo.FLAG_A, OtherInfo.TORCH_A
            - Military: Walled compounds, GUARD_TOWER, geometric layouts
            - Civilian: Ordered city layouts, walls around districts
            - Heroes: Use appropriate regional heroes
            - Units: CHU_KO_NU, SAMURAI (civ-specific)
            """,

            "african": """
            AFRICAN STYLE (Malians, Ethiopians):
            - Camps: BuildingInfo.PAVILION_B, BuildingInfo.TENT_A
            - Religious: BuildingInfo.MONASTERY (unique architecture)
            - Decorations: OtherInfo.FLAG_D, OtherInfo.BONFIRE, OtherInfo.TORCH_A
            - Military: Mud-brick walls, unique tower designs
            - Civilian: MARKET prominence (trade focus), TOWN_CENTER
            - Heroes: HeroInfo.SUNDJATA (if available)
            - Terrain: Savanna grass, acacia-style trees
            """
        }

        result = ""
        if player_civ and player_civ in civ_styles:
            result += f"\nPLAYER BUILDING STYLE:\n{civ_styles[player_civ]}"
        if enemy_civ and enemy_civ in civ_styles:
            result += f"\nENEMY BUILDING STYLE:\n{civ_styles[enemy_civ]}"
        return result if result else "# Use default building styles"
    
    def build_scenario(self, code: str, output_path: str) -> ExecutionOutcome:
        """Execute generated scenario code and return a structured outcome.

        The generated program's own write_to_file(...) path is rewritten to
        output_path so the .aoe2scenario lands where the caller expects. Runs in
        a subprocess with a unique temp filename (safe for concurrent
        candidates/models). stdout and stderr are always captured.
        """
        try:
            output_dir = Path(output_path).parent
            if str(output_dir):
                output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return ExecutionOutcome(ok=False, returncode=-1, stdout="",
                                    stderr=f"Could not create output dir: {e}")

        # Force the generated program to write to the requested path. Use forward
        # slashes so backslashes in a Windows path don't create invalid escapes
        # inside the generated string literal.
        safe_path = str(output_path).replace("\\", "/")
        code = re.sub(r'write_to_file\(["\'].*?["\']\)',
                      f'write_to_file("{safe_path}")', code)

        temp_file = f"temp_scenario_{uuid.uuid4().hex}.py"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                f.write(code)
            logger.info("Executing generated scenario code...")
            # Force UTF-8 for the child's stdout/stderr and for our own decoding
            # so non-ASCII output (emoji, accented names) can't crash the reader
            # thread on non-UTF-8 system locales (e.g. Windows cp949/cp1252).
            child_env = dict(os.environ, PYTHONIOENCODING="utf-8")
            result = subprocess.run([sys.executable, temp_file],
                                    capture_output=True, text=True, timeout=120,
                                    encoding="utf-8", errors="replace",
                                    env=child_env)
            ok = result.returncode == 0
            if ok:
                logger.info(f"Scenario generated successfully: {output_path}")
            else:
                logger.error(f"Scenario execution failed (rc={result.returncode})")
            return ExecutionOutcome(ok=ok, returncode=result.returncode,
                                    stdout=result.stdout or "",
                                    stderr=result.stderr or "")
        except subprocess.TimeoutExpired as e:
            return ExecutionOutcome(ok=False, returncode=-1, stdout="",
                                    stderr=f"Execution timed out after {e.timeout}s")
        except Exception as e:
            return ExecutionOutcome(ok=False, returncode=-1, stdout="",
                                    stderr=f"Failed to execute scenario: {e}")
        finally:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except OSError:
                    pass

    def save_scenario(self, code: str, output_path: str) -> bool:
        """Save and execute the generated scenario code. Returns True on success.

        Thin backward-compatible wrapper over build_scenario(); use
        build_scenario() directly when you need the captured stderr/returncode.
        """
        return self.build_scenario(code, output_path).ok

    def validate_scenario_code_detailed(self, code: str, min_triggers: int = 20):
        """Validate playability PRECONDITIONS of generated code (no game sim).

        Returns (ok, detail, trigger_count). Historical fidelity is out of scope
        here - it is assessed separately by human annotation. Hard checks
        (ok=False): the code parses, required imports are present, the scenario
        is created and saved, at least one trigger is created, and at least one
        declare_victory effect exists (the cheap "an objective / win-condition
        is created" proxy - decision D3). The min_triggers count is a soft
        warning only.
        """
        # Cheap syntax check - catches a whole class of would-be execution errors.
        try:
            ast.parse(code)
        except SyntaxError as e:
            return False, f"SyntaxError: {e}", 0

        required_imports = ["AoE2DEScenario", "PlayerId", "UnitInfo", "BuildingInfo"]
        for import_name in required_imports:
            if import_name not in code:
                return False, f"Missing required import: {import_name}", 0

        if ("AoE2DEScenario.from_default()" not in code
                and "AoE2DEScenario.from_file(" not in code):
            return False, "Missing scenario creation (AoE2DEScenario.from_default())", 0

        if "write_to_file" not in code:
            return False, "Missing scenario save operation (write_to_file)", 0

        trigger_count = code.count("add_trigger(")
        if trigger_count < 1:
            return False, "No triggers created (need at least one add_trigger)", trigger_count

        if "declare_victory(" not in code:
            return False, "No objective created (need at least one declare_victory effect)", trigger_count

        # Soft warning only - low trigger counts are allowed through.
        if trigger_count < min_triggers:
            logger.warning(
                f"Low trigger count: found {trigger_count}, expected >= {min_triggers}")
        else:
            logger.info(f"Trigger count validated: {trigger_count} triggers found")

        return True, "ok", trigger_count

    def validate_scenario_code(self, code: str, min_triggers: int = 20) -> bool:
        """Validate playability preconditions of generated code. Returns bool.

        Checks playability preconditions ONLY (syntax, structure, at least one
        trigger and one victory condition) - NOT historical fidelity, which is
        assessed separately by human annotation. Thin, backward-compatible
        wrapper over validate_scenario_code_detailed().
        """
        try:
            ok, detail, _ = self.validate_scenario_code_detailed(code, min_triggers)
            if not ok:
                logger.warning(f"Validation failed: {detail}")
            return ok
        except Exception as e:
            logger.error(f"Code validation failed: {e}")
            return False

    # -----------------------------------------------------------------------
    # High-level orchestration: generate -> validate -> execute, with a
    # self-repair loop and optional best-of-N. Produces exactly one terminal
    # outcome per attempt, writes a metadata sidecar, and (optionally) appends
    # one JSONL line per attempt to a per-run results log.
    # -----------------------------------------------------------------------
    def generate(self, config: ScenarioConfig, results_log: str = None,
                 run_id: str = None) -> GenerationResult:
        """Run the full pipeline for one ScenarioConfig and return the result.

        For best_of > 1, generates candidates until one builds successfully (or
        the budget is exhausted) and returns the first success, else the last
        candidate's terminal result. Every attempt - including self-repair
        retries - is logged to results_log (JSONL) when provided, and a metadata
        sidecar is written next to the scenario for the chosen result.
        """
        run_id = run_id or new_run_id()
        model = api_config.resolve_model(config.model)
        temperature = config.temperature
        max_tokens = config.max_tokens
        reach = config.reachability_prompting
        best_of = max(1, config.best_of)

        chosen = None
        for candidate in range(1, best_of + 1):
            result = self._generate_one_candidate(
                config, model, temperature, max_tokens, reach,
                run_id, candidate, results_log)
            chosen = result  # keep the latest; a success breaks below
            if result.outcome == "success":
                break

        self._write_sidecar(config, chosen)
        return chosen

    def _generate_one_candidate(self, config, model, temperature, max_tokens,
                                reachability_prompting, run_id, candidate,
                                results_log) -> GenerationResult:
        """One candidate: initial generation then up to max_repair_attempts
        self-repair retries. Returns the candidate's terminal result."""
        max_attempts = 1 + max(0, config.max_repair_attempts)
        code = None
        error_detail = None
        result = None

        for attempt in range(1, max_attempts + 1):
            # introspection kind that produced THIS attempt's code (None for the
            # initial generation and for repairs where no parser API error was
            # recognized). Recorded on every result line for this attempt.
            introspection = None
            # 1) Produce code (initial generation, then repair).
            try:
                if attempt == 1:
                    code = self.generate_scenario(
                        config, model=model, temperature=temperature,
                        max_tokens=max_tokens,
                        reachability_prompting=reachability_prompting)
                else:
                    # Pull ground truth from the installed parser for the failure
                    # so repair picks a valid name/signature instead of guessing.
                    intro_block, introspection = _introspect_error(error_detail)
                    repair_detail = (error_detail or "") + intro_block
                    if introspection:
                        logger.info(f"Introspection ({introspection}) added to repair prompt "
                                    f"for '{config.title}' (candidate {candidate})")
                    logger.info(
                        f"Self-repair attempt {attempt - 1}/{config.max_repair_attempts} "
                        f"for '{config.title}' (candidate {candidate})")
                    code = self.api.repair_scenario_code(
                        code, repair_detail, model=model, temperature=temperature,
                        max_tokens=max_tokens,
                        reachability_prompting=reachability_prompting)
            except Exception as e:
                # An API failure is not repairable by fixing code - record and stop.
                result = self._mk_result(
                    "api_error", config, model, temperature, max_tokens,
                    reachability_prompting, run_id, candidate, attempt, error=str(e),
                    introspection=introspection)
                self._log_attempt(results_log, result)
                break

            # 2) Validate playability preconditions. The soft trigger-count floor
            #    depends on prompt_style: freeform lets the model choose the count.
            min_trig = (FREEFORM_MIN_TRIGGERS if config.prompt_style == "freeform"
                        else TEMPLATED_MIN_TRIGGERS)
            ok, detail, trig = self.validate_scenario_code_detailed(code, min_triggers=min_trig)
            if not ok:
                result = self._mk_result(
                    "validation_failure", config, model, temperature, max_tokens,
                    reachability_prompting, run_id, candidate, attempt,
                    trigger_count=trig, code=code, validation_detail=detail,
                    introspection=introspection)
                self._log_attempt(results_log, result)
                error_detail = "Validation failed: " + detail
                continue

            # Passed the hard gates. If it is below the soft floor, tag
            # validation_detail (not just the log) so below-floor rates are
            # queryable per prompt_style from the results log.
            soft_note = (f"below soft trigger floor: {trig} < {min_trig} (validation passed)"
                         if trig < min_trig else "")

            # 3) Execute.
            exe = self.build_scenario(code, config.output_path)
            if exe.ok:
                result = self._mk_result(
                    "success", config, model, temperature, max_tokens,
                    reachability_prompting, run_id, candidate, attempt,
                    trigger_count=trig, code=code, validation_detail=soft_note,
                    introspection=introspection)
                self._log_attempt(results_log, result)
                break
            else:
                result = self._mk_result(
                    "execution_error", config, model, temperature, max_tokens,
                    reachability_prompting, run_id, candidate, attempt,
                    trigger_count=trig, code=code, stderr=exe.stderr,
                    validation_detail=soft_note, introspection=introspection)
                self._log_attempt(results_log, result)
                error_detail = "Execution error (stderr):\n" + (exe.stderr or "").strip()
                continue

        return result

    def _mk_result(self, outcome, config, model, temperature, max_tokens,
                   reachability_prompting, run_id, candidate, attempt,
                   trigger_count=0, code="", stderr="", validation_detail="",
                   error="", introspection=None) -> GenerationResult:
        return GenerationResult(
            outcome=outcome, title=config.title, scenario_type=config.scenario_type,
            model=model, temperature=temperature, max_tokens=max_tokens,
            reachability_prompting=reachability_prompting,
            output_path=config.output_path, run_id=run_id, candidate=candidate,
            attempts=attempt, trigger_count=trigger_count, code=code,
            stderr=stderr, validation_detail=validation_detail, error=error,
            prompt_style=config.prompt_style, introspection=introspection)

    def _log_attempt(self, results_log, result: GenerationResult):
        if not results_log:
            return
        append_result(results_log, {
            "run_id": result.run_id,
            "candidate": result.candidate,
            "attempt": result.attempts,
            "outcome": result.outcome,
            "title": result.title,
            "scenario_type": result.scenario_type,
            "model": result.model,
            "temperature": result.temperature,
            "max_tokens": result.max_tokens,
            "reachability_prompting": result.reachability_prompting,
            "prompt_style": result.prompt_style,
            "trigger_count": result.trigger_count,
            "output_path": result.output_path,
            "validation_detail": result.validation_detail or None,
            "stderr": result.stderr or None,
            "error": result.error or None,
            "introspection": result.introspection,
        })

    def _write_sidecar(self, config: ScenarioConfig, result: GenerationResult):
        if result is None:
            return
        meta = {
            "title": config.title,
            "description": config.description,
            "scenario_type": config.scenario_type,
            "map_size": config.map_size,
            "players": config.players,
            "difficulty": config.difficulty,
            "region": config.region,
            "player_civ": config.player_civ,
            "enemy_civ": config.enemy_civ,
            "wikipedia_url": config.wikipedia_url,
            "reachability_prompting": result.reachability_prompting,
            "prompt_style": config.prompt_style,
            "best_of": config.best_of,
            "max_repair_attempts": config.max_repair_attempts,
            "model": result.model,
            "temperature": result.temperature,
            "max_tokens": result.max_tokens,
            "generator_version": GENERATOR_VERSION,
            "outcome": result.outcome,
            "run_id": result.run_id,
            "candidate": result.candidate,
            "attempts": result.attempts,
            "trigger_count": result.trigger_count,
            "output_path": config.output_path,
        }
        try:
            write_sidecar(config.output_path, meta)
        except Exception as e:
            logger.warning(f"Could not write metadata sidecar: {e}")


def main():
    """Main function to demonstrate the scenario generator"""
    
    # Get API key from environment variable
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("Please set the OPENROUTER_API_KEY environment variable")
        return
    
    # Initialize the generator
    generator = ScenarioGenerator(api_key)
    
    # Example scenario configurations showcasing all scenario types
    scenarios = [
        # ESCORT scenario (Joan of Arc style)
        ScenarioConfig(
            title="The Road to Orleans",
            description="Escort Joan of Arc through enemy territory to reach the besieged city of Orleans",
            scenario_type="escort",
            map_size=144,
            players=5,
            difficulty="medium",
            output_path="road_to_orleans.aoe2scenario"
        ),
        # DIPLOMACY scenario (Genghis Khan style)
        ScenarioConfig(
            title="Uniting the Clans",
            description="Travel across the steppes to unite the scattered Mongol tribes under your banner",
            scenario_type="diplomacy",
            map_size=168,
            players=7,
            difficulty="medium",
            output_path="uniting_the_clans.aoe2scenario"
        ),
        # DEFENSE scenario (Siege defense style)
        ScenarioConfig(
            title="The Siege of Constantinople",
            description="Defend the great city of Constantinople against waves of Ottoman invaders",
            scenario_type="defense",
            map_size=120,
            players=4,
            difficulty="hard",
            output_path="constantinople_siege.aoe2scenario"
        ),
        # CONQUEST scenario (Genghis Khan style)
        ScenarioConfig(
            title="Breaking the Great Wall",
            description="Lead your forces to breach the mighty fortifications and conquer the Jin Empire",
            scenario_type="conquest",
            map_size=200,
            players=4,
            difficulty="hard",
            output_path="breaking_the_wall.aoe2scenario"
        ),
        # BATTLE scenario (Direct combat)
        ScenarioConfig(
            title="The Battle of Hastings",
            description="Command the Norman forces against Harold's Saxon army for control of England",
            scenario_type="battle",
            map_size=120,
            players=2,
            difficulty="medium",
            output_path="battle_of_hastings.aoe2scenario"
        ),
        # STORY scenario (Narrative-driven)
        ScenarioConfig(
            title="The Rise of Saladin",
            description="Follow Saladin's journey from young warrior to Sultan, uniting Egypt and facing the Crusaders",
            scenario_type="story",
            map_size=144,
            players=4,
            difficulty="easy",
            output_path="rise_of_saladin.aoe2scenario"
        )
    ]
    
    # Generate scenarios
    for config in scenarios:
        try:
            print(f"\nGenerating scenario: {config.title}")
            
            # Generate the scenario code
            generated_code = generator.generate_scenario(config)
            
            # Validate the code
            if not generator.validate_scenario_code(generated_code):
                print(f"Warning: Generated code may have issues for {config.title}")
            
            # Save and execute the scenario
            if generator.save_scenario(generated_code, config.output_path):
                print(f"Successfully generated: {config.output_path}")
            else:
                print(f"Failed to generate: {config.title}")
                
        except Exception as e:
            print(f"Error generating {config.title}: {e}")

if __name__ == "__main__":
    main() 