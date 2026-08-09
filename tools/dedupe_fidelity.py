#!/usr/bin/env python3
"""
De-duplicate a fidelity results log.

Two judging processes running the same --resume set (for example, a sweep that
looked dead but was still buffering) can each append a row for the same
(scenario, repeat, mode) triple. Duplicates silently double-weight those
scenarios in every cell mean, so the log needs collapsing before analysis.

Policy per (scenario, repeat, mismatch_control) triple:
  * keep the first successful judgement;
  * if none succeeded, keep the last failure so the attempt stays on record.

The original file is copied to <path>.raw before rewriting.

    python tools/dedupe_fidelity.py output/fidelity.jsonl
    python tools/dedupe_fidelity.py output/fidelity.jsonl --check   # report only
"""

import argparse
import json
import os
import shutil
from collections import Counter, OrderedDict


def key_of(row):
    return (os.path.normpath(str(row.get("scenario", ""))).replace("\\", "/").lower(),
            row.get("repeat", 1),
            bool(row.get("mismatch_control")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--check", action="store_true", help="Report duplicates, change nothing")
    args = ap.parse_args()

    rows = []
    with open(args.path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    kept = OrderedDict()
    for row in rows:
        k = key_of(row)
        prev = kept.get(k)
        if prev is None:
            kept[k] = row
        elif not prev.get("ok"):
            # A success always wins; otherwise the newer failure replaces the old.
            kept[k] = row if row.get("ok") else row

    counts = Counter(key_of(r) for r in rows)
    dupes = {k: v for k, v in counts.items() if v > 1}
    print(f"rows in file        : {len(rows)}")
    print(f"distinct triples    : {len(kept)}")
    print(f"duplicated triples  : {len(dupes)}  (extra rows: {len(rows) - len(kept)})")

    ok_rows = [r for r in kept.values() if r.get("ok")]
    matched = [r for r in ok_rows if not r.get("mismatch_control")]
    mismatched = [r for r in ok_rows if r.get("mismatch_control")]
    print(f"after dedupe: {len(matched)} matched ok over "
          f"{len({r['scenario'] for r in matched})} scenarios, "
          f"{len(mismatched)} mismatch ok")

    if args.check:
        return 0

    backup = args.path + ".raw"
    if not os.path.exists(backup):
        shutil.copy2(args.path, backup)
        print(f"raw log preserved   : {backup}")
    with open(args.path, "w", encoding="utf-8") as f:
        for row in kept.values():
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"rewrote {args.path} with {len(kept)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
