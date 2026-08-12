"""v3 fidelity rubric -- the iteration that goes looking for the ceiling.

DO NOT EDIT rubric_v2.py to produce this. v2 is now a frozen instrument:
the 114 rev2 judgements are hashed against its exact text, and changing it
would orphan them. v3 is a new file with new text and a new hash; the two
series are bridged by bridge_score_v2() below rather than by editing.

WHAT CHANGED, AND WHY

v3 exists to test one hypothesis: that this pipeline can be taught facts
but not perception. Every intervention that has worked so far -- rename
generics, assign civilizations, match victory form to history -- is
knowledge the model applies without seeing anything. The generator writes
code blind, before execution, and the judge reads a digest rather than the
artifact. So anything requiring the produced artifact to be PERCEIVED is
predicted to stall.

The v2 `setting` dimension is therefore split into its two halves:

  civilization -- knowledge-shaped. Solved in v2 once the API fact was
                  supplied (0/31 -> 8/8). Expected near ceiling.
  terrain      -- perception-shaped. Whether the map's geography is the
                  episode's geography. Nothing in the pipeline currently
                  sees space at all. This is the prediction.

`combatants` and `events` are sharpened so they retain headroom, and
`objective` -- saturated at 4.95 under v2, dead as an instrument -- is
re-anchored to require the DEFEAT condition to be episode-specific too.

See predictions_v3.md, which must be committed BEFORE this rubric is run.
"""

import re

from rubric_v2 import (  # helpers are shared; only the rubric text is versioned
    check_combatants_precondition,
    format_objective_facts,
)

DIMENSIONS_V3 = (
    "combatants", "civilization", "terrain", "events", "objective", "pedagogy",
)

# The overall score is the unweighted mean of these five.
SCORED_DIMENSIONS_V3 = (
    "combatants", "civilization", "terrain", "events", "objective",
)

REPORTED_DIMENSIONS_V3 = ("pedagogy",)


# ---------------------------------------------------------------------------
# Generator side.
# ---------------------------------------------------------------------------

GENERATOR_FIDELITY_BLOCK_V3 = """\
HISTORICAL FIDELITY REQUIREMENTS

The scenario you produce will be graded from 1 to 5 on each dimension
below, against the historical brief above. Write it to satisfy them.

COMBATANTS
Place the principal parties the brief names, on the correct sides, and use
the correct named leaders. The engine's hero roster is fixed and you cannot
add to it: where it ships no hero for a historical figure, place a generic
unit and RENAME it to that figure. Where it DOES ship the correct hero, use
it -- do not rename a generic in place of a hero that exists. If you reach
for a substitute hero, closeness counts: same culture and era is a minor
error, an unrelated culture or era is a major one.
Force composition is graded too, not just leadership. The unit types and
their rough proportions should match what the sources describe: if the
brief describes a battle decided by heavy cavalry against massed infantry,
the map should show that, not an even spread of whatever the civilization
can build.

CIVILIZATION
Assign a civilization explicitly to every active player, and pick one apt
for the place and period. Never leave a player set to RANDOM. Architecture
and unit access follow from the civilization, so this choice determines
what the scenario looks like on screen regardless of which building
constants you place.

TERRAIN
Build the map's geography to match the place. Identify the features the
episode actually turned on -- a river or strait to be crossed, high ground
to be held, a wall line, a forest or marsh that channelled movement, a
chokepoint -- and place them in the right relation to each other and to
where each player starts. A map whose terrain could belong to any
engagement of the period is a failure of this dimension even if every unit
on it is correct. You cannot see the map you are producing, so reason
explicitly about the layout before you place anything: state where north
is, what occupies each edge, and where the two sides begin relative to the
feature that mattered.

EVENTS
Reproduce the shape of what happened, including its turning points and its
outcome. The turning points must fire IN ORDER, and each should be gated on
the preceding event actually occurring -- a trigger activated by the event
before it -- rather than on elapsed time. A scripted sequence on timers
will play out identically whatever the player does, which is not the
history. Every dated or attributed claim in your objectives text and
dialogue must be supported by the brief.

OBJECTIVE
Both the victory AND the defeat conditions must encode what the history
posed. Key victory to the particular person, place, or deadline the brief
identifies, and defeat to the loss that side actually faced -- not to a
generic "your units are dead". A scenario whose victory is specific but
whose defeat is a default scores 3.
Match the form to the history:
  - a siege the defenders had only to outlast -> survive a timer
  - an escort -> the escorted unit reaching its destination
  - a battle turning on one leader -> that leader's death
  - a conquest -> holding or razing the specific objective

PEDAGOGY
The objectives, text, and events a playthrough exposes the player to should
give an attentive player an accurate working picture of what happened. Make
the objectives text describe the goal the triggers actually implement.

WHAT IS NOT AN ERROR
The engine's inherent abstraction is not penalized. Representing a Frankish
shield wall with the engine's spearmen, or a Landsknecht with a two-handed
swordsman, is a limitation of the medium and scores as correct. You are
penalized only for avoidable error: the wrong person, the wrong culture,
the wrong ground, the wrong events, the wrong goal.
"""


# ---------------------------------------------------------------------------
# Judge side.
# ---------------------------------------------------------------------------

JUDGE_RUBRIC_V3 = """\
Score each dimension from 1 to 5 against the historical brief. Anchors are
given for 1, 3, and 5; use even scores for artifacts between anchors.

COMBATANTS
The engine's hero roster is fixed, so where it ships no hero for a
historical figure the criterion cannot be met by casting alone. Grade the
substitution, not the absence: a renamed generic unit is correct, a
substitute of the same culture and era is a minor error, and a figure from
an unrelated culture or era is a major one. Renaming a generic where the
correct hero DOES exist in the engine is also an error.
1  Wrong or generic forces; the principal parties are absent or
   interchangeable, or a hero of an unrelated culture or era stands in for
   a historical figure.
3  The principal sides and leaders are present, but force composition is
   generic -- the unit mix would fit any engagement of the period.
5  The right sides, the right named leaders, and a force composition whose
   unit types and rough proportions match what the sources describe.

CIVILIZATION
1  Civilization broadly wrong for the place and period, or left
   unassigned.
3  Assigned and roughly right, but architecture or unit access contradicts
   the setting in visible ways.
5  Every active player is assigned a civilization apt for the place and
   period, and the architecture that follows from it is consistent with
   the brief.

TERRAIN
Score this from the terrain digest supplied below, which is a downsampled
map of what the scenario actually contains. Judge the geography, not the
units standing on it.
1  The map's geography bears no relation to the place: no water where the
   episode turned on a river or strait, flat ground where it turned on
   elevation, open field where it turned on a chokepoint.
3  The gross features exist but are unplaced or mis-scaled -- there is
   water, but not where it mattered; there is high ground, but not where
   the fighting was.
5  The map reproduces the features the episode turned on, in the right
   relation to each other and to where each side begins.

EVENTS
1  A generic engagement: the events described are unrecognizable, or the
   narration invents or misdates them.
3  The turning points are present but arrive out of order, or are gated on
   elapsed time so the sequence plays out identically whatever the player
   does.
5  The turning points appear in order, each gated on the preceding event
   occurring, reproducing the shape of what happened and asserting nothing
   the sources do not.

OBJECTIVE
Score this dimension from the extracted victory and defeat conditions
supplied below, and from nothing else. You are judging whether the goal
those conditions encode is the goal the history posed. You are NOT judging
whether the objectives text agrees with them (that is pedagogy), and you
are NOT judging whether the win is reachable -- that is settled by a static
audit, and the two can legitimately disagree. A victory gated on a timer
alone is flagged by that audit as degenerate but is the CORRECT objective
for a siege the defenders had only to outlast.
1  Neither condition is the historical one: victory or defeat turns on
   something the history did not.
3  One is specific and the other is a default -- typically a victory that
   names the real objective alongside a generic "all your units are dead"
   defeat, or the reverse.
5  Both are the historical ones: victory turns on the particular person,
   place, or deadline the sources identify, and defeat on the loss that
   side actually faced.

PEDAGOGY
Score what the scenario asserts, not the roster it had to assert it with.
The hero substitutions an AoE2 player reads past as a condition of the
medium are scored under combatants; do not penalize them again here.
1  The content a playthrough exposes the player to is untrue or misleading
   about what happened.
3  Play would expose the player to some true content amid noise.
5  The objectives, text, and events of a playthrough would give an
   attentive player an accurate working picture of what happened.

SCORING NOTES
The engine's inherent abstraction is not an error: representing a Frankish
shield wall with the engine's spearmen is a limitation of the medium and
scores as correct. Penalize only avoidable error.
The overall score is the unweighted mean of combatants, civilization,
terrain, events, and objective. Score and report pedagogy, but leave it out
of the mean.
"""


# ---------------------------------------------------------------------------
# Scoring.
# ---------------------------------------------------------------------------

def overall_score_v3(scores):
    """Unweighted mean of the five scored dimensions. Pedagogy excluded."""
    missing = [d for d in SCORED_DIMENSIONS_V3 if d not in scores]
    if missing:
        raise KeyError("missing dimension scores: %s" % ", ".join(missing))
    return sum(scores[d] for d in SCORED_DIMENSIONS_V3) / len(SCORED_DIMENSIONS_V3)


def bridge_score_v2(scores):
    """Recombine v3 scores into the v2 four-dimension mean.

    v3 splits `setting` into `civilization` and `terrain`, so a raw v3 mean
    is not comparable to the v2 series. This averages the two halves back
    into a synthetic `setting` and returns the v2-shaped MEAN4, so the
    longitudinal series survives the rubric revision.

    It is a bridge, not a substitute: report it alongside overall_score_v3,
    never instead of it, and never pool the two.
    """
    setting = (scores["civilization"] + scores["terrain"]) / 2
    parts = (scores["combatants"], setting, scores["events"], scores["objective"])
    return sum(parts) / len(parts)


# ---------------------------------------------------------------------------
# The terrain digest -- the instrument the terrain dimension needs.
# ---------------------------------------------------------------------------

_DEFAULT_LEGEND = {
    "water": "~", "shallow": "-", "grass": ".", "dirt": ",", "sand": ":",
    "forest": "T", "snow": "*", "road": "=", "rock": "#", "unknown": "?",
}


def render_terrain_grid(grid, classify, size=32, elevation=None):
    """Downsample a terrain grid to an ASCII map the judge can actually read.

    Nothing in this pipeline perceives space: the generator writes blind and
    the judge reads a digest that carries no layout. A terrain dimension
    cannot be scored until that is fixed, so this renders the map the
    scenario really contains into text.

    `grid` is a 2D sequence of terrain ids, `classify` maps an id to a
    legend key (see _DEFAULT_LEGEND), and `elevation` is an optional 2D
    sequence of heights rendered as digits in a second panel. Downsampling
    is by majority vote, so a small decisive feature survives only if it is
    large enough to win its cell -- state that limit when reporting.
    """
    if not grid or not grid[0]:
        return "TERRAIN DIGEST: empty map"

    height, width = len(grid), len(grid[0])
    step_y = max(1, height // size)
    step_x = max(1, width // size)

    def majority(block):
        counts = {}
        for value in block:
            counts[value] = counts.get(value, 0) + 1
        return max(counts, key=counts.get)

    rows = []
    for y in range(0, height, step_y):
        row = []
        for x in range(0, width, step_x):
            block = [
                grid[yy][xx]
                for yy in range(y, min(y + step_y, height))
                for xx in range(x, min(x + step_x, width))
            ]
            key = classify(majority(block))
            row.append(_DEFAULT_LEGEND.get(key, _DEFAULT_LEGEND["unknown"]))
        rows.append("".join(row))

    legend = "  ".join("%s=%s" % (v, k) for k, v in _DEFAULT_LEGEND.items()
                       if v in set("".join(rows)))
    out = [
        "TERRAIN DIGEST (%dx%d map downsampled to %dx%d; north is up)"
        % (width, height, len(rows[0]), len(rows)),
        "legend: " + legend,
        "",
    ] + rows

    if elevation:
        out += ["", "ELEVATION (same footprint, 0-9)"]
        for y in range(0, len(elevation), step_y):
            row = []
            for x in range(0, len(elevation[0]), step_x):
                block = [
                    elevation[yy][xx]
                    for yy in range(y, min(y + step_y, len(elevation)))
                    for xx in range(x, min(x + step_x, len(elevation[0])))
                ]
                row.append(str(min(9, int(sum(block) / len(block)))))
            out.append("".join(row))

    return "\n".join(out)


def check_terrain_precondition(terrain_counts, min_classes=3):
    """Cheap static support for `terrain`, needing no model.

    A map that is one terrain type everywhere has no geography to score.
    Returns (passed, distinct_class_count). This is a floor check, not a
    fidelity check -- passing it means only that the dimension is worth
    asking the judge about.
    """
    distinct = sum(1 for _, n in terrain_counts.items() if n > 0)
    return distinct >= min_classes, distinct
