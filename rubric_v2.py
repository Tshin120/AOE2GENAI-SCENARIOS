"""Single source of truth for the v2 fidelity rubric.

Both sides of the pipeline import from here: the generator pastes
GENERATOR_FIDELITY_BLOCK into its system prompt, and the judge pastes
JUDGE_RUBRIC_V2 into its grading prompt. They are two phrasings of the
same anchors -- instruction and criterion -- so keeping them in one file
is what stops them drifting apart.

Keep in sync with tables/rubric_v2.tex in the paper repo.

v2 changes from v1: drops `anachronism`, renames `material` -> `setting`
(unit rosters move to `combatants`), adds `objective`. Scores are NOT
comparable to v1 scores -- see the note in fidelity_judge wiring.
"""

import re

DIMENSIONS_V2 = ("combatants", "setting", "events", "objective", "pedagogy")

# The overall score is the unweighted mean of these four only.
SCORED_DIMENSIONS = ("combatants", "setting", "events", "objective")

# Scored and reported, but excluded from the mean: largely predicted by
# the other four (79% in the v1 data).
REPORTED_DIMENSIONS = ("pedagogy",)


# ---------------------------------------------------------------------------
# Generator side: the anchors phrased as instructions.
# ---------------------------------------------------------------------------

GENERATOR_FIDELITY_BLOCK = """\
HISTORICAL FIDELITY REQUIREMENTS

The scenario you produce will be graded from 1 to 5 on each dimension
below, against the historical brief above. Write it to satisfy them.

COMBATANTS
Place the principal parties the brief names, on the correct sides, with
force composition consistent with it, and use the correct named leaders.
The engine's hero roster is fixed and you cannot add to it, so where it
ships no hero for a historical figure, place a generic unit and RENAME it
to that figure. That is the correct move and scores full marks. If you
reach for a substitute hero instead, closeness is what counts: one of the
same culture and era is a minor error, one from an unrelated culture or
era is a major one, because it asserts something false about who was
there.

SETTING
Assign a civilization explicitly to every active player. Never leave a
player set to RANDOM -- an unassigned civilization means the game picks
the architecture set at load time, so the buildings you place may render
in the material culture of an unrelated part of the world regardless of
which building constants you chose. Architecture, terrain, and
civilization must all be plausible for the place and period in the brief.

EVENTS
Reproduce the shape of what happened, including its turning points and
its outcome. Every dated or attributed claim in your objectives text and
dialogue must be supported by the brief. Do not invent, reorder, or
misdate events, and assert nothing the brief does not.

OBJECTIVE
The victory and defeat conditions must encode the goal the history
actually posed. Key victory to the particular person, place, or deadline
the brief identifies, and defeat to the loss that side actually faced.
Do not fall back on a default goal -- usually eliminating the opposing
force -- where the brief describes something more specific: a default
that would fit any engagement of the period scores a 3 at best.
Match the form to the history:
  - a siege the defenders had only to outlast -> survive a timer
  - an escort -> the escorted unit reaching its destination
  - a battle turning on one leader -> that leader's death
  - a conquest -> holding or razing the specific objective
A player playing to win should be attempting what the historical actors
attempted.

PEDAGOGY
The objectives, text, and events a playthrough exposes the player to
should give an attentive player an accurate working picture of what
happened. Make the objectives text describe the goal the triggers
actually implement -- a briefing that promises one goal while the
triggers implement another misleads the player.

WHAT IS NOT AN ERROR
The engine's inherent abstraction is not penalized. Representing a
Frankish shield wall with the engine's spearmen, or a Landsknecht with a
two-handed swordsman, is a limitation of the medium and scores as
correct. You are penalized only for avoidable error: the wrong person,
the wrong culture, the wrong events, the wrong goal.
"""


# Append this ONLY when the reachability block is also active, to resolve
# the one place the two blocks give contradictory guidance.
REACHABILITY_RECONCILIATION = """\
NOTE ON TIMER VICTORIES
The reachability guidance above tells you to avoid a victory gated on a
timer alone, because a player wins it by waiting. That rule is about
playability, not history, and history wins where they conflict: if the
brief describes a situation whose whole problem was to still be there at
the end, a survival victory is the historically correct objective and you
should use it. When you do, give the scenario a real defeat condition
that can fire before the timer -- the death of the commander, the loss of
the position -- so that waiting is not a guaranteed win.
"""


# ---------------------------------------------------------------------------
# Judge side: the anchors phrased as grading criteria.
# ---------------------------------------------------------------------------

JUDGE_RUBRIC_V2 = """\
Score each dimension from 1 to 5 against the historical brief. Anchors
are given for 1, 3, and 5; use even scores for artifacts between anchors.

COMBATANTS
The engine's hero roster is fixed, so where it ships no hero for a
historical figure the criterion cannot be met by casting alone. Grade the
substitution, not the absence: a renamed generic unit is correct, a
substitute of the same culture and era is a minor error, and a figure
from an unrelated culture or era is a major one.
1  Wrong or generic forces; the principal parties are absent or
   interchangeable, or a hero of an unrelated culture or era stands in
   for a historical figure.
3  The principal sides are present, but leaders are missing or generic,
   force composition is substantially off, or a substituted hero is of
   the right culture and era but the wrong person.
5  The right sides, the right named leaders, and force composition
   consistent with the sources. Where the engine ships no hero for a
   figure, a renamed generic unit stands in.

SETTING
1  Architecture, terrain, and civilization broadly wrong for the place
   and period, or left unassigned.
3  Mostly plausible, with notable exceptions.
5  Civilization, architecture, and terrain are explicitly assigned and
   consistently plausible for the place and period.

EVENTS
1  A generic engagement: the events described are unrecognizable, or the
   narration invents or misdates them.
3  The broad shape of what happened is present, but key events are
   missing, reordered, or invented.
5  The scenario reproduces the shape of what happened, including its
   turning points and outcome, and asserts nothing the sources do not.

OBJECTIVE
Score this dimension from the extracted victory and defeat conditions
supplied below, and from nothing else. You are judging whether the goal
those conditions encode is the goal the history posed. You are NOT
judging whether the objectives text agrees with them (that is pedagogy),
and you are NOT judging whether the win is reachable or well-formed --
that is settled separately by a static audit, and the two can legitimately
disagree. In particular, a victory gated on a timer alone is flagged by
that audit as degenerate, but it is the CORRECT objective for a siege the
defenders had only to outlast; score it a 5 in that case.
1  The encoded goal is not the historical one: victory or defeat turns on
   something the history did not, as when a siege the defenders had only
   to outlast is won by hunting down the besiegers.
3  The encoded goal is of the right kind but generic: the specific goal
   gives way to a default -- usually eliminating the opposing force --
   that would fit any engagement of the period.
5  The encoded goal is the historical one: victory turns on the
   particular person, place, or deadline the sources identify, and defeat
   on the loss that side actually faced, so playing to win means
   attempting what the historical actors did.

PEDAGOGY
Score what the scenario asserts, not the roster it had to assert it with.
The hero substitutions an AoE2 player reads past as a condition of the
medium are scored under combatants; do not penalize them again here.
1  The content a playthrough exposes the player to is untrue or
   misleading about what happened.
3  Play would expose the player to some true content amid noise.
5  The objectives, text, and events of a playthrough would give an
   attentive player an accurate working picture of what happened.

SCORING NOTES
The engine's inherent abstraction is not an error: representing a
Frankish shield wall with the engine's spearmen is a limitation of the
medium and scores as correct. Penalize only avoidable error.
The overall score is the unweighted mean of combatants, setting, events,
and objective. Score and report pedagogy, but leave it out of the mean.
"""


# ---------------------------------------------------------------------------
# Static support, computed before the judge is invoked.
# ---------------------------------------------------------------------------

def overall_score(scores):
    """Unweighted mean of the four scored dimensions. Pedagogy excluded."""
    missing = [d for d in SCORED_DIMENSIONS if d not in scores]
    if missing:
        raise KeyError("missing dimension scores: %s" % ", ".join(missing))
    return sum(scores[d] for d in SCORED_DIMENSIONS) / len(SCORED_DIMENSIONS)


# Particles and TITLES. Titles have to be stripped for the same reason
# particles do: they are shared across people, so matching on one is not
# evidence the right person is present. GENGHIS_KHAN against a brief
# naming Kublai Khan matched on "khan" and read as supported until "khan"
# was listed here. Extend this as the hero roster grows -- it is a
# curated list, not a rule, and it is the reason this check needs a
# manual pass when new episodes are added.
_NAME_STOPWORDS = frozenset((
    "the", "of", "de", "di", "da", "von", "van",
    "khan", "hun",
))


def _mentions(haystack, needle):
    """Whole-word containment. Substring matching is not safe here: the
    short tokens real hero names reduce to ("cid") occur inside ordinary
    words ("decided"), which would silently pass every brief."""
    return re.search(r"\b%s\b" % re.escape(needle), haystack) is not None


def check_combatants_precondition(placed_hero_names, brief_text):
    """Pass/fail precondition for `combatants`, needing no model.

    Every named hero placed in the scenario must appear in the brief.
    Returns (passed, unsupported_heroes).

    Matching is whole-word, full name first, then the distinctive tokens.

    Know what this does and does not decide. It checks whether a name is
    PRESENT in the brief, which is not the same as whether the right
    person was cast. It catches the common failure -- a famous hero with
    no connection to the episode -- and it is blind by construction to
    the harder one, where the substitute shares tokens with the correct
    figure (Genghis for Kublai). _NAME_STOPWORDS narrows that gap for
    known titles but does not close it, which is why the same-culture
    middle tier of the combatants anchors is judged rather than checked.

    The converse case, a hero the brief names only by an alias (Temujin
    for GENGHIS_KHAN), would read as unsupported; no such case occurs in
    the current corpus, where that brief uses both names.
    """
    haystack = brief_text.casefold()
    unsupported = []
    for name in placed_hero_names:
        phrase = name.replace("_", " ").casefold().strip()
        if phrase and _mentions(haystack, phrase):
            continue
        tokens = [t for t in phrase.split() if t not in _NAME_STOPWORDS]
        # Prefer long tokens, but never end up with an empty candidate
        # list -- a name like EL_CID has none, and an empty any() is
        # False, which would flag it unsupported against every brief.
        distinctive = [t for t in tokens if len(t) > 3] or tokens
        if not any(_mentions(haystack, t) for t in distinctive):
            unsupported.append(name)
    return (not unsupported), unsupported


def check_setting_precondition(player_civilizations):
    """Pass/fail precondition for `setting`.

    Every active player must have a civilization assigned. Pass a mapping
    of player id -> civilization for ACTIVE players only. All 31 built
    scenarios in the v1 study failed this check.
    """
    unassigned = [
        pid for pid, civ in player_civilizations.items()
        if civ is None or str(civ).upper() in ("RANDOM", "NONE", "")
    ]
    return (not unassigned), unassigned


def format_objective_facts(victory_conditions, defeat_conditions):
    """Render the extracted trigger facts handed to the judge for `objective`.

    Each condition is a dict with at least {"form": ..., "target": ...},
    e.g. {"form": "DESTROY_OBJECT", "target": "GENGHIS_KHAN (P2)"} or
    {"form": "TIMER", "target": "1800s"}. The reachability audit already
    classifies victory-condition shape, so build these from its output
    rather than re-parsing the trigger graph.

    The judge sees this block ALONGSIDE the objectives text, not instead
    of it: the digest still carries IN-GAME TEXT, and it has to, because
    `pedagogy` is defined over what the narration tells the player and
    `events` over the dated and attributed claims it makes. Removing the
    narration to insulate `objective` would break both of those to fix
    one. What keeps `objective` from turning into a second narration
    score is the anchor's instruction to score it from these extracted
    facts "and from nothing else" -- an instruction to the judge, not a
    property of the prompt. Treat it as the softer guarantee it is.
    """
    def render(label, conditions):
        if not conditions:
            return "%s: none found" % label
        lines = ["%s:" % label]
        for c in conditions:
            target = c.get("target") or "unspecified"
            lines.append("  - %s on %s" % (c.get("form", "UNKNOWN"), target))
        return "\n".join(lines)

    return (
        "EXTRACTED VICTORY AND DEFEAT CONDITIONS\n"
        "(taken directly from the trigger graph; score `objective` from\n"
        "these, not from the objectives text)\n\n"
        + render("Victory", victory_conditions)
        + "\n"
        + render("Defeat", defeat_conditions)
    )
