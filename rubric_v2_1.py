"""Point revision of the OBJECTIVE anchor, for both the v2 and v3 instruments.

WHY THIS FILE EXISTS AND WHY IT IS NOT AN EDIT TO rubric_v2.py

`rubric_v2.py` and `rubric_v3.py` are frozen instruments: 138 v2 judgements are
hashed against `JUDGE_RUBRIC_V2` and 48 v3 judgements against `JUDGE_RUBRIC_V3`.
Editing either text in place would leave those rows claiming a text that no
longer exists. So the revision lives here, splices itself into a copy of the
frozen text, and gets a fresh `rubric_hash` -- exactly the mechanism the hash
was added for.

WHAT IS WRONG WITH THE v2/v3 OBJECTIVE ANCHOR

Both tell the judge it is "NOT judging whether the win is reachable or
well-formed -- that is settled separately by a static audit", and then say a
timer-alone victory is the correct objective for a siege. Neither says anything
about the timer's MAGNITUDE. A one-second victory timer and a thirty-minute
siege hold are therefore indistinguishable to the judge, and the disclaimer
actively instructs it not to look. The observed consequence: a Hastings
scenario whose entire victory condition was `TIMER on 1s elapsed` -- an instant
win before a single arrow is loosed -- scored 4, 4, 5 on `objective`.

The missed distinction is between a condition's FORM and its PARAMETERS. Form
is the kind of goal (outlast / escort / kill the commander / take the place);
parameters are the magnitude and the target that say WHICH goal of that kind.
Form alone was being scored. Parameters are not polish -- a survival timer's
duration IS the claim about how long the defenders had to hold -- so they
belong to this dimension, not to the audit.

WHAT IS DELIBERATELY UNCHANGED

Only the OBJECTIVE section is replaced. Every other dimension's text is spliced
through byte-identical from the frozen source, so a v2 -> v2.1 comparison is a
single-factor change. The dimension sets, the means, and the two static
preconditions are all reused unchanged from their original modules.

The narration is also still in the digest, on purpose. See the note on
`rubric_v2.format_objective_facts`: `pedagogy` and `events` both read the
objectives text by definition, so removing it to insulate `objective` would
break two dimensions to fix one. The separation is enforced by the anchor's
"from nothing else", not by omission from the prompt.
"""

import re

import rubric_v2
import rubric_v3

# Dimension sets and means are NOT revised -- only the objective anchor is.
DIMENSIONS_V2_1 = rubric_v2.DIMENSIONS_V2
SCORED_DIMENSIONS_V2_1 = rubric_v2.SCORED_DIMENSIONS
DIMENSIONS_V3_1 = rubric_v3.DIMENSIONS_V3
SCORED_DIMENSIONS_V3_1 = rubric_v3.SCORED_DIMENSIONS_V3


# ---------------------------------------------------------------------------
# The revised anchor.
#
# The preamble is shared by both instruments; only the numbered 1/3/5 anchors
# differ, because v3 additionally requires the DEFEAT condition to be
# episode-specific and v2 does not.
# ---------------------------------------------------------------------------

_OBJECTIVE_PREAMBLE = """\
OBJECTIVE
Score this dimension from the extracted victory and defeat conditions
supplied below, and from nothing else. You are judging whether the goal
those conditions encode is the goal the history posed. You are NOT
judging whether the objectives text agrees with them (that is pedagogy).

Reachability and well-formedness are settled separately by a static
audit and you should not re-derive that audit here -- with one
exception. A condition's PARAMETERS are part of the goal it encodes, not
a separate question of polish. A survival timer states how long the
defenders had to hold; a target states who or what the fight was over.
Therefore:

  - A victory timer short enough that the player wins before the
    historical situation can play out encodes no goal at all. Treat any
    victory timer under 60 seconds as encoding nothing, whatever its
    trigger is named, and score 1.
  - A victory keyed to a target the history does not single out -- an
    ordinary unit of the line, an arbitrary building -- encodes a unit
    hunt rather than the historical goal. Score at most 2, even when the
    side that must be beaten is the right one.

Read the target carefully before applying that second rule. Each
extracted condition names the ENGINE'S UNIT TYPE, not the unit's in-game
name, so a generic unit renamed to a historical figure appears here as
an ordinary unit. The trigger path name quoted with each condition is
the evidence that separates the two cases: a victory on a common unit
type whose path names the commander that unit stands for is keyed to
that commander and is not a unit hunt, while a victory on the same unit
type under a path naming no person or place is one.

A victory gated on a timer alone remains the CORRECT form for a siege
the defenders had only to outlast, and still scores 5 when its duration
is long enough to be a real hold AND some defeat condition can fire
before it expires.
"""

_OBJECTIVE_ANCHORS_V2_1 = """\
1  The encoded goal is not the historical one, or is no goal at all:
   victory or defeat turns on something the history did not, as when a
   siege the defenders had only to outlast is won by hunting down the
   besiegers, or victory fires on a parameter that ends the scenario
   before the history it depicts can happen.
3  The encoded goal is of the right kind but generic: the specific goal
   gives way to a default -- usually eliminating the opposing force --
   that would fit any engagement of the period.
5  The encoded goal is the historical one: victory turns on the
   particular person, place, or deadline the sources identify, with
   parameters that match what the history required, and defeat on the
   loss that side actually faced, so playing to win means attempting
   what the historical actors did.
"""

# v3 raised the bar: BOTH conditions must be episode-specific, and a specific
# victory alongside a default defeat caps at 3. That change is kept; only the
# parameters clause is added on top of it.
_OBJECTIVE_ANCHORS_V3_1 = """\
1  Neither condition is the historical one, or victory encodes no goal
   at all: it turns on something the history did not, or fires on a
   parameter that ends the scenario before the history it depicts can
   happen.
3  One is specific and the other is a default -- typically a victory
   that names the real objective alongside a generic "all your units are
   dead" defeat, or the reverse.
5  Both are the historical ones, with parameters that match what the
   history required: victory turns on the particular person, place, or
   deadline the sources identify, and defeat on the loss that side
   actually faced.
"""

OBJECTIVE_SECTION_V2_1 = _OBJECTIVE_PREAMBLE + _OBJECTIVE_ANCHORS_V2_1
OBJECTIVE_SECTION_V3_1 = _OBJECTIVE_PREAMBLE + _OBJECTIVE_ANCHORS_V3_1


# ---------------------------------------------------------------------------
# Splicing.
#
# The revised text is built from the frozen text rather than pasted as a new
# copy. A pasted copy silently drifts the moment anyone touches either file;
# splicing makes "everything except OBJECTIVE is byte-identical to the frozen
# instrument" a property the code enforces rather than a claim in a comment.
# ---------------------------------------------------------------------------

# Section headers in these rubrics are a bare ALL-CAPS line: COMBATANTS,
# SETTING, TERRAIN, ..., SCORING NOTES.
_SECTION_RE = re.compile(r"^[A-Z][A-Z ]*$", re.M)


def replace_section(rubric_text, heading, replacement):
    """Return `rubric_text` with one ALL-CAPS section swapped for `replacement`.

    Raises if the heading is absent, so a rename upstream fails loudly here
    instead of quietly shipping an unrevised rubric under a revised hash.
    """
    starts = [(m.start(), m.group()) for m in _SECTION_RE.finditer(rubric_text)]
    for i, (pos, name) in enumerate(starts):
        if name.strip() != heading:
            continue
        last = i + 1 == len(starts)
        end = len(rubric_text) if last else starts[i + 1][0]
        # Sections are separated by one blank line; normalize so the splice
        # cannot change the surrounding whitespace and thus the hash for a
        # reason unrelated to the revision.
        body = replacement.rstrip("\n") + ("\n" if last else "\n\n")
        return rubric_text[:pos] + body + rubric_text[end:]
    raise ValueError("no %r section in the rubric text" % heading)


JUDGE_RUBRIC_V2_1 = replace_section(
    rubric_v2.JUDGE_RUBRIC_V2, "OBJECTIVE", OBJECTIVE_SECTION_V2_1)

JUDGE_RUBRIC_V3_1 = replace_section(
    rubric_v3.JUDGE_RUBRIC_V3, "OBJECTIVE", OBJECTIVE_SECTION_V3_1)


# ---------------------------------------------------------------------------
# Means. Unrevised -- re-exported so a caller selecting "v2.1" never has to
# reach back into the frozen module and pick the wrong one.
# ---------------------------------------------------------------------------

overall_score_v2_1 = rubric_v2.overall_score
overall_score_v3_1 = rubric_v3.overall_score_v3
bridge_score_v2 = rubric_v3.bridge_score_v2


if __name__ == "__main__":  # pragma: no cover - inspection aid
    import hashlib
    import sys

    which = sys.argv[1] if len(sys.argv) > 1 else "v2.1"
    text = JUDGE_RUBRIC_V3_1 if which == "v3.1" else JUDGE_RUBRIC_V2_1
    print(text)
    print("rubric_hash(%s) = %s" % (
        which, hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]))
