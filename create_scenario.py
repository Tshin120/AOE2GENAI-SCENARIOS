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
    title="The Flight to Chinon",
    description="Joan must escape English territory and reach the Dauphin. Enemy cavalry pursue relentlessly.",
    scenario_type="escort",
    map_size=120,
    players=4,
    difficulty="medium",
    output_path="flight_to_chinon.aoe2scenario"
)  

print(f"Generating scenario: {config.title}")
code = generator.generate_scenario(config)

if generator.validate_scenario_code(code):
    print("Code validation passed")
else:
    print("Warning: Code validation found issues")

if generator.save_scenario(code, config.output_path):
    print(f"Successfully created: {config.output_path}")
else:
    print("Failed to create scenario")
