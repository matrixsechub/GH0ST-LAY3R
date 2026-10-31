"""
Read-only endpoints — GET /audit/:id, /agents/:id, /operators/:id,
/agent-pools/:id, the full GET /audit filter set (API_CONTRACT.md v2), and
rejection of repeated query parameters on every GET route.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import pytest

import scripts.serve as serve

TOKEN = "test-operator-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture(autouse=True)
def _operator_token(monkeypatch):
    monkeypatch.setenv(serve.OPERATOR_TOKEN_ENV, TOKEN)


def _events(hq, query: str = "") -> list:
    status, body = hq.get("/audit" + query)
    assert status == 200, body
    return body


def _populate_audit(hq) -> None:
    """A mix of events: public and operator intents, a GOV-3 escalation, a session."""
    hq.post("/intents", {"raw": "hello", "source": "web"})
    hq.post("/intents", {"raw": "urgent", "source": "web", "tags": ["critical"]}, AUTH)
    hq.post("/operator/sessions", {"operator_id": "lupe"}, AUTH)


# ---------------------------------------------------------------------------
# By-id lookups
# ---------------------------------------------------------------------------

def test_get_audit_event_by_id(hq):
    _populate_audit(hq)
    for event in _events(hq):
        assert hq.get(f"/audit/{event['id']}") == (200, event)


@pytest.mark.parametrize("collection, key", [("agents", "id"), ("operators", "operator_id")])
def test_get_registry_record_by_id(hq, collection, key):
    records = hq.get(f"/{collection}")[1]
    assert records
    for record in records:
        assert hq.get(f"/{collection}/{record[key]}") == (200, record)


def test_operator_lookup_uses_operator_id(hq):
    status, body = hq.get("/operators/lupe")
    assert status == 200
    assert body["operator_id"] == "lupe"


def test_get_agent_pool_by_id(hq):
    pool = {"type": "agent_pool", "id": "security-pool", "name": "security-pool", "agent_ids": []}
    with serve._lock:
        serve._pools.append(pool)
    assert hq.get("/agent-pools/security-pool") == (200, pool)
    assert hq.get("/agent-pools") == (200, [pool])


@pytest.mark.parametrize("path, fragment", [
    ("/audit/nope", "No audit event"),
    ("/agents/nope", "No agent"),
    ("/operators/nope", "No operator"),
    ("/agent-pools/nope", "No agent pool"),
])
def test_unknown_id_is_404(hq, path, fragment):
    status, body = hq.get(path)
    assert status == 404
    assert fragment in body["error"]


@pytest.mark.parametrize("path", ["/audit/a/b", "/agents/a/b", "/operators/a/b", "/agent-pools/a/b"])
def test_nested_paths_are_not_routes(hq, path):
    status, body = hq.get(path)
    assert status == 404
    assert "No route" in body["error"]


def test_intake_agent_entry_still_served(hq):
    status, body = hq.get("/agents/intake-agent-v2")
    assert status == 200
    assert (body["id"], body["status"]) == ("intake-agent-v2", "experimental")


# ---------------------------------------------------------------------------
# GET /audit filters
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("field", ["actor_id", "actor_type", "target_id", "target_type", "event_type"])
def test_audit_exact_match_filters(hq, field):
    _populate_audit(hq)
    events = _events(hq)
    values = {e[field] for e in events}
    assert len(values) > 1, f"fixture needs varied {field}"
    for value in values:
        assert _events(hq, f"?{field}={value}") == [e for e in events if e[field] == value]


def test_audit_filters_combine(hq):
    _populate_audit(hq)
    events = _events(hq)
    expected = [e for e in events if e["actor_type"] == "operator" and e["target_type"] == "intent"]
    assert expected
    assert _events(hq, "?actor_type=operator&target_type=intent") == expected


def test_audit_since_until_bound_inclusively(hq):
    _populate_audit(hq)
    events = _events(hq)
    middle = events[len(events) // 2]["timestamp"]
    q = quote(middle)
    assert _events(hq, f"?since={q}") == [e for e in events if e["timestamp"] >= middle]
    assert _events(hq, f"?until={q}") == [e for e in events if e["timestamp"] <= middle]
    assert _events(hq, f"?since={q}&until={q}") == [e for e in events if e["timestamp"] == middle]


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


@pytest.mark.parametrize("fmt", [
    lambda dt: _iso(dt),                                          # trailing Z
    lambda dt: dt.isoformat(),                                    # +00:00
    lambda dt: dt.replace(tzinfo=None).isoformat(),               # naive = UTC
    lambda dt: dt.astimezone(timezone(timedelta(hours=-7))).isoformat(),  # other offset
], ids=["z", "utc-offset", "naive", "other-offset"])
def test_audit_time_bounds_compare_instants_not_strings(hq, fmt):
    _populate_audit(hq)
    events = _events(hq)
    before = datetime.now(timezone.utc) - timedelta(hours=1)
    after = datetime.now(timezone.utc) + timedelta(hours=1)
    assert _events(hq, f"?since={quote(fmt(before))}") == events
    assert _events(hq, f"?until={quote(fmt(before))}") == []
    assert _events(hq, f"?since={quote(fmt(after))}") == []
    assert _events(hq, f"?until={quote(fmt(after))}") == events


def test_audit_accepts_date_only_bounds(hq):
    _populate_audit(hq)
    today = datetime.now(timezone.utc).date()
    assert _events(hq, f"?since={today}") == _events(hq)
    assert _events(hq, f"?until={today - timedelta(days=1)}") == []


@pytest.mark.parametrize("query", ["?since=yesterday", "?until=2026-13-01"])
def test_audit_invalid_bounds_are_400(hq, query):
    status, body = hq.get("/audit" + query)
    assert status == 400
    assert "ISO 8601" in body["error"]


# ---------------------------------------------------------------------------
# Repeated query parameters
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    "/escalations?status=pending&status=resolved",   # used to crash the handler
    "/escalations?severity=high&severity=low",
    "/audit?event_type=a&event_type=b",
    "/audit?since=2026-01-01&since=2026-02-01",
    "/operator/sessions?active=true&active=false",
    "/marketplace?x=1&x=2",
])
def test_repeated_query_parameter_is_400(hq, path):
    status, body = hq.get(path)
    assert status == 400
    assert "more than once" in body["error"]


# ---------------------------------------------------------------------------
# Blank query values are kept, not dropped
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    "/escalations?status=pending&status=",
    "/audit?event_type=&event_type=a",
    "/operator/sessions?active=&active=true",
])
def test_repeated_parameter_with_blank_value_is_400(hq, path):
    status, body = hq.get(path)
    assert status == 400
    assert "more than once" in body["error"]


@pytest.mark.parametrize("bound", ["since", "until"])
def test_empty_time_bound_is_400(hq, bound):
    _populate_audit(hq)
    status, body = hq.get(f"/audit?{bound}=")
    assert status == 400
    assert "ISO 8601" in body["error"]


@pytest.mark.parametrize("field", ["actor_id", "actor_type", "target_id", "target_type", "event_type"])
def test_empty_exact_match_filter_matches_empty_values(hq, field):
    _populate_audit(hq)
    assert _events(hq, f"?{field}=") == [e for e in _events(hq) if e[field] == ""]


def test_empty_escalation_and_session_filters_match_nothing(hq):
    hq.post("/intents", {"raw": "urgent", "source": "t", "tags": ["critical"]})
    hq.post("/operator/sessions", {"operator_id": "lupe"}, AUTH)
    assert hq.get("/escalations?status=") == (200, [])
    assert hq.get("/escalations?severity=") == (200, [])
    assert hq.get("/operator/sessions?operator_id=") == (200, [])
    assert hq.get("/operator/sessions?active=")[0] == 400
