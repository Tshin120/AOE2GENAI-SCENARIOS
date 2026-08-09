"""
Provenance helpers for the AoE2 scenario generator.

Two artefacts are produced per run so playability rates and generation
parameters can be analysed statistically after the fact:

1. A metadata SIDECAR (`<scenario>.aoe2scenario.meta.json`) written next to each
   generated scenario, recording the exact model/temperature/max_tokens/flags
   and terminal outcome for that scenario.

2. A per-run RESULTS LOG (JSONL, append-only). Every generation ATTEMPT -
   including self-repair retries - is one line, tagged with run_id, candidate
   and attempt numbers. The run's terminal outcome is the last attempt's line
   for that (run_id, candidate).

Everything here is stdlib-only (no third-party dependencies).
"""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path


def new_run_id():
    """Return a short, unique id grouping all attempts of one experiment run."""
    return "run_" + uuid.uuid4().hex[:12]


def utc_now_iso():
    """Return the current UTC time as an ISO-8601 string (e.g. 2026-07-17T12:34:56Z)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sidecar_path(scenario_path):
    """Return the metadata sidecar path for a given scenario output path."""
    return str(scenario_path) + ".meta.json"


def write_sidecar(scenario_path, meta):
    """Write (overwrite) the metadata sidecar next to a generated scenario.

    Returns the sidecar path. `meta` is any JSON-serialisable mapping; a
    `timestamp_utc` key is added if absent.
    """
    meta = dict(meta)
    meta.setdefault("timestamp_utc", utc_now_iso())
    path = sidecar_path(scenario_path)
    parent = Path(path).parent
    if str(parent):
        parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    return path


def append_result(results_log_path, record):
    """Append one attempt record as a single JSON line to the results log.

    A `timestamp_utc` key is added if absent. No-op when results_log_path is
    falsy, so callers can disable logging by passing None.
    """
    if not results_log_path:
        return
    record = dict(record)
    record.setdefault("timestamp_utc", utc_now_iso())
    parent = Path(results_log_path).parent
    if str(parent):
        parent.mkdir(parents=True, exist_ok=True)
    with open(results_log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
