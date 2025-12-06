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
    title="The Battle of Agincourt",
    description="English longbowmen face the French cavalry in 1415",
    scenario_type="battle",  # Options: "battle", "story", "defense", "conquest"
    difficulty="hard",       # Options: "easy", "medium", "hard"
    output_path="agincourt.aoe2scenario"
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
