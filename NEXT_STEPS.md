# AoE2 scenario generation — where things stand and what to do next

Written 2026-08-12. Resume point after iteration 3 of the rubric loop, with
STEP 0 resolved and the v2/v3 arms re-scored under the corrected `objective`
anchor the same day.

---

## The research program

An iterative loop, run with Prof. Santolucito: build a rubric → put it in the
generator's system prompt → measure whether scenario quality rises, falls, or
stagnates → revise the rubric → repeat. The finding being chased is the
**residual**: what the models fail to improve at even when handed the exact
grading criteria. Keep going until a dimension refuses to move.

A dimension counts as a roadblock when it moves **less than 0.2 across two
consecutive interventions that specifically target it, while other dimensions
in the same run do move.** That control clause is load-bearing — a dimension
that stalls in a run where nothing else moves indicates a weak intervention,
not a ceiling.

---

## STEP 0 — RESOLVED: the anchor was broken, not the wiring

**The wiring was intact.** `{objective_facts}` is a live placeholder in both the
v2 and v3 user templates, and the `EXTRACTED VICTORY AND DEFEAT CONDITIONS`
block does reach the judge. The "every `objective` score is invalid" branch does
**not** fire.

**The defect was in the anchor text**, which told the judge it was "NOT judging
whether the win is reachable or well-formed — that is settled separately by a
static audit" and then blessed a timer-alone victory as correct for a siege.
Nothing mentioned the timer's **magnitude**, so a 1-second win and a
thirty-minute hold were indistinguishable.

The missed distinction is a condition's **form** (the kind of goal) versus its
**parameters** (the magnitude and target that say *which* goal of that kind).
Only form was being scored. A survival timer's duration *is* the claim about how
long the defenders had to hold, so it belongs to this dimension, not the audit.

**The fix** lives in `rubric_v2_1.py`, which splices a revised OBJECTIVE section
into a copy of the frozen v2 and v3 text — every other dimension comes through
byte-identical, enforced by the splice. New hashes: v2.1 `c51d48535325f97f`,
v3.1 `02346252f802005e`. `rubric_v2.py` and `rubric_v3.py` are unmodified except
for one corrected docstring (see below).

**One thing the draft anchor got wrong and the shipped one handles.**
`format_objective_facts()` renders the *engine unit constant*, not the unit's
in-game name, so a generic renamed to a historical commander is
indistinguishable from an ordinary unit of the line. A flat "a unit hunt scores
at most 2" would punish exactly the renaming `combatants` rewards — Tours'
`DESTROY_OBJECT on CAMEL_RIDER [path "Death of Abd al-Rahman"]` is the
commander's death, not a unit hunt. The anchor points the judge at the trigger
path name as the disambiguator, worded generically so no episode is named in the
instrument.

**Also corrected:** `format_objective_facts`'s docstring claimed the judge sees
its block "INSTEAD of the objectives text". It does not, and must not —
`pedagogy` is defined over the narration and `events` over its dated claims, so
stripping it to insulate `objective` would break two dimensions to fix one. The
separation is enforced by the anchor's "and from nothing else", not by omission
from the prompt. Treat it as the softer guarantee it is. Docstring only;
`rubric_hash` unaffected.

**Smoke test** (3 repeats each, v3.1) before the full re-score:

| scenario | victory condition | before | after |
|---|---|---:|---:|
| Hastings | `TIMER on 1s elapsed` | 4.33 | **1.00** |
| Vienna | unit hunt on a `CAMEL_RIDER` | 3.00 | **2.00** |
| Constantinople | `TIMER 450s` + real Hagia Sophia defeat | 5.00 | **5.00** ← control |

**Full re-score: 186 judgements, zero failures.** Results in
`output/fidelity_v2_1.jsonl` (46 scenarios × 3) and `output/fidelity_v3_1.jsonl`
(16 × 3); sidecars carry them under their own `fidelity_v2_1` key so the frozen
v2 scores beside them are untouched.

**Verdict: `objective` stays in the scored mean.** See "Where the numbers stand"
for the evidence — the short version is that the criterion which excluded
`pedagogy` (largely predicted by the others) points the *other* way here.

### Harness changes that came with it

- **Sidecar slots are now per-instrument.** v3 wrote to `fidelity_v2`, so the
  first `--update-sidecars` run under v3 would have silently overwritten the v2
  scores. Nothing had yet. `sidecar_key()` now gives each version its own.
- **`JUDGE_MAX_TOKENS` 4000 → 12000.** At 4000, ~a quarter of replies under the
  longer anchor were cut off mid-JSON and discarded as `judge_failed` —
  paid-for judgements thrown away. The cap bounds reply length only, so it
  cannot change a score that already fit under it. 186/186 succeeded after.

---

## STEP 1 — DONE: the falsification is recorded

Full record in **`falsification_v3.md`**. Summary:

`predictions_v3.md` pre-registered *terrain moves more than 0.5 → hypothesis
wrong.* Terrain moved **+0.75**. The rule fired. It is recorded as fired and is
not reinterpreted — the pre-registration is worth more than the hypothesis.

**Correct conclusion: "not supported," not "false."** Hastings alone contributes
+3.00 of the +6.00 total; without it the mean over the remaining seven is +0.43,
in the undetermined band between the 0.2 stall line and the 0.5 falsification
line. The split is 5W–1L–2T: one-sided p ≈ 0.11, two-sided p ≈ 0.22.

- Dead: the strong claim that perception is unreachable by instruction.
- Not established: that instruction reaches it either.

**The discriminating prediction failed on all three clauses**, which matters
more than the headline. It required terrain < 0.2 while combatants and objective
each moved > 0.4; observed was terrain **+0.75**, combatants **+0.00**,
objective **−0.46** — the exact inverse of the predicted pattern, with the
control clause that was meant to guard against misreading a weak intervention
firing in the wrong direction.

Prediction accuracy was poor and is reported as such: **1 of 5 ranges hit, and
the hit was `civilization`, the control predicted to do nothing.** The
`objective` miss is now explained by STEP 0 — it assumed A would fall to ~3.4
once defeat was graded, and A came back 5.00 because the anchor could not see a
condition's parameters. That was an instrument fault, not a wrong guess.

**Not an artifact of the broken anchor.** Re-scored under v3.1, terrain reads
2.46 → 3.25 = **+0.79**, still over the line, still +3.00 of it from Hastings,
still +0.48 without.

The Hastings map was the only one in either arm using elevation — a plateau at
height 3 across the middle third, i.e. Senlac Hill — produced by the v3 clause
telling the model to reason explicitly about layout before placing anything.
Explicit symbolic reasoning partially substituting for perception is a
hypothesis this run generated, not a result it produced.

---

## STEP 2 — DONE: prior strength does not explain it

Ratings by a model shown only the episode briefs, never the terrain scores or
the hypothesis; six repeats. `python tools/topography_prior.py --repeats 6`,
saved to `output/topography_prior.json`. A hand ranking was rejected as
unblindable — whoever writes it has already seen the deltas.

**It does not track. Terrain's ambiguity does not resolve.**

| correlation | Spearman ρ | exact perm p |
|---|---:|---:|
| prior vs terrain **Δ** | **−0.35** | 0.394 |
| prior vs baseline A | +0.55 | 0.156 |
| prior vs post-v3 B | +0.56 | 0.151 |

The sign on Δ is *negative*, and the three highest-prior episodes returned 0.00,
−1.00 and +3.00 — the entire observed range. A post-hoc rescue (instruction
helps most where a strong prior is *unexpressed* in the baseline) also fails:
ρ = −0.12, p = 0.79, and −0.69 with Hastings removed. Recorded in
`falsification_v3.md` so it is not re-derived later and mistaken for a finding.

**One durable secondary result.** Prior does predict the **baseline**: ρ = +0.55,
and **+0.90 with Hastings removed**. The model's topographic knowledge already
reaches the map before any terrain instruction exists — pre-v3 maps are better
for better-documented ground. Hastings is the single episode that breaks that
otherwise-tight relationship, and it is the one episode the instruction moved.

Every candidate explanation tested — perception, prior strength, unexpressed
prior — collapses onto that one episode.

---

## STEP 3 — v4, targeting force composition

### The revised hypothesis: point facts vs. structural relations

Not perception vs. knowledge. The model sets fields correctly and structures
programs poorly.

| what was asked for | shape | Δ |
|---|---|---|
| assign a civilization | one enum per player | +0.29 (from near-ceiling) |
| use the right hero | one constant per unit | +1.10 (v2) |
| match force **proportions** | quantitative relation | **+0.00** |
| order events **causally** | trigger-graph structure | **+0.17** |

`combatants` moved **exactly 0.00** after being told explicitly to match unit
types and rough proportions to the sources — in a run where `civilization` and
`terrain` both moved. That is one stall with a live control. **A second
targeted intervention that also stalls confirms the roadblock** under the
criterion above.

### v4 design

- Target force composition again, harder and more specifically than v3 did.
- Keep `civilization` in as the live control.
- `events` ordering is the secondary probe — same structural shape, +0.17.
- `objective` stays scored (STEP 0, resolved). Carry the v2.1/v3.1 anchor
  forward into v4 rather than re-deriving it, and pre-register the ceiling
  caveat: at 50–69% of scenarios already at ≥4.5, a null on this dimension is
  ceiling-limited and must not be read as a stall.

Write `predictions_v4.md` and commit it **before** running.

### The digest-feedback arm — deprioritized, but not on the stated grounds

Originally iteration 4 — feed the generator the terrain digest of its own first
attempt. It was retired because its premise (that terrain stalls under
instruction) is falsified.

**That reasoning does not survive STEP 2.** The falsification is one episode out
of eight, and every explanation for it collapses onto that episode. At n=8 the
data cannot separate *instruction reaches terrain* from *instruction reached
Hastings*, so the arm's premise is undetermined, not dead.

Composition may still be the better probe on cost and value — that is a
different argument and the one to make. Do not cite the falsification as the
reason.

---

## STEP 4 — Power, before any confirmatory claim

n=8 is exploratory and every result so far carries that caveat. A stagnation
claim is a null result and needs power that positive results do not — at n=8,
"no movement" and "a real 0.3 effect" are indistinguishable. Expand to
**16–24 episodes** before the roadblock claim goes in the paper. This also
supplies the held-out set for the API-facts generalization question (those
facts were derived from these same eight episodes' failures).

STEP 2 raises this from a caveat to a precondition. It is no longer only the
*null* claims that need the corpus: the terrain **positive** is carried entirely
by one episode, and every attempt to explain it returned to that episode. Any
terrain claim in either direction needs a corpus in which a single episode
cannot carry the result.

---

## Where the numbers stand

Judge noise: within-scenario SD of the overall score = 0.07 (v2) / 0.09 (v2.1).
"before" is the frozen v2 rubric `675888722d2d3786`; "after" is v2.1
`c51d48535325f97f`. Both 3× scored. **Do not pool the two columns.**

| cell | MEAN4 before | MEAN4 after | `objective` before → after |
|---|---:|---:|---|
| v2 baseline, all 31 | 2.97 | **2.97** | 4.11 → 4.05 |
| arm: fidelity block only | 3.62 | **3.65** | 4.33 → 4.33 |
| arm: fidelity + API facts | 4.21 | **4.10** | 4.96 → 4.71 |

Broken out by factorial cell: reach_off__templated 2.85→2.76, reach_off__freeform
3.27→3.22, reach_on__templated 2.74→2.80, reach_on__freeform 2.99→3.06.

**The API-facts result survives the rewrite intact.** 8/8 first-attempt builds
(from 0/8), wall clock 12.1 → 6.5 min, both static preconditions 8/8 (from 0/8
and 4/8). The dissociation is the finding: `setting` was 71% API-knowledge,
`combatants` was 83% instruction. The unset-civilization defect that ran through
all 31 baseline scenarios was never a modelling failure — three lines of API
fact fixed it.

v3 arm (generator arm `e3f5afbf797e19a1`), measA → measB:

| rubric | combatants | civilization | terrain | events | objective | MEAN5 |
|---|---|---|---|---|---|---|
| v3 `dcfc95e1f8ba8c98` | 3.46→3.46 | 4.38→4.67 | 2.50→3.25 | 3.71→3.88 | 5.00→4.54 | 3.81→3.96 (+0.15) |
| v3.1 `02346252f802005e` | 3.54→3.50 | 4.50→4.67 | 2.46→3.25 | 3.67→3.88 | **4.75→4.00** | 3.78→3.86 (+0.08) |

### What the objective rewrite actually changed

Pooled means barely moved because most scenarios were already scored on a form
the anchor got right. Every dimension the revision did not touch stayed inside
judge noise (combatants 2.82→2.85, setting 2.43→2.40, events 3.57→3.62), which
is the sanity check that the splice isolated one dimension. Only 5 of 46
scenarios moved ≥1.0, each a parameter defect the old anchor was blind to:

| scenario | victory condition | before → after |
|---|---|---|
| Hastings (measB) | `TIMER on 1s elapsed` | 4.33 → 1.33 |
| Temujin (fidelity arm) | `UNCONDITIONAL` — fires immediately | 2.00 → 1.00 |
| Constantinople (reach_off__freeform) | `TIMER 600s` + destroy **own** monastery | 4.67 → 3.00 |
| Vienna (measB) | unit hunt on a `CAMEL_RIDER` | 3.00 → 2.00 |
| Vienna (reach_off__freeform) | `TIMER 250s` survival | 5.00 → 4.00 |

What changed is the **floor**. The `objective` range opens from 1.7–5.0 to
1.0–5.0 under v2.1, and from 3.0–5.0 to **1.3–5.0** under v3.1, where the
dimension's SD more than doubles (0.51 → 1.10).

### Why `objective` stays in the scored mean

The criterion that excluded `pedagogy` was redundancy — ~79% predicted by the
other four. Run that test on the revised data and `objective` is the *least*
redundant scored dimension, not the most:

| dimension (v2.1) | r with mean of the other scored dims | SD | at ceiling (≥4.5) |
|---|---:|---:|---:|
| combatants | +0.55 | 1.07 | 7% |
| setting | +0.49 | 0.80 | 0% |
| events | +0.55 | 0.70 | 9% |
| **objective** | **+0.34** | 0.93 | 50% |

Under v3.1 it is *anti*-correlated with the rest (−0.44, was −0.19): the
scenarios that get combatants and terrain right are not the ones that get the
goal right. That independence is what a scored dimension is for. Signal/noise is
comfortable — SD 0.93–1.10 against within-scenario judge noise of 0.09.

**The caveat to write down:** it is still the most ceiling-bound scored
dimension (50% of scenarios at ≥4.5 under v2.1, 69% under v3.1), so it has the
least headroom left to register a future improvement. If a later iteration
targets `objective`, expect a ceiling-limited effect and say so **in advance** —
do not read that null as a stall under the roadblock criterion.

### measA's clean sweep: mostly real, and that is the constraint

The 24/24 sweep of 5s breaks, but only barely: **24/24 → 18/24 (5.00 → 4.75)**,
six of eight scenarios still at a clean 5.00. Two dropped to 4.00 — Temujin
(`DESTROY_OBJECT on CAVALIER`) and Vienna (`TIMER on 300s`, a five-minute hold
the judge now reads as thin).

So the thing that looked wrong was only ~8% artifact. The API-facts arm really
does produce specific victory *and* defeat conditions — the near-ceiling score
on a no-v3-instruction arm was earned, not an anchor failure. **This undercuts
the STEP 0 suspicion rather than confirming it**, and it constrains v4:
`objective` was already close to solved by the API facts before v3 said anything
about it.

The sharper finding runs the other way. The measA→measB `objective` drop was
5.00→4.54 under v3 and is now **4.75→4.00**, driven almost entirely by measB's
Hastings 1-second timer. The v3 **generator** instruction arm shipped a
degenerate victory condition that the v3 **judge** anchor could not see. Two
halves of the same rubric disagreeing about the same artifact is worth a line in
the write-up.

Static preconditions with the corrected checker: **35/50** heroes flagged,
matching the figure cited in §5.5.

---

## Open items outside the loop

**Repo**

- `tools/analyze.py` must be updated to emit `tables/audit.tex`. The paper now
  inputs that merged table; `tables/reach.tex` and `tables/modes.tex` are
  orphaned, so regenerating them will not update the paper.
- `tools/test_api.py` fails on a `UnicodeEncodeError` (emoji under cp949).
  Pre-existing, unrelated.
- Self-repair is fidelity-blind: it strips instructions it cannot execute (it
  deleted civilization assignments in 5 of 7 scenarios in the pre-API arm) and
  incidentally fixes map gaps (resource dead ends rose 0/7 → 2/8 once builds
  stopped needing repair). It is an uncontrolled channel in both directions.
  Making it fidelity-aware is the natural next *system* contribution.

**Paper** (`C:\Users\user\Downloads\IJSCAR_Template (1)`)

- Now 10 pages, 7 floats, after cutting the v1 rubric table, folding
  Motivating Example into the intro, dropping `fig:usage` and `fig:sidecar`,
  and merging the reachability tables into `tables/audit.tex`.
  `sections/motivating.tex` still exists on disk but is no longer `\input`.
- `sections/conclusion.tex` is still a placeholder.
- The Evaluation section needs a rewrite, not an edit. The headline is no
  longer "2.8 of 5 is mediocre" but the API-knowledge dissociation. Next page
  of savings is the reachability prose (~800 words), which the rewrite
  replaces anyway.
- Soften the §5.5 claim that the hero failure is "fully determinable
  statically" — the Genghis/Kublai false pass needed a curated title list, and
  the same-culture case stays judge-only.

**The rubric modules** (all now in the repo and tracked)

- `rubric_v2.py` — frozen instrument, hash `675888722d2d3786`; 138 judgements
  hashed against its text. Do not edit. (Its `format_objective_facts` docstring
  was corrected in STEP 0; that is docstring-only and does not move the hash.)
- `rubric_v3.py` — frozen instrument, hash `dcfc95e1f8ba8c98`; 48 judgements.
  Defines its **own** OBJECTIVE anchor — it inherits only the helpers from v2,
  so a fix to one is not a fix to the other. Also carries
  `render_terrain_grid()` and `bridge_score_v2()`.
- `rubric_v2_1.py` — the STEP 0 revision. Splices a new OBJECTIVE section into
  copies of both frozen texts; every other dimension comes through
  byte-identical. Yields v2.1 `c51d48535325f97f` and v3.1 `02346252f802005e`.
- `predictions_v3.md` — the pre-registration that failed. Keep as the record.
