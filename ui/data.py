"""Cached data access for the UI: result files and the offline demo run."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"


def load_json(name: str) -> dict | None:
    path = RESULTS / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


@st.cache_data(show_spinner=False)
def results_bundle(stamp: float) -> dict:
    """All experiment outputs; `stamp` (latest mtime) invalidates the cache when files change."""
    return {name: load_json(f"{name}.json") for name in
            ("benchmark", "benchmark_v1", "benchmark_v2", "spec_audit", "spec_audit_v2", "mutation_study", "safety_eval")}


def results() -> dict:
    stamp = max((p.stat().st_mtime for p in RESULTS.glob("*.json")), default=0.0)
    return results_bundle(stamp)


@st.cache_resource(show_spinner=False)
def demo_run() -> dict:
    """Runs the scripted demo once (real sandbox executions, pre-recorded model replies)."""
    from reflexdebug import ReflexDebugAgent, Settings
    from reflexdebug.demo import DEMO_TASK, demo_llm
    from reflexdebug.memory import ReflexionMemory

    settings = Settings()
    settings.max_steps_per_trial = 3
    llm = demo_llm()
    memory = ReflexionMemory(Path(tempfile.mkdtemp()) / "demo_memory.json", llm)
    return ReflexDebugAgent(llm, settings, memory=memory).solve(DEMO_TASK).to_dict()


def api_key_present() -> bool:
    from reflexdebug.config import Settings

    return bool(Settings().api_key)
