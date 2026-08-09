# AOE2GENAI-SCENARIOS

Generating playable **Age of Empires II: Definitive Edition** scenarios with LLMs.

An LLM is prompted (via [OpenRouter](https://openrouter.ai)) to write Python that drives the
[AoE2ScenarioParser](https://github.com/KSneijders/AoE2ScenarioParser) library. The generated code
is validated, executed in a subprocess, and — if it fails — fed back to the model for repair. Every
attempt is logged, so playability rates are measurable per model, per prompt condition, and per
scenario type.

The research question is **historical fidelity**: can a model turn a real historical episode into a
scenario that is both playable and faithful? This repo covers the *playable* half end to end and
covers the *faithful* half with an LLM fidelity judge scored against a fixed rubric.

---

## Quick start

```bash
pip install -r requirements.txt

# OpenRouter API key (required for anything that calls a model)
set OPENROUTER_API_KEY=your_key_here      # Windows
export OPENROUTER_API_KEY=your_key_here   # Linux/macOS

python tools/test_api.py                  # verify the key works
python create_scenario.py --dry-run       # preview config, no API call
python create_scenario.py                 # generate the default scenario
```

Generated files land in `output/`. Copy the `.aoe2scenario` into your game folder to play:

```
C:\Users\<USERNAME>\Games\Age of Empires 2 DE\<STEAM_ID>\resources\_common\scenario\
```

Then in-game: **Editors → Scenario Editor →** open it **→ Menu → Test**.

---

## Repository layout

```
generator.py           Core: prompts, validation, subprocess build, self-repair, best-of-N
api_config.py          Model registry, defaults (model / temperature / max_tokens / timeout)
provenance.py          Sidecar + JSONL results-log writers (stdlib only)
create_scenario.py     CLI: single scenario or JSONL batch
run_experiment.py      Control vs. treatment runner (reachability-prompting ablation)

scenario_inspect.py    Reads a built .aoe2scenario back into a structured summary
reachability_audit.py  Static unwinnability audit of built scenarios (no API)
fidelity_judge.py      LLM rubric scoring of historical fidelity

tools/                 view_scenario.py, extract_campaign.py, test_api.py,
                       run_factorial.py (experiment driver), analyze.py (result tables)
examples/              david&goliath_scenario1.py (hand-written), example_usage.py (library API)
batches/               JSONL batch specs (batch_ablation.jsonl = 8 episodes x 2 prompt styles)
campaigns/             Official .aoe2campaign files + campaign JSON, used as reference material
samples/               A couple of checked-in .aoe2scenario artifacts for inspection
docs/                  Analysis notes
reachability_research/ FROZEN original control/treatment generators — do not edit
output/                Generated scenarios, .meta.json sidecars, results.jsonl
```

Everything at the root is importable; `tools/` and `examples/` hold scripts, run from the repo root.
`output/*.aoe2scenario` is gitignored — the sidecars, `results.jsonl`, `reachability.jsonl`, and
`fidelity.jsonl` are committed, because they are the experiment record.

---

## Generating scenarios

### One at a time

```bash
python create_scenario.py                                    # default "Flight to Chinon" escort
python create_scenario.py --model opus-4.8 --scenario-type battle \
    --title "Tours" --description "Franks vs Umayyads, 732"
python create_scenario.py --no-reachability --best-of-n 3    # baseline prompt, first of 3 that builds
```

Scenario types: `battle`, `escort`, `diplomacy`, `defense`, `conquest`, `story`.

Historical framing is optional but supported — `--region` (`mediterranean`, `steppe`,
`northern_europe`, `desert`, `east_asia`, `middle_east`), `--player-civ` / `--enemy-civ`
(`western_european`, `eastern_european`, `middle_eastern`, `central_asian`, `east_asian`, `african`),
and `--wikipedia-url` to anchor the model to a source.

### In batches

```bash
python create_scenario.py --batch batches/batch_ablation.jsonl --dry-run   # verify specs
python create_scenario.py --batch batches/batch_ablation.jsonl --yes       # run all 16
```

The batch file is JSONL — one spec per line, `#` comments and blank lines ignored. Only `title` is
required; any config field may be overridden per spec, and everything else inherits the CLI flags.
A malformed line aborts the whole batch *before* any API call (exit 2), reporting the line number.
At the end you get a per-scenario table plus aggregate success rates, split into `first-attempt`,
`repair-loop rescue`, and `best-of-N rescue` so the two rescue mechanisms stay separable.

Exit code is 0 only if every requested scenario succeeded, so it composes in scripts.

### From Python

```python
from generator import ScenarioGenerator, ScenarioConfig

gen = ScenarioGenerator(api_key)
result = gen.generate(ScenarioConfig(
    title="Battle of Manzikert",
    description="Byzantine vs Seljuk clash, 1071",
    scenario_type="battle",
    region="middle_east",
    player_civ="eastern_european",
    enemy_civ="central_asian",
))
```

See `examples/example_usage.py` for a runnable version.

---

## How generation works

1. Pick a template by `scenario_type`; build the system prompt (base + optional reachability block).
2. Call the model; strip markdown fences from the returned Python.
3. **Validate** — syntax parse, required imports, scenario creation, `write_to_file`, ≥1 trigger,
   ≥1 `declare_victory`.
4. **Execute** in a subprocess against a temp file, rewriting the output path.
5. **Self-repair** on failure: the failing code plus captured stderr goes back to the model, up to
   `max_repair_attempts` times. When the error is a parser API mistake (`ImportError`,
   `AttributeError`, `TypeError`, `NameError`), the real names and signatures are introspected from
   the *installed* AoE2ScenarioParser and appended to the repair prompt — so repair picks a valid
   symbol instead of guessing again.
6. **Best-of-N** if `best_of > 1`: generate up to N candidates, keep the first that builds.

Each attempt ends in exactly one outcome: `success`, `validation_failure`, `execution_error`, or
`api_error`.

> In-pipeline validation checks **playability preconditions only** — it does not simulate the game.
> Two post-hoc analyses run over the built artefacts: `reachability_audit.py` (static, no API) for
> structural unwinnability, and `fidelity_judge.py` (LLM, rubric-scored) for historical accuracy.
> See [Evaluating generated scenarios](#evaluating-generated-scenarios).

---

## Experiments

Two prompt conditions are built into the generator and can be ablated independently.

**Reachability prompting** (`--reachability` / `--no-reachability`). The treatment appends guidance
covering four failure modes — resource dead end, composition imbalance, positional trap, timing
collapse — a checklist, a required `# REACHABILITY ANALYSIS:` comment header, and a rule to prefer
`destroy_object` over `objects_in_area(quantity=0)` for win/lose conditions (an `objects_in_area==0`
victory can become permanently unreachable if one enemy garrisons, converts, or flees).

**Prompt style** (`--prompt-style templated|freeform`). `templated` sends the rigid per-type template
("EXACTLY 25–30 TRIGGERS"); `freeform` sends a short generic instruction and lets the model choose
its own trigger structure and count. Everything else is identical, so the ablation isolates the
template alone.

```bash
python run_experiment.py                              # control + treatment, default model
python run_experiment.py --models sonnet-5,opus-4.8   # sweep
python run_experiment.py --arms treatment --best-of 3
```

`run_experiment.py` uses `temperature=0.0` by default; `create_scenario.py` defaults to `0.7`.

### Reading the results

`output/results.jsonl` gets one line per **attempt** (repairs included). A run's terminal outcome for
a `(run_id, candidate)` pair is its highest `attempt` line.

```bash
# success rate by prompt style
python -c "
import json, collections
c = collections.Counter()
for line in open('output/results.jsonl', encoding='utf-8'):
    r = json.loads(line)
    c[(r['prompt_style'], r['outcome'])] += 1
for k, v in sorted(c.items()): print(k, v)
"
```

Each scenario also gets a `<name>.aoe2scenario.meta.json` sidecar recording the full config, model,
run id, candidate/attempt counts, trigger count, and outcome.

### Running the full factorial

`tools/run_factorial.py` crosses the two prompt conditions over an episode set, one process per
(episode, cell), with a bounded worker pool and one output dir + results log per cell:

```bash
python tools/run_factorial.py --episodes output/_episodes.json --workers 8   # 8 episodes x 4 cells
python tools/run_factorial.py --cells reach     # reachability only, templated
python tools/run_factorial.py --no-introspection  # every cell with introspection-guided repair off
```

---

## Evaluating generated scenarios

Building is necessary but not sufficient: a scenario that loads can still be unwinnable, and one
that is winnable can still be historically worthless. Two analyses run over the built artefacts.

### Static reachability audit (deterministic, no API)

```bash
python reachability_audit.py output/factorial --json output/reachability.jsonl
```

Inspects the trigger graph for structural defects — missing victory or defeat path, victory gated on
`OBJECTS_IN_AREA(quantity<=0)` (fragile: one enemy that garrisons or flees strands the player),
timer-only victory (the player wins by waiting), and orphan triggers (shipped disabled, never
activated). A scenario is `clean` when it has both a victory and a defeat path, its victory is
neither fragile nor timer-only, and nothing is orphaned.

### LLM fidelity judge

```bash
python fidelity_judge.py --scan output/factorial --update-sidecars
python fidelity_judge.py --scan output/factorial --repeats 3        # judge self-consistency
python fidelity_judge.py --scan output/factorial --mismatch-control # discriminant validity
```

Scores five dimensions 1–5 (`combatants`, `material`, `events`, `anachronism`, `pedagogy`) against a
fixed rubric. The judge sees only a content digest of the built scenario — rosters, trigger
structure, in-game text — never the generating code, the model, or the prompt condition, so it
cannot infer which arm produced what. Defaults to Opus 5, a different model family from the default
generator, so it is not grading its own output.

`--mismatch-control` scores each scenario against a *different* episode's brief. A judge with real
discriminant validity should rate those far lower than matched pairs; the gap is the judge's
validation. Results append to `output/fidelity.jsonl`; `--update-sidecars` merges the aggregate into
each `.meta.json` under a `fidelity` key.

`scenario_inspect.py` is the shared reader behind both (`python scenario_inspect.py <file>` prints
the digest a judge would see).

---

## Tools

```bash
python tools/view_scenario.py samples/siege_of_constantinople_1453.aoe2scenario
python tools/extract_campaign.py campaigns/cam3.aoe2campaign   # -> campaigns/cam3_scenarios/
python tools/test_api.py
```

`extract_campaign.py` handles unencrypted AoE2 DE `.aoe2campaign` containers (version 2.00).
Encrypted `.gpv` DLC campaigns need decryption keys and are not supported.

| File | Campaign | Scenarios |
|------|----------|-----------|
| `campaigns/cam2.aoe2campaign` | Joan of Arc | 6 |
| `campaigns/cam3.aoe2campaign` | Saladin | 6 |
| `campaigns/cam4.aoe2campaign` | Genghis Khan | 6 |

These are reference material — the official campaigns are what the generated scenarios are
stylistically modelled on.

---

## Models

`api_config.MODEL_REGISTRY` maps friendly keys to pinned OpenRouter slugs. Frontier entries are
dated snapshots (captured 2026-07-17); the 2024 legacy keys are kept verbatim for reproducibility
and will 404 today. Any raw slug not in the registry is passed through unchanged.

| Key | Slug |
|-----|------|
| `sonnet-5` | `anthropic/claude-sonnet-5-20260630` (default) |
| `opus-4.8` | `anthropic/claude-opus-4.8-20260528` |
| `fable-5` | `anthropic/claude-fable-5-20260609` |

---

## Notes for contributors

`CLAUDE.md` carries the detailed spec — parser idioms, trigger-design rules (prefer area triggers
over timers), wall/gate ownership constraints for AI players, and the full config/provenance schema.
Read it before touching prompt text in `generator.py`.

`reachability_research/` holds the frozen pre-merge generators. They are superseded by the top-level
`generator.py` plus the `reachability_prompting` flag and are no longer imported by anything — keep
them byte-identical for reproducibility.
