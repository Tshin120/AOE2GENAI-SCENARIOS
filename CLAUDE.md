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

# Generate scenarios using the API
python create_scenario.py       # Single scenario generation (edit ScenarioConfig inside)
python example_usage.py         # Multiple example scenarios
python generator.py             # Main generator with examples (runs all 6 scenario types)

# Test API connection
python test_api.py

# View scenario contents
python view_scenario.py <scenario_file>    # View any .aoe2scenario file

# Extract scenarios from campaign files
python extract_campaign.py <campaign_file>  # Extracts .aoe2scenario files from .aoe2campaign
```

## Architecture

### Core Flow

1. User creates a `ScenarioConfig` with scenario parameters (title, description, map_size, players, difficulty, scenario_type, output_path, optional wikipedia_url)
2. `ScenarioGenerator.generate_scenario()` selects a template based on `scenario_type` and calls OpenRouter API
3. API returns Python code using AoE2ScenarioParser (code extracted from markdown fences if present)
4. Code is validated via `validate_scenario_code()` (checks imports, scenario creation, write_to_file)
5. Code is written to `temp_scenario_generator.py` and executed via subprocess to produce `.aoe2scenario` file

### Core Modules

- **`generator.py`**: Main module with:
  - `OpenRouterAPI`: API communication with detailed system prompt containing AoE2ScenarioParser patterns
  - `ScenarioGenerator`: Template selection (battle/escort/diplomacy/defense/conquest/story) and code generation
  - `ScenarioConfig`: Dataclass for scenario parameters
  - `validate_scenario_code()`: Basic validation for required imports and structure
  - `save_scenario()`: Writes code to temp file and executes it

- **`api_config.py`**: Configuration (model selection, timeouts). Default model: `anthropic/claude-3.5-sonnet`

- **`create_scenario.py`**: Entry point for generating a single scenario - edit the `ScenarioConfig` here

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
