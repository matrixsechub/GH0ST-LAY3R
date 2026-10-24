from core.engine import create_default_engine


def test_default_engine_runs_demo_cycle():
    engine = create_default_engine()

    result = engine.run("Ghost Layer Studio online.", source="test")

    assert result["source"] == "test"
    assert result["operator_axis"] == "operator-defensive"
    assert result["payload"]["agent_count"] >= 1
