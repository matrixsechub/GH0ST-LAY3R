"""
scripts/serve.py's _REGISTRY_FALLBACK must mirror agents/registry.yaml: the
server uses it whenever PyYAML is missing, so drift would silently change
what GET /agents, /engines, /operators and /capabilities return.
"""

from __future__ import annotations

import os

import pytest

import scripts.serve as serve

yaml = pytest.importorskip("yaml")


def _normalize(value):
    # YAML folded scalars ("description: >") end with a newline.
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return {k: _normalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    return value


def test_fallback_mirrors_registry_yaml():
    with open(os.path.join(serve._REPO_ROOT, "agents", "registry.yaml"), encoding="utf-8") as fh:
        registry = yaml.safe_load(fh)
    assert _normalize(serve._REGISTRY_FALLBACK) == _normalize(registry)
