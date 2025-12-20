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
    
    def generate_scenario_code(self, prompt: str, model: str = "anthropic/claude-3.5-sonnet") -> str:
        """Generate scenario code using OpenRouter API"""
        
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
                    ```

                    IMPORTANT API USAGE - Follow this exact pattern:
                    ```python
                    # Load scenario from template
                    scenario = AoE2DEScenario.from_file("test_battle.aoe2scenario")

                    # Get managers
                    unit_manager = scenario.unit_manager
                    trigger_manager = scenario.trigger_manager
                    map_manager = scenario.map_manager

                    # Add units - use .ID property
                    unit_manager.add_unit(PlayerId.ONE, unit_const=UnitInfo.MILITIA.ID, x=50, y=50)
                    unit_manager.add_unit(PlayerId.TWO, unit_const=UnitInfo.ARCHER.ID, x=60, y=60)
                    unit_manager.add_unit(PlayerId.ONE, unit_const=BuildingInfo.BARRACKS.ID, x=45, y=45)
                    unit_manager.add_unit(PlayerId.ONE, unit_const=HeroInfo.JOAN_OF_ARC.ID, x=55, y=55)
                    unit_manager.add_unit(PlayerId.GAIA, unit_const=OtherInfo.GOLD_MINE.ID, x=30, y=30)

                    # Create triggers - ONLY use these conditions:
                    trigger = trigger_manager.add_trigger("My Trigger")
                    trigger.new_condition.timer(10)
                    trigger.new_condition.bring_object_to_area(unit_object=unit.reference_id, area_x1=10, area_y1=10, area_x2=20, area_y2=20)
                    trigger.new_condition.destroy_object(unit_object=enemy.reference_id)
                    trigger.new_condition.objects_in_area(quantity=5, object_list=UnitInfo.SPEARMAN.ID, source_player=PlayerId.ONE, area_x1=10, area_y1=20, area_x2=30, area_y2=30)
                    trigger.new_condition.accumulate_attribute(quantity=200, attribute=2, source_player=PlayerId.ONE)

                    # Create triggers - ONLY use these effects:
                    trigger.new_effect.display_instructions(display_time=10, message="Hello!")
                    trigger.new_effect.declare_victory(source_player=PlayerId.ONE, enabled=1)
                    trigger.new_effect.create_object(object_list_unit_id=UnitInfo.ARCHER.ID, source_player=PlayerId.ONE, location_x=50, location_y=50)
                    trigger.new_effect.kill_object(source_player=PlayerId.TWO, area_x1=0, area_y1=0, area_x2=100, area_y2=100)
                    trigger.new_effect.change_ownership(source_player=PlayerId.TWO, target_player=PlayerId.ONE, area_x1=10, area_y1=10, area_x2=20, area_y2=20)

                    # Save scenario
                    scenario.write_to_file("output.aoe2scenario")
                    ```

                    Use template files:
                    - AoE2DEScenario.from_file("david_and_goliath.aoe2scenario") for story/hero scenarios
                    - AoE2DEScenario.from_file("test_battle.aoe2scenario") for battle scenarios

                    CRITICAL RULES:
                    - Do NOT use scenario_metadata - it doesn't exist
                    - Always use .ID when adding units (e.g., UnitInfo.MILITIA.ID)
                    - Use unit_manager.add_unit() for units AND buildings
                    - Use PlayerId.ONE, PlayerId.TWO, PlayerId.GAIA for players
                    - For trigger conditions/effects, ALWAYS use source_player (NOT player)
                    - Do NOT use these methods: own_fewer_objects, victory(), own_objects with player param

                    VALID UNITS (UnitInfo) - Use .ID property:
                    Infantry: MILITIA, MAN_AT_ARMS, LONG_SWORDSMAN, TWO_HANDED_SWORDSMAN, CHAMPION, SPEARMAN, PIKEMAN, HALBERDIER
                    Archers: ARCHER, CROSSBOWMAN, ARBALESTER, SKIRMISHER, ELITE_SKIRMISHER, CAVALRY_ARCHER, HEAVY_CAVALRY_ARCHER, HAND_CANNONEER, LONGBOWMAN, ELITE_LONGBOWMAN
                    Cavalry: SCOUT_CAVALRY, LIGHT_CAVALRY, HUSSAR, KNIGHT, CAVALIER, PALADIN, CAMEL_RIDER, HEAVY_CAMEL_RIDER
                    Siege: BATTERING_RAM, CAPPED_RAM, SIEGE_RAM, MANGONEL, ONAGER, SIEGE_ONAGER, SCORPION, HEAVY_SCORPION, BOMBARD_CANNON, TREBUCHET
                    Villagers: VILLAGER_MALE, VILLAGER_FEMALE
                    Ships: GALLEY, WAR_GALLEY, GALLEON, FIRE_GALLEY, FIRE_SHIP, FAST_FIRE_SHIP, DEMOLITION_RAFT, DEMOLITION_SHIP, CANNON_GALLEON, TRANSPORT_SHIP
                    Monks: MONK, MISSIONARY
                    Animals: SHEEP, DEER, WILD_BOAR, WOLF, LION, CROCODILE, ELEPHANT, JAGUAR, TIGER

                    VALID BUILDINGS (BuildingInfo) - Use .ID property:
                    Military: BARRACKS, ARCHERY_RANGE, STABLE, SIEGE_WORKSHOP, CASTLE, DOCK, KREPOST, DONJON
                    Economy: TOWN_CENTER, HOUSE, MILL, LUMBER_CAMP, MINING_CAMP, MARKET, FARM, FISH_TRAP, FEITORIA
                    Defense: OUTPOST, WATCH_TOWER, GUARD_TOWER, KEEP, BOMBARD_TOWER, PALISADE_WALL, STONE_WALL, FORTIFIED_WALL, GATE_NORTH_TO_SOUTH, GATE_WEST_TO_EAST
                    Other: BLACKSMITH, UNIVERSITY, MONASTERY, WONDER

                    VALID HEROES (HeroInfo) - Use .ID property:
                    JOAN_OF_ARC, WILLIAM_WALLACE, GENGHIS_KHAN, EL_CID, BARBAROSSA, FREDERICK_BARBAROSSA, ATTILA_THE_HUN, CHARLES_MARTEL, ROLAND, BELISARIUS, RICHARD_THE_LIONHEART, THE_BLACK_PRINCE, SALADIN, ALEXANDER_NEVSKI, ROBIN_HOOD, VLAD_DRACULA, TAMERLANE, HENRY_V, WILLIAM_THE_CONQUEROR, KING_ARTHUR, LANCELOT, ERIK_THE_RED, LEIF_ERIKSON, HARALD_HARDRADA, KHOSRAU, THEODORIC_THE_GOTH

                    VALID GAIA/OTHER (OtherInfo) - Use .ID property:
                    Resources: GOLD_MINE, STONE_MINE, FORAGE_BUSH, FRUIT_BUSH
                    Trees: TREE_A, TREE_B, TREE_C, TREE_OAK, TREE_OAK_FOREST, TREE_PINE_FOREST, TREE_PALM_FOREST, TREE_JUNGLE, TREE_BAMBOO_FOREST, TREE_BIRCH, TREE_CYPRESS, TREE_DEAD, TREE_SNOW_PINE, TREE_DRAGON, TREE_BAOBAB, TREE_ACACIA, TREE_ITALIAN_PINE, TREE_RAINFOREST, TREE_MANGROVE
                    Decorations: RUINS, FLAG_A, FLAG_B, FLAG_C, FLAG_D, FLAG_E, STATUE, ROMAN_RUINS, FLOWERS_1, FLOWERS_2, FLOWERS_3, FLOWERS_4, BONFIRE, TORCH, GRAVE
                    Cliffs: CLIFF_1, CLIFF_2, CLIFF_3, CLIFF_4, CLIFF_5, CLIFF_6, CLIFF_7, CLIFF_8, CLIFF_9, CLIFF_10

                    Return ONLY the Python code, no explanations or markdown formatting."""
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
        
        # Select appropriate template
        template = self.scenario_templates.get(config.scenario_type, self.scenario_templates["story"])
        
        # Format the prompt
        prompt = template.format(
            title=config.title,
            description=config.description,
            map_size=config.map_size,
            players=config.players,
            difficulty=config.difficulty
        )
        
        # Generate the scenario code
        logger.info(f"Generating scenario: {config.title}")
        generated_code = self.api.generate_scenario_code(prompt)
        
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
            
            # Check for basic structure
            if "AoE2DEScenario.from_default()" not in code and "AoE2DEScenario.from_file(" not in code:
                logger.warning("Missing scenario object creation")
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
    
    # Initialize the generator
    generator = ScenarioGenerator(api_key)
    
    # Example scenario configurations
    scenarios = [
        ScenarioConfig(
            title="The Siege of Constantinople",
            description="Defend the great city of Constantinople against the Ottoman invaders",
            scenario_type="defense",
            difficulty="hard",
            output_path="constantinople_siege.aoe2scenario"
        ),
        ScenarioConfig(
            title="The Battle of Hastings",
            description="Relive the famous battle between William the Conqueror and Harold Godwinson",
            scenario_type="battle",
            difficulty="medium",
            output_path="battle_of_hastings.aoe2scenario"
        ),
        ScenarioConfig(
            title="The Rise of Rome",
            description="Guide Rome from a small settlement to a mighty empire",
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