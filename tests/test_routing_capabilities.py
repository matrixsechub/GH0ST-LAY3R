"""
Read-only routing table and capability index — GET /routing-table[/:id] and
GET /capabilities[/:capability] (API_CONTRACT.md v2).

The routing table is the server's in-memory, never-dispatched table, listed
in AGENT_HQ.md's evaluation order (priority, then id). The capability index
is derived from the registry's engine and agent capabilities.
"""

from __future__ import annotations

import copy

import pytest

import scripts.serve as serve

ENTRY_FIELDS = {"id", "type", "target_engine_id", "priority", "active", "match_tags",
                "match_capability", "description"}


def _registry_capabilities() -> dict:
    expected: dict = {}
    for collection, key in (("engines", "provided_by_engines"), ("agents", "provided_by_agents")):
        for record in serve._registry.get(collection, []):
            for capability in record.get("capabilities", []):
                expected.setdefault(capability, {"provided_by_engines": [], "provided_by_agents": []})
                expected[capability][key].append(record["id"])
    return expected


# ---------------------------------------------------------------------------
# GET /routing-table
# ---------------------------------------------------------------------------

def test_lists_every_entry_in_evaluation_order(hq):
    status, entries = hq.get("/routing-table")
    assert status == 200
    assert sorted(e["id"] for e in entries) == sorted(e["id"] for e in serve._routing_table)
    assert [(e["priority"], e["id"]) for e in entries] == sorted((e["priority"], e["id"]) for e in entries)
    for entry in entries:
        assert ENTRY_FIELDS <= set(entry)
        assert entry["type"] == "routing-entry"


def test_ties_are_broken_by_id(hq, monkeypatch):
    table = [
        {"id": "rt-b", "type": "routing-entry", "target_engine_id": "e", "priority": 5, "active": True,
         "match_tags": ["x"], "match_capability": "", "description": ""},
        {"id": "rt-a", "type": "routing-entry", "target_engine_id": "e", "priority": 5, "active": True,
         "match_tags": ["x"], "match_capability": "", "description": ""},
        {"id": "rt-c", "type": "routing-entry", "target_engine_id": "e", "priority": 1, "active": True,
         "match_tags": ["x"], "match_capability": "", "description": ""},
    ]
    monkeypatch.setattr(serve, "_routing_table", table)
    assert [e["id"] for e in hq.get("/routing-table")[1]] == ["rt-c", "rt-a", "rt-b"]
    # POST /intents records matches in the same order.
    hq.post("/intents", {"raw": "x", "source": "t", "tags": ["x"]})
    [event] = hq.get("/audit?event_type=intent.submitted")[1]
    assert [m["entry_id"] for m in event["payload"]["routing_matches"]] == ["rt-c", "rt-a", "rt-b"]


def test_active_filter(hq, monkeypatch):
    table = copy.deepcopy(serve._routing_table)
    table[0]["active"] = False
    monkeypatch.setattr(serve, "_routing_table", table)
    assert [e["id"] for e in hq.get("/routing-table?active=false")[1]] == [table[0]["id"]]
    assert table[0]["id"] not in [e["id"] for e in hq.get("/routing-table?active=true")[1]]
    assert len(hq.get("/routing-table?active=true")[1]) == len(table) - 1


@pytest.mark.parametrize("query, count", [
    ("ghost-layer-core", len(serve._routing_table)),
    ("other-engine", 0),
    ("", 0),
])
def test_target_engine_filter(hq, query, count):
    status, entries = hq.get(f"/routing-table?target_engine_id={query}")
    assert status == 200
    assert len(entries) == count


@pytest.mark.parametrize("query", ["?active=yes", "?active=", "?active=true&active=false"])
def test_bad_routing_filters_are_400(hq, query):
    assert hq.get("/routing-table" + query)[0] == 400


def test_get_routing_entry_by_id(hq):
    for entry in hq.get("/routing-table")[1]:
        assert hq.get(f"/routing-table/{entry['id']}") == (200, entry)


@pytest.mark.parametrize("path, code, fragment", [
    ("/routing-table/nope", 404, "No routing entry"),
    ("/routing-table/a/b", 404, "No route"),
])
def test_unknown_routing_paths(hq, path, code, fragment):
    status, body = hq.get(path)
    assert status == code
    assert fragment in body["error"]


@pytest.mark.parametrize("method", ["POST", "PATCH"])
def test_routing_table_is_read_only(hq, method):
    before = copy.deepcopy(serve._routing_table)
    status, _ = hq.request(method, "/routing-table", {"target_engine_id": "x", "priority": 1})
    assert status == 404
    assert serve._routing_table == before


# ---------------------------------------------------------------------------
# GET /capabilities
# ---------------------------------------------------------------------------

def test_capability_index_mirrors_registry(hq):
    status, index = hq.get("/capabilities")
    assert status == 200
    expected = _registry_capabilities()
    assert [c["capability"] for c in index] == sorted(expected)
    for record in index:
        assert record["type"] == "capability-index"
        assert {k: record[k] for k in ("provided_by_engines", "provided_by_agents")} == expected[record["capability"]]


def test_known_capabilities(hq):
    assert hq.get("/capabilities/lane-suggestion")[1]["provided_by_agents"] == ["route-advisory-agent"]
    engine_cap = hq.get("/capabilities/substrate-ingestion")[1]
    assert (engine_cap["provided_by_engines"], engine_cap["provided_by_agents"]) == (["ghost-layer-core"], [])


def test_capability_shared_by_engine_and_agents(hq, monkeypatch):
    registry = copy.deepcopy(serve._registry)
    registry["engines"][0]["capabilities"].append("shared")
    for agent in registry["agents"][:2]:
        agent["capabilities"].append("shared")
    monkeypatch.setattr(serve, "_registry", registry)
    record = hq.get("/capabilities/shared")[1]
    assert record["provided_by_engines"] == [registry["engines"][0]["id"]]
    assert record["provided_by_agents"] == [a["id"] for a in registry["agents"][:2]]


def test_capability_substring_filter(hq):
    index = hq.get("/capabilities")[1]
    assert hq.get("/capabilities?capability=intake")[1] == [c for c in index if "intake" in c["capability"]]
    assert hq.get("/capabilities?capability=intake")[1]
    assert hq.get("/capabilities?capability=zzz")[1] == []
    assert hq.get("/capabilities?capability=")[1] == index    # "" is a substring of everything


@pytest.mark.parametrize("path, code, fragment", [
    ("/capabilities/intake", 404, "No capability"),      # exact match only
    ("/capabilities/a/b", 404, "No route"),
])
def test_unknown_capability_paths(hq, path, code, fragment):
    status, body = hq.get(path)
    assert status == code
    assert fragment in body["error"]


def test_repeated_capability_filter_is_400(hq):
    assert hq.get("/capabilities?capability=a&capability=b")[0] == 400
