# Pre-registered predictions — v3 rubric

**Commit this file before running anything.** Its value is entirely in being
written down first; a prediction recorded after the result is not a
prediction. Record the commit hash in the run log.

- Rubric: `rubric_v3.py`, hash `<fill in at run time>`
- Comparison cell: the arm+API cell (fidelity block + API facts), 8 episodes
- Judge noise: within-scenario SD of the overall score = 0.081 under v2

## The hypothesis

This pipeline can be taught facts but not perception.

Every intervention that has worked — rename generics, assign civilizations,
match victory form to history — is knowledge the model applies without seeing
anything. The generator writes code blind, before execution. The judge reads a
digest, not the artifact. So a criterion that requires the produced artifact to
be *perceived* should resist instruction in a way knowledge-shaped criteria
have not.

`terrain` is that criterion. `civilization` is its control: the same v2
dimension, split off, already solved by a stated fact.

## Design

Two measurements, no confound between them:

- **A — v3 re-score.** Score the *existing* arm+API artifacts under v3. No
  generation. Establishes where v3's re-anchored dimensions place artifacts
  that were built without v3 instructions.
- **B — v3 arm.** Generate with `GENERATOR_FIDELITY_BLOCK_V3` (API facts
  still attached), then score under v3.

Predictions are about **B − A**.

## Predictions

| dimension | A: v3 re-score | B: after v3 generation | predicted Δ |
|---|---|---|---|
| combatants | ~3.2 (drops from 3.90 — composition now graded) | ~4.0 | **+0.5 to +0.9** |
| civilization | ~4.3 (already solved in v2) | ~4.5 | +0.0 to +0.3 (ceiling) |
| terrain | ~1.8 (never targeted by any arm) | ~2.0 | **+0.0 to +0.2 — STALL** |
| events | ~3.4 (drops from 4.14 — ordering now graded) | ~3.9 | +0.3 to +0.6 |
| objective | ~3.4 (drops from 4.95 — defeat now graded) | ~4.2 | +0.5 to +0.9 |

### The discriminating prediction

**`terrain` moves less than 0.2 while `combatants` and `objective` each move
more than 0.4, in the same run.**

The control clause is the whole point. A dimension that fails to move in a run
where nothing else moves either indicates a weak intervention, not a ceiling.

## What would falsify this

- **`terrain` moves more than 0.5** → hypothesis is wrong; spatial layout is
  teachable by instruction alone, and the blind-generation account of the
  ceiling is incorrect.
- **Nothing moves** → the v3 block is too weak to test anything. Not a
  roadblock. Strengthen the instructions and re-run before concluding.
- **`terrain` re-scores above 3.0 at A** → the existing maps are already
  historically shaped, there is no headroom, and terrain is the wrong probe.
  Pick another perception-dependent criterion.
- **`civilization` falls** → the split introduced a scoring artifact; fix the
  instrument before reading anything else.

## The follow-up this sets up

If `terrain` stalls as predicted, the decisive experiment is iteration 4:
feed the generator the terrain digest **of its own first attempt** and let it
revise. Same knowledge, same instructions, perception added.

- If terrain then moves → the bottleneck is perception, not knowledge, and the
  finding is that this class of failure is unreachable by instruction and
  reachable by feedback. That is the strongest available result and it
  generalizes past AoE2.
- If terrain still does not move → the bottleneck is spatial reasoning itself,
  which is a different and also publishable claim.

Do not run iteration 4 before iteration 3. The value of the pair is the
contrast.

## Statistical note

n=8 is an **exploratory** run: enough to see whether the predicted pattern
appears, not enough to support a null claim about terrain. If the pattern
appears, the confirmatory run needs 16–24 episodes — a stagnation claim is a
null result, and nulls need power that positive results do not. At n=8, "no
movement" and "a real 0.3 effect" are indistinguishable.
