from insidegov.engine import SimulationEngine
from insidegov.experiments import run_comparison
from insidegov.scenarios import create_full_lifecycle_world


def test_reproducible_for_same_seed():
    a = SimulationEngine(create_full_lifecycle_world(42, "a")).run(16)
    b = SimulationEngine(create_full_lifecycle_world(42, "b")).run(16)
    assert a.selected_city_id == b.selected_city_id
    assert a.to_dict()["history"] == b.to_dict()["history"]


def test_world_moves_through_all_phases():
    engine = SimulationEngine(create_full_lifecycle_world())
    engine.run(3)
    assert engine.world.selected_city_id is not None
    engine.run(8)
    assert engine.world.firms["firm_nova"].operating
    assert len(engine.world.history) == 11


def test_financial_constraints_prevent_negative_payment_balance():
    engine = SimulationEngine(create_full_lifecycle_world())
    engine.intervene("fiscal_shock", "city_hai", 0.9, quarter=4)
    engine.run(14)
    assert all(city.available_budget >= 0 for city in engine.world.cities.values())


def test_decisions_are_traceable():
    world = SimulationEngine(create_full_lifecycle_world()).run(5)
    assert world.traces
    assert all(trace.evidence and trace.constraints and trace.outcome for trace in world.traces)


def test_counterfactuals_have_common_seed_and_different_outcomes():
    results = run_comparison(seed=42, quarters=16)
    assert len(results) == 4
    fingerprints = {(row["average_credibility"], row["utilization"], row["total_committed_expenditure"]) for row in results}
    assert len(fingerprints) > 1


def test_internal_governance_creates_real_veto_and_memory_chain():
    world = SimulationEngine(create_full_lifecycle_world()).run(1)
    assert len(world.negotiations) == 3
    assert all(item.final_cost <= item.finance_limit + 0.02 for item in world.negotiations)
    assert world.agents["city_hai_investment"].memories
    assert world.agents["city_hai_finance"].last_reflection != "尚无历史行动"
    lin = next(item for item in world.negotiations if item.city_id == "city_lin")
    assert lin.proposer_id == "city_lin_investment"
    assert lin.proposal_tools["subsidy"] > lin.finance_tool_limits["subsidy"]
    assert lin.final_tools["subsidy"] <= lin.finance_tool_limits["subsidy"] + 0.02
    assert lin.final_tools["equity"] <= lin.finance_tool_limits["equity"] + 0.02
    assert len(lin.payment_schedule) >= 3
    assert [turn["act"] for turn in lin.turns] == ["proposal", "review", "coordination"]


def test_payment_schedule_becomes_real_conditional_promises():
    world = SimulationEngine(create_full_lifecycle_world()).run(3)
    selected = world.selected_city_id
    negotiation = next(
        item for item in reversed(world.negotiations) if item.city_id == selected
    )
    assert len(world.promises) == len(negotiation.payment_schedule)
    assert {promise.condition for promise in world.promises} >= {
        "contract_signed", "equipment_ordered", "project_progress>=0.55",
    }


def test_private_observations_do_not_cross_agent_boundaries():
    engine = SimulationEngine(create_full_lifecycle_world())
    city = engine.world.cities["city_hai"]
    leader_view = engine._leader_observation(city, engine.world.firms["firm_nova"])
    finance_view = engine._finance_observation(city, engine.world.cities["city_hai"].active_offer)
    assert "reserve_floor" not in leader_view
    assert "true_intent" not in finance_view
