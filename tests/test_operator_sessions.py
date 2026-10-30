"""
Operator sessions — GET/POST /operator/sessions, GET/PATCH /operator/sessions/:id.

An open OperatorSessionRecord is the only signal of operator presence (GOV-7).
Covers: token-gated open/close, one open session at a time, audit events,
GOV-7 posture on POST /intents while a session is open, operator attribution
only with the token, and the retired X-Ghost-Operator-Online header.
"""

from __future__ import annotations

import urllib.request

import pytest

import scripts.serve as serve

TOKEN = "test-operator-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
SESSIONS = "/operator/sessions"


@pytest.fixture(autouse=True)
def _operator_token(monkeypatch):
    monkeypatch.setenv(serve.OPERATOR_TOKEN_ENV, TOKEN)


def _open(hq, **body) -> dict:
    status, session = hq.post(SESSIONS, body, AUTH)
    assert status == 201, session
    return session


def _close(hq, session_id: str, headers=AUTH, **body) -> tuple[int, dict]:
    return hq.request("PATCH", f"{SESSIONS}/{session_id}", body, headers)


def _intent(hq, headers=None, **extra) -> dict:
    status, envelope = hq.post("/intents", {"raw": "hello", "source": "src", **extra}, headers)
    assert status == 200, envelope
    return envelope


def _snapshot(hq) -> tuple:
    return hq.get(SESSIONS)[1], hq.get("/audit")[1]


# ---------------------------------------------------------------------------
# Open / close
# ---------------------------------------------------------------------------

def test_open_session(hq):
    session = _open(hq, notes="Starting review")
    assert session["operator_id"] == "lupe"
    assert session["ended_at"] is None
    assert session["notes"] == "Starting review"
    assert session["active_intent_ids"] == []
    assert hq.get("/hq/health")[1]["operator_online"] is True

    [event] = hq.get("/audit?event_type=operator.session_opened")[1]
    assert (event["actor_id"], event["actor_type"], event["target_id"]) == (
        "lupe", "operator", session["session_id"])


def test_open_with_explicit_registered_operator_id(hq):
    assert _open(hq, operator_id="lupe")["operator_id"] == "lupe"


def test_open_with_other_operator_id_is_rejected(hq):
    before = _snapshot(hq)
    status, body = hq.post(SESSIONS, {"operator_id": "mallory"}, AUTH)
    assert status == 422
    assert "registered operator" in body["error"]
    assert _snapshot(hq) == before


def test_only_one_session_open_at_a_time(hq):
    first = _open(hq)
    before = _snapshot(hq)
    status, body = hq.post(SESSIONS, {}, AUTH)
    assert status == 409
    assert first["session_id"] in body["error"]
    assert _snapshot(hq) == before


def test_close_session(hq):
    session = _open(hq, notes="Starting review")
    status, closed = _close(hq, session["session_id"], notes="Review complete")
    assert status == 200, closed
    assert closed["ended_at"]
    assert closed["notes"] == "Starting review\nReview complete"
    assert hq.get("/hq/health")[1]["operator_online"] is False

    [event] = hq.get("/audit?event_type=operator.session_closed")[1]
    assert (event["actor_id"], event["actor_type"], event["target_id"]) == (
        "lupe", "operator", session["session_id"])


def test_close_without_notes_keeps_notes(hq):
    session = _open(hq, notes="Starting review")
    status, closed = _close(hq, session["session_id"])
    assert status == 200
    assert closed["notes"] == "Starting review"


def test_reopen_after_close(hq):
    first = _open(hq)
    _close(hq, first["session_id"])
    second = _open(hq)
    assert second["session_id"] != first["session_id"]
    assert [s["ended_at"] is None for s in hq.get(SESSIONS)[1]] == [False, True]


def test_close_twice_is_409(hq):
    session = _open(hq)
    _close(hq, session["session_id"])
    before = _snapshot(hq)
    status, body = _close(hq, session["session_id"])
    assert status == 409
    assert "already closed" in body["error"]
    assert _snapshot(hq) == before


def test_close_unknown_session_is_404(hq):
    status, _ = _close(hq, "does-not-exist")
    assert status == 404


# ---------------------------------------------------------------------------
# Only the operator opens and closes sessions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}])
def test_open_requires_token(hq, headers):
    before = _snapshot(hq)
    status, _ = hq.post(SESSIONS, {}, headers)
    assert status == 401
    assert _snapshot(hq) == before
    assert hq.get("/hq/health")[1]["operator_online"] is False


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}])
def test_close_requires_token(hq, headers):
    session = _open(hq)
    before = _snapshot(hq)
    status, _ = _close(hq, session["session_id"], headers=headers)
    assert status == 401
    assert _snapshot(hq) == before
    assert hq.get("/hq/health")[1]["operator_online"] is True


def test_open_refused_when_token_unset(hq, monkeypatch):
    monkeypatch.delenv(serve.OPERATOR_TOKEN_ENV)
    status, body = hq.post(SESSIONS, {}, AUTH)
    assert status == 403
    assert serve.OPERATOR_TOKEN_ENV in body["error"]


def test_open_refused_on_non_loopback_bind(hq, monkeypatch):
    monkeypatch.setattr(serve, "_operator_bind_block", serve._bind_block_message("0.0.0.0", False))
    status, body = hq.post(SESSIONS, {}, AUTH)
    assert status == 403
    assert "--allow-insecure-operator" in body["error"]


def test_close_token_checked_before_lookup(hq):
    status, _ = _close(hq, "does-not-exist", headers={})
    assert status == 401


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def test_list_and_filter_sessions(hq):
    first = _open(hq)
    _close(hq, first["session_id"])
    second = _open(hq)

    assert [s["session_id"] for s in hq.get(SESSIONS)[1]] == [first["session_id"], second["session_id"]]
    assert [s["session_id"] for s in hq.get(f"{SESSIONS}?active=true")[1]] == [second["session_id"]]
    assert [s["session_id"] for s in hq.get(f"{SESSIONS}?active=false")[1]] == [first["session_id"]]
    assert len(hq.get(f"{SESSIONS}?operator_id=lupe")[1]) == 2
    assert hq.get(f"{SESSIONS}?operator_id=someone-else")[1] == []


def test_list_rejects_bad_active_filter(hq):
    status, body = hq.get(f"{SESSIONS}?active=yes")
    assert status == 400


def test_get_session_by_id(hq):
    session = _open(hq)
    status, body = hq.get(f"{SESSIONS}/{session['session_id']}")
    assert status == 200
    assert body == session
    assert hq.get(f"{SESSIONS}/does-not-exist")[0] == 404


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("body", [{"notes": 5}, {"operator_id": ["lupe"]}])
def test_open_rejects_non_string_fields(hq, body):
    status, response = hq.post(SESSIONS, body, AUTH)
    assert status == 400
    assert "must be a string" in response["error"]


def test_close_rejects_non_string_notes(hq):
    session = _open(hq)
    status, response = _close(hq, session["session_id"], notes=["x"])
    assert status == 400
    assert hq.get(f"{SESSIONS}/{session['session_id']}")[1]["ended_at"] is None


@pytest.mark.parametrize("method, path", [("PATCH", SESSIONS), ("PATCH", f"{SESSIONS}/a/b")])
def test_unknown_session_routes_are_404(hq, method, path):
    status, _ = hq.request(method, path, {}, AUTH)
    assert status == 404


# ---------------------------------------------------------------------------
# GOV-7: presence comes only from an open session
# ---------------------------------------------------------------------------

def test_no_session_no_gov7(hq):
    envelope = _intent(hq)
    assert hq.get("/audit?event_type=gov_rule.fired")[1] == []
    [submitted] = hq.get("/audit?event_type=intent.submitted")[1]
    assert submitted["payload"]["gov7_active"] is False
    assert submitted["target_id"] == envelope["intent_id"]


def test_open_session_applies_gov7_to_every_intent(hq):
    session = _open(hq)
    anonymous = _intent(hq)
    operator = _intent(hq, headers=AUTH)

    fired = hq.get("/audit?event_type=gov_rule.fired")[1]
    assert [(e["target_id"], e["actor_type"], e["payload"]["session_id"]) for e in fired] == [
        (anonymous["intent_id"], "system", session["session_id"]),
        (operator["intent_id"], "system", session["session_id"]),
    ]
    stored = hq.get(f"{SESSIONS}/{session['session_id']}")[1]
    assert stored["active_intent_ids"] == [anonymous["intent_id"], operator["intent_id"]]


def test_gov7_stops_when_session_closes(hq):
    session = _open(hq)
    _close(hq, session["session_id"])
    _intent(hq)
    assert hq.get("/audit?event_type=gov_rule.fired")[1] == []


def test_intent_attributed_to_operator_only_with_token(hq):
    _open(hq)
    _intent(hq)
    _intent(hq, headers=AUTH)
    submitted = hq.get("/audit?event_type=intent.submitted")[1]
    assert [(e["actor_id"], e["actor_type"]) for e in submitted] == [
        ("src", "system"),
        ("lupe", "operator"),
    ]


def test_intent_with_bad_token_is_rejected(hq):
    before = _snapshot(hq)
    status, _ = hq.post("/intents", {"raw": "x", "source": "src"}, {"Authorization": "Bearer wrong"})
    assert status == 401
    assert _snapshot(hq) == before


# ---------------------------------------------------------------------------
# The X-Ghost-Operator-Online header is retired
# ---------------------------------------------------------------------------

def test_presence_header_no_longer_opens_a_session(hq):
    _intent(hq, headers={"X-Ghost-Operator-Online": "true"})
    assert hq.get(SESSIONS)[1] == []
    assert hq.get("/hq/health")[1]["operator_online"] is False
    assert hq.get("/audit?event_type=gov_rule.fired")[1] == []
    [submitted] = hq.get("/audit?event_type=intent.submitted")[1]
    assert submitted["actor_type"] == "system"


def test_cors_preflight(hq):
    req = urllib.request.Request(hq.base + SESSIONS, method="OPTIONS")
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert "PATCH" in resp.headers["Access-Control-Allow-Methods"]
        assert "X-Ghost-Operator-Online" not in resp.headers["Access-Control-Allow-Headers"]
