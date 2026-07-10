"""
Ghost Layer Studio — Ecosystem Contract Validation

# ADVANCEMENT: Ecosystem contracts
Exercises integrations.ecosystem.run_ecosystem_request with valid, diagnostic,
and malformed requests. Exits 0 on PASS, nonzero on FAIL.

Run:  python3 -m scripts.check_ecosystem_contract
"""

from __future__ import annotations
import sys
from typing import Any, Callable, Dict, List, Tuple

from integrations.ecosystem import run_ecosystem_request

SAMPLE_REQUEST: Dict[str, Any] = {
    "request_id": "eco_default_001",
    "source": "hsx",
    "command": "ANALYZE::GHOST_LAYER::DEFAULT",
    "input": "Hello from ecosystem contract check.",
    "context": {
        "operator_mode": "advisory",
        "domain": "operator",
    },
    "options": {
        "include_diagnostics": False,
    },
}


def _check(name: str, ok: bool, detail: str) -> Tuple[str, bool, str]:
    return (name, ok, detail)


def _run_checks() -> List[Tuple[str, bool, str]]:
    results: List[Tuple[str, bool, str]] = []

    # A + B + C — valid default request
    response = run_ecosystem_request(SAMPLE_REQUEST)
    results.append(_check("status_ok", response.get("status") == "ok", f"status={response.get('status')!r}"))
    results.append(_check(
        "request_id_preserved",
        response.get("request_id") == SAMPLE_REQUEST["request_id"],
        f"request_id={response.get('request_id')!r}",
    ))
    results.append(_check(
        "engine_version_present",
        bool(response.get("engine_version")),
        f"engine_version={response.get('engine_version')!r}",
    ))
    results.append(_check(
        "contract_version_present",
        bool(response.get("contract_version")),
        f"contract_version={response.get('contract_version')!r}",
    ))
    results.append(_check(
        "active_agents_is_list",
        isinstance(response.get("active_agents"), list),
        f"type={type(response.get('active_agents')).__name__}",
    ))
    results.append(_check(
        "envelope_is_dict",
        isinstance(response.get("envelope"), dict),
        f"type={type(response.get('envelope')).__name__}",
    ))
    telemetry = response.get("telemetry", {})
    results.append(_check(
        "telemetry_duration_ms",
        isinstance(telemetry, dict) and "duration_ms" in telemetry,
        f"telemetry keys={list(telemetry.keys()) if isinstance(telemetry, dict) else 'n/a'}",
    ))
    diag = response.get("diagnostics")
    results.append(_check(
        "diagnostics_absent_when_disabled",
        diag is None,
        f"diagnostics={diag!r}",
    ))

    # D — diagnostics enabled
    diag_request = {
        **SAMPLE_REQUEST,
        "request_id": "eco_diag_002",
        "options": {"include_diagnostics": True},
    }
    diag_response = run_ecosystem_request(diag_request)
    diag_block = diag_response.get("diagnostics")
    results.append(_check(
        "diagnostics_present_when_enabled",
        isinstance(diag_block, dict),
        f"diagnostics type={type(diag_block).__name__}",
    ))
    if isinstance(diag_block, dict):
        results.append(_check(
            "diagnostics_ok_true",
            diag_block.get("ok") is True,
            f"diagnostics.ok={diag_block.get('ok')!r}",
        ))
        results.append(_check(
            "diagnostics_error_count_zero",
            diag_block.get("error_count") == 0,
            f"error_count={diag_block.get('error_count')!r}",
        ))

    # E — malformed command
    bad_request = {
        **SAMPLE_REQUEST,
        "request_id": "eco_bad_cmd_003",
        "command": "BADCOMMAND",
    }
    bad_response = run_ecosystem_request(bad_request)
    results.append(_check(
        "malformed_command_status_error",
        bad_response.get("status") == "error",
        f"status={bad_response.get('status')!r}",
    ))
    results.append(_check(
        "malformed_command_errors_list",
        isinstance(bad_response.get("errors"), list),
        f"errors={bad_response.get('errors')!r}",
    ))

    return results


def main() -> int:
    print("Ghost Layer Studio — Ecosystem Contract Validation")
    print("=" * 56)

    results = _run_checks()
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
    print("RESULT: PASS — ecosystem contract foundation verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
