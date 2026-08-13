from fastapi.testclient import TestClient

from insidegov.agents import (
    DeterministicCognition,
    EnterpriseResponseAction,
    NegotiationTimingAction,
    OrganizationActionChoice,
    OrganizationInitiativeChoice,
    ProcedureTransitionChoice,
)
from insidegov.api import app
from insidegov.engine import SimulationEngine
from insidegov.experiments import run_organization_mode_comparison
from insidegov.models import MemoryRecord
from insidegov.organization import ROLE_ACTIONS
from insidegov.organization_dynamics import OrganizationDynamics
from insidegov.scenarios import create_full_lifecycle_world

client = TestClient(app)


def run_mode(mode: str, quarters: int = 3):
    world = create_full_lifecycle_world(42, f"test-{mode}")
    world.process_mode = mode
    return SimulationEngine(world).run(quarters)


def test_roles_have_different_action_sets():
    unique_sets = {actions for actions in ROLE_ACTIONS.values() if actions}
    assert len(unique_sets) >= 5
    assert "preconsult_finance" in ROLE_ACTIONS[next(
        role for role in ROLE_ACTIONS if role.value == "investment"
    )]
    assert "legality_review" in ROLE_ACTIONS[next(
        role for role in ROLE_ACTIONS if role.value == "legal"
    )]


def test_formal_mode_enforces_legal_and_collective_gates():
    world = run_mode("formal", 1)
    for city_id in world.cities:
        actions = [
            item.action_id for item in world.organization_actions
            if item.city_id == city_id
        ]
        assert "risk_assessment" in actions
        assert "legality_review" in actions
        assert "collective_deliberation" in actions
        assert not {"preconsult_finance", "broker_compromise"} & set(actions)


def test_informal_mode_releases_sequence_but_keeps_fiscal_guardrail():
    world = run_mode("informal", 1)
    for city_id in world.cities:
        actions = [
            item.action_id for item in world.organization_actions
            if item.city_id == city_id
        ]
        assert actions[-1] == "fiscal_guardrail"
        assert "legality_review" not in actions
        assert "collective_deliberation" not in actions
        negotiation = next(item for item in world.negotiations if item.city_id == city_id)
        assert negotiation.final_cost <= negotiation.finance_limit + 0.02


def test_hybrid_mode_combines_informal_moves_and_formal_gates_reproducibly():
    first = run_mode("hybrid", 3)
    second = run_mode("hybrid", 3)
    assert [item.action_id for item in first.organization_actions] == [
        item.action_id for item in second.organization_actions
    ]
    assert any(item.arena == "informal" for item in first.organization_actions)
    assert any(item.action_id == "legality_review" for item in first.organization_actions)
    assert all(
        process.legal_reviewed and process.collective_deliberated
        for process in first.organization_processes.values()
    )


def test_llm_provider_can_choose_only_role_authorized_discretionary_action():
    class OrganizationLLM(DeterministicCognition):
        mode = "llm"
        model_name = "test-organization-llm"

        def choose_organization_action(self, agent, candidates, observation, memories):
            return OrganizationActionChoice(
                action_id=candidates[-1],
                confidence=0.9,
                rationale="根据本组织目标选择授权列表中的末项策略",
            )

    world = create_full_lifecycle_world(42, "organization-llm")
    world.policy_mode = "llm"
    SimulationEngine(world, cognition=OrganizationLLM()).run(1)
    discretionary = [item for item in world.organization_actions if not item.required]
    assert discretionary
    assert all(item.selection_provider == "test-organization-llm" for item in discretionary)
    assert all(item.action_id in item.candidates for item in discretionary)


def test_three_mode_comparison_and_evidence_api():
    rows = run_organization_mode_comparison(seed=42, quarters=4)
    assert [item["process_mode"] for item in rows] == ["formal", "informal", "hybrid"]
    assert len({tuple(item["action_sequence"]) for item in rows}) == 3
    evidence = client.get("/organization/evidence")
    assert evidence.status_code == 200
    assert {item["id"] for item in evidence.json()} >= {
        "formal_procedure", "fund_independence", "informal_networks", "attention",
    }
    actions = client.get("/organization/actions").json()
    assert any(item["id"] == "fiscal_guardrail" for item in actions)


def test_departments_decide_who_acts_and_attention_defers_lower_priority_moves():
    class InitiativeCognition(DeterministicCognition):
        def choose_organization_initiative(self, agent, candidates, observation, memories):
            urgency = {"investment": 0.95, "finance": 0.85, "park": 0.7, "city_leader": 0.2}[agent.role.value]
            if agent.role.value == "city_leader":
                return OrganizationInitiativeChoice(
                    decision="wait", action_id="wait", urgency=urgency,
                    rationale="当前不占用注意力",
                )
            return OrganizationInitiativeChoice(
                decision="act", action_id=candidates[0], urgency=urgency,
                rationale="此刻主动发起",
            )

    world = create_full_lifecycle_world(42, "initiative-autonomy")
    SimulationEngine(world, cognition=InitiativeCognition()).run(1)
    for city_id in world.cities:
        rows = [
            item for item in world.organization_actions
            if item.city_id == city_id and item.stage == "initiative"
        ]
        assert len(rows) == 4
        assert sum(item.decision == "act" for item in rows) == 2
        assert any(item.decision == "wait" for item in rows)
        assert any(item.decision == "deferred" for item in rows)


def test_formal_process_can_be_returned_then_resumed_by_agent():
    class ReturnThenResume(DeterministicCognition):
        def choose_procedure_transition(self, agent, candidates, observation, memories):
            transition = (
                "return_for_revision"
                if observation["formal_status"] == "dormant"
                else "resume_formal_process"
            )
            return ProcedureTransitionChoice(
                transition=transition,
                rationale="材料不足先退回，补齐后恢复程序",
            )

    world = create_full_lifecycle_world(42, "return-resume")
    engine = SimulationEngine(world, cognition=ReturnThenResume())
    engine.run(1)
    assert not world.negotiations
    assert all(state.formal_status == "returned" for state in world.organization_processes.values())
    engine.run(1)
    assert len(world.negotiations) == 3
    assert all(state.last_transition == "resume_formal_process" for state in world.organization_processes.values())


def test_enterprise_can_accept_and_select_before_fixed_third_quarter():
    class EarlyBoard(DeterministicCognition):
        def respond_to_offer(self, agent, observation, memories):
            return EnterpriseResponseAction(
                response="accept", confidence=0.92,
                rationale="高效用报价已满足董事会条件",
            )

        def decide_negotiation_timing(self, agent, observation, memories):
            return NegotiationTimingAction(
                decision="select_now", confidence=0.9,
                rationale="立即锁定已接受的优势报价",
            )

    world = create_full_lifecycle_world(42, "early-board")
    SimulationEngine(world, cognition=EarlyBoard()).run(1)
    assert world.quarter == 1
    assert world.selected_city_id is not None
    assert world.recruitment_status == "selected"
    assert any(item.enterprise_response == "accept" for item in world.external_negotiations)


def test_multi_step_plans_are_persisted_and_linked_to_actual_actions():
    world = create_full_lifecycle_world(42, "plan-tree")
    SimulationEngine(world).run(3)
    assert len(world.organization_plans) == 12
    investment = next(
        plan for plan in world.organization_plans
        if plan.actor_id == "city_hai_investment"
    )
    assert len(investment.alternatives) == 3
    assert len(investment.nodes) >= 2
    linked = [item for item in world.organization_actions if item.plan_id == investment.id]
    assert linked
    assert any(node.status == "completed" for node in investment.nodes)
    assert investment.review_history


def test_open_action_is_generated_then_permission_checked_and_effect_capped():
    world = create_full_lifecycle_world(42, "open-action")
    dynamics = OrganizationDynamics(world)
    authorized = dynamics.validate_open_action(
        "city_hai_investment", "city_hai",
        {
            "title": "邀请上级部门背书",
            "mechanism": "upward_endorsement",
            "target_actor_id": "city_hai_leader",
            "requested_effects": {"agenda_priority_delta": 0.9},
            "resource_request": {}, "rationale": "打开议程窗口",
        },
        "test", False,
    )
    assert authorized.status == "authorized"
    assert authorized.executed_effects["agenda_priority_delta"] == 0.18
    rejected = dynamics.validate_open_action(
        "city_hai_finance", "city_hai",
        {
            "title": "财政局自行寻求上级政治背书",
            "mechanism": "upward_endorsement",
            "requested_effects": {"agenda_priority_delta": 0.1},
            "resource_request": {"cash": 5}, "rationale": "越权测试",
        },
        "test", False,
    )
    assert rejected.status == "rejected"
    assert not rejected.executed_effects


def test_opportunity_windows_are_endogenous_observable_and_change_attention():
    world = create_full_lifecycle_world(42, "windows")
    engine = SimulationEngine(world)
    engine.run(2)
    assert world.opportunity_windows
    assert any(item.kind == "major_meeting" for item in world.opportunity_windows)
    assert any(event.kind == "opportunity_window" for event in world.events)
    assert any(state.attention_budget > 2 for state in world.organization_processes.values())


def test_three_vetoes_change_next_plan_and_create_transferable_lesson():
    class PersistentNegotiator(DeterministicCognition):
        def respond_to_offer(self, agent, observation, memories):
            return EnterpriseResponseAction(
                response="counter", counter_terms={"require_phased_delivery": 1.0},
                confidence=0.8, rationale="继续检验政府适应能力",
            )

        def decide_negotiation_timing(self, agent, observation, memories):
            return NegotiationTimingAction(
                decision="continue_negotiating", confidence=0.8,
                rationale="为组织学习实验继续谈判",
            )

    world = create_full_lifecycle_world(42, "learning-after-veto")
    world.negotiation_round_limit = 8
    SimulationEngine(world, cognition=PersistentNegotiator()).run(5)
    learning = world.organization_learning["city_lin_investment"]
    assert learning.veto_count >= 3
    assert any("连续财政否决" in item for item in learning.transferable_lessons)
    plans = [
        plan for plan in world.organization_plans
        if plan.actor_id == "city_lin_investment"
    ]
    assert len(plans) >= 2
    assert plans[-1].selected_strategy == "phased_adaptation"
    assert any(node.action_id == "propose_open_action" for node in plans[-1].nodes)


def test_leadership_change_partially_inherits_memory_but_keeps_institutional_learning():
    world = create_full_lifecycle_world(42, "succession")
    leader = world.agents["city_lin_leader"]
    for index in range(6):
        leader.memories.append(MemoryRecord(
            id=f"m{index}", quarter=0, kind="case", content=f"经验{index}",
            importance=0.8,
        ))
    dynamics = OrganizationDynamics(world)
    learning = dynamics.learning(leader.id)
    learning.routines["broker_compromise"] = 0.8
    for quarter in range(1, 10):
        world.quarter = quarter
        dynamics.advance_opportunity_windows()
        if learning.leadership_generation > 1:
            break
    assert learning.leadership_generation == 2
    assert learning.inherited_memory_ratio == 0.6
    assert len(leader.memories) < 6
    assert learning.routines["broker_compromise"] == 0.8
