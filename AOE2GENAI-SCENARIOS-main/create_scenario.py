import os
from generator import ScenarioGenerator, ScenarioConfig

# Set your API key here or via environment variable
# os.environ["OPENROUTER_API_KEY"] = "your_key_here"

api_key = os.getenv("OPENROUTER_API_KEY")
if not api_key:
    print("Please set the OPENROUTER_API_KEY environment variable")
    print("Example: set OPENROUTER_API_KEY=your_key_here")
    exit(1)

generator = ScenarioGenerator(api_key)

config = ScenarioConfig(
    title="Siege of Constantinople (1453)",
    description="The Siege of Constantinople was a decisive victory for the Ottoman forces, led by Sultan Mehmed II, defeated the Byzantine forces, led by Emperor Constantine XI, in a decisive victory that helped to turn the tide of the war.",
    scenario_type="battle",  # Options: "battle", "story", "defense", "conquest"
    difficulty="hard",       # Options: "easy", "medium", "hard"
    output_path="siege_of_constantinople.aoe2scenario",
    # Optional: Add a Wikipedia link for better historical accuracy
    wikipedia_link="https://en.wikipedia.org/wiki/Fall_of_Constantinople"
)

print(f"Generating scenario: {config.title}")
print("=" * 60)

# Use generate_with_validation for automatic retry on validation failures
code = generator.generate_with_validation(config, max_attempts=3)

# Run comprehensive validation
print("\n" + "=" * 60)
print("VALIDATION REPORT")
print("=" * 60)

validation = generator.validate_scenario_code(code, config.scenario_type)

print(f"\nStatus: {'PASSED' if validation['valid'] else 'FAILED'}")
print(f"\n--- Player Requirements ---")
print(f"Player ONE Units: {validation['stats']['player_one_units']} (min 20)")
print(f"Player ONE Town Center: {'Yes' if validation['stats']['player_one_tc'] else 'No'}")
print(f"Player TWO Units: {validation['stats']['player_two_units']} (min 20)")
print(f"Player TWO Town Center: {'Yes' if validation['stats']['player_two_tc'] else 'No'}")
print(f"GAIA Objects: {validation['stats']['gaia_objects']}")
print(f"\n--- Story & Triggers ---")
print(f"Total Triggers: {validation['stats']['trigger_count']} (min 8)")
print(f"Dialogue Lines: {validation['stats']['dialogue_count']} (min 5)")
print(f"Trigger Chaining: {'Yes' if validation['stats']['has_chaining'] else 'No'}")
print(f"Navigation Triggers: {'Yes' if validation['stats']['has_navigation'] else 'No'}")
print(f"Reveal/View Triggers: {'Yes' if validation['stats']['has_reveals'] else 'No'}")
print(f"Trigger Type Variety: {validation['stats']['trigger_variety']}/5")
print(f"\n--- Environment Quality ---")
print(f"Building Categories: {validation['stats']['building_categories']}/5")
print(f"Unit Variety: {validation['stats']['unit_variety']}/5")

if validation['issues']:
    print(f"\nERRORS ({len(validation['issues'])}):")
    for issue in validation['issues']:
        print(f"  ❌ {issue}")

if validation['warnings']:
    print(f"\nWARNINGS ({len(validation['warnings'])}):")
    for warning in validation['warnings']:
        print(f"  ⚠️ {warning}")

print("\n" + "=" * 60)

# Save even if there are warnings (only block on errors)
if validation['valid'] or len(validation['issues']) == 0:
    if generator.save_scenario(code, config.output_path):
        print(f"✅ Successfully created: {config.output_path}")
    else:
        print("❌ Failed to execute scenario code")
else:
    print("❌ Scenario has validation errors. Review and fix before saving.")
    # Optionally save the code for manual review
    with open("failed_scenario_code.py", "w", encoding="utf-8") as f:
        f.write(code)
    print("   Code saved to 'failed_scenario_code.py' for manual review.")
