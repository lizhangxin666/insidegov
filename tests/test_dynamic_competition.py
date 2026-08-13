from insidegov.dynamic_competition import run_dynamic_competition_experiment
from insidegov.engine import SimulationEngine
from insidegov.scenarios import create_full_lifecycle_world
from insidegov.serde import world_from_dict


def test_city_imitation_is_agent_selected_but_rule_bounded() -> None:
    world = create_full_lifecycle_world(42, "imitation-test")
    world.imitation_policy = "aggressive"
    SimulationEngine(world).run(10)

    created = [item for item in world.imitation_decisions if item.created_firm_id]
    assert created
    assert all(item.approved_cost <= item.requested_cost for item in created)
    assert all(item.added_capacity > 0 for item in created)
    assert any(audit.action_type == "city_imitation" for audit in world.action_audits)


def test_exit_rescue_and_conditional_restructuring_diverge() -> None:
    report = run_dynamic_competition_experiment(seed=42, quarters=24)
    variants = {item["id"]: item for item in report["variants"]}

    assert variants["market_exit"]["final"]["exited_firms"] > 0
    assert variants["market_exit"]["final"]["rescue_spending"] == 0
    assert variants["unconditional"]["final"]["zombie_firms"] > 0
    assert variants["unconditional"]["final"]["rescue_spending"] > 0
    assert variants["conditional"]["final"]["zombie_firms"] == 0
    assert any(
        item["conditional"]
        and item["capacity_after"] < item["capacity_before"]
        for item in variants["conditional"]["rescue_decisions"]
    )


def test_dynamic_state_round_trips() -> None:
    world = create_full_lifecycle_world(42, "roundtrip-dynamic")
    world.imitation_policy = "aggressive"
    world.rescue_policy = "conditional"
    engine = SimulationEngine(world)
    engine.intervene("demand_shock", "market", -0.42, quarter=10)
    engine.run(14)

    restored = world_from_dict(world.to_dict())
    assert restored.imitation_policy == "aggressive"
    assert restored.rescue_policy == "conditional"
    assert len(restored.imitation_decisions) == len(world.imitation_decisions)
    assert len(restored.rescue_decisions) == len(world.rescue_decisions)
    assert restored.history[-1].imitation_capacity == world.history[-1].imitation_capacity


def test_dynamic_experiment_resumes_without_replaying_saved_quarters() -> None:
    world = create_full_lifecycle_world(31, "resume-dynamic")
    world.imitation_policy = "aggressive"
    world.rescue_policy = "conditional"
    engine = SimulationEngine(world)
    engine.intervene("demand_shock", "market", -0.42, quarter=10)
    engine.run(12)
    saved_history = list(world.history)

    report = run_dynamic_competition_experiment(
        seed=31,
        quarters=14,
        policy_ids=["conditional"],
        initial_world=world,
    )

    assert world.quarter == 14
    assert world.history[:len(saved_history)] == saved_history
    assert report["variants"][0]["final"]["quarter"] == 14
