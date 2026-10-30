"""
Shared pytest fixtures.

- Puts the repo root on sys.path (the repo has no packaging; `core`,
  `agents`, and `scripts` are implicit namespace packages).
- `hq` starts scripts/serve.py's GhostHQHandler on an ephemeral port in a
  daemon thread, once per session, and exposes a small JSON client.
- `_reset_hq_state` clears serve.py's in-memory state before every test so
  tests are independent of execution order.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import scripts.serve as serve  # noqa: E402  (after sys.path fix)


class HQClient:
    def __init__(self, base: str) -> None:
        self.base = base

    def request(self, method: str, path: str, body: dict | None = None,
                headers: dict | None = None) -> tuple[int, object]:
        data = json.dumps(body).encode() if body is not None else None
        h = {"Content-Type": "application/json", **(headers or {})}
        req = urllib.request.Request(self.base + path, data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode())

    def get(self, path: str) -> tuple[int, object]:
        return self.request("GET", path)

    def post(self, path: str, body: dict, headers: dict | None = None) -> tuple[int, object]:
        return self.request("POST", path, body, headers)


@pytest.fixture(scope="session")
def hq():
    # Silence per-request access logging during tests.
    serve.GhostHQHandler.log_message = lambda *a, **k: None
    server = ThreadingHTTPServer(("127.0.0.1", 0), serve.GhostHQHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield HQClient(f"http://127.0.0.1:{server.server_address[1]}")
    server.shutdown()
    server.server_close()


@pytest.fixture(autouse=True)
def _reset_hq_state():
    with serve._lock:
        serve._intake_lifecycle.clear()
        serve._audit_log.clear()
        serve._escalations.clear()
        serve._sessions.clear()
        serve._pools.clear()
        serve._intent_lanes.clear()
        serve._route6_held.clear()
    yield
