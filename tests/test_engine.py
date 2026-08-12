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

