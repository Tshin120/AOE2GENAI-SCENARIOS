import os
import sys
import io
import json
import requests
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import logging
from pathlib import Path

# Fix Unicode encoding for Windows console
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

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

@dataclass
class ScenarioConfig:
    """Configuration for scenario generation"""
    title: str
    description: str
    template_path: str  # Path to base .aoe2scenario file (required)
    map_size: int = 120
    players: int = 2
    difficulty: str = "medium"
    scenario_type: str = "story"
    output_path: str = "generated_scenario.aoe2scenario"

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
    
    def generate_scenario_code(self, prompt: str, template_path: str, model: str = "anthropic/claude-3.5-sonnet") -> str:
        """Generate scenario code using OpenRouter API"""

        # Convert backslashes to forward slashes for the template path
        safe_template_path = template_path.replace('\\', '/')

        system_content = f"""You are an expert Age of Empires 2 scenario creator using the AoE2ScenarioParser library (version 0.6.x).

IMPORTANT: Generate complete, runnable Python code that creates an Age of Empires 2 scenario.

CRITICAL REQUIREMENTS:
1. You MUST load the scenario from a template file using: AoE2DEScenario.from_file("{safe_template_path}")
2. Do NOT use AoE2DEScenario.from_default() - this method does not exist
3. Save the scenario using scenario.write_to_file("output.aoe2scenario")
4. Use ONLY forward slashes in file paths, never backslashes

CORRECT IMPORTS (use these exactly):
```python
from AoE2ScenarioParser.scenarios.aoe2_de_scenario import AoE2DEScenario
from AoE2ScenarioParser.datasets.players import PlayerId
from AoE2ScenarioParser.datasets.units import UnitInfo
from AoE2ScenarioParser.datasets.buildings import BuildingInfo
from AoE2ScenarioParser.datasets.other import OtherInfo
from AoE2ScenarioParser.datasets.heroes import HeroInfo
```

CORRECT USAGE PATTERN:
```python
# Load scenario from template
scenario = AoE2DEScenario.from_file("{safe_template_path}")

# Get managers
unit_manager = scenario.unit_manager
trigger_manager = scenario.trigger_manager
map_manager = scenario.map_manager

# Add units using: unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.MILITIA.ID, x=10, y=10)
# Add buildings using: unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.TOWN_CENTER.ID, x=20, y=20)

# Create triggers using:
# trigger = trigger_manager.add_trigger("Trigger Name")
# trigger.new_condition.timer(10)
# trigger.new_effect.display_instructions(display_time=10, message="Hello")

# Save scenario
scenario.write_to_file("output.aoe2scenario")
```

Return ONLY the Python code, no explanations or markdown formatting."""

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": system_content
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.7,
            "max_tokens": 4000
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=payload,
                timeout=60
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

def display_scenario(scenario_path: str) -> None:
    """Display the contents of an AoE2 scenario file in a readable format"""

    if not os.path.exists(scenario_path):
        print(f"ERROR: Scenario file not found: {scenario_path}")
        return

    print(f"\nLoading scenario: {scenario_path}")
    scenario = AoE2DEScenario.from_file(scenario_path)

    # Get managers
    unit_manager = scenario.unit_manager
    trigger_manager = scenario.trigger_manager
    map_manager = scenario.map_manager

    print("\n" + "=" * 60)
    print(f"SCENARIO: {scenario_path}")
    print("=" * 60)

    # --- MAP INFO ---
    print(f"\n--- MAP INFO ---")
    print(f"Map Size: {map_manager.map_size} x {map_manager.map_size}")

    # --- UNITS BY PLAYER ---
    print(f"\n--- UNITS ---")

    # Get units for each player
    for player_id in PlayerId:
        try:
            units = unit_manager.get_player_units(player_id)
            if units:
                print(f"\n  Player: {player_id.name} ({len(units)} units)")
                print("  " + "-" * 40)

                # Count unit types
                unit_counts = {}
                for unit in units:
                    unit_type = unit.unit_const
                    if unit_type not in unit_counts:
                        unit_counts[unit_type] = []
                    unit_counts[unit_type].append(unit)

                for unit_type, unit_list in unit_counts.items():
                    # Try to get unit name
                    name = f"Unit ID {unit_type}"
                    for dataset in [UnitInfo, BuildingInfo, HeroInfo, OtherInfo]:
                        try:
                            for item in dataset:
                                if item.ID == unit_type:
                                    name = item.name
                                    break
                        except:
                            pass
                        if name != f"Unit ID {unit_type}":
                            break

                    # Show positions
                    positions = [(int(u.x), int(u.y)) for u in unit_list]
                    pos_str = str(positions[:5])
                    if len(positions) > 5:
                        pos_str = pos_str[:-1] + ", ...]"
                    print(f"    {name}: {len(unit_list)}x at {pos_str}")
        except:
            pass

    # --- TRIGGERS ---
    print(f"\n--- TRIGGERS ({len(trigger_manager.triggers)} total) ---")

    for i, trigger in enumerate(trigger_manager.triggers):
        print(f"\n  [{i+1}] {trigger.name}")
        print(f"      Enabled: {trigger.enabled}")

        # Conditions
        if trigger.conditions:
            print(f"      Conditions ({len(trigger.conditions)}):")
            for cond in trigger.conditions:
                cond_type = cond.condition_type
                cond_name = cond_type.name if hasattr(cond_type, 'name') else str(cond_type)
                print(f"        - {cond_name}")

        # Effects
        if trigger.effects:
            print(f"      Effects ({len(trigger.effects)}):")
            for effect in trigger.effects:
                effect_type = effect.effect_type
                effect_name = effect_type.name if hasattr(effect_type, 'name') else str(effect_type)
                # Try to get message if it's a display instruction
                msg = ""
                if hasattr(effect, 'message') and effect.message:
                    msg_text = str(effect.message)
                    msg = f' - "{msg_text[:50]}..."' if len(msg_text) > 50 else f' - "{msg_text}"'
                print(f"        - {effect_name}{msg}")

    print("\n" + "=" * 60)
    print("END OF SCENARIO")
    print("=" * 60)


def display_all_scenarios(directory: str = ".") -> None:
    """Display all .aoe2scenario files in a directory"""

    scenario_files = list(Path(directory).glob("*.aoe2scenario"))

    if not scenario_files:
        print(f"No .aoe2scenario files found in: {directory}")
        return

    print(f"\nFound {len(scenario_files)} scenario file(s) in {directory}:")
    for f in scenario_files:
        print(f"  - {f.name}")

    for scenario_file in scenario_files:
        try:
            display_scenario(str(scenario_file))
        except Exception as e:
            print(f"\nERROR loading {scenario_file.name}: {e}")


class ScenarioGenerator:
    """Main class for generating AoE2 scenarios using AI"""

    def __init__(self, api_key: str):
        self.api = OpenRouterAPI(api_key)
        self.scenario_templates = self._load_templates()
    
    def _load_templates(self) -> Dict[str, str]:
        """Load scenario generation templates"""
        return {
            "battle": """Create an Age of Empires 2 scenario with the following requirements:
            - Title: {title}
            - Description: {description}
            - Map size: {map_size}x{map_size}
            - Players: {players}
            - Difficulty: {difficulty}
            - Type: Battle scenario
            
            The scenario should include:
            - Strategic unit placement for both sides
            - Resource distribution (gold, stone, wood, food)
            - Multiple triggers for victory conditions
            - Defensive structures and military units
            - Balanced gameplay for the specified difficulty
            - Clear objectives and win conditions""",
            
            "story": """Create an Age of Empires 2 scenario with the following requirements:
            - Title: {title}
            - Description: {description}
            - Map size: {map_size}x{map_size}
            - Players: {players}
            - Difficulty: {difficulty}
            - Type: Story-driven scenario
            
            The scenario should include:
            - Narrative elements and story progression
            - Character units with specific roles
            - Multiple objectives and quests
            - Environmental storytelling through map design
            - Trigger-based story events
            - Immersive gameplay experience""",
            
            "defense": """Create an Age of Empires 2 scenario with the following requirements:
            - Title: {title}
            - Description: {description}
            - Map size: {map_size}x{map_size}
            - Players: {players}
            - Difficulty: {difficulty}
            - Type: Defense scenario
            
            The scenario should include:
            - Defensive structures and fortifications
            - Wave-based enemy attacks
            - Resource management for defense
            - Strategic positioning of units
            - Multiple defense objectives
            - Escalating difficulty levels""",
            
            "conquest": """Create an Age of Empires 2 scenario with the following requirements:
            - Title: {title}
            - Description: {description}
            - Map size: {map_size}x{map_size}
            - Players: {players}
            - Difficulty: {difficulty}
            - Type: Conquest scenario
            
            The scenario should include:
            - Multiple enemy bases to conquer
            - Strategic resource control points
            - Progressive difficulty as you advance
            - Different unit types and strategies
            - Victory conditions based on territory control
            - Balanced progression system"""
        }
    
    def generate_scenario(self, config: ScenarioConfig) -> str:
        """Generate a scenario based on the provided configuration"""

        # Validate template file exists
        if not os.path.exists(config.template_path):
            raise FileNotFoundError(f"Template scenario file not found: {config.template_path}")

        # Select appropriate template
        template = self.scenario_templates.get(config.scenario_type, self.scenario_templates["story"])

        # Format the prompt with additional output path info
        prompt = template.format(
            title=config.title,
            description=config.description,
            map_size=config.map_size,
            players=config.players,
            difficulty=config.difficulty
        )
        prompt += f"\n\nIMPORTANT: Save the output scenario to: {config.output_path}"

        # Generate the scenario code
        logger.info(f"Generating scenario: {config.title}")
        logger.info(f"Using template: {config.template_path}")
        generated_code = self.api.generate_scenario_code(prompt, config.template_path)

        return generated_code
    
    def save_scenario(self, code: str, output_path: str) -> bool:
        """Save the generated scenario code to a file and execute it"""
        try:
            # Create output directory if it doesn't exist
            output_dir = Path(output_path).parent
            output_dir.mkdir(parents=True, exist_ok=True)

            # Fix common AI mistakes in generated code
            import re
            code = code.replace("AoE2Scenario.from_file", "AoE2DEScenario.from_file")
            code = code.replace("PlayerId.NEUTRAL", "PlayerId.GAIA")
            code = code.replace("OtherInfo.TREE.ID", "OtherInfo.TREE_OAK.ID")
            code = code.replace("OtherInfo.FOREST_TREE.ID", "OtherInfo.TREE_OAK.ID")
            code = code.replace("OtherInfo.TREE_A.ID", "OtherInfo.TREE_OAK.ID")
            code = code.replace("OtherInfo.TREE_B.ID", "OtherInfo.TREE_OAK.ID")
            code = code.replace("BuildingInfo.WALL_STONE.ID", "BuildingInfo.STONE_WALL.ID")
            code = code.replace("UnitInfo.VILLAGER.ID", "UnitInfo.VILLAGER_MALE.ID")
            code = code.replace("UnitInfo.SWORDSMAN.ID", "UnitInfo.MILITIA.ID")
            # Fix parameter name mistakes (be careful not to double-replace)
            # Only replace 'player=' when not already 'source_player='
            code = re.sub(r'(?<!source_)player=PlayerId', 'source_player=PlayerId', code)
            code = re.sub(r'(?<!source_)player=(\d)', r'source_player=PlayerId.ONE', code)
            # Fix victory/defeat effect calls
            code = re.sub(r'\.victory\([^)]*\)', '.declare_victory(source_player=PlayerId.ONE)', code)
            code = re.sub(r'\.defeat\([^)]*\)', '.declare_victory(source_player=PlayerId.TWO)', code)

            # Remove lines that use incorrect API
            lines = code.split('\n')
            filtered_lines = []
            skip_until_close_paren = 0
            for line in lines:
                stripped = line.strip()
                # Skip incorrect message/meta API calls - track multi-line blocks
                if 'scenario.messages' in line or 'scenario.scenario_messages' in line:
                    skip_until_close_paren = line.count('(') - line.count(')')
                    continue
                if 'scenario.scenario_meta' in line:
                    skip_until_close_paren = line.count('(') - line.count(')')
                    continue
                if 'scenario.header' in line:
                    skip_until_close_paren = line.count('(') - line.count(')')
                    continue
                if 'map_manager.map_size' in line:
                    continue
                if 'set_messages(' in line:
                    skip_until_close_paren = line.count('(') - line.count(')')
                    continue
                # Handle skipping multi-line blocks
                if skip_until_close_paren > 0:
                    skip_until_close_paren += line.count('(') - line.count(')')
                    continue
                # Skip player config that doesn't exist
                if 'player.set_resources' in line:
                    continue
                # Skip incorrect trigger conditions with lists
                if 'object_list=[' in line:
                    continue
                # Skip incorrect destroy_object calls (needs unit reference, not building type)
                if 'destroy_object(' in line and 'object_list' in line:
                    continue
                # Skip orphaned lines that are just continuation of removed blocks
                if stripped.startswith('title=') or stripped.startswith('description='):
                    continue
                if stripped == ')':
                    # Skip if it's just a closing paren with no context
                    if filtered_lines and filtered_lines[-1].strip().startswith('#'):
                        continue
                filtered_lines.append(line)
            code = '\n'.join(filtered_lines)

            # Prepend UTF-8 encoding fix for Windows console
            utf8_fix = '''import sys
import io
# Fix Unicode encoding for Windows console
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

'''
            code = utf8_fix + code

            # Write the generated code to a temporary file
            temp_file = "temp_scenario_generator.py"
            with open(temp_file, "w", encoding="utf-8") as f:
                f.write(code)
            
            # Execute the generated code
            logger.info(f"Executing generated scenario code...")
            
            # Import and execute the generated code
            import subprocess
            import sys
            
            result = subprocess.run([sys.executable, temp_file], 
                                  capture_output=True, text=True, timeout=60)
            
            if result.returncode != 0:
                logger.error(f"Scenario execution failed: {result.stderr}")
                return False
            
            logger.info(f"Scenario generated successfully: {output_path}")
            
            # Clean up temporary file
            if os.path.exists(temp_file):
                os.remove(temp_file)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to save/execute scenario: {e}")
            return False
    
    def validate_scenario_code(self, code: str) -> bool:
        """Validate the generated scenario code for basic syntax and structure"""
        try:
            # Check for required imports
            required_imports = [
                "AoE2DEScenario",
                "PlayerId",
                "UnitInfo",
                "BuildingInfo"
            ]

            for import_name in required_imports:
                if import_name not in code:
                    logger.warning(f"Missing required import: {import_name}")
                    return False

            # Check for basic structure - must use from_file(), not from_default()
            if "AoE2DEScenario.from_file(" not in code:
                logger.warning("Missing scenario object creation with from_file()")
                return False

            if "AoE2DEScenario.from_default()" in code:
                logger.warning("Code uses from_default() which doesn't exist - should use from_file()")
                return False

            if "write_to_file" not in code:
                logger.warning("Missing scenario save operation")
                return False

            return True

        except Exception as e:
            logger.error(f"Code validation failed: {e}")
            return False

def main():
    """Main function to demonstrate the scenario generator"""
    import sys

    # Check for display command
    if len(sys.argv) > 1:
        if sys.argv[1] == "--display" or sys.argv[1] == "-d":
            if len(sys.argv) > 2:
                # Display specific scenario file
                display_scenario(sys.argv[2])
            else:
                # Display all scenarios in current directory
                display_all_scenarios(".")
            return
        elif sys.argv[1] == "--display-all" or sys.argv[1] == "-da":
            directory = sys.argv[2] if len(sys.argv) > 2 else "."
            display_all_scenarios(directory)
            return
        elif sys.argv[1] == "--help" or sys.argv[1] == "-h":
            print("AoE2 Scenario Generator")
            print("")
            print("Usage:")
            print("  python generator.py                    - Generate example scenarios")
            print("  python generator.py -d <file>          - Display a scenario file")
            print("  python generator.py -d                 - Display all scenarios in current dir")
            print("  python generator.py -da [directory]    - Display all scenarios in directory")
            print("  python generator.py -h                 - Show this help")
            return

    # Get API key from environment variable or use default
    api_key = os.getenv("OPENROUTER_API_KEY", "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")
    if not api_key:
        print("Please set the OPENROUTER_API_KEY environment variable")
        return

    # Get template path from environment or use default (test_battle.aoe2scenario)
    template_path = os.getenv("AOE2_TEMPLATE_PATH", "test_battle.aoe2scenario")
    if not os.path.exists(template_path):
        print(f"ERROR: Template scenario file not found: {template_path}")
        print("")
        print("To use this generator, you need a base .aoe2scenario file.")
        print("Create one in Age of Empires 2 DE Scenario Editor:")
        print("  1. Open AoE2 DE")
        print("  2. Go to Editors -> Scenario Editor")
        print("  3. Create a new blank scenario")
        print("  4. Save it as 'template.aoe2scenario'")
        print("  5. Copy the file to this directory")
        print("")
        print("Or set AOE2_TEMPLATE_PATH environment variable to your template file.")
        return

    # Initialize the generator
    generator = ScenarioGenerator(api_key)

    # Example scenario configurations
    scenarios = [
        ScenarioConfig(
            title="The Plains Skirmish",
            description="A tactical battle between knights and cavalry archers on an open plain with contested gold mines",
            template_path=template_path,
            scenario_type="battle",
            difficulty="medium",
            output_path="plains_skirmish.aoe2scenario"
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