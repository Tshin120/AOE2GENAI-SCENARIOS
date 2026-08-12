#!/usr/bin/env python3
"""
Factorial experiment driver.

Runs the episode set through every cell of a prompt-condition factorial, one
`create_scenario.py` process per (episode, cell), with a bounded worker pool.
Each cell gets its own output directory so scenario filenames never collide and
every artefact is attributable to exactly one arm.

    python tools/run_factorial.py --episodes output/_episodes.json --workers 8

Cells (2x2): reachability_prompting {on, off} x prompt_style {templated, freeform}.
Every run is temperature 0.0 by default so the comparison is a prompt ablation
rather than a sampling-noise measurement.

`--cells rubric` runs a fifth cell instead: the v1 historical-fidelity rubric on
top of the reach-off/freeform prompt. It differs from reach_off__freeform in
exactly one factor, so that cell is its baseline.

    python tools/run_factorial.py --root output/rubric_arm --cells rubric --workers 4

`--cells fidelity` is the v2 equivalent (rubric_v2's GENERATOR_FIDELITY_BLOCK),
against the same baseline; `--cells fidelity_reach` adds it on top of the
reachability block instead, which is the only configuration where the
reconciliation text between the two blocks applies.

    python tools/run_factorial.py --root output/fidelity_v2_arm --cells fidelity --workers 4

Results stream into one JSONL per cell under <root>/<cell>/results.jsonl; the
arm is recoverable from the logged `reachability_prompting` / `prompt_style` /
`fidelity_rubric` / `fidelity_prompt` fields as well as from the path.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def slug(text):
    keep = [c.lower() if c.isalnum() else "_" for c in text]
    out = "".join(keep)
    while "__" in out:
        out = out.replace("__", "_")
    return out.strip("_")


def build_jobs(episodes, cells, root, temperature, model, max_repair, introspection):
    jobs = []
    for cell in cells:
        cell_dir = os.path.join(root, cell["name"])
        for ep in episodes:
            out = os.path.join(cell_dir, slug(ep["title"]) + ".aoe2scenario")
            cmd = [
                sys.executable, os.path.join(REPO_ROOT, "create_scenario.py"),
                "--title", ep["title"],
                "--description", ep.get("description", ""),
                "--scenario-type", ep.get("scenario_type", "story"),
                "--difficulty", ep.get("difficulty", "medium"),
                "--map-size", str(ep.get("map_size", 120)),
                "--players", str(ep.get("players", 2)),
                "--temperature", str(temperature),
                "--max-repair-attempts", str(max_repair),
                "--prompt-style", cell["prompt_style"],
                "--reachability" if cell["reachability"] else "--no-reachability",
                "--fidelity-rubric" if cell.get("fidelity_rubric") else "--no-fidelity-rubric",
                "--fidelity-prompt", "on" if cell.get("fidelity_prompt") else "off",
                "--fidelity-prompt-version", cell.get("fidelity_prompt_version", "v2"),
                "--introspection" if introspection else "--no-introspection",
                "--output", out,
                "--results-log", os.path.join(cell_dir, "results.jsonl"),
            ]
            for flag, key in (("--region", "region"), ("--player-civ", "player_civ"),
                              ("--enemy-civ", "enemy_civ"), ("--wikipedia-url", "wikipedia_url")):
                if ep.get(key):
                    cmd += [flag, ep[key]]
            if model:
                cmd += ["--model", model]
            jobs.append({"cell": cell["name"], "title": ep["title"], "cmd": cmd, "out": out})
    return jobs


def run_job(job, timeout):
    t0 = time.time()
    try:
        p = subprocess.run(job["cmd"], capture_output=True, text=True,
                           timeout=timeout, cwd=REPO_ROOT)
        rc, tail = p.returncode, (p.stdout or "")[-400:]
    except subprocess.TimeoutExpired:
        rc, tail = -1, "TIMEOUT"
    return {**job, "rc": rc, "secs": round(time.time() - t0, 1), "tail": tail}


def main():
    ap = argparse.ArgumentParser(description="Run the prompt-condition factorial.")
    ap.add_argument("--episodes", default="output/_episodes.json")
    ap.add_argument("--root", default="output/factorial")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--model", default=None)
    ap.add_argument("--max-repair-attempts", type=int, default=3, dest="max_repair")
    ap.add_argument("--no-introspection", dest="introspection", action="store_false",
                    help="Run every cell with introspection-guided repair disabled")
    ap.add_argument("--cells", default="all",
                    help="'all' (2x2), 'baseline' (reach_off__freeform alone - the "
                         "shared baseline of every fidelity arm), "
                         "'reach' (reachability only, templated), "
                         "'style' (prompt style only, reachability on), "
                         "'rubric' (the v1 fidelity-rubric arm alone; baseline is "
                         "reach_off__freeform), 'fidelity' (the v2 fidelity-prompt arm; "
                         "same baseline), or 'fidelity_reach' (v2 fidelity with "
                         "reachability also on; baseline is reach_on__freeform)")
    ap.add_argument("--timeout", type=int, default=2400)
    ap.set_defaults(introspection=True)
    args = ap.parse_args()

    all_cells = [
        {"name": "reach_on__templated", "reachability": True, "prompt_style": "templated",
         "fidelity_rubric": False},
        {"name": "reach_off__templated", "reachability": False, "prompt_style": "templated",
         "fidelity_rubric": False},
        {"name": "reach_on__freeform", "reachability": True, "prompt_style": "freeform",
         "fidelity_rubric": False},
        {"name": "reach_off__freeform", "reachability": False, "prompt_style": "freeform",
         "fidelity_rubric": False},
    ]
    # One-factor fidelity arm: identical to reach_off__freeform except that the
    # historical-fidelity rubric is appended to the system prompt, so that cell
    # is its baseline.
    rubric_cells = [
        {"name": "rubric_on__freeform", "reachability": False, "prompt_style": "freeform",
         "fidelity_rubric": True},
    ]
    # v2 fidelity arm. Two one-factor cells, each against its own baseline:
    #   fidelity_on__freeform            vs reach_off__freeform  (fidelity alone)
    #   fidelity_on__reach_on__freeform  vs reach_on__freeform   (both arms, which
    #                                    is the only cell where the reachability
    #                                    reconciliation text is in play)
    fidelity_cells = [
        {"name": "fidelity_on__freeform", "reachability": False, "prompt_style": "freeform",
         "fidelity_prompt": True},
    ]
    # v3 arm: same cell shape as the v2 fidelity arm, different rubric text.
    fidelity_v3_cells = [
        {"name": "fidelity_v3__freeform", "reachability": False, "prompt_style": "freeform",
         "fidelity_prompt": True, "fidelity_prompt_version": "v3"},
    ]
    fidelity_reach_cells = [
        {"name": "fidelity_on__reach_on__freeform", "reachability": True,
         "prompt_style": "freeform", "fidelity_prompt": True},
    ]
    if args.cells == "baseline":
        # The shared baseline of every fidelity arm, on its own. `all` would run
        # the full 2x2 to get it, which is 4x the generation cost when a paired
        # comparison only needs this one cell.
        cells = [c for c in all_cells if c["name"] == "reach_off__freeform"]
    elif args.cells == "reach":
        cells = [c for c in all_cells if c["prompt_style"] == "templated"]
    elif args.cells == "style":
        cells = [c for c in all_cells if c["reachability"]]
    elif args.cells == "rubric":
        cells = rubric_cells
    elif args.cells == "fidelity":
        cells = fidelity_cells
    elif args.cells == "fidelity_v3":
        cells = fidelity_v3_cells
    elif args.cells == "fidelity_reach":
        cells = fidelity_reach_cells
    else:
        cells = all_cells

    with open(args.episodes, encoding="utf-8") as f:
        episodes = json.load(f)

    jobs = build_jobs(episodes, cells, args.root, args.temperature, args.model,
                      args.max_repair, args.introspection)
    for c in cells:
        os.makedirs(os.path.join(args.root, c["name"]), exist_ok=True)

    print(f"{len(jobs)} runs = {len(episodes)} episodes x {len(cells)} cells, "
          f"{args.workers} workers, temperature={args.temperature}, "
          f"introspection={'on' if args.introspection else 'off'}", flush=True)

    done = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(run_job, j, args.timeout) for j in jobs]
        for fut in as_completed(futs):
            r = fut.result()
            done += 1
            status = "ok " if r["rc"] == 0 else f"FAIL({r['rc']})"
            print(f"[{done}/{len(jobs)}] {status} {r['secs']:>6.1f}s  "
                  f"{r['cell']:<22} {r['title']}", flush=True)

    print(f"\nAll {len(jobs)} runs finished in {(time.time()-t0)/60:.1f} min")


if __name__ == "__main__":
    main()
