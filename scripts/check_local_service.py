"""
Ghost Layer Studio — Local HTTP Service Validation

# ADVANCEMENT: Local HTTP adapter
Starts the local HTTP service in a background thread, exercises all routes
via urllib.request, and shuts down cleanly. No external network calls.

Run:  python -m scripts.check_local_service
Exits 0 on PASS, nonzero on FAIL.
"""

from __future__ import annotations
import json
import socket
import sys
import threading
import time
from http.server import HTTPServer
from typing import Any, Dict, List, Tuple
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from integrations.http_service import create_handler

SAMPLE_REQUEST: Dict[str, Any] = {
    "request_id": "local_svc_001",
    "source": "hsx",
    "command": "ANALYZE::GHOST_LAYER::DEFAULT",
    "input": "Hello from local service check.",
    "context": {"operator_mode": "advisory"},
    "options": {"include_diagnostics": False},
}


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _request(
    method: str,
    url: str,
    payload: Dict[str, Any] | None = None,
    *,
    raw_body: bytes | None = None,
) -> Tuple[int, Dict[str, Any] | None, str]:
    data = raw_body
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
            parsed = json.loads(body) if body else {}
            return resp.status, parsed if isinstance(parsed, dict) else None, body
    except HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = None
        return exc.code, parsed if isinstance(parsed, dict) else None, body


def _check(name: str, ok: bool, detail: str) -> Tuple[str, bool, str]:
    return (name, ok, detail)


def _run_checks(base_url: str) -> List[Tuple[str, bool, str]]:
    results: List[Tuple[str, bool, str]] = []

    # A. GET /health
    status, body, _ = _request("GET", f"{base_url}/health")
    results.append(_check("health_status_code", status == 200, f"status={status}"))
    results.append(_check(
        "health_status_ok",
        isinstance(body, dict) and body.get("status") == "ok",
        f"status={body.get('status') if body else None!r}",
    ))
    results.append(_check(
        "health_service_name",
        isinstance(body, dict) and body.get("service") == "ghost-layer-local",
        f"service={body.get('service') if body else None!r}",
    ))
    results.append(_check(
        "health_engine_version",
        isinstance(body, dict) and bool(body.get("engine_version")),
        f"engine_version={body.get('engine_version') if body else None!r}",
    ))

    # B. GET /contracts
    status, body, _ = _request("GET", f"{base_url}/contracts")
    results.append(_check("contracts_status_code", status == 200, f"status={status}"))
    results.append(_check(
        "contracts_request_version",
        isinstance(body, dict) and bool(body.get("ecosystem_request_version")),
        f"ecosystem_request_version={body.get('ecosystem_request_version') if body else None!r}",
    ))
    supported = body.get("supported_commands", []) if isinstance(body, dict) else []
    results.append(_check(
        "contracts_supports_analyze",
        isinstance(supported, list) and "ANALYZE" in supported,
        f"supported_commands={supported!r}",
    ))

    # C. POST /validate-command
    status, body, _ = _request(
        "POST",
        f"{base_url}/validate-command",
        {"command": "ANALYZE::GHOST_LAYER::DEFAULT"},
    )
    results.append(_check("validate_command_status", status == 200, f"status={status}"))
    results.append(_check(
        "validate_command_ok",
        isinstance(body, dict) and body.get("ok") is True,
        f"ok={body.get('ok') if body else None!r}",
    ))
    results.append(_check(
        "validate_command_category",
        isinstance(body, dict) and body.get("category") == "ANALYZE",
        f"category={body.get('category') if body else None!r}",
    ))

    # D. POST /validate-request
    status, body, _ = _request("POST", f"{base_url}/validate-request", SAMPLE_REQUEST)
    results.append(_check("validate_request_status", status == 200, f"status={status}"))
    results.append(_check(
        "validate_request_ok",
        isinstance(body, dict) and body.get("ok") is True,
        f"ok={body.get('ok') if body else None!r}",
    ))

    # E. POST /run
    status, body, _ = _request("POST", f"{base_url}/run", SAMPLE_REQUEST)
    results.append(_check("run_status_code", status == 200, f"status={status}"))
    results.append(_check(
        "run_status_ok",
        isinstance(body, dict) and body.get("status") == "ok",
        f"status={body.get('status') if body else None!r}",
    ))
    results.append(_check(
        "run_request_id_preserved",
        isinstance(body, dict) and body.get("request_id") == SAMPLE_REQUEST["request_id"],
        f"request_id={body.get('request_id') if body else None!r}",
    ))
    results.append(_check(
        "run_envelope_exists",
        isinstance(body, dict) and isinstance(body.get("envelope"), dict),
        f"envelope type={type(body.get('envelope') if body else None).__name__}",
    ))
    diag = body.get("diagnostics") if isinstance(body, dict) else "missing"
    results.append(_check(
        "run_diagnostics_absent",
        diag is None,
        f"diagnostics={diag!r}",
    ))

    # F. POST /run-diagnostics
    status, body, _ = _request("POST", f"{base_url}/run-diagnostics", SAMPLE_REQUEST)
    results.append(_check("run_diag_status_code", status == 200, f"status={status}"))
    results.append(_check(
        "run_diag_status_ok",
        isinstance(body, dict) and body.get("status") == "ok",
        f"status={body.get('status') if body else None!r}",
    ))
    diag_block = body.get("diagnostics") if isinstance(body, dict) else None
    results.append(_check(
        "run_diag_present",
        isinstance(diag_block, dict),
        f"diagnostics type={type(diag_block).__name__}",
    ))
    if isinstance(diag_block, dict):
        results.append(_check(
            "run_diag_ok_true",
            diag_block.get("ok") is True,
            f"diagnostics.ok={diag_block.get('ok')!r}",
        ))

    # G. POST malformed JSON
    status, body, _ = _request(
        "POST",
        f"{base_url}/run",
        raw_body=b"{not valid json",
    )
    results.append(_check("malformed_json_status", status == 400, f"status={status}"))
    results.append(_check(
        "malformed_json_error",
        isinstance(body, dict) and body.get("status") == "error",
        f"body={body!r}",
    ))

    # H. GET /missing
    status, body, _ = _request("GET", f"{base_url}/missing")
    results.append(_check("missing_route_status", status == 404, f"status={status}"))
    results.append(_check(
        "missing_route_error",
        isinstance(body, dict) and body.get("status") == "error",
        f"body={body!r}",
    ))

    return results


def main() -> int:
    port = _find_free_port()
    host = "127.0.0.1"
    handler = create_handler()
    server = HTTPServer((host, port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)

    base_url = f"http://{host}:{port}"
    print("Ghost Layer Studio — Local HTTP Service Validation")
    print("=" * 56)
    print(f"  Service URL: {base_url}")

    try:
        results = _run_checks(base_url)
    finally:
        server.shutdown()
        thread.join(timeout=5)

    failed = 0
    for name, ok, detail in results:
        status = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"  [{status}] {name}: {detail}")

    print("-" * 56)
    if failed:
        print(f"RESULT: FAIL ({failed} check(s) failed)")
        return 1
    print("RESULT: PASS — local HTTP service verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
