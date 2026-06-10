"""Operator debug helper: step through phase4 imports on CPU with a trace log.

Not used in CI or scheduled runs. Writes to data/exports/finish-debug.log.
See runbook-local.md §17f.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

p = Path(__file__).resolve().parents[1] / "data" / "exports" / "finish-debug.log"
p.parent.mkdir(parents=True, exist_ok=True)

def log(msg: str) -> None:
    p.write_text(p.read_text(encoding="utf-8") + msg + "\n", encoding="utf-8") if p.is_file() else p.write_text(msg + "\n", encoding="utf-8")

try:
    log("start")
    os.environ["TORCH_DEVICE"] = "cpu"
    ROOT = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(ROOT / "src"))
    log("import cli_context")
    from ebay_workflows.cli_context import cli_session, load_settings
    log("load_settings")
    settings = load_settings(action="debug")
    log("settings ok")
    log("import workflows.phase4")
    from ebay_workflows.workflows.phase4 import run_phase4_ranking
    log("phase4 import ok")
    log("run phase4")
    with cli_session(action="phase4 rank", settings=settings) as (_, session):
        run_id = run_phase4_ranking(session, settings, use_hybrid=True)
    log(f"done {run_id}")
except Exception as exc:
    log(f"error: {exc!r}")
