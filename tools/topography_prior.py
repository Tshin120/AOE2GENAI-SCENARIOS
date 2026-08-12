#!/usr/bin/env python3
"""STEP 2: rank each episode by how well its battlefield geography is documented.

The question this exists to answer: when the v3 generator block told the model
to reason explicitly about layout before placing anything, `terrain` rose +0.75
overall but almost entirely on one episode. Is the operative variable
*perception* (the model now attends to space) or *prior strength* (the model
already knows what that particular ground looked like, and the instruction only
gave it license to use what it knew)?

If terrain movement tracks how canonically documented an episode's topography
is, the second reading wins and terrain stops being evidence about perception.

The ranking is taken from a model that is shown ONLY the episode briefs. It is
never shown the terrain scores, the deltas, the hypothesis, or that this has
anything to do with map generation - a judge told what the answer would imply
is not evidence. Ranking them by hand after having seen the deltas is worse: it
cannot be blind, because whoever writes it already knows the answer.

    python tools/topography_prior.py --repeats 3 --out output/topography_prior.json
"""

import argparse
import itertools
import json
import math
import os
import sys
from collections import defaultdict

# Run from the repo root (`python tools/topography_prior.py`); this makes the
# root-level modules importable regardless of the working directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api_config
from fidelity_judge import call_judge, _extract_json

SYSTEM = """\
You are a military historian assessing source availability. You answer with a \
single JSON object and nothing else."""

# Deliberately says nothing about maps, games, generation, or terrain scoring.
# The rating asked for is a property of the historical record, not of any
# artifact, so the answer cannot be steered by what it would imply downstream.
PROMPT = """\
For each historical episode below, rate how precisely its PHYSICAL GROUND is
documented in the surviving record: the specific battlefield, route, or siege
lines, at a level of detail that would let a historian draw a map with the
features in the right places relative to each other.

Rate 1 to 10.

  10  The ground is a named, surveyed, still-identifiable place. Contemporary
      or near-contemporary sources describe the relevant features - slope,
      watercourse, wall line, chokepoint - and their relation to where each
      side stood. A modern historian can and does draw a confident map.
   5  The general locality is known and some features are attested, but their
      arrangement is reconstructed or disputed.
   1  Only the region is known. The specific ground is unlocated, or the
      episode is a journey or campaign with no single site at all.

Judge the RECORD, not the fame of the event: a famous battle whose site is
still argued over rates low, and an obscure siege with surviving plans rates
high. An episode spanning a long route has no single battlefield and should be
rated on whether its decisive terrain is pinned down.

Episodes:

{episodes}

Return exactly this JSON shape, one entry per episode, using the exact keys
given:

{{
  "ratings": {{
{shape}
  }}
}}

Each value is an object: {{"score": <1-10>, "reason": "<one sentence naming the
sources or the specific uncertainty>"}}"""


def _rank(vals):
    """Ranks with ties averaged, so tied terrain scores do not bias rho."""
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    out = [0.0] * len(vals)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return out


def _pearson(a, b):
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    return num / den if den else float("nan")


def _spearman(a, b):
    return _pearson(_rank(a), _rank(b))


def _perm_p(x, y):
    """Exact two-sided permutation p for Spearman. n=8 is 40320 orderings."""
    obs = abs(_spearman(x, y))
    hits = total = 0
    for perm in itertools.permutations(y):
        total += 1
        if abs(_spearman(x, list(perm))) >= obs - 1e-12:
            hits += 1
    return hits / total


def terrain_by_episode(path, version="v3"):
    """episode key -> mean terrain score in one fidelity log."""
    acc = defaultdict(list)
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("ok") and row.get("rubric_version") == version:
                key = os.path.basename(row["scenario"]).replace(".aoe2scenario", "")
                acc[key].append(row["terrain"])
    return {k: sum(v) / len(v) for k, v in acc.items()}


def correlate(rows, log_a, log_b, version):
    """Join the ratings to the terrain scores and report the correlations.

    Reported against the baseline and the post-instruction score as well as the
    delta, because they answer different questions: whether the prior reaches
    the map at all, versus whether it governs how far instruction moves it.
    """
    a = terrain_by_episode(log_a, version)
    b = terrain_by_episode(log_b, version)
    keys = [r["episode"] for r in rows if r["episode"] in a and r["episode"] in b]
    if len(keys) < 3:
        print("\nnot enough overlapping episodes to correlate", file=sys.stderr)
        return None

    prior = [next(r["mean"] for r in rows if r["episode"] == k) for k in keys]
    base = [a[k] for k in keys]
    post = [b[k] for k in keys]
    delta = [b[k] - a[k] for k in keys]

    print(f"\n{'episode':<32}{'prior':>7}{'A':>7}{'B':>7}{'delta':>8}")
    print("-" * 61)
    for i, k in enumerate(keys):
        print(f"{k:<32}{prior[i]:>7.2f}{base[i]:>7.2f}{post[i]:>7.2f}{delta[i]:>+8.2f}")

    out = {}
    print()
    for label, series, key in (("baseline terrain (A)", base, "baseline"),
                               ("post-v3 terrain (B)", post, "post"),
                               ("delta (B - A)", delta, "delta")):
        rho, p = _spearman(prior, series), _perm_p(prior, series)
        out[key] = {"spearman": round(rho, 3), "perm_p": round(p, 4)}
        print(f"prior vs {label:<22} rho={rho:+.2f}  exact perm p={p:.3f}")

    # A correlation one episode can carry is not a correlation. Say so in the
    # output rather than leaving it for whoever reads the number later.
    print("\nleave-one-out (prior vs delta):")
    loo = {}
    for i, k in enumerate(keys):
        rho = _spearman([x for j, x in enumerate(prior) if j != i],
                        [x for j, x in enumerate(delta) if j != i])
        loo[k] = round(rho, 3)
        print(f"   without {k:<32} rho={rho:+.2f}")
    out["delta_leave_one_out"] = loo
    return out


def episode_briefs(root):
    """(key, title, description) per distinct episode under `root`."""
    out = {}
    for dirpath, _dirs, files in os.walk(root):
        for name in sorted(files):
            if not name.endswith(".aoe2scenario.meta.json"):
                continue
            with open(os.path.join(dirpath, name), encoding="utf-8") as f:
                meta = json.load(f)
            key = name.replace(".aoe2scenario.meta.json", "")
            out.setdefault(key, (meta.get("title", key), meta.get("description", "")))
    return [(k, v[0], v[1]) for k, v in sorted(out.items())]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default="output/fidelity_v3_arm",
                    help="Tree whose sidecars supply the episode briefs")
    ap.add_argument("--model", default="opus-5")
    ap.add_argument("--repeats", type=int, default=3,
                    help="Independent ratings; reported with their spread")
    ap.add_argument("--out", default="output/topography_prior.json")
    ap.add_argument("--terrain-a", default="output/fidelity_v3_measA.jsonl",
                    help="Fidelity log for measurement A (pre-instruction baseline)")
    ap.add_argument("--terrain-b", default="output/fidelity_v3_measB.jsonl",
                    help="Fidelity log for measurement B (post-instruction)")
    ap.add_argument("--rubric-version", default="v3",
                    help="Only pool rows scored under this version")
    ap.add_argument("--no-correlate", dest="correlate", action="store_false",
                    help="Produce the ratings only, without joining terrain scores")
    ap.set_defaults(correlate=True)
    args = ap.parse_args()

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("OPENROUTER_API_KEY is not set", file=sys.stderr)
        return 1

    episodes = episode_briefs(args.root)
    if not episodes:
        print(f"No episode sidecars under {args.root}", file=sys.stderr)
        return 1

    listing = "\n\n".join(f"[{k}] {t}\n{d}" for k, t, d in episodes)
    shape = ",\n".join(f'    "{k}": {{"score": <1-10>, "reason": "..."}}'
                       for k, _t, _d in episodes)
    prompt = PROMPT.format(episodes=listing, shape=shape)

    print(f"Rating {len(episodes)} episode(s) x {args.repeats} repeat(s)  "
          f"model={api_config.resolve_model(args.model)}", flush=True)

    scores = defaultdict(list)
    reasons = {}
    for rep in range(1, args.repeats + 1):
        verdict = _extract_json(call_judge(api_key, prompt, args.model))
        ratings = verdict["ratings"]
        for key, _t, _d in episodes:
            entry = ratings[key]
            scores[key].append(int(entry["score"]))
            reasons.setdefault(key, entry.get("reason", ""))
        print(f"  repeat {rep}: "
              + ", ".join(f"{k.split('_')[-1]}={ratings[k]['score']}"
                          for k, _t, _d in episodes), flush=True)

    rows = []
    for key, title, _d in episodes:
        vals = scores[key]
        rows.append({"episode": key, "title": title,
                     "scores": vals,
                     "mean": round(sum(vals) / len(vals), 2),
                     "spread": max(vals) - min(vals),
                     "reason": reasons[key]})
    rows.sort(key=lambda r: -r["mean"])

    print(f"\n{'episode':<32}{'mean':>6}{'spread':>8}   raw")
    print("-" * 72)
    for r in rows:
        print(f"{r['episode']:<32}{r['mean']:>6.2f}{r['spread']:>8}   {r['scores']}")

    stats = None
    if args.correlate:
        if os.path.exists(args.terrain_a) and os.path.exists(args.terrain_b):
            stats = correlate(rows, args.terrain_a, args.terrain_b,
                              args.rubric_version)
        else:
            print("\nskipping correlation: terrain log(s) not found",
                  file=sys.stderr)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"model": api_config.resolve_model(args.model),
                   "repeats": args.repeats, "ratings": rows,
                   "terrain_a": args.terrain_a, "terrain_b": args.terrain_b,
                   "rubric_version": args.rubric_version,
                   "correlations": stats}, f, indent=2)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
