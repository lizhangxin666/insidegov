from insidegov.agents import (
    DeterministicCognition,
    EnterpriseResponseAction,
    FinanceAction,
    ResolutionAction,
    _repair_structured_payload,
)
from insidegov.engine import SimulationEngine
from insidegov.experiments import run_comparison
from insidegov.scenarios import create_full_lifecycle_world


def test_reproducible_for_same_seed():
    a = SimulationEngine(create_full_lifecycle_world(42, "a")).run(16)
    b = SimulationEngine(create_full_lifecycle_world(42, "b")).run(16)
    assert a.selected_city_id == b.selected_city_id
    assert a.to_dict()["history"] == b.to_dict()["history"]


def test_chinese_enterprise_response_is_repaired_to_structured_protocol():
    repaired = _repair_structured_payload(
        EnterpriseResponseAction,
        '{"response":"还价","counter_terms":{"subsidy_floor":9},"confidence":0.8,"rationale":"保障不足"}',
    )
    action = EnterpriseResponseAction.model_validate(repaired)
    assert action.response == "counter"
    assert action.counter_terms["subsidy_floor"] == 9


def test_seed_changes_world_conditions_and_population_outcomes():
    worlds = [
        SimulationEngine(create_full_lifecycle_world(seed, str(seed))).run(16)
        for seed in [11, 23, 42, 57, 89]
    ]
    assert len({world.cities["city_lin"].supply_chain for world in worlds}) > 1
    assert len({world.firms["firm_nova"].private_intent for world in worlds}) > 1
    assert len({world.history[-1].total_employment for world in worlds}) > 1


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
    audits = [item for item in world.action_audits if item.quarter == 1]
    assert len(audits) == 13
    assert any(item.action_type == "decide_negotiation_timing" for item in audits)
    assert len(world.external_negotiations) == 3
    assert all(item.enterprise_response in {"accept", "counter", "terminate"} for item in world.external_negotiations)
    finance_audit = next(
        item for item in audits
        if item.agent_id == "city_lin_finance" and item.action_type == "review_offer"
    )
    assert "maximum_subsidy" in finance_audit.llm_suggestion
    assert finance_audit.executed_action["maximum_subsidy"] > 0
    assert finance_audit.rule_adjustment["source"] == "deterministic_finance_constraints"
    assert finance_audit.reflection


def test_external_counter_enters_next_internal_offer_and_final_acceptance_filters_cities():
    engine = SimulationEngine(create_full_lifecycle_world(42, "nested-negotiation"))
    engine.run(1)
    q1 = {
        item.city_id: item for item in engine.world.external_negotiations
        if item.quarter == 1
    }
    assert all(item.enterprise_response == "counter" for item in q1.values())
    engine.run(1)
    q2_internal = {
        item.city_id: item for item in engine.world.negotiations if item.quarter == 2
    }
    for city_id, response in q1.items():
        assert q2_internal[city_id].proposal_tools["subsidy"] >= response.counter_terms["subsidy_floor"]
    engine.run(1)
    q3 = [item for item in engine.world.external_negotiations if item.quarter == 3]
    accepted = {item.city_id for item in q3 if item.enterprise_response == "accept"}
    assert accepted
    assert engine.world.selected_city_id in accepted


def test_rule_engine_fills_finance_limits_and_rebuilds_schedule_for_llm_actions():
    class ShortLLMCognition(DeterministicCognition):
        mode = "llm"
        model_name = "test-short-llm"

        def review_offer(self, agent, city, proposal, observation, memories):
            return FinanceAction(
                approved=True,
                concerns=["现金压力"],
                conditions=["分期兑现"],
                rationale="财政只表达态度，数值由规则引擎填充",
            )

        def resolve_offer(self, agent, city, proposal, review, observation, memories):
            return ResolutionAction(
                resolution="restructured_after_tool_veto",
                subsidy=proposal.subsidy,
                equity=proposal.equity,
                land_discount=proposal.land_discount,
                credit_support=proposal.credit_support,
                approval_speed=proposal.approval_speed,
                talent_support=proposal.talent_support,
                payment_schedule=[],
                rationale="接受财政上限并保留招商强度",
            )

    world = create_full_lifecycle_world()
    world.policy_mode = "llm"
    engine = SimulationEngine(world, cognition=ShortLLMCognition())
    engine.run(1)
    negotiation = next(item for item in world.negotiations if item.city_id == "city_lin")
    assert negotiation.finance_limit > 0
    assert negotiation.final_cost <= negotiation.finance_limit + 0.02
    assert negotiation.payment_schedule
    assert all(row.item != "credit_support" for row in negotiation.payment_schedule)
    assert any(row.item == "credit_support_cost" for row in negotiation.payment_schedule)


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
