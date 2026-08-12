"""
Generate AoE2 scenarios from the command line.

This is a THIN CLI over ``generator.ScenarioGenerator.generate()``: it only
parses arguments, loads batch specs, calls ``generate()`` and reports. All
generation, validation, self-repair, best-of-N, sidecar writing and results
logging live in ``generator.py``.

Every invocation routes through ``generate()``, so every scenario produces a
metadata sidecar next to its ``.aoe2scenario`` and one ``results.jsonl`` line
per attempt (self-repair retries included). The results log defaults to
``output/results.jsonl`` so a bare run still leaves a machine-readable trail.

Single scenario (no args == the default "Flight to Chinon" escort):
    python create_scenario.py
    python create_scenario.py --model opus-4.8 --scenario-type battle \
        --title "Tours" --description "Franks vs Umayyads, 732"
    python create_scenario.py --no-reachability --best-of-n 3

Batch mode (JSONL, one scenario spec per line):
    python create_scenario.py --batch specs.jsonl
    python create_scenario.py --batch specs.jsonl --yes      # skip confirmation
    python create_scenario.py --batch specs.jsonl --dry-run  # preview, no API calls

Preview the resolved config without calling the API:
    python create_scenario.py --dry-run

Exit code is 0 only if every requested scenario reached ``success``; non-zero
otherwise (2 for a malformed batch file), so it composes in scripts.
"""

import os
import re
import sys
import json
import argparse

import api_config
from provenance import new_run_id
from generator import ScenarioGenerator, ScenarioConfig, GenerationResult

# ScenarioConfig fields a single batch-spec line may set. Anything else is a
# typo we refuse rather than silently ignore.
ALLOWED_SPEC_KEYS = {
    "title", "description", "scenario_type", "map_size", "players", "difficulty",
    "output_path", "wikipedia_url", "region", "player_civ", "enemy_civ",
    "model", "temperature", "max_tokens", "reachability_prompting",
    "fidelity_rubric", "fidelity_prompt", "fidelity_prompt_version",
    "best_of", "max_repair_attempts",
    "prompt_style", "use_introspection",
}

# Spec fields that select an experimental arm. A string here would be truthy
# whatever it said - {"fidelity_prompt": "off"} would silently turn the arm ON
# and mislabel a whole cell - so these are type-checked rather than trusted.
BOOL_SPEC_KEYS = ("reachability_prompting", "fidelity_rubric", "fidelity_prompt",
                  "use_introspection")

# Structural defaults for batch specs that omit a field. Deliberately the
# ScenarioConfig dataclass defaults (generic), NOT the single-mode CLI defaults
# (which describe one specific "Flight to Chinon" scenario).
_STRUCTURAL_DEFAULTS = ScenarioConfig(title="", description="")


def slug(title):
    """Filesystem-safe stem derived from a scenario title."""
    s = re.sub(r"[^a-z0-9]+", "_", (title or "").lower()).strip("_")
    return s or "scenario"


def derive_output_path(output_dir, title, explicit=None):
    """Single-scenario output path: an explicit --output wins, else
    ``<output_dir>/<slug(title)>.aoe2scenario``."""
    if explicit:
        return explicit
    return os.path.join(output_dir, slug(title) + ".aoe2scenario")


def batch_output_path(output_dir, title, prompt_style, spec_output, seen):
    """Resolve a batch spec's output path, avoiding collisions.

    An explicit spec ``output_path`` is respected (relative joins under
    output_dir, absolute is kept). A path derived from the title slug also
    embeds ``prompt_style`` - so templated/freeform variants of the same title
    never overwrite each other - and gets a numeric suffix on any remaining
    collision (same title AND style). ``seen`` is the set of paths already
    handed out in this batch.
    """
    if spec_output:
        return spec_output if os.path.isabs(spec_output) else os.path.join(output_dir, spec_output)
    stem = f"{slug(title)}_{slug(prompt_style)}"
    candidate = os.path.join(output_dir, stem + ".aoe2scenario")
    n = 2
    while candidate in seen:
        candidate = os.path.join(output_dir, f"{stem}_{n}.aoe2scenario")
        n += 1
    return candidate


# --------------------------------------------------------------------------- #
# Argument parsing
# --------------------------------------------------------------------------- #
def build_parser():
    p = argparse.ArgumentParser(
        prog="create_scenario.py",
        description="Generate one or many AoE2 scenarios through ScenarioGenerator.generate().",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "batch file format (JSONL, one spec per line; blank lines and #-comments ignored):\n"
            '  {"title": "The Battle of Tours", "description": "Franks vs Umayyads, 732", "scenario_type": "battle"}\n'
            '  {"title": "Defense of Vienna", "scenario_type": "defense", "best_of": 3, "model": "opus-4.8"}\n'
            "\n"
            "Each spec inherits the CLI generation flags (--model, --temperature, etc.) as\n"
            "batch-wide defaults and may override any config field. Only 'title' is required."
        ),
    )

    g = p.add_argument_group("generation parameters (batch-wide defaults; per-spec overridable)")
    g.add_argument("--model", default=None,
                   help="MODEL_REGISTRY key (e.g. opus-4.8) or raw OpenRouter slug "
                        "(default: api_config.DEFAULT_MODEL)")
    g.add_argument("--temperature", type=float, default=api_config.DEFAULT_TEMPERATURE,
                   help=f"Sampling temperature (default: {api_config.DEFAULT_TEMPERATURE})")
    g.add_argument("--max-tokens", type=int, default=api_config.DEFAULT_MAX_TOKENS, dest="max_tokens",
                   help=f"Completion token cap (default: {api_config.DEFAULT_MAX_TOKENS})")
    reach = g.add_mutually_exclusive_group()
    reach.add_argument("--reachability", dest="reachability", action="store_true",
                       help="Enable reachability-analysis prompting (default)")
    reach.add_argument("--no-reachability", dest="reachability", action="store_false",
                       help="Disable it (baseline/control prompt)")
    g.set_defaults(reachability=True)
    rubric = g.add_mutually_exclusive_group()
    rubric.add_argument("--fidelity-rubric", dest="fidelity_rubric", action="store_true",
                        help="Append the historical-fidelity guidance to the system prompt "
                             "(fidelity treatment arm)")
    rubric.add_argument("--no-fidelity-rubric", dest="fidelity_rubric", action="store_false",
                        help="Omit it (default; baseline prompt)")
    g.set_defaults(fidelity_rubric=False)
    g.add_argument("--fidelity-prompt", choices=["on", "off"], default="off",
                   dest="fidelity_prompt",
                   help="Append the v2 historical-fidelity rubric (rubric_v2.py) to the system "
                        "prompt: 'on' is the v2 fidelity treatment arm, 'off' the baseline "
                        "(default). Separate lever from --fidelity-rubric, which is the v1 block "
                        "kept for reproducing the published scores")
    g.add_argument("--fidelity-prompt-version", choices=["v2", "v3"], default="v2",
                   dest="fidelity_prompt_version",
                   help="Which fidelity rubric text the arm appends when --fidelity-prompt is on: "
                        "v2 (default) or v3")
    g.add_argument("--best-of-n", "--best-of", type=int, default=1, dest="best_of",
                   help="Generate N candidates; keep the first that builds (default: 1)")
    g.add_argument("--max-repair-attempts", type=int, default=3, dest="max_repair_attempts",
                   help="Self-repair retries after a validation/execution failure (default: 3)")
    intro = g.add_mutually_exclusive_group()
    intro.add_argument("--introspection", dest="use_introspection", action="store_true",
                       help="Ground self-repair in the installed parser's real API surface (default)")
    intro.add_argument("--no-introspection", dest="use_introspection", action="store_false",
                       help="Repair from the raw error text only (introspection-ablation control)")
    g.set_defaults(use_introspection=True)
    g.add_argument("--prompt-style", choices=["templated", "freeform"], default="templated",
                   dest="prompt_style",
                   help="Prompt-style ablation: 'templated' uses the per-scenario-type template "
                        "(default); 'freeform' sends a short generic instruction and lets the model "
                        "choose the trigger structure/count")

    o = p.add_argument_group("output & logging")
    o.add_argument("--output-dir", default="output", dest="output_dir",
                   help="Directory for generated scenarios + sidecars (default: output)")
    o.add_argument("--results-log", default="output/results.jsonl", dest="results_log",
                   help="Append-only JSONL results log, one line per attempt "
                        "(default: output/results.jsonl)")

    s = p.add_argument_group("single-scenario spec (ignored when --batch is given)")
    s.add_argument("--title", default="The Flight to Chinon")
    s.add_argument("--description",
                   default="Joan must escape English territory and reach the Dauphin. "
                           "Enemy cavalry pursue relentlessly.")
    s.add_argument("--scenario-type", default="escort", dest="scenario_type",
                   help="battle | escort | diplomacy | defense | conquest | story")
    s.add_argument("--map-size", type=int, default=120, dest="map_size")
    s.add_argument("--players", type=int, default=4)
    s.add_argument("--difficulty", default="medium")
    s.add_argument("--region", default=None)
    s.add_argument("--player-civ", default=None, dest="player_civ")
    s.add_argument("--enemy-civ", default=None, dest="enemy_civ")
    s.add_argument("--wikipedia-url", default=None, dest="wikipedia_url")
    s.add_argument("--output", default=None, dest="output_path",
                   help="Explicit full output path (overrides --output-dir + derived name)")

    m = p.add_argument_group("modes")
    m.add_argument("--batch", default=None, metavar="FILE",
                   help="JSONL file: one scenario spec per line (see format below)")
    m.add_argument("--dry-run", action="store_true", dest="dry_run",
                   help="Print the resolved config (and parsed specs) without calling the API")
    m.add_argument("-y", "--yes", action="store_true",
                   help="Skip the batch confirmation prompt (for scripting)")
    return p


# --------------------------------------------------------------------------- #
# Config construction
# --------------------------------------------------------------------------- #
def config_from_args(args):
    """Build the single-scenario ScenarioConfig from top-level CLI flags."""
    return ScenarioConfig(
        title=args.title,
        description=args.description,
        scenario_type=args.scenario_type,
        map_size=args.map_size,
        players=args.players,
        difficulty=args.difficulty,
        output_path=derive_output_path(args.output_dir, args.title, explicit=args.output_path),
        region=args.region,
        player_civ=args.player_civ,
        enemy_civ=args.enemy_civ,
        wikipedia_url=args.wikipedia_url,
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        reachability_prompting=args.reachability,
        fidelity_rubric=args.fidelity_rubric,
        fidelity_prompt=(args.fidelity_prompt == "on"),
        fidelity_prompt_version=args.fidelity_prompt_version,
        best_of=args.best_of,
        max_repair_attempts=args.max_repair_attempts,
        prompt_style=args.prompt_style,
        use_introspection=args.use_introspection,
    )


def load_specs(path, args):
    """Parse a JSONL batch file into (configs, errors).

    Generation params (model/temperature/max_tokens/reachability/best_of/
    max_repair_attempts) inherit the CLI flags as batch-wide defaults; structural
    fields fall back to ScenarioConfig defaults. Blank lines and #-comment lines
    are skipped. Fail-fast: if ``errors`` is non-empty the caller runs nothing.
    """
    configs, errors = [], []
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as e:
        return [], [f"could not open batch file: {e}"]

    d = _STRUCTURAL_DEFAULTS
    seen_paths = set()
    for lineno, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            spec = json.loads(line)
        except json.JSONDecodeError as e:
            errors.append(f"line {lineno}: invalid JSON ({e.msg})")
            continue
        if not isinstance(spec, dict):
            errors.append(f"line {lineno}: expected a JSON object, got {type(spec).__name__}")
            continue
        unknown = set(spec) - ALLOWED_SPEC_KEYS
        if unknown:
            errors.append(f"line {lineno}: unknown field(s): {', '.join(sorted(unknown))}")
            continue
        title = spec.get("title")
        if not title:
            errors.append(f"line {lineno}: missing required field 'title'")
            continue
        bad_bools = [k for k in BOOL_SPEC_KEYS
                     if k in spec and not isinstance(spec[k], bool)]
        if bad_bools:
            errors.append(
                f"line {lineno}: {', '.join(bad_bools)} must be true/false, not a string "
                "(a quoted value would silently select the wrong arm)")
            continue
        ps = spec.get("prompt_style", args.prompt_style)
        out = batch_output_path(args.output_dir, title, ps, spec.get("output_path"), seen_paths)
        seen_paths.add(out)
        configs.append(ScenarioConfig(
            title=title,
            description=spec.get("description") or title,
            scenario_type=spec.get("scenario_type", d.scenario_type),
            map_size=spec.get("map_size", d.map_size),
            players=spec.get("players", d.players),
            difficulty=spec.get("difficulty", d.difficulty),
            output_path=out,
            region=spec.get("region", d.region),
            player_civ=spec.get("player_civ", d.player_civ),
            enemy_civ=spec.get("enemy_civ", d.enemy_civ),
            wikipedia_url=spec.get("wikipedia_url", d.wikipedia_url),
            model=spec.get("model", args.model),
            temperature=spec.get("temperature", args.temperature),
            max_tokens=spec.get("max_tokens", args.max_tokens),
            reachability_prompting=spec.get("reachability_prompting", args.reachability),
            fidelity_rubric=spec.get("fidelity_rubric", args.fidelity_rubric),
            fidelity_prompt=spec.get("fidelity_prompt", args.fidelity_prompt == "on"),
            fidelity_prompt_version=spec.get("fidelity_prompt_version",
                                             args.fidelity_prompt_version),
            best_of=spec.get("best_of", args.best_of),
            max_repair_attempts=spec.get("max_repair_attempts", args.max_repair_attempts),
            prompt_style=ps,
            use_introspection=spec.get("use_introspection", args.use_introspection),
        ))

    if not configs and not errors:
        errors.append("no scenario specs found (file is empty or all comments)")
    return configs, errors


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def print_resolved_config(args, batch_mode):
    print("Resolved configuration")
    print("----------------------")
    print(f"  model:               {api_config.resolve_model(args.model)}")
    print(f"  temperature:         {args.temperature}")
    print(f"  max_tokens:          {args.max_tokens}")
    print(f"  reachability:        {'on' if args.reachability else 'off'}")
    print(f"  fidelity_rubric:     {'on' if args.fidelity_rubric else 'off'}  (v1 block)")
    print(f"  fidelity_prompt:     {args.fidelity_prompt}  "
          f"({args.fidelity_prompt_version} block)")
    print(f"  prompt_style:        {args.prompt_style}")
    print(f"  introspection:       {'on' if args.use_introspection else 'off'}")
    print(f"  best_of_n:           {args.best_of}")
    print(f"  max_repair_attempts: {args.max_repair_attempts}")
    print(f"  output_dir:          {args.output_dir}")
    print(f"  results_log:         {args.results_log}")
    if batch_mode:
        print("  (values above are batch-wide defaults; per-spec overrides shown below)")


def print_spec_list(configs):
    print(f"\nParsed {len(configs)} scenario spec(s):")
    for i, c in enumerate(configs, 1):
        title = c.title if len(c.title) <= 32 else c.title[:29] + "..."
        print(f"  {i:>3}. {title:<32} [{c.scenario_type:<9}] "
              f"model={api_config.resolve_model(c.model)} best_of={c.best_of} "
              f"style={c.prompt_style} reach={'on' if c.reachability_prompting else 'off'} "
              f"rubric_v1={'on' if c.fidelity_rubric else 'off'} "
              f"fid_v2={'on' if c.fidelity_prompt else 'off'} "
              f"-> {c.output_path}")


def print_result_line(result, config, verbose):
    if result.success:
        print(f"  -> success  (attempts={result.attempts}, candidate={result.candidate}, "
              f"triggers={result.trigger_count})")
        print(f"     scenario: {config.output_path}")
        print(f"     sidecar:  {config.output_path}.meta.json")
        return
    detail = (result.validation_detail or result.stderr or result.error or "").strip()
    if verbose:
        print(f"  -> {result.outcome}  (attempts={result.attempts})")
        print(f"     detail:\n{detail or '(no detail)'}")
    else:
        first = detail.splitlines()[0] if detail else "(no detail)"
        print(f"  -> {result.outcome}  (attempts={result.attempts}): {first}")


def print_summary(results, run_id):
    """Per-scenario table plus aggregate first-attempt / repair-loop / best-of-N rates.

    Successes partition into three mutually exclusive buckets so the two rescue
    mechanisms stay separable:
      first-attempt      : candidate 1, attempt 1 (built on the very first try)
      repair-loop rescue : candidate 1, attempts > 1 (self-repair fixed it)
      best-of-N rescue   : candidate > 1 (a later best-of-N candidate won)
    """
    n = len(results)
    print(f"\n=== Batch summary (run_id {run_id}) ===")
    print(f"{'#':>3}  {'Scenario':<34}  {'Type':<10}  {'Outcome':<18}  {'Att':>3}  {'Cand':>4}")
    print(f"{'':->3}  {'':-<34}  {'':-<10}  {'':-<18}  {'':->3}  {'':->4}")
    for i, r in enumerate(results, 1):
        title = r.title if len(r.title) <= 34 else r.title[:31] + "..."
        print(f"{i:>3}  {title:<34}  {r.scenario_type:<10}  {r.outcome:<18}  "
              f"{r.attempts:>3}  {r.candidate:>4}")

    succeeded = [r for r in results if r.success]
    first  = [r for r in succeeded if r.candidate == 1 and r.attempts == 1]
    repair = [r for r in succeeded if r.candidate == 1 and r.attempts > 1]
    bestof = [r for r in succeeded if r.candidate > 1]
    failed = [r for r in results if not r.success]

    def rate(k):
        return f"{k:>3}/{n}  ({(100.0 * k / n):5.1f}%)" if n else f"{k:>3}/0"

    print(f"\nAggregate over {n} scenario(s):")
    print(f"  succeeded:            {rate(len(succeeded))}")
    print(f"    first-attempt:      {rate(len(first))}   [candidate 1, attempt 1]")
    print(f"    repair-loop rescue: {rate(len(repair))}   [candidate 1, attempts > 1]")
    print(f"    best-of-N rescue:   {rate(len(bestof))}   [candidate > 1]")
    print(f"  failed:               {rate(len(failed))}")


# --------------------------------------------------------------------------- #
# Confirmation gate
# --------------------------------------------------------------------------- #
def confirm_batch(configs, results_log):
    models = ", ".join(sorted({api_config.resolve_model(c.model) for c in configs}))
    print(f"About to generate {len(configs)} scenario(s) with model(s): {models}")
    print(f"Results log: {results_log}")
    try:
        reply = input("Proceed? [y/N] ").strip().lower()
    except EOFError:
        print("No input available; aborting. Pass --yes to run non-interactively.")
        return False
    return reply in ("y", "yes")


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def main():
    args = build_parser().parse_args()
    batch_mode = args.batch is not None

    # 1) Assemble the list of scenarios to run.
    if batch_mode:
        configs, errors = load_specs(args.batch, args)
        if errors:
            print(f"Batch file '{args.batch}' has {len(errors)} problem(s):", file=sys.stderr)
            for e in errors:
                print(f"  - {e}", file=sys.stderr)
            return 2
    else:
        configs = [config_from_args(args)]

    # 2) Dry run: show the resolved config (+ parsed specs) and stop. No API key
    #    required, nothing written.
    if args.dry_run:
        print_resolved_config(args, batch_mode)
        if batch_mode:
            print_spec_list(configs)
        else:
            c = configs[0]
            print(f"\nSingle scenario: {c.title!r} [{c.scenario_type}] -> {c.output_path}")
        return 0

    # 3) A real run needs an API key.
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("Please set the OPENROUTER_API_KEY environment variable", file=sys.stderr)
        print("Example (Windows): set OPENROUTER_API_KEY=your_key_here", file=sys.stderr)
        return 1

    # 4) Batch confirmation gate (skippable with --yes for scripting).
    if batch_mode and not args.yes:
        if not confirm_batch(configs, args.results_log):
            print("Aborted.")
            return 1

    # 5) Run each config through the funnel, sharing one run_id per invocation.
    run_id = new_run_id()
    generator = ScenarioGenerator(api_key)
    verbose = not batch_mode
    results = []
    for c in configs:
        print(f"Generating: {c.title}  [{c.scenario_type}]  "
              f"(model={api_config.resolve_model(c.model)})")
        try:
            result = generator.generate(c, results_log=args.results_log, run_id=run_id)
        except Exception as e:  # keep a batch going past an unexpected crash
            result = GenerationResult(
                outcome="api_error", title=c.title, scenario_type=c.scenario_type,
                model=api_config.resolve_model(c.model), temperature=c.temperature,
                max_tokens=c.max_tokens, reachability_prompting=c.reachability_prompting,
                fidelity_rubric=c.fidelity_rubric, fidelity_prompt=c.fidelity_prompt,
                fidelity_prompt_version=c.fidelity_prompt_version,
                prompt_style=c.prompt_style,
                output_path=c.output_path, run_id=run_id, error=str(e))
        results.append(result)
        print_result_line(result, c, verbose)

    # 6) Summary (always for batch; single-scenario line already printed above).
    if batch_mode:
        print_summary(results, run_id)

    # 7) Exit 0 only if every requested scenario succeeded.
    return 0 if all(r.success for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
