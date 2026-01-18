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
python create_scenario.py       # Single scenario generation
python example_usage.py         # Multiple example scenarios
python generator.py             # Main generator with examples

# Test API connection
python test_api.py

# View scenario contents
python view_scenario.py <scenario_file>    # View any .aoe2scenario file

# Extract scenarios from campaign files
python extract_campaign.py <campaign_file>  # Extracts .aoe2scenario files from .aoe2campaign
```

## Architecture

### Core Components

- **`generator.py`**: Main module containing:
  - `OpenRouterAPI`: Handles OpenRouter API communication with a detailed system prompt for AoE2ScenarioParser usage
  - `ScenarioGenerator`: Orchestrates scenario generation using templates (battle/story/defense/conquest)
  - `ScenarioConfig`: Dataclass for scenario parameters (title, description, map_size, players, difficulty, type, output_path)

- **`api_config.py`**: API configuration (model selection, timeouts, output paths). Default model: `anthropic/claude-3.5-sonnet`

### Key Flow

1. User creates a `ScenarioConfig` with scenario parameters
2. `ScenarioGenerator.generate_scenario()` selects a template and calls OpenRouter API
3. API returns Python code using AoE2ScenarioParser
4. Code is validated via `validate_scenario_code()` and executed to produce `.aoe2scenario` file

### AoE2ScenarioParser Usage

The generated code pattern:
```python
scenario = AoE2DEScenario.from_default()  # Creates a new blank scenario
unit_manager = scenario.unit_manager
trigger_manager = scenario.trigger_manager

# Add units with .ID property
unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.MILITIA.ID, x=50, y=50)
unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.BARRACKS.ID, x=45, y=45)

# Create triggers
trigger = trigger_manager.add_trigger("Name")
trigger.new_condition.timer(10)
trigger.new_effect.display_instructions(display_time=10, message="Text")

scenario.write_to_file("output.aoe2scenario")
```

### Monkey Patch Note

`david&goliath_scenario1.py` includes a monkey patch for `AoE2ScenarioParser.helper.bytes_conversions.int_to_bytes` to handle enum-to-int conversion issues. Apply this pattern if encountering similar errors.

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

**Note:** Encrypted `.gpv` campaign files (DLC campaigns) require decryption keys extracted via Cheat Engine. Unencrypted `.aoe2campaign` files can be extracted directly.

## Included Campaign Files

| File | Campaign | Scenarios |
|------|----------|-----------|
| cam2.aoe2campaign | Joan of Arc | 6 |
| cam3.aoe2campaign | Saladin | 6 |
| cam4.aoe2campaign | Genghis Khan | 6 |
