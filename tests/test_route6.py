"""
ROUTE-6 — operator-review lane holds (AGENT_HQ.md "Routing integration").

An intent with a pending or acknowledged escalation is routed to the reserved
operator-review lane, overriding any other lane, until every such escalation
is resolved or dismissed. scripts/serve.py records this as intent.routed
audit events; nothing is dispatched. The lane an intent returns to is the one
recorded at POST /intents (ROUTE-1 for the operator, else the agent's
suggested_lane) or, for an intake, its operator-assigned lane.
"""

from __future__ import annotations

import uuid

import pytest

import scripts.serve as serve

TOKEN = "test-operator-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
ACTION = "/intake-agent-v2/lifecycle/action"
REVIEW = serve.OPERATOR_REVIEW_LANE


@pytest.fixture(autouse=True)
def _operator_token(monkeypatch):
    monkeypatch.setenv(serve.OPERATOR_TOKEN_ENV, TOKEN)


def _routes(hq, intent_id: str) -> list:
    """(held, from_lane, lane) for each intent.routed event on the intent."""
    events = hq.get(f"/audit?event_type=intent.routed&target_id={intent_id}")[1]
    assert all(e["payload"]["rule"] == "ROUTE-6" for e in events)
    assert all((e["actor_id"], e["actor_type"]) == ("ghost-layer-core", "system") for e in events)
    return [(e["payload"]["held"], e["payload"]["from_lane"], e["payload"]["lane"]) for e in events]


def _submitted_lane(hq, intent_id: str) -> str:
    [event] = hq.get(f"/audit?event_type=intent.submitted&target_id={intent_id}")[1]
    return event["payload"]["lane"]


def _suggested(envelope: dict) -> str:
    [lane] = [a["result"]["suggested_lane"] for a in envelope["payload"]["agents"]
              if a["agent"] == "RouteAdvisoryAgent"]
    return lane


def _patch(hq, escalation_id: str, status: str, headers=AUTH) -> None:
    code, body = hq.request("PATCH", f"/escalations/{escalation_id}", {"status": status}, headers)
    assert code == 200, body


def _critical_intent(hq, headers=None) -> tuple[dict, dict]:
    status, envelope = hq.post("/intents", {"raw": "urgent", "source": "t", "tags": ["critical"]}, headers)
    assert status == 200
    [escalation] = hq.get("/escalations")[1]
    assert escalation["intent_id"] == envelope["intent_id"]
    return envelope, escalation


def _escalated_intake(hq) -> tuple[str, dict]:
    _, reg = hq.post("/api/register", {"raw": "x"})
    _, body = hq.post(ACTION, {"lifecycle_id": reg["lifecycle"]["id"], "action": "escalate"}, AUTH)
    return reg["lifecycle"]["intent_id"], body["escalations"][0]


def _intake_action(hq, intent_id: str, action: str, **extra) -> dict:
    latest = [r for r in hq.get("/intake-agent-v2/lifecycle")[1] if r["intent_id"] == intent_id][-1]
    code, body = hq.post(ACTION, {"lifecycle_id": latest["id"], "action": action, **extra}, AUTH)
    assert code == 200, body
    return body


# ---------------------------------------------------------------------------
# Lane recorded at submission (what ROUTE-6 overrides and releases back to)
# ---------------------------------------------------------------------------

def test_public_intent_records_agent_suggested_lane(hq):
    _, envelope = hq.post("/intents", {"raw": "hello", "source": "t"})
    lane = _suggested(envelope)
    assert lane
    assert _submitted_lane(hq, envelope["intent_id"]) == lane


def test_operator_intent_records_operator_priority_lane(hq):
    # ROUTE-1: the operator's priority lane overrides the agent's suggestion.
    _, envelope = hq.post("/intents", {"raw": "hello", "source": "t"}, AUTH)
    assert _submitted_lane(hq, envelope["intent_id"]) == "operator"


def test_intent_without_escalation_is_never_routed_to_review(hq):
    _, envelope = hq.post("/intents", {"raw": "hello", "source": "t"})
    assert _routes(hq, envelope["intent_id"]) == []


# ---------------------------------------------------------------------------
# GOV-3 escalations from POST /intents
# ---------------------------------------------------------------------------

def test_gov3_escalation_holds_intent_in_operator_review(hq):
    envelope, escalation = _critical_intent(hq)
    assert _routes(hq, envelope["intent_id"]) == [(True, _suggested(envelope), REVIEW)]
    [event] = hq.get(f"/audit?event_type=intent.routed&target_id={envelope['intent_id']}")[1]
    assert event["payload"]["escalation_id"] == escalation["id"]


def test_hold_is_recorded_after_submission_and_escalation(hq):
    envelope, _ = _critical_intent(hq)
    events = hq.get(f"/audit?target_id={envelope['intent_id']}")[1]
    assert [e["event_type"] for e in events] == ["intent.submitted", "intent.routed"]
    created = hq.get("/audit?event_type=escalation.created")[1]
    assert created[0]["timestamp"] <= events[1]["timestamp"]


def test_operator_intent_hold_overrides_operator_lane(hq):
    envelope, escalation = _critical_intent(hq, AUTH)
    _patch(hq, escalation["id"], "dismissed")
    assert _routes(hq, envelope["intent_id"]) == [
        (True, "operator", REVIEW),
        (False, REVIEW, "operator"),
    ]


def test_acknowledging_keeps_the_hold(hq):
    envelope, escalation = _critical_intent(hq)
    _patch(hq, escalation["id"], "acknowledged", headers={})
    assert _routes(hq, envelope["intent_id"]) == [(True, _suggested(envelope), REVIEW)]


@pytest.mark.parametrize("path", [["acknowledged", "resolved"], ["acknowledged", "dismissed"], ["dismissed"]])
def test_closing_the_escalation_releases_the_intent(hq, path):
    envelope, escalation = _critical_intent(hq)
    for status in path:
        _patch(hq, escalation["id"], status)
    lane = _suggested(envelope)
    assert _routes(hq, envelope["intent_id"]) == [(True, lane, REVIEW), (False, REVIEW, lane)]


@pytest.mark.parametrize("status, headers, code", [
    ("resolved", AUTH, 422),                        # pending -> resolved is not allowed
    ("dismissed", {}, 401),                         # operator only
    ("dismissed", {"Authorization": "Bearer x"}, 401),
])
def test_refused_transition_does_not_release(hq, status, headers, code):
    envelope, escalation = _critical_intent(hq)
    got, _ = hq.request("PATCH", f"/escalations/{escalation['id']}", {"status": status}, headers)
    assert got == code
    assert _routes(hq, envelope["intent_id"]) == [(True, _suggested(envelope), REVIEW)]


# ---------------------------------------------------------------------------
# Several open escalations on one intent
# ---------------------------------------------------------------------------

def test_hold_lasts_until_every_escalation_is_closed(hq):
    envelope, first = _critical_intent(hq)
    second = dict(first, id=str(uuid.uuid4()))
    with serve._lock:
        serve._escalations.append(second)

    _patch(hq, first["id"], "dismissed")
    assert len(_routes(hq, envelope["intent_id"])) == 1    # still held

    _patch(hq, second["id"], "dismissed")
    lane = _suggested(envelope)
    assert _routes(hq, envelope["intent_id"]) == [(True, lane, REVIEW), (False, REVIEW, lane)]
    [_, release] = hq.get(f"/audit?event_type=intent.routed&target_id={envelope['intent_id']}")[1]
    assert release["payload"]["escalation_id"] == second["id"]


# ---------------------------------------------------------------------------
# Intake escalations (operator escalate / approve / close / reassign)
# ---------------------------------------------------------------------------

def test_intake_escalate_holds_and_approve_releases(hq):
    intent_id, _ = _escalated_intake(hq)
    assert _routes(hq, intent_id) == [(True, "", REVIEW)]
    _intake_action(hq, intent_id, "approve")
    assert _routes(hq, intent_id) == [(True, "", REVIEW), (False, REVIEW, "")]


def test_intake_close_releases(hq):
    intent_id, _ = _escalated_intake(hq)
    _intake_action(hq, intent_id, "close")
    assert _routes(hq, intent_id)[-1] == (False, REVIEW, "")


def test_reassign_while_held_takes_effect_on_release(hq):
    # ROUTE-6 overrides the operator-assigned lane until the escalation closes.
    intent_id, _ = _escalated_intake(hq)
    _intake_action(hq, intent_id, "reassign", lane="tier-2")
    assert _routes(hq, intent_id) == [(True, "", REVIEW)]
    _intake_action(hq, intent_id, "approve")
    assert _routes(hq, intent_id) == [(True, "", REVIEW), (False, REVIEW, "tier-2")]


def test_intake_escalation_closed_by_patch_releases(hq):
    intent_id, escalation = _escalated_intake(hq)
    _patch(hq, escalation["id"], "dismissed")
    assert _routes(hq, intent_id) == [(True, "", REVIEW), (False, REVIEW, "")]


def test_reescalating_holds_again(hq):
    intent_id, escalation = _escalated_intake(hq)
    _patch(hq, escalation["id"], "dismissed")
    _intake_action(hq, intent_id, "approve")      # back to validated
    _intake_action(hq, intent_id, "escalate")
    assert [held for held, _, _ in _routes(hq, intent_id)] == [True, False, True]
