"""
Escalation management — GET /escalations/:id and PATCH /escalations/:id.

Covers AGENT_HQ.md's Escalation Lifecycle state machine (pending ->
acknowledged -> resolved, pending -> dismissed, acknowledged -> dismissed),
the authority rule (anyone may acknowledge; only the operator may resolve or
dismiss), audit events, and how closing an escalation interacts with GOV-3
escalations and the intake flow.
"""

from __future__ import annotations

import pytest

import scripts.serve as serve

TOKEN = "test-operator-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
ACTION = "/intake-agent-v2/lifecycle/action"


@pytest.fixture(autouse=True)
def _operator_token(monkeypatch):
    monkeypatch.setenv(serve.OPERATOR_TOKEN_ENV, TOKEN)


def _gov3_escalation(hq) -> dict:
    """Raise a GOV-3 escalation the way production does: a critical-tagged intent."""
    status, _ = hq.post("/intents", {"raw": "urgent", "source": "t", "tags": ["critical"]})
    assert status == 200
    [escalation] = [e for e in hq.get("/escalations")[1] if e["trigger_rule"] == "GOV-3"][-1:]
    return escalation


def _patch(hq, escalation_id: str, body: dict, headers: dict | None = None) -> tuple[int, dict]:
    return hq.request("PATCH", f"/escalations/{escalation_id}", body, headers)


def _ok(hq, escalation_id: str, status: str, headers=AUTH, **extra) -> dict:
    code, body = _patch(hq, escalation_id, {"status": status, **extra}, headers)
    assert code == 200, body
    return body


def _snapshot(hq) -> tuple:
    return hq.get("/escalations")[1], hq.get("/audit")[1]


# ---------------------------------------------------------------------------
# GET /escalations/:id
# ---------------------------------------------------------------------------

def test_get_escalation_by_id(hq):
    escalation = _gov3_escalation(hq)
    status, body = hq.get(f"/escalations/{escalation['id']}")
    assert status == 200
    assert body == escalation


def test_get_unknown_escalation_is_404(hq):
    status, body = hq.get("/escalations/does-not-exist")
    assert status == 404
    assert "No escalation" in body["error"]


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path, final", [
    (["acknowledged", "resolved"], "resolved"),
    (["acknowledged", "dismissed"], "dismissed"),
    (["dismissed"], "dismissed"),
])
def test_allowed_paths(hq, path, final):
    escalation = _gov3_escalation(hq)
    for status in path:
        body = _ok(hq, escalation["id"], status, resolution="reviewed")
    assert body["status"] == final
    assert body["resolved_at"]
    assert body["resolution"] == "reviewed"
    assert hq.get(f"/escalations/{escalation['id']}")[1] == body
    assert hq.get("/hq/health")[1]["open_escalation_count"] == 0


@pytest.mark.parametrize("path, status", [
    ([], "resolved"),                              # spec: resolve only after acknowledging
    (["acknowledged"], "acknowledged"),
    (["dismissed"], "acknowledged"),               # closed escalations stay closed
    (["dismissed"], "dismissed"),
    (["acknowledged", "resolved"], "dismissed"),
    (["acknowledged", "resolved"], "acknowledged"),
])
def test_disallowed_transitions_rejected_without_side_effects(hq, path, status):
    escalation = _gov3_escalation(hq)
    for step in path:
        _ok(hq, escalation["id"], step)
    before = _snapshot(hq)
    code, body = _patch(hq, escalation["id"], {"status": status}, AUTH)
    assert code == 422
    assert "not allowed" in body["error"]
    assert _snapshot(hq) == before


def test_acknowledge_keeps_escalation_open_and_has_no_resolution(hq):
    escalation = _gov3_escalation(hq)
    body = _ok(hq, escalation["id"], "acknowledged", headers={}, resolution="ignored")
    assert body["status"] == "acknowledged"
    assert body["resolved_at"] is None
    assert body["resolution"] == ""
    assert hq.get("/hq/health")[1]["open_escalation_count"] == 1
    assert [e["id"] for e in hq.get("/escalations?status=pending,acknowledged")[1]] == [escalation["id"]]


# ---------------------------------------------------------------------------
# Authority: anyone may acknowledge; only the operator may resolve / dismiss
# ---------------------------------------------------------------------------

def test_anyone_may_acknowledge(hq):
    escalation = _gov3_escalation(hq)
    _ok(hq, escalation["id"], "acknowledged", headers={})
    [event] = hq.get("/audit?event_type=escalation.status_changed")[1]
    assert (event["actor_id"], event["actor_type"]) == ("public", "system")


def test_operator_acknowledgement_is_attributed(hq):
    escalation = _gov3_escalation(hq)
    _ok(hq, escalation["id"], "acknowledged")
    [event] = hq.get("/audit?event_type=escalation.status_changed")[1]
    assert (event["actor_id"], event["actor_type"]) == ("lupe", "operator")


def test_acknowledge_with_bad_token_is_rejected(hq):
    # A token that is sent must be valid; it is not silently ignored.
    escalation = _gov3_escalation(hq)
    before = _snapshot(hq)
    code, _ = _patch(hq, escalation["id"], {"status": "acknowledged"}, {"Authorization": "Bearer wrong"})
    assert code == 401
    assert _snapshot(hq) == before


@pytest.mark.parametrize("status", ["resolved", "dismissed"])
@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}])
def test_resolve_and_dismiss_require_token(hq, status, headers):
    escalation = _gov3_escalation(hq)
    _ok(hq, escalation["id"], "acknowledged")
    before = _snapshot(hq)
    code, body = _patch(hq, escalation["id"], {"status": status}, headers)
    assert code == 401
    assert _snapshot(hq) == before


def test_resolve_refused_when_token_unset(hq, monkeypatch):
    escalation = _gov3_escalation(hq)
    monkeypatch.delenv(serve.OPERATOR_TOKEN_ENV)
    code, body = _patch(hq, escalation["id"], {"status": "dismissed"}, AUTH)
    assert code == 403
    assert serve.OPERATOR_TOKEN_ENV in body["error"]


def test_resolve_refused_on_non_loopback_bind(hq, monkeypatch):
    escalation = _gov3_escalation(hq)
    monkeypatch.setattr(serve, "_operator_bind_block", serve._bind_block_message("0.0.0.0", False))
    before = _snapshot(hq)
    code, body = _patch(hq, escalation["id"], {"status": "dismissed"}, AUTH)
    assert code == 403
    assert "--allow-insecure-operator" in body["error"]
    assert _snapshot(hq) == before


def test_token_checked_before_escalation_lookup(hq):
    code, _ = _patch(hq, "does-not-exist", {"status": "dismissed"}, {})
    assert code == 401


def test_operator_resolution_audit(hq):
    escalation = _gov3_escalation(hq)
    _ok(hq, escalation["id"], "acknowledged", headers={})
    _ok(hq, escalation["id"], "resolved", resolution="handled")
    events = hq.get("/audit?event_type=escalation.status_changed")[1]
    assert [(e["actor_id"], e["payload"]["from_status"], e["payload"]["status"]) for e in events] == [
        ("public", "pending", "acknowledged"),
        ("lupe", "acknowledged", "resolved"),
    ]
    assert all(e["target_id"] == escalation["id"] for e in events)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("body, code, fragment", [
    ({}, 400, "required"),
    ({"status": ""}, 400, "required"),
    ({"status": ["dismissed"]}, 400, "must be a string"),
    ({"status": "dismissed", "resolution": 5}, 400, "must be a string"),
    ({"status": "pending"}, 422, "Unknown status"),
    ({"status": "closed"}, 422, "Unknown status"),
])
def test_input_validation(hq, body, code, fragment):
    escalation = _gov3_escalation(hq)
    status, response = _patch(hq, escalation["id"], body, AUTH)
    assert status == code
    assert fragment in response["error"]


def test_unknown_escalation_is_404(hq):
    status, body = _patch(hq, "does-not-exist", {"status": "dismissed"}, AUTH)
    assert status == 404


@pytest.mark.parametrize("path", ["/escalations", "/escalations/", "/escalations/a/b", "/intents"])
def test_patch_on_other_paths_is_404(hq, path):
    status, _ = hq.request("PATCH", path, {"status": "dismissed"}, AUTH)
    assert status == 404


def test_cors_preflight_allows_patch(hq):
    import urllib.request
    req = urllib.request.Request(hq.base + "/escalations/x", method="OPTIONS")
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert "PATCH" in resp.headers["Access-Control-Allow-Methods"]


# ---------------------------------------------------------------------------
# Interaction with GOV-3 and the intake flow
# ---------------------------------------------------------------------------

def test_gov3_escalations_can_now_be_closed(hq):
    # Before this endpoint, GOV-3 escalations stayed open until restart.
    escalation = _gov3_escalation(hq)
    assert hq.get("/hq/health")[1]["open_escalation_count"] == 1
    _ok(hq, escalation["id"], "dismissed", resolution="false alarm")
    assert hq.get("/hq/health")[1]["open_escalation_count"] == 0


def test_closing_an_intake_escalation_leaves_the_intake_escalated(hq):
    _, reg = hq.post("/api/register", {"raw": "x"})
    _, esc_body = hq.post(ACTION, {"lifecycle_id": reg["lifecycle"]["id"], "action": "escalate"}, AUTH)
    escalation = esc_body["escalations"][0]
    assert hq.get("/marketplace")[1]["mode"] == "review"

    _ok(hq, escalation["id"], "dismissed")

    # Review lifts, but the intake is still escalated and has no access.
    market = hq.get("/marketplace")[1]
    assert (market["mode"], market["latest_intake_stage"]) == ("observer", "escalated")

    # The operator can still decide the intake; there is nothing left to close.
    latest = hq.get("/intake-agent-v2/lifecycle")[1][-1]
    _, approved = hq.post(ACTION, {"lifecycle_id": latest["id"], "action": "approve"}, AUTH)
    assert approved["current"]["stage"] == "validated"
    assert approved["escalations"] == []
    assert hq.get("/marketplace")[1]["mode"] == "full"


def test_intake_approve_still_closes_acknowledged_escalations(hq):
    _, reg = hq.post("/api/register", {"raw": "x"})
    _, esc_body = hq.post(ACTION, {"lifecycle_id": reg["lifecycle"]["id"], "action": "escalate"}, AUTH)
    escalation = esc_body["escalations"][0]
    _ok(hq, escalation["id"], "acknowledged", headers={})

    latest = hq.get("/intake-agent-v2/lifecycle")[1][-1]
    _, approved = hq.post(ACTION, {"lifecycle_id": latest["id"], "action": "approve"}, AUTH)
    assert [(e["id"], e["status"]) for e in approved["escalations"]] == [(escalation["id"], "resolved")]
