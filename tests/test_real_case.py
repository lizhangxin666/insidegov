from insidegov.cases import create_hefei_nio_world
from insidegov.engine import SimulationEngine


def test_hefei_nio_case_keeps_public_facts_and_runs_normally():
    world = create_hefei_nio_world(42)
    assert world.cities["city_lin"].name == "合肥市"
    assert world.firms["firm_nova"].name == "蔚来中国"
    assert world.firms["firm_nova"].cash == 42.6
    assert world.parameter_provenance["historical_contract.strategic_equity"]["final_value"] == 70.0
    assert {
        row["provenance"] for row in world.parameter_provenance.values()
    } <= {"public_source", "expert_judgment", "model_assumption", "user_input"}
    result = SimulationEngine(world).run(16)
    assert result.selected_city_id == "city_lin"
    assert result.negotiations
    assert result.action_audits
    assert result.history[-1].cluster_size >= 1
