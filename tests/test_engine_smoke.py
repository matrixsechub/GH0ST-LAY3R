"""Regression tests for the Ghost Layer engine boot path.

The engine previously failed at import time (circular IntentVector import,
then a mutable dataclass default), so the demo could not run at all.
"""

import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULES = [
    "core.types",
    "core.substrate",
    "core.physics",
    "core.oversoul",
    "core.output",
    "agents.constellation",
    "core.engine",
    "core.registry",
]


@pytest.mark.parametrize("name", MODULES)
def test_module_imports_in_fresh_interpreter(name):
    # A fresh interpreter catches import cycles that a warm sys.modules hides.
    proc = subprocess.run(
        [sys.executable, "-c", f"import {name}"],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr


def test_intent_vector_is_shared_and_reexported():
    engine = importlib.import_module("core.engine")
    types = importlib.import_module("core.types")
    assert engine.IntentVector is types.IntentVector
    assert engine.OperatorAxis is types.OperatorAxis


def test_default_engine_run_returns_structured_result():
    from core.engine import create_default_engine

    engine = create_default_engine()
    result = engine.run("Boot sequence: Ghost Layer Studio online.", source="pytest")

    assert result["source"] == "pytest"
    assert result["intent_id"]
    assert result["operator_axis"] == "operator-defensive"
    payload = result["payload"]
    assert payload["agent_count"] == len(payload["agents"]) >= 1
    assert payload["recursion_complete"] is True
    # Recursion is bounded by EngineConfig.max_recursion.
    assert len(payload["recursion_trace"]) == engine.config.max_recursion


def test_oversoul_configs_are_not_shared_between_instances():
    from core.oversoul import DefaultOversoul

    first, second = DefaultOversoul(), DefaultOversoul()
    assert first.config is not second.config


def test_demo_script_runs():
    proc = subprocess.run(
        [sys.executable, "scripts/run_demo.py"],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert '"recursion_complete": true' in proc.stdout
