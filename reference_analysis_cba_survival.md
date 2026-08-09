# Reference-repo analysis: `razakadam74/aoe2-cba-survival`

**Status: report + proposals only. No changes were made to `BASE_SYSTEM_PROMPT`, the
reachability block, or any validation/generation code.** Everything below is for your review
before any prompt changes land.

## Scope & provenance

- **Source:** `https://github.com/razakadam74/aoe2-cba-survival`, cloned as read-only reference
  material into a scratch dir (not into this repo). **License: MIT** — we may read and borrow
  *idioms* with attribution; we must not vendor its files wholesale.
- **What it is:** a code-generated, config-driven **PvE survival** mod (hold 4 Castles vs endless
  escalating waves, then raze the enemy fortress). Its README status is *"Milestones 1–2 code
  complete … Pending in-game playtest + balance pass"* → treat it as **probably-correct, not
  verified-correct**.
- **Parser version skew:** it pins `AoE2ScenarioParser==0.8.3`; we pin `>=0.6.0`. Every concrete
  method/kwarg proposed below **must be verified against our installed parser version** before it
  goes into the prompt (signatures like `own_fewer_objects`, `attack_move`, `add_train_location`
  can differ across versions).
- **Compliance note:** `AoE2TriggerCraft2` (GPL-3.0) was **not** cloned, referenced, or copied.

The comparison is against what our `generator.py` system prompt currently teaches
(`BASE_SYSTEM_PROMPT` body at `generator.py:~410–551` + `REACHABILITY_ANALYSIS_BLOCK` at
`generator.py:42–127`).

---

## 1. Where its idioms are more correct / more robust than our prompt

### 1a. Victory conditions — teach `own_fewer_objects` over a unit **type** (not only `destroy_object` on one reference)

**Reference:** `src/cba_survival/triggers.py:260–291`
```python
win.new_condition.own_fewer_objects(quantity=1, object_list=CASTLE_ID, source_player=enemy_id)
win.new_effect.declare_victory(source_player=pid, enabled=1)
# defeat: one own_fewer_objects condition per defender, ANDed, then enemy declared victor
```

**Our prompt today:** the reachability block (`generator.py:83–103`) correctly says *prefer
`destroy_object` on a stored reference over `objects_in_area(quantity=0)`*. But `destroy_object`
targets exactly **one** object. For "raze **all** enemy castles" / "kill **all** enemies," the model
must then store and AND-together every reference — brittle and often skipped.

**Why the reference is more robust:** `own_fewer_objects(quantity=1, object_list=<TYPE>.ID,
source_player=X)` counts how many of a type player X owns **across the whole map**. It is immune to
the `objects_in_area` fragility (garrison/convert/flee/out-of-area) *and* scales to any count without
enumerating references.

**Proposed amendment** (extend the win/lose guidance, don't replace it):
> For a **single named target** (enemy hero/leader, one key castle), use `destroy_object` on a stored
> `reference_id`. For **"eliminate all of type X"** (raze every enemy Castle, wipe an army), prefer
> `own_fewer_objects(quantity=1, object_list=<UNIT/BUILDING>.ID, source_player=<enemy>)` — it counts
> owned objects globally and cannot be stranded the way `objects_in_area(quantity=0)` can. Reserve
> `objects_in_area(quantity=0)` for non-terminal zone detection only. (Add `own_fewer_objects` /
> `own_objects` to the whitelisted condition list.)

### 1b. Player setup — the biggest gap: our prompt teaches **none** of it

**Reference:** `src/cba_survival/players.py:21–58`
```python
manager = scenario.player_manager
manager.active_players = enemy_id                 # contiguous from Player 1
player = manager.players[pid]
player.human = True                               # or False for AI
player.starting_age = age                         # StartingAge enum
player.food/.wood/.gold/.stone = stipend[...]     # starting resource stockpile
player.population_cap = balance.population_cap
player.allied_victory = True
```

**Our prompt today:** assigns `PlayerId` to units, but says nothing about `player_manager`,
starting resources, starting age, population cap, human/AI seats, or `active_players`.

**Why this matters for reachability (our paper's core lever):** the `RESOURCE DEAD END` failure mode
(`generator.py:57–61`) is currently only mitigated via GAIA piles. A **starting stipend** on
`player_manager` is the direct, reliable fix and the reference shows exactly how. `active_players`
must be **contiguous from Player 1** (engine constraint) — worth stating so multi-faction scenarios
don't silently drop players.

**Proposed amendment** (new "PLAYER SETUP" section):
> After placing units, configure `scenario.player_manager`: set `active_players` to the number of
> players (contiguous from Player 1); for each human player set `.human=True`, a `.starting_age`
> (`StartingAge.*`), a starting stipend (`.food/.wood/.gold/.stone`) large enough to reach the victory
> condition, and `.population_cap`; set enemy seats `.human=False`. Giving a starting stipend is the
> primary defense against the RESOURCE DEAD END failure mode.

### 1c. Diplomacy — without it, "defeat is possible" can silently fail

**Reference:** `src/cba_survival/players.py:50–58`
```python
manager.set_diplomacy_teams(defender_ids, diplomacy=DiplomacyState.ALLY)   # pass the list, don't unpack
manager.players[pid].set_player_diplomacy(enemy_id, DiplomacyState.ENEMY)   # both directions
manager.players[enemy_id].set_player_diplomacy(defender_ids, DiplomacyState.ENEMY)
```

**Our prompt today:** nothing on diplomacy. If the enemy isn't explicitly hostile, an AI enemy may
never attack → **no defeat path** → a reachability failure our prompt claims to guard against but
can't detect.

**Proposed amendment:**
> Set diplomacy explicitly: ally co-op players via `player_manager.set_diplomacy_teams([...],
> diplomacy=DiplomacyState.ALLY)` (pass the team **list**, not unpacked args), and set the enemy at
> war **both directions** with `set_player_diplomacy(other, DiplomacyState.ENEMY)`. An enemy that is
> not explicitly hostile may never engage, leaving no defeat path.

### 1d. Global victory condition = **Custom** so triggers are authoritative

**Reference:** `src/cba_survival/builder.py:23` + `datasets.py:34`
```python
scenario.option_manager.victory_condition = VictoryCondition.CUSTOM
```

**Our prompt today:** never touches `option_manager`. With standard/conquest/wonder victory left
enabled, the engine can decide the game before/around the designed triggers — undermining the exact
win/lose reachability the treatment prompt is trying to guarantee.

**Proposed amendment:**
> Set `scenario.option_manager.victory_condition = VictoryCondition.CUSTOM` so that **only your
> triggers** decide victory/defeat; otherwise the engine's standard/conquest routes can win or lose
> the game independently of your designed conditions.

### 1e. Unit placement — tile-center offsets, a safety margin, and a collision-free grid

**Reference:** `placement.py:48,67` (units at `x+0.5, y+0.5`; buildings at integer tiles),
`layout.py:15–21,144–166` (per-type spacing + `_clamp` = `max(2, min(size-3, value))` +
`_centered_grid` via `divmod`).

**Our prompt today** (`generator.py:436–449`): "all coordinates must be integers," valid range
"0 to map_size-1," and ad-hoc per-unit offsets.

Three refinements the reference demonstrates:
- **Center mobile units** on tiles (`x+0.5, y+0.5`); keep **buildings/GAIA on integer tiles**. Blanket
  "integers only" is right for trigger **area** coords and building footprints, but corner-placing
  mobile units invites overlap/pathing quirks. *(Verify our executor/validator accepts float unit
  coords on our parser version before adopting.)*
- **Safety margin:** clamp placements to roughly `[2, map_size-3]` rather than the full
  `0..map_size-1`; edge tiles are error-prone and buildings need room.
- **Collision-free grid:** lay out N units with `divmod(i, cols)` + a per-type step (castle≈8,
  production≈6, house≈3, unit≈2) so overlaps are impossible by construction — sturdier than
  "offset each one" prose.

**Proposed amendment:** add the tile-center rule for mobile units, the `[2, map_size-3]` margin, and a
one-line `divmod` grid pattern with footprint-scaled spacing.

### 1f. Trigger construction — a state machine (`enabled` / `execute_on_load` / `looping` / `activate_trigger`)

**Reference:** `triggers.py:75–131` (Setup uses `execute_on_load=True`; waves start
`enabled=False` and are woken by `activate_trigger(trigger_id=...)`; the Peak wave is
`looping=True`).

**Our prompt today** (`generator.py:499–524`): good "timers vs area triggers" guidance and min-count
rules, but nothing on the trigger **state machine**. Chaining via `activate_trigger` is the robust way
to sequence events **without** timers — directly reinforcing our "avoid timers for main objectives"
rule with a concrete alternative.

**Proposed amendment** (new "TRIGGER STATE MACHINE" note):
> Sequence events with trigger state, not timers: start follow-on triggers `enabled=False` and wake
> them with `new_effect.activate_trigger(trigger_id=other.trigger_id)`; use `execute_on_load=True` for
> a one-shot Setup/intro trigger; use `looping=True` for periodic effects (income, waves). A
> Setup→step1→…→loop chain gives deterministic, player-paced progression.

Also worth borrowing: the fuller `display_instructions(source_player=…, message=…, display_time=…,
instruction_panel_position=PanelLocation.MIDDLE.value, string_id=-1, play_sound=0)` form
(`triggers.py:97–104`) vs our minimal two-kwarg example.

### 1g. Resource handling — grant economy via triggers, not only GAIA piles

**Reference:** `triggers.py:175–228` (`modify_resource(quantity=…, tribute_list=RESOURCE_IDS["gold"],
source_player=pid, operation=Operation.ADD.value)` for periodic income; `change_object_cost` for
cost tuning; `Attribute.*_STORAGE.value` resource ids from `datasets.py:37–42`).

**Our prompt today:** mentions "alternative income sources (market, trade route, relics)" in the
RESOURCE DEAD END text but never shows how to grant resources programmatically.

**Proposed amendment:**
> To guarantee resource sufficiency you can grant income directly: a `looping` timer trigger with
> `modify_resource(quantity=N, tribute_list=Attribute.GOLD_STORAGE.value, source_player=P,
> operation=Operation.ADD.value)`. Prefer this (or a market/trade route) over piling ever-more GAIA
> mines when the victory condition needs sustained economy.

### 1h. (Minor) ASCII-only display text

The reference enforces "no em/en-dash/Unicode-minus anywhere" (`tests/test_no_fancy_dashes.py`) to
dodge a Windows encoding crash inside the parser. We already wrap subprocess stdout in UTF-8; a small
prompt line — *"keep all in-game message text ASCII; no em/en dashes, Unicode minus, or emoji"* —
would remove a class of encoding failures at the source.

---

## 2. Would a snippet work as a few-shot exemplar?

**Yes — for idioms, in small generic pieces, not as a whole scenario.** Guidance:

- **Borrow idioms, not structure.** It's a PvE **survival** mod (endless waves, 4 castles,
  raze-to-win). Pasting a large block risks the model over-fitting every request toward
  survival/wave scenarios. Extract **tight 5–12 line snippets**, relabel generically, and strip
  survival-specific constants.
- **Best exemplar candidates** (each teaches one gap above):
  - *Win/lose pair* (`triggers.py:260–291`) → `own_fewer_objects` + `declare_victory`-per-player.
  - *Player setup* (`players.py:31–58`) → stipend + age + `active_players` + diplomacy.
  - *Placement* (`placement.py:41–48`) → buildings on integer tiles, units at `+0.5`.
  - *Trigger chain* (`triggers.py:75–131`) → `execute_on_load` + `activate_trigger` + `looping`.
- **Mark it "probably-correct."** The README says *pending in-game playtest*. Use snippets to teach
  **API usage** (which method, which kwargs), **not** as a guarantee of playability or balance. Don't
  present it to the model as a "known-good scenario."
- **Version-gate before embedding.** Confirm each snippet's signatures against our installed parser
  version, since literal kwargs are what the model will copy.

Recommendation: add **3–5 short, generic idiom snippets** (with one-line "why" comments) rather than
one large survival exemplar — lower risk of structural over-fit, and each maps cleanly to an
amendment in §1.

---

## 3. Testing approach → a post-build verification step for our pipeline

The reference `tests/` go **well beyond our AST-level checks**. Two patterns are directly adoptable.

### What they do that we don't
- **Round-trip re-open** (`tests/test_roundtrip.py:10–29`): build → `write_to_file` →
  **`AoE2DEScenario.from_file(path)`** → assert on the *reloaded* object: expected trigger **names**
  present, and castle **counts** via `get_player_units(pid)` filtered by `unit_const`. This proves the
  written file is not just present but **parseable and structurally intact**.
- **Structural shape assertions** (`tests/test_generator.py`, `test_triggers_economy.py`): assert
  `trigger.looping`, `execute_on_load`, `len(conditions)`, `len(effects)`,
  `effect.effect_type == EffectId.CREATE_OBJECT`, condition `object_list`/`source_player`, and a
  **trigger-graph traversal** (`test_generator.py:93–127`) that walks `ACTIVATE_TRIGGER` edges to
  prove the Setup→waves→looping-Peak chain is actually wired and terminates — a structural
  *reachability* check on the trigger graph itself.
- **Determinism** (`test_roundtrip.py:32–43`): build twice, compare `(names, sorted units)`. Less
  applicable to our stochastic LLM outputs, but a useful idea for pinned-temperature regression.
- **Env hardening** (`tests/conftest.py:14–16`): `AoE2ScenarioParser settings.PRINT_STATUS_UPDATES =
  False` to avoid the Windows emoji crash — a cleaner belt-and-suspenders than our stdout wrapper.

### Our pipeline today
`validate_scenario_code_detailed()` (AST: syntax, imports, `write_to_file`, ≥1 trigger, textual
`declare_victory`) → `build_scenario()` subprocess (checks **return code** only). We **never re-open
the produced `.aoe2scenario`** to confirm it parses or contains what we asked for. An exit-code-0 run
that wrote a truncated/half-populated file would currently be recorded as `success`.

### Proposed: a `verify_built_scenario(output_path)` post-build stage
Add a stage **after** `build_scenario()` returns ok and **before** marking `success`:
1. **Re-open**: `AoE2DEScenario.from_file(output_path)` (catches corrupt/truncated writes exit code
   0 misses).
2. **Units**: `get_all_units()` non-empty; every unit's `x,y` within `[0, map_size)`.
3. **Triggers**: count ≥ our `min_triggers`; every trigger has ≥1 effect; ≥1 trigger enabled.
4. **Victory (stronger than our text check)**: assert ≥1 `EffectId.DECLARE_VICTORY` effect exists on
   an **enabled** trigger — inspecting the serialized effect, not a substring of the source.
5. **(Optional, reachability-aligned)**: traverse `ACTIVATE_TRIGGER` edges to flag orphaned triggers
   and confirm a victory-bearing trigger is reachable from an `execute_on_load`/enabled trigger.

**Integration:** make its failure feed the **existing self-repair loop** — either a new terminal
outcome (e.g. `postbuild_failure`) or folded into `execution_error` — so the reload error text is sent
back to the model for a retry, and `results.jsonl` distinguishes "ran but produced a bad file" from
"crashed." This upgrades our validation from *"the code looks right and didn't crash"* to *"the
artifact on disk actually contains a winnable, in-bounds, correctly-wired scenario"* — squarely on the
playability-precondition goal, still short of (and complementary to) human historical-fidelity review.

---

## Summary of proposed prompt amendments (for your review — not yet applied)

| # | Area | Amendment | Priority |
|---|------|-----------|----------|
| 1a | Victory conditions | Add `own_fewer_objects(type)` for "eliminate all of X"; keep `destroy_object` for single targets | High |
| 1b | Player setup | New section: `active_players`, human/AI, `starting_age`, **starting stipend**, `population_cap` | High |
| 1c | Diplomacy | Ally teams + enemy-at-war both directions → guarantees a defeat path | High |
| 1d | Victory condition | `option_manager.victory_condition = VictoryCondition.CUSTOM` | High |
| 1e | Unit placement | Tile-center `+0.5` for mobile units; `[2, map_size-3]` margin; `divmod` grid | Medium |
| 1f | Trigger construction | State machine: `enabled`/`execute_on_load`/`looping`/`activate_trigger` chaining | Medium |
| 1g | Resource handling | `modify_resource` periodic income as a RESOURCE-DEAD-END fix | Medium |
| 1h | Message text | ASCII-only in-game text | Low |
| 3  | Verification | Post-build `from_file` re-open + structural/victory/graph asserts, wired into self-repair | High |

**Every concrete signature above is version-sensitive (reference = 0.8.3, us = ≥0.6.0) and must be
verified against our installed parser before landing. No prompt or validation code was changed in this
report.**
