# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This project uses OpenRouter API to generate Age of Empires 2 Definitive Edition scenario files via the AoE2ScenarioParser library. The generator prompts an LLM to produce Python code that creates complete scenarios with units, buildings, triggers, and objectives.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Set API key (required)
set OPENROUTER_API_KEY=your_key_here    # Windows
export OPENROUTER_API_KEY=your_key_here # Linux/Mac

# Run the David & Goliath scenario (pre-built example)
python "david&goliath_scenario1.py"

# Generate scenarios using the API (thin CLI over ScenarioGenerator.generate())
python create_scenario.py       # Single scenario (no args = default "Flight to Chinon" escort)
python create_scenario.py --model opus-4.8 --scenario-type battle \
    --title "Tours" --description "Franks vs Umayyads, 732"
python create_scenario.py --no-reachability --best-of-n 3  # baseline prompt, keep first of 3 that builds
python create_scenario.py --dry-run                        # preview resolved config, no API call
python create_scenario.py --batch specs.jsonl             # many scenarios from a JSONL file (see below)
python create_scenario.py --batch specs.jsonl --yes       # skip the batch confirmation prompt (scripting)
# Every run writes a .meta.json sidecar next to each scenario and appends one line
# per attempt to output/results.jsonl. Exit code is 0 only if ALL requested scenarios
# succeeded (2 for a malformed batch file), so it composes in scripts.
python example_usage.py         # Multiple example scenarios
python generator.py             # Main generator with examples (runs all 6 scenario types)

# Run the control vs treatment experiment (both arms share one merged generator)
python run_experiment.py                              # default model, control + treatment
python run_experiment.py --models sonnet-5,opus-4.8   # sweep multiple models
python run_experiment.py --arms treatment --best-of 3 # treatment only, best-of-3
# Outcomes are appended to output/results.jsonl; a .meta.json sidecar sits next to each scenario.

# Test API connection
python test_api.py

# View scenario contents
python view_scenario.py <scenario_file>    # View any .aoe2scenario file

# Extract scenarios from campaign files
python extract_campaign.py <campaign_file>  # Extracts .aoe2scenario files from .aoe2campaign
```

### `create_scenario.py` batch mode

`--batch <file>` runs many scenarios sequentially through `generate()`, sharing one `run_id`,
continuing past per-scenario failures. The file is **JSONL, one spec per line**; blank lines and
`#`-comment lines are ignored. Only `title` is required. Each spec inherits the CLI generation flags
(`--model`, `--temperature`, `--max-tokens`, `--reachability/--no-reachability`, `--best-of-n`,
`--max-repair-attempts`, `--prompt-style`) as batch-wide defaults and may override **any** config field. A malformed
line (bad JSON / not an object / unknown field / missing title) is reported with its line number and
aborts the whole batch before any API call (exit 2). Before the first API call, batch mode prints the
scenario count and resolved model(s) and asks for confirmation unless `--yes` is passed.

Example `specs.jsonl`:

```jsonl
# battles use the CLI-level model; defense overrides best_of; conquest overrides model + difficulty
{"title": "The Battle of Tours", "description": "Franks vs Umayyads, 732", "scenario_type": "battle"}
{"title": "The Siege of Constantinople", "scenario_type": "defense", "best_of": 3}
{"title": "Alexander's Persian Campaign", "scenario_type": "conquest", "model": "opus-4.8", "difficulty": "hard"}
{"title": "Joan of Arc's Journey", "description": "Domremy to Orleans", "scenario_type": "story", "reachability_prompting": false}
```

At the end, batch mode prints a per-scenario table (outcome + attempts) plus aggregate rates.
Successes partition into three mutually exclusive buckets so the two rescue mechanisms stay separable
— `first-attempt` (candidate 1, attempt 1), `repair-loop rescue` (candidate 1, attempts > 1), and
`best-of-N rescue` (candidate > 1):

```text
=== Batch summary (run_id run_ab12cd34ef56) ===
  #  Scenario                            Type        Outcome             Att  Cand
---  ----------------------------------  ----------  ------------------  ---  ----
  1  The Battle of Tours                 battle      success               1     1
  2  The Siege of Constantinople         defense     success               3     1
  3  Alexander's Persian Campaign        conquest    success               2     2
  4  The Defense of Vienna               defense     execution_error       4     1

Aggregate over 4 scenario(s):
  succeeded:              3/4  ( 75.0%)
    first-attempt:        1/4  ( 25.0%)   [candidate 1, attempt 1]
    repair-loop rescue:   1/4  ( 25.0%)   [candidate 1, attempts > 1]
    best-of-N rescue:     1/4  ( 25.0%)   [candidate > 1]
  failed:                 1/4  ( 25.0%)
```

## Architecture

### Core Flow

1. User creates a `ScenarioConfig` (title, description, map_size, players, difficulty, scenario_type, output_path, optional wikipedia_url/region/civ, plus generation params: `model`, `temperature`, `max_tokens`, `reachability_prompting`, `best_of`, `max_repair_attempts`, `prompt_style`)
2. `ScenarioGenerator.generate(config, results_log=...)` orchestrates the whole pipeline (this is the funnel; `generate_scenario()` is still the lower-level "return raw code" method)
3. `generate_scenario()` selects a template by `scenario_type`, builds the system prompt (base + optional reachability block), and calls the OpenRouter model
4. Returned Python code is extracted from markdown fences and validated via `validate_scenario_code_detailed()` (syntax parse, imports, scenario creation, `write_to_file`, ≥1 trigger, ≥1 `declare_victory`)
5. Valid code is executed via `build_scenario()` in a subprocess (unique temp file; the code's `write_to_file(...)` path is rewritten to `output_path`)
6. On `validation_failure` or `execution_error`, the **self-repair loop** sends the failing code + captured stderr/detail back to the model and retries (up to `max_repair_attempts`). When the failure is a parser API error (`ImportError`/`ModuleNotFoundError`, `AttributeError`, `TypeError`, or `NameError`), `_introspect_error()` pulls **ground truth from the installed AoE2ScenarioParser** — the real importable names, object `dir()`, or `inspect.signature` — and appends it (capped ~30 lines) to the repair prompt, so repair picks a valid name/signature instead of guessing. Which kind fired (`importerror|attributeerror|typeerror|nameerror`, else `null`) is recorded per attempt in the results log.
7. With `best_of > 1`, up to N candidates are generated; the first that builds is kept
8. Every attempt is appended to the per-run **results log** (JSONL); a **metadata sidecar** JSON is written next to the `.aoe2scenario`

Each attempt ends in exactly one recorded outcome: `success` | `validation_failure` | `execution_error` | `api_error`.

### Core Modules

- **`generator.py`**: Main module with:
  - `OpenRouterAPI`: API communication. `generate_scenario_code(prompt, model, temperature, max_tokens, reachability_prompting)` and `repair_scenario_code(failing_code, error_detail, ...)` for the self-repair loop. `REACHABILITY_ANALYSIS_BLOCK` is appended to the system prompt when `reachability_prompting` is True.
  - `ScenarioGenerator`: template selection + orchestration.
    - `generate(config, results_log=None, run_id=None) -> GenerationResult`: the funnel (generate → validate → execute, self-repair, best-of-N, sidecar, JSONL logging)
    - `generate_scenario(config, model=..., temperature=..., max_tokens=..., reachability_prompting=...) -> str`: returns raw code (public API preserved; new optional overrides)
    - `validate_scenario_code_detailed(code) -> (ok, detail, trigger_count)`; `validate_scenario_code(code) -> bool` (backward-compatible wrapper)
    - `build_scenario(code, output_path) -> ExecutionOutcome` (structured: ok/returncode/stdout/stderr); `save_scenario(code, output_path) -> bool` (wrapper)
  - `ScenarioConfig`: dataclass for scenario + generation parameters
  - `ExecutionOutcome`, `GenerationResult`: structured results

- **`api_config.py`**: `MODEL_REGISTRY` (friendly key → pinned OpenRouter slug), `resolve_model()`, `DEFAULT_MODEL` (current Claude Sonnet: `anthropic/claude-sonnet-5-20260630`), `DEFAULT_TEMPERATURE=0.7`, `DEFAULT_MAX_TOKENS=32000`, `REQUEST_TIMEOUT=600`. Frontier slugs are pinned dated snapshots captured from OpenRouter's live list (2026-07-17); legacy 2024 entries are retained verbatim for reproducibility (no longer served by OpenRouter).

- **`provenance.py`**: `write_sidecar()`, `append_result()`, `new_run_id()`, `utc_now_iso()` (stdlib only) — the metadata sidecar and JSONL results log.

- **`create_scenario.py`**: Thin CLI entry point (no generation logic — just argparse, batch-spec loading, calling `generate()`, and reporting). Runs with no args (default "Flight to Chinon" escort) or via CLI flags. Single-scenario and generation flags: `--model`, `--temperature`, `--max-tokens`, `--reachability/--no-reachability`, `--best-of-n` (alias `--best-of`), `--max-repair-attempts`, `--prompt-style` (`templated`|`freeform`), `--scenario-type`, `--title`, `--description`, `--map-size`, `--players`, `--difficulty`, `--region`, `--player-civ`, `--enemy-civ`, `--wikipedia-url`, `--output-dir` (default `output`; filenames derived from a title slug — in batch mode the slug also embeds `prompt_style`, plus a numeric suffix on any remaining same-title/same-style collision, so specs never overwrite each other), `--output` (explicit full-path override), `--results-log` (default `output/results.jsonl`). Modes: `--batch <file>` (JSONL, see "batch mode" above), `--dry-run` (print resolved config / parsed specs, no API call), `--yes`/`-y` (skip the batch confirmation prompt). Exit code is 0 only if every requested scenario reached `success`, else non-zero (2 for a malformed batch file).

- **`run_experiment.py`**: Control/treatment runner over one merged generator (`control` = `reachability_prompting=False`, `treatment` = `True`), `temperature=0.0` by default. Flags: `--model`, `--models` (sweep), `--arms`, `--best-of`, `--max-repair-attempts`, `--temperature`, `--results-log`.

- **`reachability_research/generator.py`, `reachability_research/generator_reachability.py`**: FROZEN originals of the control and treatment generators, retained for reproducibility. Superseded by the top-level `generator.py` + the `reachability_prompting` flag; no longer imported by `run_experiment.py`. Do not edit.

### Generation Parameters, Flags & Provenance

**`ScenarioConfig` generation fields** (all optional, backward-compatible defaults):

| Field | Default | Meaning |
|-------|---------|---------|
| `model` | `None` → `api_config.DEFAULT_MODEL` | Friendly `MODEL_REGISTRY` key or raw OpenRouter slug |
| `temperature` | `0.7` | Sampling temperature (default unchanged; `run_experiment.py` sets `0.0`) |
| `max_tokens` | `32000` | Completion cap (raised from 16000 so large multi-trigger scenarios aren't truncated) |
| `reachability_prompting` | `True` | Append reachability guidance to the system prompt (see below). `False` = baseline/control prompt |
| `best_of` | `1` | Generate N candidates; keep the first that builds successfully |
| `max_repair_attempts` | `3` | Self-repair retries after a `validation_failure` / `execution_error` |
| `prompt_style` | `"templated"` | Ablation lever: `"templated"` uses the per-`scenario_type` template (rigid trigger count/structure); `"freeform"` skips it for a short generic instruction and lets the model choose the trigger structure/count. See below. |

**Reachability prompting (control vs treatment).** `reachability_prompting=True` appends `REACHABILITY_ANALYSIS_BLOCK` to the system prompt: the four failure modes (resource dead end, composition imbalance, positional trap, timing collapse), a checklist, a required `# REACHABILITY ANALYSIS:` comment header, and — added in the merge — explicit guidance to **prefer `destroy_object` (on a stored reference) over `objects_in_area(quantity=0)` for win/lose conditions** (an `objects_in_area==0` victory can become permanently unreachable if a single enemy garrisons, converts, or flees). `False` reproduces the original baseline prompt. Note: the merged base prompt also carries unconditional bug-fixes (builtin-shadowing warning, expanded unit datasets, `RUINS`→`ROMAN_RUINS`), so both arms benefit from those.

**Prompt-style ablation (`prompt_style`).** The per-`scenario_type` templates in `_load_templates()` are the *user message* and prescribe a rigid trigger count and per-section breakdown (e.g. battle = "EXACTLY 25-30 TRIGGERS"). `prompt_style="freeform"` (constant `FREEFORM_PROMPT_TEMPLATE` in `generator.py`) **skips the scenario-type template** and instead sends a short generic instruction — state the title/description/map/players/difficulty and require a complete, playable scenario with dialogue, clear objectives, and reachable victory **and** defeat, letting the model choose the trigger structure and count it judges fit for the episode (soft minimum only: setup + narrative + objectives + win/loss; no fixed number). Everything else is **identical** across modes — the system prompt (base + reachability block), the region/civ templates and all parser-usage rules — so the ablation isolates the scenario-type template alone. In freeform mode the soft trigger-count floor drops from `TEMPLATED_MIN_TRIGGERS=20` to `FREEFORM_MIN_TRIGGERS=4`; the **hard** validation gates (≥1 trigger, ≥1 `declare_victory`) are unchanged. When a scenario passes the hard gates but falls below the soft floor, that is recorded in the attempt's `validation_detail` (e.g. `"below soft trigger floor: 3 < 4 (validation passed)"`), so below-floor rates are queryable per mode from the results log. `prompt_style` is recorded in both the sidecar and every results.jsonl line.

**Model registry** (`api_config.MODEL_REGISTRY`; `resolve_model(key_or_slug)`): frontier keys are pinned to exact dated OpenRouter snapshots; legacy keys are retained verbatim for provenance (no longer served).

| Friendly key | Slug | Notes |
|--------------|------|-------|
| `sonnet-5` | `anthropic/claude-sonnet-5-20260630` | **DEFAULT_MODEL** |
| `opus-4.8` | `anthropic/claude-opus-4.8-20260528` | current Opus-class |
| `fable-5` | `anthropic/claude-fable-5-20260609` | most capable |
| `claude-3.5-sonnet`, `claude-3-opus`, `gpt-4`, `llama-3.1-70b`, `gemini-pro` | (legacy 2024 slugs) | retained for reproducibility; will 404 today |

A raw slug not in the registry is passed through unchanged, so any OpenRouter model works.

**Metadata sidecar** — `<output_path>.meta.json`, written next to every generated scenario:

```json
{
  "title": "...", "description": "...", "scenario_type": "battle",
  "map_size": 120, "players": 2, "difficulty": "easy",
  "region": null, "player_civ": null, "enemy_civ": null, "wikipedia_url": null,
  "reachability_prompting": true, "prompt_style": "templated", "best_of": 1, "max_repair_attempts": 3,
  "model": "anthropic/claude-sonnet-5-20260630", "temperature": 0.0, "max_tokens": 32000,
  "generator_version": "2.0", "outcome": "success",
  "run_id": "run_ab12cd34ef56", "candidate": 1, "attempts": 2, "trigger_count": 27,
  "output_path": "output/treatment/battle_of_tours.aoe2scenario",
  "timestamp_utc": "2026-07-17T12:34:56Z"
}
```

**Results log** — JSONL, append-only (default `output/results.jsonl`). One line per **attempt** (self-repair retries included), so playability rates are computable per model / arm / scenario_type by grouping:

```json
{"run_id":"run_ab12cd34ef56","candidate":1,"attempt":2,"outcome":"success",
 "title":"The Battle of Tours","scenario_type":"battle",
 "model":"anthropic/claude-sonnet-5-20260630","temperature":0.0,"max_tokens":32000,
 "reachability_prompting":true,"prompt_style":"templated","trigger_count":27,
 "output_path":"output/treatment/battle_of_tours.aoe2scenario",
 "validation_detail":null,"stderr":null,"error":null,"introspection":null,"timestamp_utc":"2026-07-17T12:34:56Z"}
```

The run's terminal outcome for a `(run_id, candidate)` is its highest `attempt` line. Outcomes: `success` (built), `validation_failure` (failed `validate_scenario_code_detailed`, not executed), `execution_error` (subprocess returncode ≠ 0, `stderr` captured), `api_error` (model call raised; not code-repairable).

> **Note:** validation checks **playability preconditions only** (syntax, structure, ≥1 trigger, ≥1 `declare_victory`). It does **not** simulate the game. **Historical fidelity** — the paper's core contribution — is assessed separately by human annotation and is out of scope for this codebase.

### Scenario Types (Templates in generator.py)

| Type | Pattern | Example |
|------|---------|---------|
| `battle` | Direct combat, military formations | Saladin Campaign style |
| `escort` | Protect hero traveling to destination | Joan of Arc Campaign style |
| `diplomacy` | Unite factions through quests/tribute | Genghis Khan Campaign style |
| `defense` | Survive waves of attackers | Siege defense patterns |
| `conquest` | Capture enemy bases progressively | Great Wall breach style |
| `story` | Narrative-driven with multiple acts | Combined patterns |

### AoE2ScenarioParser Patterns

```python
scenario = AoE2DEScenario.from_default()  # ALWAYS use from_default(), not from_file()
unit_manager = scenario.unit_manager
trigger_manager = scenario.trigger_manager
map_manager = scenario.map_manager

# Get map size FIRST for coordinate calculations
map_size = map_manager.map_size  # Default is 120
center = map_size // 2

# Add units - ALWAYS use .ID property
unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.MILITIA.ID, x=50, y=50)
unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.BARRACKS.ID, x=45, y=45)
unit_manager.add_unit(PlayerId.ONE, unit_const=HeroInfo.JOAN_OF_ARC.ID, x=60, y=60)
unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.GOLD_MINE.ID, x=30, y=30)

# Store unit references for triggers
hero = unit_manager.add_unit(PlayerId.ONE, unit_const=HeroInfo.LEONIDAS.ID, x=50, y=50)

# Create triggers with stored references
trigger = trigger_manager.add_trigger("Victory")
trigger.new_condition.destroy_object(unit_object=enemy.reference_id)
trigger.new_effect.display_instructions(display_time=10, message="Victory!")
trigger.new_effect.declare_victory(source_player=PlayerId.ONE, enabled=1)

scenario.write_to_file("output.aoe2scenario")
```

### Historical Accuracy: Regions and Civilizations

The generator supports historically accurate terrain and buildings through `region` and `player_civ`/`enemy_civ` parameters:

**Geographic Regions:**
| Region | Terrain | Trees | Features |
|--------|---------|-------|----------|
| `mediterranean` | Grass, dirt, beach | Palm, sparse | Coastlines, hills |
| `steppe` | Dry grass | Very sparse | Rolling hills, rocks |
| `northern_europe` | Grass, forest | Oak, dense | Rivers, marshes |
| `desert` | Sand, dirt | Palm at oases | Dunes, rocky outcrops |
| `east_asia` | Grass | Bamboo | Mountains, rivers |
| `middle_east` | Dirt, sand edges | Palm along rivers | River valleys, ruins |

**Civilization Styles:**
| Style | Camps | Military | Units |
|-------|-------|----------|-------|
| `western_european` | Pavilions, tents | Stone castles | Knights, crossbowmen |
| `eastern_european` | Pavilions | Thick walls, keeps | Infantry, cavalry |
| `middle_eastern` | Tents, pavilions | Curved walls | Camels, cavalry archers |
| `central_asian` | Yurts | Minimal fortifications | Light cavalry, horse archers |
| `east_asian` | Pavilions | Walled compounds | Unique regional units |
| `african` | Tents, pavilions | Mud-brick | Trade-focused |

**Example Usage:**
```python
config = ScenarioConfig(
    title="Battle of Manzikert",
    description="Byzantine vs Seljuk clash",
    scenario_type="battle",
    region="middle_east",
    player_civ="eastern_european",  # Byzantines
    enemy_civ="central_asian",       # Seljuks
    wikipedia_url="https://en.wikipedia.org/wiki/Battle_of_Manzikert"
)
```

### Critical Constraints

- **Coordinates**: Must be within 0 to map_size-1. Always calculate relative to `map_manager.map_size`
- **Unit constants**: Always use `.ID` property (e.g., `UnitInfo.MILITIA.ID`, not `UnitInfo.MILITIA`)
- **Player references**: Use `PlayerId.ONE`, `PlayerId.TWO`, `PlayerId.GAIA` - never strings
- **Trigger parameters**: Use `source_player` not `player`; all coordinates must be integers
- **Resources**: GAIA resources (gold, stone, forage, huntables) required near player starts

### Trigger Design: Timers vs Area Triggers

**Avoid timers for main objectives and story progression.** Players move at their own pace - timer-based events feel artificial and can frustrate players who explore or move cautiously.

| Use This | Not This | Why |
|----------|----------|-----|
| `bring_object_to_area` | `timer(120)` | Player controls pacing |
| `destroy_object` | `timer(300)` | Combat milestones are player-driven |
| `objects_in_area` | `timer(180)` | Detects actual unit positions |

**When timers ARE appropriate:**
- Opening narration (first 5-10 seconds to set the scene)
- Ambient dialogue that doesn't block progress
- Defense scenario wave spawns (time-based by design)
- Historical time pressure that's part of the narrative (e.g., "reach the city before the siege begins")

```python
# CORRECT - Player-driven progression
ambush = trigger_manager.add_trigger("[D3] Ambush")
ambush.new_condition.bring_object_to_area(
    unit_object=hero.reference_id, area_x1=50, area_y1=50, area_x2=60, area_y2=60)

# WRONG - Timer assumes player location
ambush = trigger_manager.add_trigger("[D3] Ambush")
ambush.new_condition.timer(timer=120)  # Player might not be there yet!
```

### Walls and Gates for AI Players

AI players can ONLY pass through gates they own. This is critical for scenarios with walled bases.

**Gate Ownership Rules:**
- Gates must be owned by the player whose units need to pass through
- Enemy AI bases with walls MUST have AI-owned gates so units can exit to attack
- Player-owned gates block enemy AI units (useful for defense scenarios)

```python
# CORRECT: AI owns gate to its own base - units can exit
enemy_gate = unit_manager.add_unit(PlayerId.TWO, unit_const=BuildingInfo.GATE_NORTH_TO_SOUTH.ID, x=50, y=50)

# WRONG: Player owns gate around enemy base - AI trapped forever!
# unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.GATE_NORTH_TO_SOUTH.ID, x=50, y=50)
```

**Gate Control Triggers:**
```python
# Delete gate to "breach" it
trigger.new_effect.remove_object(object_list_unit_id=gate.reference_id, source_player=PlayerId.TWO)

# Transfer gate ownership
trigger.new_effect.change_ownership(area_x1=48, area_y1=48, area_x2=52, area_y2=52,
                                    source_player=PlayerId.TWO, target_player=PlayerId.ONE)

# Make AI units patrol through their gate
trigger.new_effect.patrol(object_list_unit_id=UnitInfo.KNIGHT.ID, source_player=PlayerId.TWO,
                          location_x=target_x, location_y=target_y)
```

**Design Patterns:**
| Scenario Type | Wall/Gate Approach |
|--------------|-------------------|
| Defense | Player owns gates in defensive walls; attackers spawn outside |
| Battle | Each side owns gates to their own base |
| Conquest | Enemy owns gates; use triggers to delete/breach them |
| Escort | Use wall gaps or enemy-owned gates at chokepoints |

### Monkey Patch

`david&goliath_scenario1.py` includes a monkey patch for `int_to_bytes` to handle enum-to-int conversion. Apply this pattern if encountering `TypeError` with enum values:

```python
import AoE2ScenarioParser.helper.bytes_conversions
_original = AoE2ScenarioParser.helper.bytes_conversions.int_to_bytes
def _patched(integer, length, endian='little', signed=True):
    if hasattr(integer, 'value') and hasattr(integer, 'name'):
        integer = integer.value
    return _original(integer, length, endian, signed)
AoE2ScenarioParser.helper.bytes_conversions.int_to_bytes = _patched
```

## Generated Files

Scenario files (`.aoe2scenario`) go to user's AoE2 DE folder:
```
C:\Users\<USERNAME>\Games\Age of Empires 2 DE\<STEAM_ID>\resources\_common\scenario\
```

## Campaign Tools

### extract_campaign.py
Extracts individual `.aoe2scenario` files from `.aoe2campaign` container files.

```bash
python extract_campaign.py cam3.aoe2campaign
# Creates cam3_scenarios/ folder with all scenario files
```

Supports AoE2 DE campaign format (version 2.00).

### view_scenario.py
Displays scenario contents including map size, units by player, and triggers.

```bash
python view_scenario.py cam3_scenarios/3_Saladin_1.aoe2scenario
```

**Note:** Encrypted `.gpv` campaign files (DLC campaigns) require decryption keys. Unencrypted `.aoe2campaign` files can be extracted directly.

## Included Campaign Files

| File | Campaign | Scenarios |
|------|----------|-----------|
| cam2.aoe2campaign | Joan of Arc | 6 |
| cam3.aoe2campaign | Saladin | 6 |
| cam4.aoe2campaign | Genghis Khan | 6 |
