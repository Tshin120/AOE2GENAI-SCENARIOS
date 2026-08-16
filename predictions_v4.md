# Pre-registered predictions — v4

**Commit this file before running anything.** Its value is entirely in being
written down first; a prediction recorded after the result is not a prediction.
Record the commit hash in the run log.

- Base condition: rubric v2.1 (`c51d48535325f97f`) **plus API facts**, freeform
- Corpus: the same 8 episodes. Deliberately not expanded — see "What n=8 can
  and cannot support", which is the governing constraint on every claim below
- Judge noise: within-scenario SD of MEAN4 = 0.116 under v2.1 (n=46)

---

## The hypothesis

**Instruction reaches point facts. It does not reach structural relations.**

Where the ask is *which entity belongs in this slot*, stating the criterion
works. Where the ask is *how the parts relate to each other*, stating the
criterion does close to nothing. This is a claim about the shape of the
demand, not about the difficulty of the history.

The evidence it was derived from (v2.1 arms, paired, 7 episodes):

| dimension | shape of the ask | Δ from instruction |
|---|---|---:|
| combatants | fill a slot with the right name | **+1.00** |
| setting | fill one field with the right enum | +0.62 |
| events | relations across a trigger graph | **+0.10** |
| objective | structure of victory/defeat paths | **+0.10** |

And from v3: told explicitly to match unit types and rough force proportions,
`combatants` moved **+0.00** — the same dimension that moved +1.00 when the ask
was "name the right person."

This run exists to test that split **within a single run**, with both asks
matched for specificity, so the difference between them is shape and nothing
else. The v3 run could not do this: its control clause inverted, so it never
established that the run was capable of moving anything.

---

## What n=8 can and cannot support

Stated first, because it constrains every prediction below.

Per-episode SD of paired deltas, measured from the v2.1 arms:

| dimension | SD of Δ | 95% CI half-width at n=8 |
|---|---:|---:|
| events | 0.25 | ±0.17 |
| setting | 0.71 | ±0.49 |
| combatants | 0.77 | ±0.53 |
| objective | 1.49 | ±1.03 |

**A judge-scored delta of 0.00 on `combatants` is compatible with a true effect
of ±0.53 at this n** — larger than the `setting` effect we call movement
elsewhere. Therefore:

- **No stall claim in this run may rest on a rubric delta**, with the single
  exception of `events`, whose SD of 0.25 makes ±0.2 resolvable at n=8. Note
  that SD is itself estimated from 7 episodes and is the least certain number
  in this document.
- **The primary measure is a deterministic static check.** Pass/fail per
  scenario, no judge, no noise. The precedent is the civilization precondition:
  0/8 → 8/8 settled that question at n=8 and no interval was needed.
- **The roadblock criterion is redefined for this run.** The original form
  ("moves less than 0.2 across two consecutive targeted interventions") is not
  verifiable against judge scores at any corpus size we will reach — it needs
  roughly 57 episodes on `combatants`. For v4 a roadblock means: *the static
  check does not improve, while a matched point-fact intervention in the same
  run does improve its own static check.*

---

## Design

Three arms, same 8 episodes, three judge repeats each.

| arm | added to the generator prompt | role |
|---|---|---|
| **Base** | nothing beyond v2.1 + API facts | reference (already built; re-used) |
| **P** | point-fact ask: where the engine ships no hero for a historical figure, **rename a generic unit** rather than substitute a wrong famous one | positive control — **must move** |
| **R** | structural ask: order events causally through the trigger graph, and match force composition to the sources | the probe — predicted to stall |

Arm P is chosen because the roster limit is the identified cause of
`combatants` topping out at 3.83 in the base condition, the fix is a point fact,
and it has never been run. It is the strongest available positive control.

**Match the two prompt blocks for length, specificity, and concreteness.** If
R is vaguer than P, the run tests prompt quality rather than ask shape and is
void. Record both blocks and their word counts in the log.

### Measurement A costs nothing

Both static checks run on the **existing** base artifacts before any
generation — they are static analyses of already-built scenarios. Measurement A
is therefore free, and B is the only run that costs API calls.

---

## Predictions

### Primary — static checks (deterministic)

| check | A (base, existing artifacts) | predicted B | |
|---|---|---|---|
| hero substitution, arm **P** | measure in Phase 0 | **improves by ≥4 of 8** | control must fire |
| force composition, arm **R** | measure in Phase 0 | **improves by ≤1 of 8** | **STALL** |

### Secondary — rubric deltas, reported with CIs

| dimension | arm | predicted Δ | interpretable at n=8? |
|---|---|---|---|
| combatants | P | **+0.4 to +0.9** | no — corroboration only |
| events | R | **+0.0 to +0.2 — STALL** | **yes**, ±0.17 |
| combatants | R | +0.0 to +0.2 | no — use the static check |
| setting | either | +0.0 to +0.2 (not targeted) | no |
| objective | either | **excluded in advance** | no — see below |

### `objective` is excluded from all stall analysis, decided now

Two independent reasons, both established before this run: it is the most
ceiling-bound scored dimension (50% of scenarios ≥4.5 under v2.1, 69% under
v3.1), and it has the widest delta SD of any dimension at 1.49. A null on
`objective` in this run carries no information and **may not be cited as
evidence of a roadblock**. It is reported, not interpreted.

---

## The discriminating prediction

**Arm P improves its static check by ≥4 of 8 while arm R improves its own by
≤1 of 8, in the same run, with `events` moving less than 0.2 under R.**

---

## Validity gate — read before interpreting anything

**If arm P does not move, this run does not diagnose, and no stall claim may be
read from arm R.** Fix the intervention and re-run.

This is written down in advance because the v3 run failed exactly here: its
control clause inverted, and the temptation afterwards was to read the stalls
anyway. A dimension that fails to move in a run where the control also failed
indicates a weak intervention, not a ceiling.

---

## What would falsify the hypothesis

- **Arm R's composition check improves by ≥4 of 8** → structural relations are
  teachable by instruction, the hypothesis is wrong, and the v3 `combatants`
  stall was a weak intervention rather than a ceiling. Cleanly negative and
  publishable.
- **`events` moves more than 0.4 under R** → same conclusion by the other probe.
- **Both arms stall** → the run is void by the validity gate above. Suspect the
  prompt blocks or the repair loop before concluding anything about the model.
- **Arm P moves but its rubric `combatants` score falls** → the static check and
  the judge disagree about what "right unit" means; fix the instrument before
  reading either.

---

## Known threats to this run, recorded in advance

**Self-repair is fidelity-blind.** It strips instructions it cannot execute —
it deleted civilization assignments in 5 of 7 scenarios in the pre-API arm. If
it strips composition constructs, the stall we measure is repair, not the model.
**Log every instruction-bearing construct repair removes.** This is the single
most likely way for this run to produce a false roadblock.

**Headroom under R.** `events` already sits at 4.04 in the base condition, so
part of any stall could be ceiling rather than resistance. Report the per-episode
distribution, not just the mean, and note how many episodes are at or above 4.5.

**Composition targets are ground truth and must be frozen.** Commit the
per-episode force-composition targets in Phase 0, before generation. Tuning them
after seeing results converts the primary measure into a post-hoc one.

---

## Statistical note

n=8 is unchanged from previous runs and remains **exploratory for anything
judge-scored**. The claim this run can support is not "the true effect is below
0.2" — it is:

> On this corpus, a point-fact intervention moved a deterministic check while a
> matched structural intervention did not.

That is a paired contrast on the same eight episodes, measured without a judge.
It is weaker than a certified null and stronger than anything n=8 rubric deltas
can deliver. State it in that form and do not upgrade it later.
