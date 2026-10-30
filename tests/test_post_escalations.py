"""
POST /escalations — creating an EscalationEvent (API_CONTRACT.md v2).

Any caller may create a pending escalation (AGENT_HQ.md's Escalation
Lifecycle) — except on an intake, where it would suspend marketplace access,
so the operator token is required; a token that is sent must be valid and
attributes it to the operator. Only GOV-1, GOV-2, GOV-3 and GOV-5 produce escalations, with the
GOV-n -> severity defaults. The new escalation is audited, holds its intent
in operator-review (ROUTE-6), and then follows the usual lifecycle.
"""

from __future__ import annotations

import pytest

import scripts.serve as serve

TOKEN = "test-operator-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture(autouse=True)
def _operator_token(monkeypatch):
    monkeypatch.setenv(serve.OPERATOR_TOKEN_ENV, TOKEN)


def _intent(hq) -> str:
    status, envelope = hq.post("/intents", {"raw": "hello", "source": "t"})
    assert status == 200
    return envelope["intent_id"]


def _create(hq, body: dict, headers: dict | None = None) -> tuple[int, dict]:
    return hq.post("/escalations", body, headers)


def _snapshot(hq) -> tuple:
    return hq.get("/escalations")[1], hq.get("/audit")[1]


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rule, severity", [
    ("GOV-1", "low"), ("GOV-2", "medium"), ("GOV-3", "high"), ("GOV-5", "critical"),
])
def test_create_with_default_severity(hq, rule, severity):
    intent_id = _intent(hq)
    status, esc = _create(hq, {"trigger_rule": rule, "intent_id": intent_id, "reason": "why"})
    assert status == 201
    assert {k: esc[k] for k in ("type", "trigger_rule", "intent_id", "severity", "reason",
                                "agent_ids", "status", "resolved_at", "resolution")} == {
        "type": "escalation", "trigger_rule": rule, "intent_id": intent_id, "severity": severity,
        "reason": "why", "agent_ids": [], "status": "pending", "resolved_at": None, "resolution": "",
    }
    assert esc["id"] and esc["created_at"]
    assert hq.get(f"/escalations/{esc['id']}") == (200, esc)


def test_explicit_severity_and_agents(hq):
    intent_id = _intent(hq)
    status, esc = _create(hq, {
        "trigger_rule": "GOV-2", "intent_id": intent_id, "severity": "critical",
        "agent_ids": ["containment-agent", "adversarial-intel-agent"],
    })
    assert status == 201
    assert esc["severity"] == "critical"
    assert esc["agent_ids"] == ["containment-agent", "adversarial-intel-agent"]


def _validated_intake(hq) -> str:
    _, reg = hq.post("/api/register", {"raw": "x"})
    code, _ = hq.post("/intake-agent-v2/lifecycle/transition",
                      {"lifecycle_id": reg["lifecycle"]["id"], "to_stage": "validated"}, AUTH)
    assert code == 200
    assert hq.get("/marketplace")[1]["mode"] == "full"
    return reg["lifecycle"]["intent_id"]


def test_operator_can_escalate_an_intake(hq):
    intent_id = _validated_intake(hq)
    status, _ = _create(hq, {"trigger_rule": "GOV-5", "intent_id": intent_id}, AUTH)
    assert status == 201
    market = hq.get("/marketplace")[1]
    assert (market["mode"], market["access"]) == ("review", False)


@pytest.mark.parametrize("headers, code", [({}, 401), ({"Authorization": "Bearer nope"}, 401)])
def test_public_cannot_escalate_an_intake(hq, headers, code):
    # It would suspend marketplace access for every client; only the
    # operator's token may change that.
    intent_id = _validated_intake(hq)
    before = _snapshot(hq), hq.get("/marketplace")[1]
    status, body = _create(hq, {"trigger_rule": "GOV-5", "intent_id": intent_id}, headers)
    assert status == code
    assert "Operator authentication required" in body["error"]
    assert (_snapshot(hq), hq.get("/marketplace")[1]) == before


def test_intake_escalation_refused_when_token_unset(hq, monkeypatch):
    _, reg = hq.post("/api/register", {"raw": "x"})
    monkeypatch.delenv(serve.OPERATOR_TOKEN_ENV)
    status, body = _create(hq, {"trigger_rule": "GOV-5", "intent_id": reg["lifecycle"]["intent_id"]})
    assert status == 403
    assert serve.OPERATOR_TOKEN_ENV in body["error"]


@pytest.mark.parametrize("headers, actor", [({}, ("public", "system")), (AUTH, ("lupe", "operator"))])
def test_creation_is_audited_and_attributed(hq, headers, actor):
    intent_id = _intent(hq)
    _, esc = _create(hq, {"trigger_rule": "GOV-1", "intent_id": intent_id}, headers)
    [event] = hq.get("/audit?event_type=escalation.created")[1]
    assert (event["actor_id"], event["actor_type"]) == actor
    assert (event["target_id"], event["target_type"]) == (esc["id"], "escalation")
    assert event["payload"] == {"trigger_rule": "GOV-1", "severity": "low"}


def test_counts_as_open_escalation(hq):
    _create(hq, {"trigger_rule": "GOV-1", "intent_id": _intent(hq)})
    assert hq.get("/hq/health")[1]["open_escalation_count"] == 1
    assert len(hq.get("/escalations?status=pending")[1]) == 1


# ---------------------------------------------------------------------------
# ROUTE-6 and the lifecycle
# ---------------------------------------------------------------------------

def test_created_escalation_holds_intent_until_closed(hq):
    intent_id = _intent(hq)
    _, esc = _create(hq, {"trigger_rule": "GOV-2", "intent_id": intent_id})
    code, _ = hq.request("PATCH", f"/escalations/{esc['id']}", {"status": "dismissed"}, AUTH)
    assert code == 200
    events = hq.get(f"/audit?event_type=intent.routed&target_id={intent_id}")[1]
    assert [(e["payload"]["held"], e["payload"]["lane"]) for e in events][0] == (True, serve.OPERATOR_REVIEW_LANE)
    assert [e["payload"]["held"] for e in events] == [True, False]
    assert all(e["payload"]["escalation_id"] == esc["id"] for e in events)


def test_public_creator_cannot_close_it(hq):
    _, esc = _create(hq, {"trigger_rule": "GOV-1", "intent_id": _intent(hq)})
    code, _ = hq.request("PATCH", f"/escalations/{esc['id']}", {"status": "dismissed"})
    assert code == 401


# ---------------------------------------------------------------------------
# Validation — every refusal leaves no trace
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("body, code, fragment", [
    ({"intent_id": "X"}, 400, "'trigger_rule' is required"),
    ({"trigger_rule": "GOV-1"}, 400, "'intent_id' is required"),
    ({"trigger_rule": "", "intent_id": "X"}, 400, "'trigger_rule' is required"),
    ({"trigger_rule": 1, "intent_id": "X"}, 400, "must be a string"),
    ({"trigger_rule": "GOV-1", "intent_id": "X", "reason": 5}, 400, "must be a string"),
    ({"trigger_rule": "GOV-1", "intent_id": "X", "agent_ids": "containment-agent"}, 400, "list of strings"),
    ({"trigger_rule": "GOV-1", "intent_id": "X", "agent_ids": [1]}, 400, "list of strings"),
    ({"trigger_rule": "GOV-1", "intent_id": "X", "status": "resolved"}, 400, "Server-assigned"),
    ({"trigger_rule": "GOV-1", "intent_id": "X", "id": "mine"}, 400, "Server-assigned"),
    ({"trigger_rule": "GOV-4", "intent_id": "X"}, 422, "does not produce escalations"),
    ({"trigger_rule": "GOV-7", "intent_id": "X"}, 422, "does not produce escalations"),
    ({"trigger_rule": "operator-manual", "intent_id": "X"}, 422, "does not produce escalations"),
    ({"trigger_rule": "GOV-1", "intent_id": "X", "severity": "urgent"}, 422, "Unknown severity"),
    ({"trigger_rule": "GOV-1", "intent_id": "never-seen"}, 422, "Unknown intent"),
    ({"trigger_rule": "GOV-1", "intent_id": "X", "agent_ids": ["ContainmentAgent"]}, 422, "Unknown agent"),
])
def test_invalid_bodies_rejected_without_side_effects(hq, body, code, fragment):
    intent_id = _intent(hq)
    body = {k: (intent_id if v == "X" else v) for k, v in body.items()}
    before = _snapshot(hq)
    status, response = _create(hq, body)
    assert status == code, response
    assert fragment in response["error"]
    assert _snapshot(hq) == before


def test_bad_token_rejected_without_side_effects(hq):
    intent_id = _intent(hq)
    before = _snapshot(hq)
    status, _ = _create(hq, {"trigger_rule": "GOV-1", "intent_id": intent_id}, {"Authorization": "Bearer nope"})
    assert status == 401
    assert _snapshot(hq) == before


def test_bad_token_refused_when_token_unset(hq, monkeypatch):
    intent_id = _intent(hq)
    monkeypatch.delenv(serve.OPERATOR_TOKEN_ENV)
    status, _ = _create(hq, {"trigger_rule": "GOV-1", "intent_id": intent_id}, AUTH)
    assert status == 403
    # Without a token, creation stays open to anyone.
    status, _ = _create(hq, {"trigger_rule": "GOV-1", "intent_id": intent_id})
    assert status == 201


# ---------------------------------------------------------------------------
# Existing creators are unchanged by the shared helper
# ---------------------------------------------------------------------------

def test_gov3_auto_escalation_unchanged(hq):
    hq.post("/intents", {"raw": "urgent", "source": "t", "tags": ["critical"]})
    [esc] = hq.get("/escalations")[1]
    assert (esc["trigger_rule"], esc["severity"], esc["agent_ids"]) == (
        "GOV-3", "critical", ["adversarial-intel-agent", "containment-agent"])
    [event] = hq.get("/audit?event_type=escalation.created")[1]
    assert (event["actor_id"], event["payload"]) == ("ghost-layer-core", {"trigger_rule": "GOV-3", "severity": "critical"})


def test_intake_escalate_unchanged(hq):
    _, reg = hq.post("/api/register", {"raw": "x"})
    _, body = hq.post("/intake-agent-v2/lifecycle/action",
                      {"lifecycle_id": reg["lifecycle"]["id"], "action": "escalate", "notes": "look"}, AUTH)
    [esc] = body["escalations"]
    assert (esc["trigger_rule"], esc["reason"], esc["agent_ids"]) == ("operator-manual", "look", ["intake-agent-v2"])
    assert esc["created_at"] == body["current"]["created_at"]
    [event] = hq.get("/audit?event_type=escalation.created")[1]
    assert event["payload"] == {"trigger_rule": "operator-manual", "severity": esc["severity"],
                                "intake_record_id": body["current"]["id"]}
