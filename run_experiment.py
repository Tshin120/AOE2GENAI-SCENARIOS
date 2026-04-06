import os
import sys

# Add reachability_research to path so we can import both generators
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "reachability_research"))

from generator import ScenarioGenerator, ScenarioConfig
from generator_reachability import ScenarioGenerator as ScenarioGeneratorReachability

api_key = os.getenv("OPENROUTER_API_KEY")
if not api_key:
    print("Please set the OPENROUTER_API_KEY environment variable")
    exit(1)

# Scenario definitions using ScenarioConfig objects
scenarios = [
    # Battle scenarios
    ScenarioConfig(
        title="The Battle of Tours",
        description="Charles Martel's Franks defend against the Umayyad invasion of 732",
        scenario_type="battle",
        map_size=120,
        players=2,
        difficulty="easy",
        output_path="battle_of_tours.aoe2scenario",
    ),
    ScenarioConfig(
        title="The Battle of Hastings",
        description="William the Conqueror vs Harold Godwinson in 1066",
        scenario_type="battle",
        map_size=120,
        players=2,
        difficulty="easy",
        output_path="battle_of_hastings.aoe2scenario",
    ),
    ScenarioConfig(
        title="The Battle of Thermopylae",
        description="Leonidas and the Spartans hold the pass against the Persian army",
        scenario_type="battle",
        map_size=120,
        players=2,
        difficulty="easy",
        output_path="battle_of_thermopylae.aoe2scenario",
    ),
    # Defense scenarios
    ScenarioConfig(
        title="The Defense of Vienna",
        description="Defend Vienna from the Ottoman siege of 1529",
        scenario_type="defense",
        map_size=120,
        players=2,
        difficulty="easy",
        output_path="defense_of_vienna.aoe2scenario",
    ),
    ScenarioConfig(
        title="The Siege of Constantinople",
        description="Defend Constantinople against the Ottoman assault of 1453",
        scenario_type="defense",
        map_size=120,
        players=2,
        difficulty="easy",
        output_path="siege_of_constantinople.aoe2scenario",
    ),
    ScenarioConfig(
        title="The Siege of Acre",
        description="Defend the last Crusader fortress against the Mamluk assault of 1291",
        scenario_type="defense",
        map_size=120,
        players=2,
        difficulty="easy",
        output_path="siege_of_acre.aoe2scenario",
    ),
    # Story scenarios
    ScenarioConfig(
        title="The Rise of Rome",
        description="Guide Rome from a small settlement to regional power",
        scenario_type="story",
        map_size=120,
        players=2,
        difficulty="easy",
        output_path="rise_of_rome.aoe2scenario",
    ),
    ScenarioConfig(
        title="Joan of Arc's Journey",
        description="Follow Joan of Arc from Domremy to the Siege of Orleans",
        scenario_type="story",
        map_size=120,
        players=2,
        difficulty="easy",
        output_path="joan_of_arc.aoe2scenario",
    ),
    ScenarioConfig(
        title="The Rise of the Mongols",
        description="Guide Genghis Khan from uniting the tribes to forging an empire",
        scenario_type="story",
        map_size=120,
        players=2,
        difficulty="easy",
        output_path="rise_of_mongols.aoe2scenario",
    ),
    # Conquest scenarios
    ScenarioConfig(
        title="The Norman Conquest of Sicily",
        description="Conquer the island of Sicily as the Normans",
        scenario_type="conquest",
        map_size=120,
        players=2,
        difficulty="easy",
        output_path="norman_sicily.aoe2scenario",
    ),
    ScenarioConfig(
        title="Alexander's Persian Campaign",
        description="Conquer the Persian Empire as Alexander the Great",
        scenario_type="conquest",
        map_size=120,
        players=2,
        difficulty="easy",
        output_path="alexander_persia.aoe2scenario",
    ),
    ScenarioConfig(
        title="The Reconquista Begins",
        description="Reclaim Iberian territories from Moorish control",
        scenario_type="conquest",
        map_size=120,
        players=2,
        difficulty="easy",
        output_path="reconquista.aoe2scenario",
    ),
]

# Create output directories
os.makedirs("output/control", exist_ok=True)
os.makedirs("output/control/code", exist_ok=True)
os.makedirs("output/treatment", exist_ok=True)
os.makedirs("output/treatment/code", exist_ok=True)

# Run control
control = ScenarioGenerator(api_key)
for s in scenarios:
    config = ScenarioConfig(
        title=s.title,
        description=s.description,
        scenario_type=s.scenario_type,
        map_size=s.map_size,
        players=s.players,
        difficulty=s.difficulty,
        output_path=f"output/control/{s.output_path}",
    )
    print(f"[CONTROL] Generating: {config.title}")
    code = control.generate_scenario(config)

    # Save raw LLM-generated code for inspection
    code_filename = os.path.splitext(s.output_path)[0] + ".py"
    code_path = f"output/control/code/{code_filename}"
    with open(code_path, "w", encoding="utf-8") as f:
        f.write(code)
    print(f"[CONTROL] Saved code to: {code_path}")

    control.save_scenario(code, config.output_path)

# Run treatment
treatment = ScenarioGeneratorReachability(api_key)
for s in scenarios:
    config = ScenarioConfig(
        title=s.title,
        description=s.description,
        scenario_type=s.scenario_type,
        map_size=s.map_size,
        players=s.players,
        difficulty=s.difficulty,
        output_path=f"output/treatment/{s.output_path}",
    )
    print(f"[TREATMENT] Generating: {config.title}")
    code = treatment.generate_scenario(config)

    # Save raw LLM-generated code for inspection
    code_filename = os.path.splitext(s.output_path)[0] + ".py"
    code_path = f"output/treatment/code/{code_filename}"
    with open(code_path, "w", encoding="utf-8") as f:
        f.write(code)
    print(f"[TREATMENT] Saved code to: {code_path}")

    treatment.save_scenario(code, config.output_path)
