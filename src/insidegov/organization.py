from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass

from .models import (
    AgentRole,
    AgentState,
    CityState,
    OrganizationActionRecord,
    OrganizationPlan,
    OrganizationPlanNode,
    OrganizationProcessState,
    ProcessMode,
    WorldState,
)
from .organization_dynamics import OrganizationDynamics

BEHAVIOR_EVIDENCE = {
    "formal_procedure": {
        "title": "《重大行政决策程序暂行条例》答记者问",
        "url": "https://www.moj.gov.cn/pub/sfbgw/zcjd/201905/t20190516_390231.html",
        "claim": "重大行政决策以公众参与、专家论证、风险评估、合法性审查和集体讨论构成程序链；合法性审查与集体讨论是刚性程序。",
    },
    "fund_independence": {
        "title": "国务院办公厅关于促进政府投资基金高质量发展的指导意见",
        "url": "https://www.mee.gov.cn/zcwj/gwywj/202501/t20250108_1100235.shtml",
        "claim": "政府投资基金应市场化、法治化、专业化运作，建立独立投资决策和尽职调查机制，行政部门不得干预具体项目投资决策。",
    },
    "informal_networks": {
        "title": "Policy Experimentation within Bureaucratic Power Networks",
        "url": "https://www.cambridge.org/core/journals/china-quarterly/article/policy-experimentation-within-bureaucratic-power-networks-the-policebusiness-cooperation-scheme-in-urban-china/6E7E2E1536065118E626082F0CFF58E8",
        "claim": "政策企业家通过对上议程建议、对同级修辞联盟和对下支持性指导，弥补正式权力网络在议程、协调和执行上的不足。",
    },
    "attention": {
        "title": "Competition for attention in the Chinese bureaucracy",
        "url": "https://link.springer.com/article/10.1186/s40711-018-0071-z",
        "claim": "科层组织中的政策推进受到有限注意力与议题竞争影响，议程优先级不是固定常量。",
    },
}


@dataclass(frozen=True, slots=True)
class ActionDefinition:
    id: str
    name: str
    roles: tuple[AgentRole, ...]
    arenas: tuple[str, ...]
    rationale: str
    evidence_ids: tuple[str, ...]


ACTION_CATALOG: dict[str, ActionDefinition] = {
    item.id: item for item in (
        ActionDefinition("request_materials", "要求补充项目材料", (AgentRole.INVESTMENT,), ("formal",), "先降低信息缺口，再形成正式方案", ("formal_procedure",)),
        ActionDefinition("clarify_need", "澄清企业真实需求", (AgentRole.INVESTMENT,), ("formal", "informal"), "避免把表面诉求直接翻译为补贴", ("formal_procedure",)),
        ActionDefinition("preconsult_finance", "与财政局会前沟通", (AgentRole.INVESTMENT,), ("informal",), "在正式送审前探测可执行边界", ("informal_networks",)),
        ActionDefinition("frame_strategic_project", "将项目上推为战略议题", (AgentRole.INVESTMENT,), ("informal",), "争取有限的领导注意力和跨部门资源", ("informal_networks", "attention")),
        ActionDefinition("mobilize_park_coalition", "联合园区形成同级联盟", (AgentRole.INVESTMENT, AgentRole.PARK), ("informal",), "用产业与执行证据扩大同级支持", ("informal_networks",)),
        ActionDefinition("verify_site_readiness", "核验园区承载条件", (AgentRole.PARK,), ("formal",), "核验土地、建设和配套条件是否满足正式承诺", ("formal_procedure",)),
        ActionDefinition("risk_assessment", "开展财政风险评估", (AgentRole.FINANCE,), ("formal",), "根据真实财政状态选择风险政策", ("formal_procedure",)),
        ActionDefinition("disclose_fiscal_boundary", "非正式披露财政边界", (AgentRole.FINANCE,), ("informal",), "减少后续正式否决的协调成本", ("informal_networks",)),
        ActionDefinition("negotiate_phasing", "协商分期与条件", (AgentRole.FINANCE,), ("informal",), "把总额冲突转化为现金流和条件设计", ("informal_networks",)),
        ActionDefinition("legality_review", "进行合法性审查", (AgentRole.LEGAL,), ("formal",), "检查权限、程序和承诺可执行性", ("formal_procedure",)),
        ActionDefinition("collective_deliberation", "提交集体讨论", (AgentRole.CITY_LEADER,), ("formal",), "由集体讨论形成可追责的最终意见", ("formal_procedure",)),
        ActionDefinition("broker_compromise", "领导居中协调工具组合", (AgentRole.CITY_LEADER,), ("informal",), "在招商目标与财政底线之间重组政策工具", ("informal_networks",)),
        ActionDefinition("authorize_pilot", "授权小规模试点", (AgentRole.CITY_LEADER,), ("informal",), "用可逆试点替代一次性全面承诺", ("informal_networks",)),
        ActionDefinition("propose_open_action", "提出目录外组织手段", (AgentRole.INVESTMENT, AgentRole.FINANCE, AgentRole.PARK, AgentRole.CITY_LEADER), ("informal",), "提出新的组织手段，并接受职责、资源与状态效果审查", ("informal_networks", "attention")),
        ActionDefinition("fiscal_guardrail", "执行财政硬约束检查", (AgentRole.FINANCE,), ("control",), "无论程序模式如何，均不得突破财政与现金流硬边界", ("formal_procedure",)),
        ActionDefinition("fund_due_diligence", "产业基金独立尽调", (AgentRole.FUND,), ("formal", "informal"), "基金依据项目质量和自身风控独立决定", ("fund_independence",)),
    )
}


ROLE_ACTIONS: dict[AgentRole, tuple[str, ...]] = {
    role: tuple(item.id for item in ACTION_CATALOG.values() if role in item.roles)
    for role in AgentRole
}


def playable_actions(world: WorldState, actor_id: str) -> list[dict[str, object]]:
    """Return role- and arena-valid moves for a first-person experience.

    This is deliberately derived from the same catalog used by the authority
    engine.  The public UI therefore cannot invent a capability that the
    underlying organization does not possess.
    """
    actor = world.agents.get(actor_id)
    if actor is None:
        return []
    mode = ProcessMode(world.process_mode)
    results = []
    for action_id in ROLE_ACTIONS.get(actor.role, ()):
        definition = ACTION_CATALOG[action_id]
        if action_id in {"fiscal_guardrail", "fund_due_diligence"}:
            continue
        if mode != ProcessMode.HYBRID and mode.value not in definition.arenas:
            continue
        results.append({
            "id": definition.id,
            "name": definition.name,
            "arena": " / ".join(definition.arenas),
            "rationale": definition.rationale,
            "evidence_ids": list(definition.evidence_ids),
        })
    return results


@dataclass(slots=True)
class OrganizationRoundEffects:
    proposal_aggressiveness: float = 1.0
    equity_shift: float = 0.0
    finance_multiplier: float = 1.0
    approval_speed_bonus: float = 0.0
    credibility_delta: float = 0.0
    action_ids: list[str] | None = None
    offer_authorized: bool = False
    procedure_transition: str = "not_started"
    procedure_status: str = "dormant"


class OrganizationProcessEngine:
    """Selects organization moves while leaving state settlement to hard rules."""

    def __init__(
        self,
        world: WorldState,
        random_source: random.Random,
        initiative_selector: Callable[
            [str, list[str], dict[str, object]],
            tuple[str, str, float, str | None, str, str, bool],
        ] | None = None,
        transition_selector: Callable[
            [str, list[str], dict[str, float | bool | str]],
            tuple[str, str, str, bool],
        ] | None = None,
        plan_selector: Callable[
            [str, list[str], dict[str, object]], tuple[dict[str, object], str, bool]
        ] | None = None,
        novel_action_selector: Callable[
            [str, dict[str, object]], tuple[dict[str, object], str, bool]
        ] | None = None,
    ):
        self.world = world
        self.random = random_source
        self.initiative_selector = initiative_selector
        self.transition_selector = transition_selector
        self.plan_selector = plan_selector
        self.novel_action_selector = novel_action_selector
        self.dynamics = OrganizationDynamics(world)
        self._round_plan_context: dict[
            str, tuple[OrganizationPlan | None, OrganizationPlanNode | None, dict[str, object]]
        ] = {}

    def advance_opportunity_windows(self):
        return self.dynamics.advance_opportunity_windows()

    def record_veto(self, city_id: str, rationale: str) -> None:
        self.dynamics.record_veto(city_id, rationale)

    def record_successful_coordination(self, city_id: str) -> None:
        self.dynamics.record_successful_coordination(city_id)

    def record_enterprise_response(self, city_id: str, response: str) -> None:
        self.dynamics.record_enterprise_response(city_id, response)

    def run_round(self, city: CityState) -> OrganizationRoundEffects:
        mode = ProcessMode(self.world.process_mode)
        state = self.world.organization_processes.setdefault(
            city.id, OrganizationProcessState(city_id=city.id)
        )
        self._round_plan_context = {}
        effects = OrganizationRoundEffects(action_ids=[])
        nominations = self._collect_initiatives(city, state, mode)
        active = [item for item in nominations if item[1] == "act"]
        active.sort(key=lambda item: item[3], reverse=True)
        selected_keys = {
            (item[0], item[2]) for item in active[: max(1, state.attention_budget)]
        }
        sequence = 0
        for actor_id, decision, action_id, urgency, target_id, selection_meta, candidates in nominations:
            plan, plan_node, actor_observation = self._round_plan_context.get(
                actor_id, (None, None, {})
            )
            if decision == "wait":
                record = self._initiative_record(
                    city, state, actor_id, "wait", "wait", urgency, target_id,
                    selection_meta, candidates, 0, "本轮主动等待",
                )
                self.dynamics.review_plan_action(plan, plan_node, record)
                self.dynamics.learn_from_action(record)
                self.world.organization_actions.append(record)
                continue
            if (actor_id, action_id) not in selected_keys:
                record = self._initiative_record(
                    city, state, actor_id, action_id, "deferred", urgency, target_id,
                    selection_meta, candidates, 0, "组织注意力预算不足，顺延至后续轮次",
                )
                self.dynamics.review_plan_action(plan, plan_node, record)
                self.dynamics.learn_from_action(record)
                self.world.organization_actions.append(record)
                continue
            sequence += 1
            if action_id == "propose_open_action":
                record = self._execute_open_action(
                    city, state, actor_id, candidates, actor_observation,
                    selection_meta, sequence, urgency, target_id,
                )
            else:
                record = self._execute(
                    city, state, actor_id, action_id, False, selection_meta,
                    stage="initiative", sequence=sequence, urgency=urgency,
                    target_actor_id=target_id,
                )
            self.dynamics.review_plan_action(plan, plan_node, record)
            self.dynamics.learn_from_action(record)
            self.world.organization_actions.append(record)
            effects.action_ids.append(record.action_id)
            self._merge_effects(effects, record.effects)

        transition, transition_meta = self._choose_transition(city, state, mode)
        sequence += 1
        transition_record = self._transition_record(
            city, state, transition, transition_meta, sequence
        )
        self.world.organization_actions.append(transition_record)
        self.dynamics.learn_from_action(transition_record)
        effects.action_ids.append(transition)
        effects.procedure_transition = transition
        effects.offer_authorized = self._apply_transition(state, transition)
        state.last_transition_quarter = self.world.quarter

        required: list[tuple[str, str]] = []
        if effects.offer_authorized and mode in {ProcessMode.FORMAL, ProcessMode.HYBRID}:
            required = [
                (f"{city.id}_finance", "risk_assessment"),
                (f"{city.id}_legal", "legality_review"),
                (f"{city.id}_leader", "collective_deliberation"),
            ]
        elif effects.offer_authorized:
            required = [(f"{city.id}_finance", "fiscal_guardrail")]
        for actor_id, action_id in required:
            sequence += 1
            record = self._execute(
                city, state, actor_id, action_id, True,
                ("程序一旦获准推进即进入不可跳过的硬检查", "rule_engine", False),
                stage="formal_gate", sequence=sequence,
            )
            self.world.organization_actions.append(record)
            self.dynamics.learn_from_action(record)
            effects.action_ids.append(action_id)
            self._merge_effects(effects, record.effects)
        if effects.offer_authorized:
            state.formal_status = "completed"
            state.paused_reason = None
        effects.procedure_status = state.formal_status

        posture_factor = {"conservative": 0.86, "balanced": 1.0, "developmental": 1.08}
        effects.finance_multiplier = posture_factor[state.risk_posture]
        if mode == ProcessMode.INFORMAL and state.procedural_completeness < 0.45:
            effects.credibility_delta -= 0.018
        elif state.procedural_completeness >= 0.7:
            effects.credibility_delta += 0.012
        return effects

    def _collect_initiatives(
        self, city: CityState, state: OrganizationProcessState, mode: ProcessMode,
    ) -> list[tuple[str, str, str, float, str | None, tuple[str, str, bool], list[str]]]:
        pools = {
            f"{city.id}_investment": ["request_materials", "clarify_need"] if mode == ProcessMode.FORMAL else ["preconsult_finance", "frame_strategic_project", "clarify_need"],
            f"{city.id}_park": ["verify_site_readiness"] if mode == ProcessMode.FORMAL else ["mobilize_park_coalition"],
            f"{city.id}_finance": ["risk_assessment"] if mode == ProcessMode.FORMAL else ["disclose_fiscal_boundary", "negotiate_phasing"],
            f"{city.id}_leader": ["collective_deliberation"] if mode == ProcessMode.FORMAL else ["broker_compromise", "authorize_pilot"],
        }
        base_observation: dict[str, object] = {
            "quarter": float(self.world.quarter),
            "fiscal_pressure": round(city.fiscal_pressure, 3),
            "agenda_priority": round(state.agenda_priority, 3),
            "coalition_support": round(state.coalition_support, 3),
            "procedural_completeness": round(state.procedural_completeness, 3),
            "finance_preconsulted": state.finance_preconsulted,
            "negotiation_pressure": min(1.0, self.world.quarter / 4),
        }
        result = []
        for actor_id, base_candidates in pools.items():
            actor = self.world.agents[actor_id]
            allowed_actions = [
                action_id for action_id in ROLE_ACTIONS[actor.role]
                if action_id != "fund_due_diligence" and (
                    mode == ProcessMode.HYBRID
                    or mode.value in ACTION_CATALOG[action_id].arenas
                )
            ]
            if mode != ProcessMode.FORMAL and "propose_open_action" not in allowed_actions:
                allowed_actions.append("propose_open_action")
            if not allowed_actions:
                allowed_actions = list(base_candidates)
            windows = [
                {
                    "id": item.id, "kind": item.kind, "title": item.title,
                    "magnitude": item.magnitude, "effects": dict(item.effects),
                }
                for item in self.dynamics.active_windows(city.id, actor_id)
            ]
            learning = self.dynamics.learning_context(actor_id)
            planning_observation = {
                **base_observation,
                "active_windows": windows,
                **learning,
            }
            plan = self._ensure_plan(actor_id, city.id, allowed_actions, planning_observation)
            plan_node = self.dynamics.current_plan_node(plan) if plan else None
            candidates = [item for item in base_candidates if item in allowed_actions]
            directive = next((
                item for item in self.world.experience_directives
                if item.get("actor_id") == actor_id
                and item.get("status") == "pending"
                and int(item.get("execute_quarter", self.world.quarter)) <= self.world.quarter
            ), None)
            if directive and directive.get("action_id") in allowed_actions:
                requested = str(directive["action_id"])
                if requested not in candidates:
                    candidates.append(requested)
            if mode != ProcessMode.FORMAL and "propose_open_action" not in candidates:
                candidates.append("propose_open_action")
            if plan_node and plan_node.action_id in allowed_actions and plan_node.action_id not in candidates:
                candidates.append(plan_node.action_id)
            observation = {
                **planning_observation,
                "plan_id": plan.id if plan else None,
                "plan_objective": plan.objective if plan else None,
                "plan_selected_strategy": plan.selected_strategy if plan else None,
                "plan_current_node": plan_node.id if plan_node else None,
                "plan_current_action": plan_node.action_id if plan_node else None,
                "plan_preconditions": plan_node.preconditions if plan_node else [],
            }
            self._round_plan_context[actor_id] = (plan, plan_node, observation)
            if self.initiative_selector:
                decision, action_id, urgency, target_id, rationale, provider, fallback = (
                    self.initiative_selector(actor_id, candidates, observation)
                )
            else:
                decision, action_id, urgency, target_id = "act", candidates[0], 0.6, None
                rationale, provider, fallback = "按角色目标主动发起", "scheduler", False
            if decision not in {"act", "wait"}:
                decision = "wait"
            if decision == "act" and action_id not in candidates:
                decision, action_id = "wait", "wait"
                rationale = f"模型动作不在角色权限内，规则引擎改为等待；{rationale}"
            if decision == "wait":
                action_id = "wait"
            result.append((
                actor_id, decision, action_id, min(1.0, max(0.0, urgency)),
                target_id, (rationale, provider, fallback), candidates,
            ))
        return result

    def _ensure_plan(
        self, actor_id: str, city_id: str, allowed_actions: list[str],
        observation: dict[str, object],
    ) -> OrganizationPlan | None:
        plan = self.dynamics.active_plan(actor_id)
        if plan or not self.plan_selector:
            return plan
        payload, provider, fallback = self.plan_selector(actor_id, allowed_actions, observation)
        return self.dynamics.create_plan(
            actor_id, city_id, payload, allowed_actions, provider, fallback
        )

    def _transition_candidates(
        self, state: OrganizationProcessState, mode: ProcessMode,
    ) -> list[str]:
        status = state.formal_status
        if mode == ProcessMode.INFORMAL:
            return ["authorize_informal_offer", "continue_informal_coordination", "abandon_proposal"]
        if status == "dormant":
            values = ["start_formal_process", "pause_formal_process", "return_for_revision"]
        elif status == "completed":
            values = ["re_agenda", "keep_closed"]
        elif status in {"paused", "returned"}:
            values = ["resume_formal_process", "re_agenda", "abandon_proposal"]
        else:
            values = ["proceed_formal_review", "pause_formal_process", "return_for_revision"]
        if mode == ProcessMode.HYBRID:
            values.append("continue_informal_coordination")
        return values

    def _choose_transition(
        self, city: CityState, state: OrganizationProcessState, mode: ProcessMode,
    ) -> tuple[str, tuple[str, str, bool]]:
        candidates = self._transition_candidates(state, mode)
        observation: dict[str, float | bool | str] = {
            "quarter": float(self.world.quarter),
            "formal_status": state.formal_status,
            "agenda_priority": round(state.agenda_priority, 3),
            "coalition_support": round(state.coalition_support, 3),
            "procedural_completeness": round(state.procedural_completeness, 3),
            "fiscal_pressure": round(city.fiscal_pressure, 3),
            "return_count": float(state.return_count),
        }
        if self.transition_selector:
            selected, rationale, provider, fallback = self.transition_selector(
                f"{city.id}_leader", candidates, observation
            )
            if selected in candidates:
                return selected, (rationale, provider, fallback)
        return candidates[0], ("按当前程序状态进入下一合法节点", "scheduler", False)

    @staticmethod
    def _apply_transition(state: OrganizationProcessState, transition: str) -> bool:
        state.last_transition = transition
        if transition in {
            "start_formal_process", "resume_formal_process", "re_agenda",
            "proceed_formal_review", "authorize_informal_offer",
        }:
            state.formal_status = "active"
            return True
        if transition == "pause_formal_process":
            state.formal_status = "paused"
            state.paused_reason = "领导基于风险或协调成熟度主动暂停"
        elif transition == "return_for_revision":
            state.formal_status = "returned"
            state.return_count += 1
            state.paused_reason = "退回补充材料或重组方案"
        elif transition == "continue_informal_coordination":
            state.formal_status = "paused"
            state.paused_reason = "正式程序暂缓，继续非正式协调"
        elif transition == "abandon_proposal":
            state.formal_status = "abandoned"
            state.paused_reason = "本轮议题退出议程"
        return False

    def _initiative_record(
        self, city: CityState, state: OrganizationProcessState, actor_id: str,
        action_id: str, decision: str, urgency: float, target_actor_id: str | None,
        selection_meta: tuple[str, str, bool], candidates: list[str], sequence: int,
        blocked_reason: str,
    ) -> OrganizationActionRecord:
        definition = ACTION_CATALOG.get(action_id)
        actor = self.world.agents[actor_id]
        return OrganizationActionRecord(
            id=f"org-action-{len(self.world.organization_actions)+1:05d}",
            quarter=self.world.quarter, city_id=city.id, actor_id=actor_id,
            actor_role=actor.role.value, action_id=action_id,
            action_name=definition.name if definition else "暂不发起行动",
            arena="initiative", process_mode=self.world.process_mode,
            candidates=candidates, observations=self._state_observation(city, state),
            rationale=selection_meta[0], effects={}, required=False,
            authorized=False, blocked_reason=blocked_reason,
            evidence_ids=list(definition.evidence_ids) if definition else ["attention"],
            selection_provider=selection_meta[1], selection_rationale=selection_meta[0],
            fallback=selection_meta[2], stage="initiative", sequence=sequence,
            decision=decision, target_actor_id=target_actor_id, urgency=urgency,
        )

    def _transition_record(
        self, city: CityState, state: OrganizationProcessState, transition: str,
        selection_meta: tuple[str, str, bool], sequence: int,
    ) -> OrganizationActionRecord:
        names = {
            "start_formal_process": "启动正式程序", "pause_formal_process": "暂停正式程序",
            "return_for_revision": "退回修改", "re_agenda": "重新议程化",
            "resume_formal_process": "恢复正式程序", "keep_closed": "维持结案",
            "abandon_proposal": "退出本轮议程", "proceed_formal_review": "进入正式审议",
            "authorize_informal_offer": "授权非正式方案进入报价",
            "continue_informal_coordination": "继续非正式协调",
        }
        return OrganizationActionRecord(
            id=f"org-action-{len(self.world.organization_actions)+1:05d}",
            quarter=self.world.quarter, city_id=city.id,
            actor_id=f"{city.id}_leader", actor_role=AgentRole.CITY_LEADER.value,
            action_id=transition, action_name=names[transition], arena="procedure",
            process_mode=self.world.process_mode,
            candidates=self._transition_candidates(state, ProcessMode(self.world.process_mode)),
            observations=self._state_observation(city, state), rationale=selection_meta[0],
            effects={}, required=False, evidence_ids=["formal_procedure", "attention"],
            selection_provider=selection_meta[1], selection_rationale=selection_meta[0],
            fallback=selection_meta[2], stage="procedure_transition", sequence=sequence,
            decision=transition, urgency=state.agenda_priority,
        )

    @staticmethod
    def _state_observation(
        city: CityState, state: OrganizationProcessState,
    ) -> dict[str, float | bool | str]:
        return {
            "fiscal_pressure": round(city.fiscal_pressure, 3),
            "agenda_priority": round(state.agenda_priority, 3),
            "coalition_support": round(state.coalition_support, 3),
            "procedural_completeness": round(state.procedural_completeness, 3),
            "formal_status": state.formal_status,
        }

    def _execute_open_action(
        self, city: CityState, state: OrganizationProcessState, actor_id: str,
        candidates: list[str], observation: dict[str, object],
        selection_meta: tuple[str, str, bool], sequence: int, urgency: float,
        target_actor_id: str | None,
    ) -> OrganizationActionRecord:
        if self.novel_action_selector:
            payload, provider, fallback = self.novel_action_selector(actor_id, observation)
        else:
            payload = {
                "title": "建立跨部门临时工作组",
                "mechanism": "cross_department_taskforce",
                "target_actor_id": f"{city.id}_leader",
                "requested_effects": {"coalition_support_delta": 0.08},
                "resource_request": {},
                "rationale": "用临时协调结构降低信息损耗",
            }
            provider, fallback = "scheduler", False
        proposal = self.dynamics.validate_open_action(
            actor_id, city.id, payload, provider, fallback
        )
        actor = self.world.agents[actor_id]
        state.action_sequence.append(f"novel:{proposal.mechanism}")
        return OrganizationActionRecord(
            id=f"org-action-{len(self.world.organization_actions)+1:05d}",
            quarter=self.world.quarter, city_id=city.id, actor_id=actor_id,
            actor_role=actor.role.value, action_id="propose_open_action",
            action_name=proposal.title, arena="informal",
            process_mode=self.world.process_mode, candidates=candidates,
            observations={**self._state_observation(city, state), "novel_mechanism": proposal.mechanism},
            rationale=proposal.rationale, effects=dict(proposal.executed_effects),
            required=False, authorized=proposal.status == "authorized",
            blocked_reason=None if proposal.status == "authorized" else proposal.validation_reason,
            evidence_ids=["informal_networks", "attention"],
            selection_provider=provider,
            selection_rationale=(
                f"{selection_meta[0]}；开放行动审查：{proposal.validation_reason}"
            ),
            fallback=fallback, stage="initiative", sequence=sequence,
            decision="act", target_actor_id=proposal.target_actor_id or target_actor_id,
            urgency=urgency, open_action_proposal_id=proposal.id,
        )

    def _execute(
        self, city: CityState, state: OrganizationProcessState,
        actor_id: str, action_id: str, required: bool,
        selection_meta: tuple[str, str, bool],
        *, stage: str = "coordination", sequence: int = 0,
        urgency: float = 0.5, target_actor_id: str | None = None,
    ) -> OrganizationActionRecord:
        definition = ACTION_CATALOG[action_id]
        actor = self.world.agents[actor_id]
        arena = "control" if action_id == "fiscal_guardrail" else (
            "formal" if "formal" in definition.arenas and action_id in {
                "request_materials", "verify_site_readiness", "risk_assessment", "legality_review",
                "collective_deliberation", "fund_due_diligence",
            } else "informal"
        )
        if action_id == "clarify_need":
            arena = "formal" if self.world.process_mode == ProcessMode.FORMAL else "informal"
        candidates = [
            item for item in ROLE_ACTIONS[actor.role]
            if arena in ACTION_CATALOG[item].arenas or (
                arena == "control" and "control" in ACTION_CATALOG[item].arenas
            )
        ]
        effects = self._effects(city, state, actor, action_id)
        state.action_sequence.append(action_id)
        return OrganizationActionRecord(
            id=f"org-action-{len(self.world.organization_actions)+1:05d}",
            quarter=self.world.quarter,
            city_id=city.id,
            actor_id=actor_id,
            actor_role=actor.role.value,
            action_id=action_id,
            action_name=definition.name,
            arena=arena,
            process_mode=self.world.process_mode,
            candidates=candidates,
            observations={
                "fiscal_pressure": round(city.fiscal_pressure, 3),
                "agenda_priority": round(state.agenda_priority, 3),
                "coalition_support": round(state.coalition_support, 3),
                "procedural_completeness": round(state.procedural_completeness, 3),
            },
            rationale=definition.rationale,
            effects=effects,
            required=required,
            evidence_ids=list(definition.evidence_ids),
            selection_rationale=selection_meta[0],
            selection_provider=selection_meta[1],
            fallback=selection_meta[2],
            stage=stage,
            sequence=sequence,
            decision="act",
            target_actor_id=target_actor_id,
            urgency=urgency,
        )

    def _effects(
        self, city: CityState, state: OrganizationProcessState,
        actor: AgentState, action_id: str,
    ) -> dict[str, float]:
        effects: dict[str, float] = {}
        if action_id == "request_materials":
            state.procedural_completeness = min(1.0, state.procedural_completeness + 0.12)
            effects["approval_speed_bonus"] = -0.025
        elif action_id == "verify_site_readiness":
            state.procedural_completeness = min(1.0, state.procedural_completeness + 0.1)
            effects["approval_speed_bonus"] = 0.015
        elif action_id == "clarify_need":
            state.procedural_completeness = min(1.0, state.procedural_completeness + 0.1)
            effects["credibility_delta"] = 0.006
        elif action_id == "preconsult_finance":
            state.finance_preconsulted = True
            state.relationships["investment-finance"] = min(
                1.0, state.relationships.get("investment-finance", 0.42) + 0.1
            )
            effects["equity_shift"] = 0.08
        elif action_id == "frame_strategic_project":
            state.agenda_priority = min(1.0, state.agenda_priority + 0.16)
            effects["proposal_aggressiveness"] = 0.06
        elif action_id == "mobilize_park_coalition":
            state.coalition_support = min(1.0, state.coalition_support + 0.14)
            effects["approval_speed_bonus"] = 0.035
        elif action_id == "risk_assessment":
            state.procedural_completeness = min(1.0, state.procedural_completeness + 0.24)
            risk = city.fiscal_pressure + actor.traits.get("risk_aversion", 0.7) * 0.45
            if risk > 0.76:
                state.risk_posture = "conservative"
            elif (
                state.finance_preconsulted
                and state.coalition_support > 0.44
                and risk < 0.72
            ):
                state.risk_posture = "developmental"
            else:
                state.risk_posture = "balanced"
        elif action_id == "disclose_fiscal_boundary":
            state.finance_preconsulted = True
            state.relationships["investment-finance"] = min(
                1.0, state.relationships.get("investment-finance", 0.42) + 0.08
            )
            effects["proposal_aggressiveness"] = -0.04
        elif action_id == "negotiate_phasing":
            state.finance_preconsulted = True
            effects["equity_shift"] = 0.12
        elif action_id == "legality_review":
            state.legal_reviewed = True
            state.procedural_completeness = min(1.0, state.procedural_completeness + 0.28)
            state.legitimacy = min(1.0, state.legitimacy + 0.06)
        elif action_id == "collective_deliberation":
            state.collective_deliberated = True
            state.procedural_completeness = min(1.0, state.procedural_completeness + 0.24)
            state.legitimacy = min(1.0, state.legitimacy + 0.05)
        elif action_id == "broker_compromise":
            state.coalition_support = min(1.0, state.coalition_support + 0.1)
            effects["equity_shift"] = 0.1
        elif action_id == "authorize_pilot":
            state.pilot_authorized = True
            effects["proposal_aggressiveness"] = -0.05
            effects["approval_speed_bonus"] = 0.05
        elif action_id == "fiscal_guardrail":
            # Without a formal risk and legality file, finance applies a precautionary
            # haircut. This changes a policy choice, never the underlying budget.
            state.risk_posture = (
                "conservative" if not state.legal_reviewed else "balanced"
            )
        return effects

    @staticmethod
    def _merge_effects(target: OrganizationRoundEffects, effects: dict[str, float]) -> None:
        target.proposal_aggressiveness += effects.get("proposal_aggressiveness", 0.0)
        target.equity_shift += effects.get("equity_shift", 0.0)
        target.approval_speed_bonus += effects.get("approval_speed_bonus", 0.0)
        target.credibility_delta += effects.get("credibility_delta", 0.0)


def behavior_evidence_payload() -> list[dict[str, str]]:
    return [{"id": key, **value} for key, value in BEHAVIOR_EVIDENCE.items()]


def action_catalog_payload() -> list[dict[str, object]]:
    return [
        {
            "id": item.id,
            "name": item.name,
            "roles": [role.value for role in item.roles],
            "arenas": list(item.arenas),
            "rationale": item.rationale,
            "evidence_ids": list(item.evidence_ids),
        }
        for item in ACTION_CATALOG.values()
    ]
