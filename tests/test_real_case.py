import pytest

from insidegov.cases import create_hefei_nio_world, run_hefei_nio_sensitivity
from insidegov.engine import SimulationEngine
from insidegov.serde import world_from_dict


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


def test_joint_funds_are_independent_promises_and_close_the_historical_equity_gap():
    result = SimulationEngine(create_hefei_nio_world(42)).run(16)
    offer = result.cities["city_lin"].active_offer
    assert offer is not None
    assert offer.equity == 16.48
    assert offer.external_equity == 53.52
    assert offer.total_equity_support == 70.0
    assert len(result.investment_funds) == 3
    fund_promises = [item for item in result.promises if item.funding_source_id]
    assert len(fund_promises) == 3
    assert sum(item.amount for item in fund_promises) == pytest.approx(53.52)
    assert all(item.status.value == "fulfilled" for item in fund_promises)
    restored = world_from_dict(result.to_dict())
    assert restored.investment_funds["fund_cmg_sdic"].source_level == "national_industrial_fund"


def test_hefei_sensitivity_compares_fiscal_space_and_joint_investment():
    report = run_hefei_nio_sensitivity(42)
    assert len(report["runs"]) == 6
    without = [item for item in report["runs"] if not item["joint_investment"]]
    with_funds = [item for item in report["runs"] if item["joint_investment"]]
    assert all(item["historical_equity_gap"] > 45 for item in without)
    assert all(
        abs(joint["historical_equity_gap"]) < municipal["historical_equity_gap"]
        for municipal, joint in zip(without, with_funds, strict=True)
    )
    assert with_funds[1]["historical_equity_gap"] == pytest.approx(0.0)
