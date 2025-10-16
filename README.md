# AOE2GENAI-SCENARIOS
Age of Empires 2 scenarios generated using LLMs

## Overview
This project uses AI (via OpenRouter API) to automatically generate Age of Empires 2 Definitive Edition scenario files. The generator creates complete scenarios with units, buildings, triggers, and objectives using the AoE2ScenarioParser library.

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up your OpenRouter API key:
```bash
export OPENROUTER_API_KEY=your_key_here
```

## Usage

### Running the David & Goliath Scenario

```bash
python david\&goliath_scenario1.py
```

This will generate a `david_and_goliath.aoe2scenario` file.

### Loading Scenarios in Age of Empires 2 DE

1. **Move the scenario file** to your Age of Empires 2 scenario folder:
   ```
   C:\Users\<USERNAME>\Games\Age of Empires 2 DE\<STEAM_ID>\resources\_common\scenario\
   ```
   Example: `C:\Users\msantolu\Games\Age of Empires 2 DE\76561198177849325\resources\_common\scenario\`

2. **Load in the game**:
   - Open Age of Empires 2 Definitive Edition
   - Go to **Editors** tab
   - Click **Scenario Editor**
   - Open your scenario (it should appear in the list)
   - Go to **Menu** → **Test** to play the scenario

## Generated Scenarios

- **david_and_goliath.aoe2scenario** - Biblical David vs Goliath scenario with triggers, units, and victory conditions

## Project Structure

- `generator.py` - Main AI scenario generator with OpenRouter integration
- `example_usage.py` - Example usage showing different scenario types
- `api_config.py` - API configuration settings
- `david&goliath_scenario1.py` - Pre-built David & Goliath scenario
- `test_api.py` - API testing utilities 
