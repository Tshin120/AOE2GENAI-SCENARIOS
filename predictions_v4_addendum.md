# Addendum to predictions_v4.md — evidence that arrived after commit

**This file does not amend `predictions_v4.md`.** That file is committed and
stays exactly as written. This is a dated record of relevant evidence that
appeared afterwards, so that when v4 is read the reader knows what was and was
not known at pre-registration time.

---

## 2026-08-12 — the held-out run moved `events`

`predictions_v4.md` predicts, for arm R:

> `events` — predicted Δ **+0.0 to +0.2 — STALL**, interpretable at n=8 (±0.17)

The held-out generalization run (commit 7f0790c, `output/fidelity_heldout.jsonl`)
was executed **after** the pre-registration was committed and reports:

| corpus | `events` Δ | 95% CI (t, n=8) |
|---|---:|---|
| original 8 | +0.12 | [−0.32, +0.57] |
| **held-out 8** | **+0.42** | **[+0.09, +0.74]** |

On the held-out corpus `events` moved, and its interval excludes zero. On the
original corpus it did not. The v4 stall prediction was written from the
original corpus alone.

### Why this is not a contradiction, and not a licence to edit the prediction

The interventions are **not the same**. The held-out delta comes from the
**combined** rubric + API-facts block — a large prompt addition whose effect on
`events` is not attributable to any structural instruction in particular. Arm R
in v4 is an **isolated** structural ask (causal event ordering plus force
proportions), matched in length and specificity against a point-fact ask in the
same run. A combined block moving `events` by +0.42 does not predict what an
isolated structural instruction does.

It is, however, genuine prior information, and it cuts against the stall. Two
consequences, both recorded now rather than after the result:

1. **The `events` stall prediction is at higher risk than it looked.** If arm R
   moves `events`, that outcome was foreseeable from this run, and claiming
   afterwards that it was expected would be exactly the reinterpretation this
   discipline exists to prevent.
2. **`events` should no longer be treated as the sole primary probe.** The
   static composition check remains the measurement that carries the claim, for
   the reason given in the pre-registration: it has no judge noise. This
   addendum strengthens that ordering rather than changing it.

### Also worth recording: the ceiling observation

The held-out episodes start lower than the original (baseline MEAN4 3.00 vs
3.22) and finish in the same place (4.18 vs 4.10; `combatants` 3.96 vs 3.95).
Whatever bounds the endpoint is not reached by API facts. That is consistent
with — but not evidence for — the structural/relational limit v4 is designed to
test. It is an observation, not a result, and v4 remains the test.

### What was NOT tested by that run

The rubric-only middle arm could not be rerun (generator 2.4 attaches
`FIDELITY_API_SUPPORT_BLOCK` unconditionally), so the held-out run says nothing
about the executability finding (first-attempt builds 6/8 → 0/8 → 8/8). That
result still rests on the original corpus alone.
