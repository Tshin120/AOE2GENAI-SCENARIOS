#!/usr/bin/env python3
"""
Example usage of the AoE2 Scenario Generator
This script demonstrates how to use the generator with different configurations.
"""

import os
from generator import ScenarioGenerator, ScenarioConfig

def main():
    """Demonstrate the scenario generator with various configurations"""
    
    # Get API key from environment variable
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("❌ Please set the OPENROUTER_API_KEY environment variable")
        print("   Windows: set OPENROUTER_API_KEY=your_key_here")
        print("   Linux/Mac: export OPENROUTER_API_KEY=your_key_here")
        return
    
    # Initialize the generator
    print("🚀 Initializing AoE2 Scenario Generator...")
    generator = ScenarioGenerator(api_key)
    
    # Example 1: Defense Scenario
    print("\n⚔️  Generating Defense Scenario...")
    defense_config = ScenarioConfig(
        title="The Siege of Constantinople",
        description="Defend the great city of Constantinople against the Ottoman invaders. Build walls, train troops, and hold the city at all costs!",
        scenario_type="defense",
        difficulty="hard",
        map_size=120,
        players=2,
        output_path="scenarios/constantinople_siege.aoe2scenario"
    )
    
    try:
        defense_code = generator.generate_scenario(defense_config)
        if generator.validate_scenario_code(defense_code):
            print("✅ Defense scenario code validated successfully")
            if generator.save_scenario(defense_code, defense_config.output_path):
                print(f"✅ Defense scenario saved: {defense_config.output_path}")
            else:
                print("❌ Failed to save defense scenario")
        else:
            print("⚠️  Defense scenario code validation failed")
    except Exception as e:
        print(f"❌ Error generating defense scenario: {e}")
    
    # Example 2: Battle Scenario
    print("\n⚔️  Generating Battle Scenario...")
    battle_config = ScenarioConfig(
        title="The Battle of Hastings",
        description="Relive the famous battle between William the Conqueror and Harold Godwinson. Command your forces in this epic medieval battle!",
        scenario_type="battle",
        difficulty="medium",
        map_size=100,
        players=2,
        output_path="scenarios/battle_of_hastings.aoe2scenario"
    )
    
    try:
        battle_code = generator.generate_scenario(battle_config)
        if generator.validate_scenario_code(battle_code):
            print("✅ Battle scenario code validated successfully")
            if generator.save_scenario(battle_code, battle_config.output_path):
                print(f"✅ Battle scenario saved: {battle_config.output_path}")
            else:
                print("❌ Failed to save battle scenario")
        else:
            print("⚠️  Battle scenario code validation failed")
    except Exception as e:
        print(f"❌ Error generating battle scenario: {e}")
    
    # Example 3: Story Scenario
    print("\n📖 Generating Story Scenario...")
    story_config = ScenarioConfig(
        title="The Rise of Rome",
        description="Guide Rome from a small settlement to a mighty empire. Build your civilization, expand your territory, and become the greatest power in the ancient world!",
        scenario_type="story",
        difficulty="easy",
        map_size=140,
        players=1,
        output_path="scenarios/rise_of_rome.aoe2scenario"
    )
    
    try:
        story_code = generator.generate_scenario(story_config)
        if generator.validate_scenario_code(story_code):
            print("✅ Story scenario code validated successfully")
            if generator.save_scenario(story_code, story_config.output_path):
                print(f"✅ Story scenario saved: {story_config.output_path}")
            else:
                print("❌ Failed to save story scenario")
        else:
            print("⚠️  Story scenario code validation failed")
    except Exception as e:
        print(f"❌ Error generating story scenario: {e}")
    
    # Example 4: Conquest Scenario
    print("\n🏰 Generating Conquest Scenario...")
    conquest_config = ScenarioConfig(
        title="The Mongol Conquest",
        description="Lead the Mongol hordes across Asia and Europe. Conquer cities, build an empire, and become the greatest conqueror in history!",
        scenario_type="conquest",
        difficulty="hard",
        map_size=160,
        players=2,
        output_path="scenarios/mongol_conquest.aoe2scenario"
    )
    
    try:
        conquest_code = generator.generate_scenario(conquest_config)
        if generator.validate_scenario_code(conquest_code):
            print("✅ Conquest scenario code validated successfully")
            if generator.save_scenario(conquest_code, conquest_config.output_path):
                print(f"✅ Conquest scenario saved: {conquest_config.output_path}")
            else:
                print("❌ Failed to save conquest scenario")
        else:
            print("⚠️  Conquest scenario code validation failed")
    except Exception as e:
        print(f"❌ Error generating conquest scenario: {e}")
    
    print("\n🎉 Scenario generation complete!")
    print("📁 Check the 'scenarios' folder for your generated scenarios")
    print("🎮 Load them in Age of Empires 2 Definitive Edition to play!")

if __name__ == "__main__":
    main() 