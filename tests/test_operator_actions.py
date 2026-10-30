"""
Operator actions on the intake lifecycle — POST /intake-agent-v2/lifecycle/action.

Covers: shared-token auth (fail closed), the action/stage table, append-only
records, escalation linkage (open / resolve / dismiss), stale-record and
re-registration guards that would otherwise bypass an escalation, and audit.
"""

from __future__ import annotations

import pytest

import scripts.serve as serve

ACTION = "/intake-agent-v2/lifecycle/action"
TRANSITION = "/intake-agent-v2/lifecycle/transition"
TOKEN = "test-operator-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture(autouse=True)
def _operator_token(monkeypatch):
    monkeypatch.setenv(serve.OPERATOR_TOKEN_ENV, TOKEN)


def _register(hq, **extra) -> dict:
    status, body = hq.post("/api/register", {"raw": "request access", "source": "test", **extra})
    assert status == 201, body
    return body["lifecycle"]


def _act(hq, lifecycle_id: str, action: str, headers=AUTH, **extra) -> tuple[int, dict]:
    return hq.post(ACTION, {"lifecycle_id": lifecycle_id, "action": action, **extra}, headers)


def _ok(hq, lifecycle_id: str, action: str, **extra) -> dict:
    status, body = _act(hq, lifecycle_id, action, **extra)
    assert status == 200, body
    return body


def _record_at(hq, stage: str) -> dict:
    """Register an intake and drive it to `stage`; return the latest record."""
    record = _register(hq)
    path = {
        "received": [],
        "validated": [("transition", "validated")],
        "queued": [("transition", "validated"), ("transition", "queued")],
        "processed": [("transition", "validated"), ("transition", "queued"),
                      ("transition", "processed")],
        "escalated": [("action", "escalate")],
    }[stage]
    for kind, step in path:
        if kind == "transition":
            status, body = hq.post(TRANSITION, {"lifecycle_id": record["id"], "to_stage": step})
            assert status == 200, body
            record = body["current"]
        else:
            record = _ok(hq, record["id"], step)["current"]
    return record


def _snapshot(hq) -> tuple:
    return (hq.get("/intake-agent-v2/lifecycle")[1], hq.get("/audit")[1],
            hq.get("/escalations")[1])


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def test_disabled_when_token_unset(hq, monkeypatch):
    record = _register(hq)
    monkeypatch.delenv(serve.OPERATOR_TOKEN_ENV)
    before = _snapshot(hq)
    status, body = _act(hq, record["id"], "approve")
    assert status == 403
    assert serve.OPERATOR_TOKEN_ENV in body["error"]
    assert _snapshot(hq) == before


@pytest.mark.parametrize("headers", [
    {},
    {"Authorization": "Bearer wrong-token"},
    {"Authorization": TOKEN},                 # missing scheme
    {"Authorization": f"Basic {TOKEN}"},
])
def test_rejects_missing_or_wrong_token_without_side_effects(hq, headers):
    record = _register(hq)
    before = _snapshot(hq)
    status, body = _act(hq, record["id"], "approve", headers=headers)
    assert status == 401
    assert "Bearer" in body["error"]
    assert _snapshot(hq) == before


def test_auth_checked_before_input_validation(hq):
    status, _ = hq.post(ACTION, {}, {"Authorization": "Bearer wrong"})
    assert status == 401


# ---------------------------------------------------------------------------
# Action / stage table
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("stage, action, to_stage", [
    ("received", "approve", "validated"),
    ("escalated", "approve", "validated"),
    ("received", "escalate", "escalated"),
    ("validated", "escalate", "escalated"),
    ("queued", "escalate", "escalated"),
    ("received", "close", "processed"),
    ("validated", "close", "processed"),
    ("queued", "close", "processed"),
    ("escalated", "close", "processed"),
    ("escalated", "reassign", "escalated"),
    ("received", "annotate", "received"),
    ("escalated", "annotate", "escalated"),
    ("processed", "annotate", "processed"),
])
def test_allowed_actions(hq, stage, action, to_stage):
    record = _record_at(hq, stage)
    body = _ok(hq, record["id"], action, notes="operator note", lane="containment-review")

    current = body["current"]
    assert body["previous"] == record
    assert current["id"] != record["id"]
    assert current["intent_id"] == record["intent_id"]
    assert current["stage"] == to_stage
    assert current["operator_action"] == action
    assert current["operator_notes"] == "operator note"
    if to_stage == "processed":
        assert current["resolved_at"]


@pytest.mark.parametrize("stage, action", [
    ("validated", "approve"),
    ("queued", "approve"),
    ("processed", "approve"),
    ("escalated", "escalate"),
    ("processed", "escalate"),
    ("processed", "close"),
    ("received", "reassign"),
    ("queued", "reassign"),
])
def test_disallowed_actions_rejected_without_side_effects(hq, stage, action):
    record = _record_at(hq, stage)
    before = _snapshot(hq)
    status, body = _act(hq, record["id"], action, notes="n", lane="x")
    assert status == 422
    assert "not allowed" in body["error"]
    assert _snapshot(hq) == before


@pytest.mark.parametrize("payload, code, fragment", [
    ({}, 400, "required"),
    ({"lifecycle_id": "x"}, 400, "required"),
    ({"lifecycle_id": "x", "action": "delete"}, 422, "Unknown action"),
    ({"lifecycle_id": "x", "action": "annotate"}, 400, "notes"),
    ({"lifecycle_id": "x", "action": "annotate", "notes": "  "}, 400, "notes"),
    ({"lifecycle_id": "x", "action": "reassign"}, 400, "lane"),
    ({"lifecycle_id": "x", "action": "escalate", "severity": "urgent"}, 400, "severity"),
    ({"lifecycle_id": "does-not-exist", "action": "approve"}, 404, "No lifecycle record"),
])
def test_input_validation(hq, payload, code, fragment):
    status, body = hq.post(ACTION, payload, AUTH)
    assert status == code
    assert fragment in body["error"]


# ---------------------------------------------------------------------------
# Escalation linkage
# ---------------------------------------------------------------------------

def test_escalate_opens_escalation_and_review_mode(hq):
    record = _register(hq)
    body = _ok(hq, record["id"], "escalate", notes="suspicious request", severity="critical")

    [esc] = body["escalations"]
    assert esc["trigger_rule"] == "operator-manual"
    assert esc["intent_id"] == record["intent_id"]
    assert esc["severity"] == "critical"
    assert esc["reason"] == "suspicious request"
    assert esc["status"] == "pending"
    assert body["marketplace"]["mode"] == "review"

    assert hq.get("/escalations?status=pending")[1] == [esc]
    assert hq.get("/marketplace")[1]["mode"] == "review"
    assert hq.get("/hq/health")[1]["open_escalation_count"] == 1
    assert hq.get("/hq/health")[1]["intake_escalated_count"] == 1


def test_escalate_defaults_to_high_severity(hq):
    body = _ok(hq, _register(hq)["id"], "escalate")
    assert body["escalations"][0]["severity"] == "high"


@pytest.mark.parametrize("action, status, mode", [
    ("approve", "resolved", "full"),
    ("close", "dismissed", "observer"),
])
def test_leaving_escalated_closes_open_escalation(hq, action, status, mode):
    escalated = _record_at(hq, "escalated")
    body = _ok(hq, escalated["id"], action, notes="reviewed")

    [esc] = body["escalations"]
    assert esc["status"] == status
    assert esc["resolved_at"]
    assert esc["resolution"] == f"{action}: reviewed"
    assert body["marketplace"]["mode"] == mode
    assert hq.get("/hq/health")[1]["open_escalation_count"] == 0


@pytest.mark.parametrize("action", ["reassign", "annotate"])
def test_staying_escalated_keeps_escalation_open(hq, action):
    escalated = _record_at(hq, "escalated")
    body = _ok(hq, escalated["id"], action, notes="looking", lane="adversarial-intel")
    assert body["escalations"] == []
    assert hq.get("/hq/health")[1]["open_escalation_count"] == 1


def test_reassign_sets_lane_and_later_records_carry_it(hq):
    escalated = _record_at(hq, "escalated")
    reassigned = _ok(hq, escalated["id"], "reassign", lane="adversarial-intel")["current"]
    assert reassigned["assigned_lane"] == "adversarial-intel"
    approved = _ok(hq, reassigned["id"], "approve")["current"]
    assert approved["assigned_lane"] == "adversarial-intel"
    queued = hq.post(TRANSITION, {"lifecycle_id": approved["id"], "to_stage": "queued"})[1]["current"]
    assert queued["assigned_lane"] == "adversarial-intel"


def test_escalation_only_affects_its_own_intent(hq):
    a = _record_at(hq, "escalated")
    b = _record_at(hq, "escalated")
    _ok(hq, a["id"], "approve")
    statuses = {e["intent_id"]: e["status"] for e in hq.get("/escalations")[1]}
    assert statuses == {a["intent_id"]: "resolved", b["intent_id"]: "pending"}


# ---------------------------------------------------------------------------
# Escalation bypass guards
# ---------------------------------------------------------------------------

def test_stale_record_cannot_bypass_escalation_via_transition(hq):
    original = _register(hq)
    _ok(hq, original["id"], "escalate")
    before = _snapshot(hq)

    status, body = hq.post(TRANSITION, {"lifecycle_id": original["id"], "to_stage": "validated"})

    assert status == 409
    assert "Stale" in body["error"]
    assert _snapshot(hq) == before
    assert hq.get("/marketplace")[1]["mode"] == "review"


def test_stale_record_rejected_for_actions(hq):
    original = _register(hq)
    _ok(hq, original["id"], "annotate", notes="first look")
    status, body = _act(hq, original["id"], "approve")
    assert status == 409
    assert "Stale" in body["error"]


def test_reregistering_intent_is_rejected(hq):
    record = _register(hq, intent_id="intent-123")
    _ok(hq, record["id"], "escalate")
    before = _snapshot(hq)

    status, body = hq.post("/api/register", {"raw": "again", "intent_id": "intent-123"})

    assert status == 409
    assert "already registered" in body["error"]
    assert _snapshot(hq) == before


def test_escalated_cannot_leave_via_public_transition(hq):
    escalated = _record_at(hq, "escalated")
    for to_stage in ("validated", "queued", "processed"):
        status, _ = hq.post(TRANSITION, {"lifecycle_id": escalated["id"], "to_stage": to_stage})
        assert status == 422


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

def test_stage_changing_action_audit_trail(hq):
    record = _register(hq)
    current = _ok(hq, record["id"], "approve", notes="looks fine")["current"]

    [action_event] = hq.get("/audit?event_type=intake.operator_action")[1]
    assert action_event["actor_id"] == "lupe"
    assert action_event["actor_type"] == "operator"
    assert action_event["target_id"] == current["id"]
    assert action_event["payload"] == {
        "intent_id": record["intent_id"], "action": "approve",
        "from_stage": "received", "stage": "validated",
        "previous_record_id": record["id"], "escalation_ids": [],
    }

    stage_events = hq.get("/audit?event_type=intake.stage_changed")[1]
    assert [e["payload"]["stage"] for e in stage_events] == ["received", "validated"]
    assert stage_events[-1]["actor_type"] == "operator"


def test_annotate_writes_no_stage_change(hq):
    record = _register(hq)
    _ok(hq, record["id"], "annotate", notes="note")
    stage_events = hq.get("/audit?event_type=intake.stage_changed")[1]
    assert [e["payload"]["stage"] for e in stage_events] == ["received"]


def test_escalation_lifecycle_audit(hq):
    record = _register(hq)
    esc_id = _ok(hq, record["id"], "escalate")["escalations"][0]["id"]
    escalated = hq.get("/intake-agent-v2/lifecycle")[1][-1]
    _ok(hq, escalated["id"], "close")

    created = hq.get("/audit?event_type=escalation.created")[1]
    changed = hq.get("/audit?event_type=escalation.status_changed")[1]
    assert [e["target_id"] for e in created] == [esc_id]
    assert [(e["target_id"], e["payload"]["from_status"], e["payload"]["status"])
            for e in changed] == [(esc_id, "pending", "dismissed")]
    actions = hq.get("/audit?event_type=intake.operator_action")[1]
    assert [a["payload"]["escalation_ids"] for a in actions] == [[esc_id], [esc_id]]


@pytest.mark.parametrize("tags, volatility", [(["high-risk"], 0.9), ([], 0.1)])
def test_agent_advertises_exactly_the_endpoints_allowed_actions(tags, volatility):
    from agents.constellation import IntakeAgentV2
    from core.substrate import SubstrateState
    from core.types import IntentVector

    out = IntakeAgentV2().run(
        IntentVector(id="t", source="test", description="d", tags=tags),
        SubstrateState(spectral_density=0.5, volatility=volatility),
    )
    allowed = {a for a, table in serve._OPERATOR_ACTIONS.items() if out["lifecycle_stage"] in table}
    assert set(out["operator_actions_available"]) == allowed


def test_action_records_are_append_only(hq):
    record = _register(hq)
    escalated = _ok(hq, record["id"], "escalate")["current"]
    approved = _ok(hq, escalated["id"], "approve")["current"]

    lifecycle = hq.get("/intake-agent-v2/lifecycle")[1]
    assert [r["id"] for r in lifecycle] == [record["id"], escalated["id"], approved["id"]]
    assert lifecycle[0] == record
    assert lifecycle[1] == escalated
