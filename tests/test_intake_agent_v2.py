"""
Intake Agent v2 HQ bootstrap — regression suite.

Covers: engine boot, GOV-4 containment, the public -> intake -> marketplace
flow, lifecycle integrity (append-only, valid/invalid transitions),
deterministic latest-state, metrics, cockpit, HQ health, and routing audit.
See docs/intake-agent-v2-integration-plan.md.
"""

from __future__ import annotations

import ast
import os

import pytest

import scripts.serve as serve
from agents.constellation import IntakeAgentV2
from core.engine import create_default_engine
from core.substrate import SubstrateState
from core.types import IntentVector

from conftest import REPO_ROOT

OBSERVER_BANNER = "IntakeAgentV2: Access Pending — You are in Observer Mode."
TRANSITION = "/intake-agent-v2/lifecycle/transition"
TOKEN = "test-operator-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}   # moving to "validated" needs the operator token


@pytest.fixture(autouse=True)
def _operator_token(monkeypatch):
    monkeypatch.setenv(serve.OPERATOR_TOKEN_ENV, TOKEN)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _register(hq, source: str = "test") -> dict:
    status, body = hq.post("/api/register", {"raw": "request access", "source": source})
    assert status == 201, body
    return body


def _transition(hq, lifecycle_id: str, to_stage: str) -> tuple[int, dict]:
    return hq.post(TRANSITION, {"lifecycle_id": lifecycle_id, "to_stage": to_stage}, AUTH)


def _advance(hq, lifecycle_id: str, *stages: str) -> str:
    """Walk a record through `stages`; return the final record id."""
    for stage in stages:
        status, body = _transition(hq, lifecycle_id, stage)
        assert status == 200, body
        lifecycle_id = body["current"]["id"]
    return lifecycle_id


def _function_source(path: str, name: str) -> str:
    with open(os.path.join(REPO_ROOT, path), encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.unparse(node)
    raise AssertionError(f"{name} not found in {path}")


# ---------------------------------------------------------------------------
# Engine + GOV-4 containment
# ---------------------------------------------------------------------------

def test_default_engine_runs():
    envelope = create_default_engine().run("Boot sequence: Ghost Layer Studio online.",
                                           source="pytest")
    assert envelope["intent_id"]
    assert envelope["payload"]["agent_count"] >= 1


def test_intake_agent_not_in_default_constellation():
    engine = create_default_engine()
    names = [agent.name for agent in engine.constellation.agents]
    assert "IntakeAgentV2" not in names
    assert "IntakeAgentV2" not in _function_source("core/engine.py", "create_default_engine")


@pytest.mark.parametrize("handler", ["_check_routing_table", "_post_intents"])
def test_routing_paths_never_execute_intake_agent(handler):
    src = _function_source("scripts/serve.py", handler)
    for forbidden in ("IntakeAgentV2(", "IntakeAgentV2.run", "create_default_engine"):
        assert forbidden not in src


def test_check_routing_table_returns_metadata_only():
    matches = serve._check_routing_table(["register", "unrelated"])
    assert [m["id"] for m in matches] == ["rt-intake-submissions"]
    assert all(m["target_agent_id"] == "intake-agent-v2" for m in matches)


@pytest.mark.parametrize("tags, stage, needs_operator", [
    (["high-risk"], "escalated", True),
    ([], "received", False),
])
def test_intake_agent_run_output(tags, stage, needs_operator):
    volatility = 0.9 if needs_operator else 0.3
    out = IntakeAgentV2().run(
        IntentVector(id="t", source="test", description="test", tags=tags),
        SubstrateState(spectral_density=0.5, volatility=volatility),
    )
    assert out["lifecycle_stage"] == stage
    assert out["operator_action_required"] is needs_operator


# ---------------------------------------------------------------------------
# Public -> intake -> marketplace
# ---------------------------------------------------------------------------

def test_register_creates_received_record_in_observer_mode(hq):
    body = _register(hq, source="public-test")
    assert body["lifecycle"]["stage"] == "received"
    assert body["marketplace"] == {"mode": "observer", "access": False,
                                   "banner": OBSERVER_BANNER}

    _, audit = hq.get("/audit?event_type=intake.stage_changed")
    assert [a["target_id"] for a in audit] == [body["lifecycle"]["id"]]


def test_marketplace_defaults_to_observer_with_no_records(hq):
    status, body = hq.get("/marketplace")
    assert status == 200
    assert body["mode"] == "observer"
    assert body["latest_intake_stage"] is None
    assert body["total_submissions"] == 0


@pytest.mark.parametrize("stages, mode, access", [
    ((), "observer", False),
    (("validated",), "full", True),
    (("validated", "queued"), "observer", False),
    (("validated", "queued", "processed"), "observer", False),
])
def test_marketplace_mode_tracks_latest_stage(hq, stages, mode, access):
    _advance(hq, _register(hq)["lifecycle"]["id"], *stages)
    _, body = hq.get("/marketplace")
    assert (body["mode"], body["access"]) == (mode, access)


# ---------------------------------------------------------------------------
# Lifecycle integrity
# ---------------------------------------------------------------------------

def test_full_transition_chain_is_append_only(hq):
    first = _register(hq)["lifecycle"]
    ids, prev_id = [first["id"]], first["id"]

    for prev_stage, stage in [("received", "validated"), ("validated", "queued"),
                              ("queued", "processed")]:
        status, body = _transition(hq, prev_id, stage)
        assert status == 200, body
        assert body["previous"]["stage"] == prev_stage
        assert body["current"]["stage"] == stage
        assert body["current"]["id"] != prev_id
        prev_id = body["current"]["id"]
        ids.append(prev_id)

    assert body["current"]["resolved_at"]

    _, lifecycle = hq.get("/intake-agent-v2/lifecycle")
    assert [r["id"] for r in lifecycle] == ids
    assert [r["stage"] for r in lifecycle] == ["received", "validated", "queued", "processed"]
    assert len({r["intent_id"] for r in lifecycle}) == 1

    _, audit = hq.get("/audit?event_type=intake.stage_changed")
    assert [a["payload"]["stage"] for a in audit] == ["received", "validated", "queued", "processed"]


@pytest.mark.parametrize("from_stages, to_stage", [
    ((), "processed"),                         # received -> processed (skip)
    ((), "queued"),                            # received -> queued (skip)
    (("validated",), "received"),              # backwards
    (("validated", "queued", "processed"), "validated"),  # out of terminal
    ((), "escalated"),                         # escalation not implemented yet
])
def test_invalid_transitions_are_rejected_without_side_effects(hq, from_stages, to_stage):
    record_id = _advance(hq, _register(hq)["lifecycle"]["id"], *from_stages)
    _, before_records = hq.get("/intake-agent-v2/lifecycle")
    _, before_audit = hq.get("/audit")

    status, body = _transition(hq, record_id, to_stage)

    assert status == 422
    assert "not allowed" in body["error"]
    assert hq.get("/intake-agent-v2/lifecycle")[1] == before_records
    assert hq.get("/audit")[1] == before_audit


@pytest.mark.parametrize("payload, code", [
    ({}, 400),
    ({"lifecycle_id": "x"}, 400),
    ({"lifecycle_id": "does-not-exist", "to_stage": "validated"}, 404),
])
def test_transition_input_validation(hq, payload, code):
    status, body = hq.post(TRANSITION, payload, AUTH)
    assert status == code
    assert "error" in body


def test_latest_state_follows_append_order_across_chains(hq):
    chain_a = _register(hq, source="A")["lifecycle"]["id"]
    _advance(hq, chain_a, "validated")
    _register(hq, source="B")  # appended after chain A's validated record

    _, body = hq.get("/marketplace")
    assert body["latest_intake_stage"] == "received"
    assert body["mode"] == "observer"


# ---------------------------------------------------------------------------
# Metrics / cockpit / HQ health
# ---------------------------------------------------------------------------

def _seed_mixed_lifecycle(hq) -> None:
    _register(hq)                                                      # received
    _advance(hq, _register(hq)["lifecycle"]["id"], "validated")        # +received +validated
    _advance(hq, _register(hq)["lifecycle"]["id"],
             "validated", "queued", "processed")                       # +r +v +q +p


def test_metrics_counts(hq):
    _seed_mixed_lifecycle(hq)
    status, metrics = hq.get("/intake-agent-v2/metrics")
    assert status == 200
    assert metrics == {
        "received_count": 3, "validated_count": 2, "queued_count": 1,
        "processed_count": 1, "processing_count": 0, "escalated_count": 0,
        "completed_count": 0, "total": 7,
    }


def test_cockpit_panel(hq):
    _seed_mixed_lifecycle(hq)
    status, panel = hq.get("/cockpit/intake")
    assert status == 200
    assert panel["agent_status"] == "experimental"
    assert "routing-active" in panel["gov4_status"]
    assert panel["routing_table_entries"] == len(serve._routing_table) == 4
    assert panel["stage_counts"] == {"received": 3, "validated": 2, "queued": 1, "processed": 1}
    assert len(panel["lifecycle_timeline"]) == 7
    assert [r["stage"] for r in panel["last_10_submissions"]] == ["received"] * 3


def test_cockpit_last_10_is_capped(hq):
    for _ in range(12):
        _register(hq)
    _, panel = hq.get("/cockpit/intake")
    assert len(panel["last_10_submissions"]) == 10


def test_hq_health_intake_fields(hq):
    _seed_mixed_lifecycle(hq)
    status, health = hq.get("/hq/health")
    assert status == 200
    assert health["intake_received_count"] == 3
    assert health["intake_validated_count"] == 2
    assert health["intake_queued_count"] == 1
    assert health["intake_queue_depth"] == 1          # legacy alias
    assert health["intake_processing_count"] == 0
    assert health["intake_processed_count"] == 1
    assert health["intake_completed_count"] == 0
    assert health["intake_escalated_count"] == 0


# ---------------------------------------------------------------------------
# Routing audit
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tag, entry_id", [
    ("intake", "rt-intake-submissions"),
    ("access-request", "rt-access-requests"),
    ("paywall", "rt-paywall-transitions"),
    ("register-transition", "rt-register-transitions"),
])
def test_intents_log_routing_matches_without_running_intake_agent(hq, tag, entry_id):
    status, envelope = hq.post("/intents", {"raw": "route test", "source": "route-test",
                                            "tags": [tag]})
    assert status == 200
    agent_names = [a["agent"] for a in envelope["payload"]["agents"]]
    assert "IntakeAgentV2" not in agent_names

    _, audit = hq.get("/audit?event_type=intent.submitted")
    assert audit[-1]["payload"]["routing_matches"] == [
        {"entry_id": entry_id, "target_agent_id": "intake-agent-v2"}
    ]


def test_routing_matches_are_priority_ordered(hq):
    hq.post("/intents", {"raw": "multi", "source": "t",
                         "tags": ["register-transition", "paywall", "intake"]})
    _, audit = hq.get("/audit?event_type=intent.submitted")
    ids = [m["entry_id"] for m in audit[-1]["payload"]["routing_matches"]]
    # priority 10 entries (table order) before the priority 15 entry
    assert ids == ["rt-intake-submissions", "rt-paywall-transitions", "rt-register-transitions"]


def test_intents_without_routing_tags_have_no_matches(hq):
    hq.post("/intents", {"raw": "plain", "source": "t", "tags": []})
    _, audit = hq.get("/audit?event_type=intent.submitted")
    assert audit[-1]["payload"]["routing_matches"] == []
