import os
import json
import requests
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import logging
from pathlib import Path

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
    
    def generate_scenario_code(self, prompt: str, template_path: str, model: str = "mistralai/mistral-7b-instruct:free") -> str:
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

    # Get API key from environment variable
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("Please set the OPENROUTER_API_KEY environment variable")
        return

    # Get template path from environment or use default
    template_path = os.getenv("AOE2_TEMPLATE_PATH", "template.aoe2scenario")
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
            title="The Siege of Constantinople",
            description="Defend the great city of Constantinople against the Ottoman invaders",
            template_path=template_path,
            scenario_type="defense",
            difficulty="hard",
            output_path="constantinople_siege.aoe2scenario"
        ),
        ScenarioConfig(
            title="The Battle of Hastings",
            description="Relive the famous battle between William the Conqueror and Harold Godwinson",
            template_path=template_path,
            scenario_type="battle",
            difficulty="medium",
            output_path="battle_of_hastings.aoe2scenario"
        ),
        ScenarioConfig(
            title="The Rise of Rome",
            description="Guide Rome from a small settlement to a mighty empire",
            template_path=template_path,
            scenario_type="story",
            difficulty="easy",
            output_path="rise_of_rome.aoe2scenario"
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