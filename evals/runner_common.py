"""Shared I/O helpers for the eval runners."""

import json
from datetime import datetime, timezone
from pathlib import Path


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def append_jsonl(path, record):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def next_baseline_dir(results_root, today):
    candidate = Path(results_root) / f"baseline-{today}"
    suffix = 2
    while candidate.exists():
        candidate = Path(results_root) / f"baseline-{today}-{suffix}"
        suffix += 1
    return candidate
