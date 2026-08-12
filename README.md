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

The method is an iterative loop — write a rubric, put it in the generator's system prompt, measure
whether quality moves, revise, repeat — run to find the **residual**: what a model fails to improve
at even when handed the exact grading criteria. What that loop has produced so far is in
[Experiment record](#experiment-record); the short version is that the largest single effect came
from three lines of **extracted API fact**, not from better instructions, and it holds on episodes
the facts were never derived from.

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
failure_modes.py       Detectors for the four failure modes the reachability prompt names
fidelity_judge.py      LLM rubric scoring of historical fidelity (--rubric v1|v2|v2.1|v3|v3.1)

rubric_v2.py           FROZEN v2 instrument. One source of truth for both sides: the
                       generator-side block and the judge-side anchors, so they cannot drift
rubric_v3.py           FROZEN v3 instrument. Splits `setting` into civilization + terrain,
                       and carries the terrain digest. Defines its OWN objective anchor
rubric_v2_1.py         The objective-anchor revision. Splices a new OBJECTIVE section into a
                       copy of each frozen text, so everything else stays byte-identical

tools/                 view_scenario.py, extract_campaign.py, test_api.py,
                       run_factorial.py (experiment driver), analyze.py (result tables),
                       dedupe_fidelity.py (collapse duplicate judgements in a fidelity log),
                       heldout_analysis.py (paired held-out generalization test),
                       topography_prior.py (blind episode ratings for the terrain analysis)
examples/              david&goliath_scenario1.py (hand-written), example_usage.py (library API)
batches/               JSONL batch specs (batch_ablation.jsonl = 8 episodes x 2 prompt styles)
campaigns/             Official .aoe2campaign files + campaign JSON, used as reference material
samples/               A couple of checked-in .aoe2scenario artifacts for inspection
docs/                  Analysis notes
reachability_research/ FROZEN original control/treatment generators — do not edit
output/                Generated scenarios, .meta.json sidecars, results.jsonl, and one dir +
                       fidelity log per arm (factorial/, fidelity_v2_arm*/, fidelity_v3_arm/,
                       heldout_base/, heldout_api/), reachability*.jsonl, tables.tex

episodes_heldout.json  The 8 held-out episodes, no overlap with the original corpus
predictions_v3.md      Pre-registration for the v3 run — falsified, kept as the record
falsification_v3.md    What the v3 rule firing does and does not license
NEXT_STEPS.md          Where the loop stands and what runs next
```

Everything at the root is importable; `tools/` and `examples/` hold scripts, run from the repo root.
`output/*.aoe2scenario` is gitignored — the sidecars, `results.jsonl`, the reachability rows, and
every fidelity log are committed, because they are the experiment record.

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

Four prompt levers are built into the generator and can be ablated independently. Each is off by
default, and each off-path is byte-identical to the prompt before that lever existed, so earlier
runs stay comparable.

**Reachability prompting** (`--reachability` / `--no-reachability`). The treatment appends guidance
covering four failure modes — resource dead end, composition imbalance, positional trap, timing
collapse — a checklist, a required `# REACHABILITY ANALYSIS:` comment header, and a rule to prefer
`destroy_object` over `objects_in_area(quantity=0)` for win/lose conditions (an `objects_in_area==0`
victory can become permanently unreachable if one enemy garrisons, converts, or flees).

**Prompt style** (`--prompt-style templated|freeform`). `templated` sends the rigid per-type template
("EXACTLY 25–30 TRIGGERS"); `freeform` sends a short generic instruction and lets the model choose
its own trigger structure and count. Everything else is identical, so the ablation isolates the
template alone.

**Fidelity rubric, v1** (`--fidelity-rubric`). Restates the judged fidelity dimensions as generation
*instructions*, never as scoring anchors. Deliberately sized to the reachability block (5744 vs 5877
chars) so an A/B cannot be confounded with prompt length. Its text is frozen — it produced the
published rubric-arm scores.

**Fidelity rubric, v2/v3** (`--fidelity-prompt on|off`, `--fidelity-prompt-version v2|v3`). The
paper's rubric text verbatim, from `rubric_v2.py` / `rubric_v3.py`, so the generator-side instruction
and the judge-side criterion cannot drift apart. Since generator 2.4 this arm also ships
`FIDELITY_API_SUPPORT_BLOCK` — the verified `Civilization` / rename API the rubric's requirements
need. **The two are attached together and cannot currently be separated**: `--fidelity-prompt on`
gives rubric *and* API facts, so any run of this arm measures the combined effect. Reproducing the
rubric-only condition means pinning generator 2.3.

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
python tools/run_factorial.py --cells reach       # reachability only, templated
python tools/run_factorial.py --no-introspection  # every cell with introspection-guided repair off
```

`--cells` selects which arm to run. Each of the one-factor arms is scored against its own baseline,
one factor apart:

| `--cells` | Cell(s) | Baseline it pairs against |
|---|---|---|
| `all` (default) | the 2×2 reachability × prompt-style factorial | — |
| `baseline` | `reach_off__freeform` alone | — (this *is* the shared baseline) |
| `reach` / `style` | one factor of the 2×2 | the opposite cell |
| `rubric` | `rubric_on__freeform` (v1 fidelity rubric) | `reach_off__freeform` |
| `fidelity` | `fidelity_on__freeform` (v2 rubric + API facts) | `reach_off__freeform` |
| `fidelity_v3` | `fidelity_v3__freeform` | `reach_off__freeform` |
| `fidelity_reach` | `fidelity_on__reach_on__freeform` | `reach_on__freeform` |

Use `baseline` rather than `all` when a paired comparison only needs that one cell — it is a quarter
of the generation cost.

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

### The four failure modes

The audit above checks the *shape* of the victory conditions. `failure_modes.py` checks the taxonomy
the reachability prompt block actually names, so the treatment is measured against its own claim
rather than against a proxy. It runs as part of the audit by default (`--no-failure-modes` skips it,
which also skips the terrain parse and is faster):

| Mode | Fires when |
|------|-----------|
| `resource_dead_end` | the player is given an economy but the map lacks a resource class it needs |
| `composition_imbalance` | an enemy force class has no counter available, in units or in production buildings |
| `positional_trap` | the objective is unreachable on foot from the start (flood fill over terrain, buildings, and gates the player cannot open) |
| `timing_collapse` | the first scripted hostile action lands before the player has anything to answer it |

Every detector reads the built artefact offline and none simulate the game, so each is a screen, not
a proof — they are tuned to fire on the clear-cut case and stay quiet when the evidence is
ambiguous. Each row of `reachability.jsonl` carries `failure_modes`, `failure_modes_fired`, and
`n_failure_modes`.

### LLM fidelity judge

```bash
python fidelity_judge.py --scan output/factorial --rubric v2.1 --repeats 3 --update-sidecars
python fidelity_judge.py --scan output/factorial --rubric v1        # the frozen published instrument
python fidelity_judge.py --scan output/factorial --mismatch-control # discriminant validity
```

Scores each dimension 1–5 against a fixed rubric. The judge sees only a content digest of the built
scenario — rosters, trigger structure, in-game text — never the generating code, the model, or the
prompt condition, so it cannot infer which arm produced what. Defaults to Opus 5, a different model
family from the default generator, so it is not grading its own output.

**Five instruments ship, and their scores are never pooled.**

| `--rubric` | Dimensions | Overall score | Rubric hash |
|---|---|---|---|
| `v1` | combatants, material, events, anachronism, pedagogy | mean of all 5 | *(predates hashing)* |
| `v2` | combatants, setting, events, objective, pedagogy | mean of first 4 | `675888722d2d3786` |
| **`v2.1`** | same as v2 | mean of first 4 | `c51d48535325f97f` |
| `v3` | combatants, civilization, terrain, events, objective, pedagogy | mean of first 5 | `dcfc95e1f8ba8c98` |
| `v3.1` | same as v3 | mean of first 5 | `02346252f802005e` |

`v2.1` / `v3.1` are point revisions that change one anchor's wording and nothing structural. Every
row records both the version *and* the hash of the exact grading text, because a bare version label
is not enough to attribute a score — the v2 text was once revised in place, and rows on both sides of
that edit carry the same `"v2"`. Two rows are comparable when their hashes match; `--resume` and
`tools/analyze.py` both refuse to pool across a mismatch.

`pedagogy` is scored and reported but excluded from every mean from v2 onward, being largely
predicted by the others. `objective` is scored from the victory and defeat conditions **extracted
from the trigger graph**, not from the objectives text — that separation is what stops it collapsing
into a second narration score. Two static preconditions run before the judge and are reported beside
the scores without being shown to it: every placed named hero must appear in the brief, and every
active player must have a civilization assigned.

`--mismatch-control` scores each scenario against a *different* episode's brief. A judge with real
discriminant validity should rate those far lower than matched pairs; the gap is the judge's
validation. Results append to the `--out` log; `--update-sidecars` merges the aggregate into each
`.meta.json` under a per-instrument key (`fidelity` for v1, `fidelity_v2`, `fidelity_v2_1`, …), so
re-scoring under one instrument never overwrites another.

The sidecar aggregate is built from the whole log rather than from the current invocation, since a
sweep is normally several passes (one per directory, then a `--resume` top-up for failures). That
also makes `--update-sidecars --resume` with nothing left to score a zero-cost repair.

`scenario_inspect.py` is the shared reader behind both (`python scenario_inspect.py <file>` prints
the digest a judge would see).

If two judging processes ever append rows for the same `(scenario, repeat, mode)` triple — a sweep
that looked dead but was still buffering — those scenarios double-weight every cell mean. Collapse
them before analysis:

```bash
python tools/dedupe_fidelity.py output/fidelity.jsonl --check   # report only
python tools/dedupe_fidelity.py output/fidelity.jsonl           # rewrite, keeping <path>.raw
```

### Joining the three streams

`tools/analyze.py` keys build outcomes, reachability rows, and fidelity scores on the scenario output
path, so one row is one (episode, cell) pair and every metric lines up:

```bash
python tools/analyze.py --root output/factorial \
    --reachability output/reachability.jsonl \
    --fidelity output/fidelity.jsonl,output/fidelity_v2_rev2.jsonl,output/fidelity_v2_1.jsonl \
    --latex output/tables.tex
```

It prints build outcomes by cell (Table 1), the reachability audit (2) and failure-mode taxonomy
(2b), fidelity by cell (3) and on matched pairs only (3b), judge validation (4), and self-repair
behaviour (5). `--latex` also writes the same tables as LaTeX.

`--fidelity` is repeatable (or comma-separated) — pass several logs to render every instrument side
by side. Each distinct (rubric version, rubric hash) gets **its own table** and they are never
pooled; an unknown version aborts rather than silently rendering one instrument's numbers under
another's column headers.

---

## Experiment record

Every arm below is committed — sidecars, results logs, and fidelity logs — so the tables regenerate
from the repo. **All of it is n=8 per cell, one model.** Treat effect sizes as exploratory.

### The factorial (the original pilot)

`output/factorial/` — **8 episodes × 4 cells**, reachability on/off × templated/freeform.

- **Build**: 31/32 built; 7 episodes needed at least one repair and all 7 were rescued.
- **Reachability**: no scenario had *every* victory path fragile. Fragile-but-redundant and
  timer-only victories appeared only under the templated style (~35 triggers, 2+ victory paths);
  freeform cells were 100% clean at ~13 triggers and ~1 path.
- **Prompt style** was the larger effect; the reachability arm did not separate cleanly at this n.

### The API-facts result — the headline

Three lines of extracted `Civilization` / rename API fact, shipped with the v2 rubric arm. Paired
per-episode against the shared baseline, scored under v2.1:

| | delta | 95% CI |
|---|---:|---|
| **MEAN4** | **+0.89** | [+0.51, +1.26] |
| setting | +1.83 | [+1.49, +2.18] |
| combatants | +1.08 | [+0.36, +1.80] |
| events | +0.12 | [−0.34, +0.59] |

The **static preconditions** are the cleanest part, being pass/fail with no judge noise: civilization
assigned went **0/8 → 8/8**, and every-placed-hero-in-the-brief **4/8 → 8/8**. The dissociation is
the finding — `setting` was mostly API knowledge, `combatants` mostly instruction. The
unset-civilization defect that ran through all 31 baseline scenarios was never a modelling failure;
three lines of API fact fixed it.

### Held-out generalization

The API facts were derived from the original eight episodes' failures, so the standing objection was
that they are eight patches. `episodes_heldout.json` is eight unseen episodes covering configuration
space the original never used — `conquest` and `diplomacy` types, `east_asia` / `middle_east`
regions, three 3-player scenarios — and several stress exactly what the facts address: figures with
no AoE2 hero unit, polities with no clean `Civilization` enum match.

```bash
python tools/run_factorial.py --episodes episodes_heldout.json --root output/heldout_base --cells baseline
python tools/run_factorial.py --episodes episodes_heldout.json --root output/heldout_api  --cells fidelity
python fidelity_judge.py --scan output/heldout_base --rubric v2.1 --repeats 3 --out output/fidelity_heldout.jsonl
python tools/heldout_analysis.py
```

| | original 8 | held-out 8 |
|---|---|---|
| MEAN4 delta | +0.89 [+0.51, +1.26] | **+1.18 [+0.88, +1.47]** |
| setting delta | +1.83 | +2.08 |
| combatants delta | +1.08 | +1.79 |
| civilization precondition | 0/8 → 8/8 | **0/8 → 8/8** |
| hero precondition | 4/8 → 8/8 | **2/8 → 8/8** |

**It generalizes.** The held-out effect is at least as large on episodes the facts never saw, from a
*lower* baseline, with all 8 per-episode deltas positive. Difference of deltas +0.29 (SE 0.20), not
distinguishable from zero.

Two caveats that belong with the number. The held-out arm measures rubric **and** API facts together,
because generator 2.4 attaches them as a unit. And the separate "first-attempt builds 0/8 → 8/8"
claim is a *different* contrast — rubric-only (generator 2.3) → rubric+API (2.4), not baseline →
rubric+API — which cannot be tested on held-out episodes, since the 2.4 baseline is already 8/8.

### The v3 run — a recorded falsification

`predictions_v3.md` pre-registered *terrain moves more than 0.5 → hypothesis wrong.* Terrain moved
**+0.75**; the rule fired and is recorded as fired. But the result is carried by one episode
(Hastings contributes +3.00 of +6.00; the other seven average +0.43), the discriminating prediction
failed on all three clauses, and 1 of 5 predicted ranges was hit — the one that was the control.
A follow-up ruled out prior strength as the explanation (ρ = −0.35, p = 0.39).

Full accounting in `falsification_v3.md`. It is kept because a pre-registration is only worth what it
costs to honour.

### Judge validation

Matched briefs mean **4.20** vs mismatched **1.03** on the v2 arm — a separation of **+3.17**.
Within-scenario SD of the overall score is 0.07–0.09 across repeats, roughly a tenth of the
between-scenario spread.

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

**Frozen means frozen.** `rubric_v2.py` and `rubric_v3.py` have judgements hashed against their exact
text (138 and 48 respectively), and `reachability_research/` holds the pre-merge generators. Editing
any of them orphans the rows that cite them. To revise a rubric, do what `rubric_v2_1.py` does:
splice the new section into a *copy* of the frozen text, so every other dimension stays
byte-identical and the change earns a fresh hash. `FIDELITY_RUBRIC_BLOCK` (the v1 generator-side
block) is frozen for the same reason — it produced the published rubric-arm scores.

**Pre-register before running.** `predictions_v3.md` says it on its own first line, and it was
nevertheless committed after the run it predicts — the record notes that, because an mtime is weaker
evidence than a commit. Write and commit `predictions_v<n>.md` first; a prediction recorded after the
result is not a prediction.

**Do not pool across instruments.** Scores carry a rubric version *and* a text hash. v1/v2/v3 measure
different dimension sets, and a `.1` revision measures the same set differently. `tools/analyze.py`
renders one table per (version, hash) and aborts on an unknown version rather than guessing.
