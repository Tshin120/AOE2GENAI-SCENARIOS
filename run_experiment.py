"""
Control vs treatment experiment runner.

Both arms now use the SINGLE merged generator (top-level generator.py); the arm
is selected purely by the reachability_prompting flag:

    control   -> reachability_prompting = False   (baseline prompt)
    treatment -> reachability_prompting = True    (reachability-analysis prompt)

Every generation attempt is funneled through ScenarioGenerator.generate(), which
records exactly one outcome per attempt (success / validation_failure /
execution_error / api_error) to a per-run JSONL results log and writes a metadata
sidecar next to each .aoe2scenario. Temperature defaults to 0.0 here for
reproducibility (both arms identical except the one flag).

Examples:
    python run_experiment.py
    python run_experiment.py --model opus-4.8 --best-of 3
    python run_experiment.py --models sonnet-5,opus-4.8 --arms treatment
"""

import os
import sys
import argparse

from generator import ScenarioGenerator, ScenarioConfig
from provenance import new_run_id
import api_config

# Base scenario specs. output_path is a bare filename here; the arm/model prefix
# is added per run in build_config().
SCENARIOS = [
    # Battle scenarios
    ScenarioConfig(title="The Battle of Tours",
                   description="Charles Martel's Franks defend against the Umayyad invasion of 732",
                   scenario_type="battle", map_size=120, players=2, difficulty="easy",
                   output_path="battle_of_tours.aoe2scenario"),
    ScenarioConfig(title="The Battle of Hastings",
                   description="William the Conqueror vs Harold Godwinson in 1066",
                   scenario_type="battle", map_size=120, players=2, difficulty="easy",
                   output_path="battle_of_hastings.aoe2scenario"),
    ScenarioConfig(title="The Battle of Thermopylae",
                   description="Leonidas and the Spartans hold the pass against the Persian army",
                   scenario_type="battle", map_size=120, players=2, difficulty="easy",
                   output_path="battle_of_thermopylae.aoe2scenario"),
    # Defense scenarios
    ScenarioConfig(title="The Defense of Vienna",
                   description="Defend Vienna from the Ottoman siege of 1529",
                   scenario_type="defense", map_size=120, players=2, difficulty="easy",
                   output_path="defense_of_vienna.aoe2scenario"),
    ScenarioConfig(title="The Siege of Constantinople",
                   description="Defend Constantinople against the Ottoman assault of 1453",
                   scenario_type="defense", map_size=120, players=2, difficulty="easy",
                   output_path="siege_of_constantinople.aoe2scenario"),
    ScenarioConfig(title="The Siege of Acre",
                   description="Defend the last Crusader fortress against the Mamluk assault of 1291",
                   scenario_type="defense", map_size=120, players=2, difficulty="easy",
                   output_path="siege_of_acre.aoe2scenario"),
    # Story scenarios
    ScenarioConfig(title="The Rise of Rome",
                   description="Guide Rome from a small settlement to regional power",
                   scenario_type="story", map_size=120, players=2, difficulty="easy",
                   output_path="rise_of_rome.aoe2scenario"),
    ScenarioConfig(title="Joan of Arc's Journey",
                   description="Follow Joan of Arc from Domremy to the Siege of Orleans",
                   scenario_type="story", map_size=120, players=2, difficulty="easy",
                   output_path="joan_of_arc.aoe2scenario"),
    ScenarioConfig(title="The Rise of the Mongols",
                   description="Guide Genghis Khan from uniting the tribes to forging an empire",
                   scenario_type="story", map_size=120, players=2, difficulty="easy",
                   output_path="rise_of_mongols.aoe2scenario"),
    # Conquest scenarios
    ScenarioConfig(title="The Norman Conquest of Sicily",
                   description="Conquer the island of Sicily as the Normans",
                   scenario_type="conquest", map_size=120, players=2, difficulty="easy",
                   output_path="norman_sicily.aoe2scenario"),
    ScenarioConfig(title="Alexander's Persian Campaign",
                   description="Conquer the Persian Empire as Alexander the Great",
                   scenario_type="conquest", map_size=120, players=2, difficulty="easy",
                   output_path="alexander_persia.aoe2scenario"),
    ScenarioConfig(title="The Reconquista Begins",
                   description="Reclaim Iberian territories from Moorish control",
                   scenario_type="conquest", map_size=120, players=2, difficulty="easy",
                   output_path="reconquista.aoe2scenario"),
]

ARM_REACHABILITY = {"control": False, "treatment": True}


def _safe_dir(slug):
    """Make a model slug safe to use as a directory name."""
    return slug.replace("/", "_").replace(":", "_").replace(".", "-")


def build_config(base, arm_dir, model, temperature, reachability, best_of, max_repair):
    return ScenarioConfig(
        title=base.title,
        description=base.description,
        scenario_type=base.scenario_type,
        map_size=base.map_size,
        players=base.players,
        difficulty=base.difficulty,
        output_path=f"output/{arm_dir}/{base.output_path}",
        model=model,
        temperature=temperature,
        reachability_prompting=reachability,
        best_of=best_of,
        max_repair_attempts=max_repair,
    )


def run_arm(gen, arm_label, arm_dir, reachability, args, model, results_log, run_id):
    os.makedirs(f"output/{arm_dir}/code", exist_ok=True)
    resolved = api_config.resolve_model(model)
    counts = {}
    for base in SCENARIOS:
        config = build_config(base, arm_dir, model, args.temperature, reachability,
                              args.best_of, args.max_repair)
        print(f"[{arm_label.upper()}] Generating: {config.title} (model={resolved})")
        result = gen.generate(config, results_log=results_log, run_id=run_id)

        # Save the chosen candidate's raw code for inspection (empty on api_error).
        if result.code:
            code_filename = os.path.splitext(base.output_path)[0] + ".py"
            with open(f"output/{arm_dir}/code/{code_filename}", "w", encoding="utf-8") as f:
                f.write(result.code)

        counts[result.outcome] = counts.get(result.outcome, 0) + 1
        print(f"[{arm_label.upper()}] {config.title}: {result.outcome} "
              f"(attempts={result.attempts}, triggers={result.trigger_count})")
    print(f"[{arm_label.upper()}] summary: {counts}")


def main():
    parser = argparse.ArgumentParser(description="Run the control/treatment scenario experiment.")
    parser.add_argument("--model", default=None,
                        help="MODEL_REGISTRY key or raw OpenRouter slug (default: api_config.DEFAULT_MODEL)")
    parser.add_argument("--models", default=None,
                        help="Comma-separated models to sweep (overrides --model)")
    parser.add_argument("--temperature", type=float, default=0.0,
                        help="Sampling temperature (default 0.0 for reproducibility)")
    parser.add_argument("--best-of", type=int, default=1, dest="best_of",
                        help="Generate N candidates, keep the first that builds")
    parser.add_argument("--max-repair-attempts", type=int, default=3, dest="max_repair",
                        help="Self-repair retries after a validation/execution failure")
    parser.add_argument("--arms", default="control,treatment",
                        help="Comma list of arms to run: control,treatment")
    parser.add_argument("--results-log", default="output/results.jsonl", dest="results_log",
                        help="Path to the per-run JSONL results log")
    args = parser.parse_args()

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("Please set the OPENROUTER_API_KEY environment variable")
        sys.exit(1)

    models = [m.strip() for m in args.models.split(",")] if args.models else [args.model]
    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    sweeping = len(models) > 1

    gen = ScenarioGenerator(api_key)
    run_id = new_run_id()  # one run id groups this whole invocation
    print(f"=== RUN {run_id} | models={[api_config.resolve_model(m) for m in models]} "
          f"| arms={arms} | temp={args.temperature} | best_of={args.best_of} ===")

    for model in models:
        resolved = api_config.resolve_model(model)
        for arm in arms:
            if arm not in ARM_REACHABILITY:
                print(f"Skipping unknown arm: {arm}")
                continue
            # When sweeping models, nest per-model dirs so outputs don't clobber.
            arm_dir = arm if not sweeping else f"{arm}/{_safe_dir(resolved)}"
            run_arm(gen, arm, arm_dir, ARM_REACHABILITY[arm], args, model,
                    args.results_log, run_id)

    print(f"\nDone. Results log: {args.results_log}")


if __name__ == "__main__":
    main()
