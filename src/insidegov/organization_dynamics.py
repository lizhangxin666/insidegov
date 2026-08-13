from __future__ import annotations

import random
from dataclasses import asdict
from typing import Any

from .models import (
    AgentRole,
    Event,
    OpenActionProposal,
    OpportunityWindow,
    OrganizationActionRecord,
    OrganizationLearningState,
    OrganizationPlan,
    OrganizationPlanNode,
    OrganizationProcessState,
    PlanStrategyOption,
    WorldState,
)

ROLE_MECHANISMS: dict[AgentRole, set[str]] = {
    AgentRole.INVESTMENT: {
        "upward_endorsement", "association_coalition", "demonstration_project",
        "meeting_window", "strategic_delay", "expert_consultation",
    },
    AgentRole.PARK: {
        "association_coalition", "demonstration_project", "strategic_delay",
        "expert_consultation",
    },
    AgentRole.FINANCE: {"strategic_delay", "expert_consultation"},
    AgentRole.CITY_LEADER: {
        "upward_endorsement", "demonstration_project", "meeting_window",
        "strategic_delay", "cross_department_taskforce", "expert_consultation",
    },
    AgentRole.LEGAL: {"strategic_delay", "expert_consultation"},
}

EFFECT_CAPS: dict[str, float] = {
    "agenda_priority_delta": 0.18,
    "coalition_support_delta": 0.15,
    "procedural_completeness_delta": 0.10,
    "approval_speed_bonus": 0.05,
    "credibility_delta": 0.012,
    "attention_budget_delta": 1.0,
}


class OrganizationDynamics:
    """Plans, political opportunity windows, permission checks and learning."""

    def __init__(self, world: WorldState):
        self.world = world

    def advance_opportunity_windows(self) -> list[OpportunityWindow]:
        quarter = self.world.quarter
        for window in self.world.opportunity_windows:
            if window.status == "active" and window.end_quarter < quarter:
                window.status = "closed"
        created: list[OpportunityWindow] = []
        for city_index, (city_id, city) in enumerate(self.world.cities.items()):
            state = self.world.organization_processes.setdefault(
                city_id, OrganizationProcessState(city_id=city_id)
            )
            state.attention_budget = 2
            schedule = random.Random(f"insidegov:window-schedule:{self.world.seed}:{city_id}")
            meeting_quarter = 1 + schedule.randrange(4)
            leadership_quarter = 4 + schedule.randrange(5)
            candidates: list[tuple[str, str, float, str, dict[str, float]]] = []
            if (quarter - meeting_quarter) % 4 == 0:
                candidates.append((
                    "major_meeting", "重大会议形成集中议程窗口", 0.72,
                    f"城市年度会议日历：第{meeting_quarter}模4季度",
                    {"agenda_priority_delta": 0.10, "attention_budget_delta": 1.0},
                ))
            superior_rng = random.Random(
                f"insidegov:superior-policy:{self.world.seed}:{city_id}:q{quarter}"
            )
            if superior_rng.random() < 0.20:
                candidates.append((
                    "superior_policy", "上级产业政策释放支持信号", 0.65,
                    "上级政策流中的可观察信号",
                    {"agenda_priority_delta": 0.12, "coalition_support_delta": 0.05},
                ))
            competing = [
                other.id for other in self.world.cities.values()
                if other.id != city_id and other.active_offer is not None
            ]
            if competing:
                candidates.append((
                    "competing_city_offer", "竞争城市报价打开抢签窗口", 0.7,
                    f"可观察到竞争城市已报价：{','.join(competing)}",
                    {"agenda_priority_delta": 0.14, "attention_budget_delta": 1.0},
                ))
            if city.fiscal_pressure > 0.62:
                candidates.append((
                    "fiscal_pressure", "财政收入与承诺压力收窄政策窗口", city.fiscal_pressure,
                    "财政账本中的压力指标超过0.62",
                    {"agenda_priority_delta": -0.08},
                ))
            incident_rng = random.Random(
                f"insidegov:public-attention:{self.world.seed}:{city_id}:q{quarter}"
            )
            if incident_rng.random() < 0.08:
                candidates.append((
                    "public_attention", "舆情事件改变领导注意力配置", 0.58,
                    "外生公共注意力冲击",
                    {"agenda_priority_delta": 0.11, "coalition_support_delta": -0.04},
                ))
            if quarter == leadership_quarter:
                candidates.append((
                    "leadership_change", "部门负责人调整触发记忆继承", 0.8,
                    "世界生成时确定的任期节点",
                    {"agenda_priority_delta": -0.04},
                ))
            for kind, title, magnitude, trigger, effects in candidates:
                window_id = f"window-{city_id}-q{quarter}-{kind}"
                if any(item.id == window_id for item in self.world.opportunity_windows):
                    continue
                observed = [
                    agent_id for agent_id, agent in self.world.agents.items()
                    if agent.owner_id == city_id
                ]
                window = OpportunityWindow(
                    id=window_id, city_id=city_id, kind=kind, title=title,
                    start_quarter=quarter, end_quarter=quarter + (1 if kind != "major_meeting" else 0),
                    magnitude=round(magnitude, 3), source="world_state", trigger=trigger,
                    effects=effects, observed_by=observed,
                )
                self.world.opportunity_windows.append(window)
                created.append(window)
                self._apply_window(window, state)
                self.world.events.append(Event(
                    quarter, "opportunity_window", title,
                    f"{trigger}；状态影响 {effects}", city_id, severity="warning"
                    if kind in {"fiscal_pressure", "public_attention", "leadership_change"}
                    else "info",
                ))
        for city_id, state in self.world.organization_processes.items():
            active = self.active_windows(city_id)
            state.attention_budget = min(
                4,
                2 + sum(int(item.effects.get("attention_budget_delta", 0)) for item in active),
            )
        return created

    def active_windows(self, city_id: str, actor_id: str | None = None) -> list[OpportunityWindow]:
        return [
            item for item in self.world.opportunity_windows
            if item.status == "active"
            and item.start_quarter <= self.world.quarter <= item.end_quarter
            and item.city_id in {None, city_id}
            and (actor_id is None or not item.observed_by or actor_id in item.observed_by)
        ]

    def _apply_window(self, window: OpportunityWindow, state: OrganizationProcessState) -> None:
        if window.applied:
            return
        state.agenda_priority = min(
            1.0, max(0.0, state.agenda_priority + window.effects.get("agenda_priority_delta", 0))
        )
        state.coalition_support = min(
            1.0, max(0.0, state.coalition_support + window.effects.get("coalition_support_delta", 0))
        )
        if window.kind == "fiscal_pressure":
            state.risk_posture = "conservative"
        if window.kind == "leadership_change" and window.city_id:
            self._leadership_succession(window.city_id)
        window.applied = True

    def learning(self, agent_id: str) -> OrganizationLearningState:
        if agent_id not in self.world.organization_learning:
            self.world.organization_learning[agent_id] = OrganizationLearningState(
                agent_id=agent_id,
                trust_by_actor={
                    other_id: 0.5 for other_id, other in self.world.agents.items()
                    if other.owner_id == self.world.agents[agent_id].owner_id
                    and other_id != agent_id
                },
            )
        return self.world.organization_learning[agent_id]

    def learning_context(self, agent_id: str) -> dict[str, Any]:
        state = self.learning(agent_id)
        return {
            "trust_by_actor": dict(state.trust_by_actor),
            "firm_type_beliefs": dict(state.firm_type_beliefs),
            "veto_count": state.veto_count,
            "strategy_preferences": dict(state.strategy_preferences),
            "routines": dict(state.routines),
            "leadership_generation": state.leadership_generation,
            "recent_lessons": state.lessons[-5:],
            "transferable_lessons": state.transferable_lessons[-3:],
        }

    def create_plan(
        self, actor_id: str, city_id: str, payload: dict[str, Any],
        allowed_actions: list[str], provider: str, fallback: bool,
    ) -> OrganizationPlan:
        current = self.world.quarter
        alternatives = []
        for index, item in enumerate(payload.get("alternatives", []), start=1):
            if not isinstance(item, dict):
                continue
            alternatives.append(PlanStrategyOption(
                id=str(item.get("id") or f"strategy_{index}"),
                name=str(item.get("name") or item.get("id") or f"策略{index}"),
                approach=str(item.get("approach") or "分阶段推进"),
                benefits=list(item.get("benefits", [])),
                risks=list(item.get("risks", [])) or ([str(item["risk"])] if item.get("risk") else []),
                score=float(item.get("score") or 0.5),
            ))
        if not alternatives:
            alternatives = [
                PlanStrategyOption("fallback", "可执行路径", "按职责边界逐步推进", score=0.5)
            ]
        allowed = set(allowed_actions)
        raw_steps = payload.get("steps", [])
        if not raw_steps and isinstance(payload.get("action_sequence"), list):
            raw_steps = [
                {
                    "id": f"s{index}", "title": f"执行 {action_id}",
                    "action_id": action_id, "earliest_offset": index - 1,
                    "latest_offset": index + 1,
                    "preconditions": [] if index == 1 else [f"s{index-1}已完成或窗口发生"],
                    "on_success": f"s{index+1}" if index < len(payload["action_sequence"]) else None,
                    "on_failure": "replan", "expected_effects": {},
                }
                for index, action_id in enumerate(payload["action_sequence"], start=1)
            ]
        nodes: list[OrganizationPlanNode] = []
        for index, row in enumerate(raw_steps, start=1):
            action_id = str(row.get("action_id", ""))
            if action_id not in allowed:
                action_id = allowed_actions[0]
            earliest = current + int(row.get("earliest_offset", index - 1))
            latest = max(earliest, current + int(row.get("latest_offset", index + 1)))
            nodes.append(OrganizationPlanNode(
                id=str(row.get("id") or f"s{index}"),
                title=str(row.get("title") or action_id), action_id=action_id,
                earliest_quarter=earliest, latest_quarter=latest,
                preconditions=list(row.get("preconditions", [])),
                on_success=row.get("on_success"), on_failure=row.get("on_failure"),
                expected_effects={
                    key: float(value) for key, value in row.get("expected_effects", {}).items()
                    if isinstance(value, (int, float))
                },
            ))
        if not nodes:
            nodes = [
                OrganizationPlanNode("s1", allowed_actions[0], allowed_actions[0], current, current + 1),
                OrganizationPlanNode("s2", allowed_actions[-1], allowed_actions[-1], current + 1, current + 3),
            ]
        selected_strategy = str(payload.get("selected_strategy") or alternatives[0].id)
        if selected_strategy not in {item.id for item in alternatives}:
            selected_strategy = max(alternatives, key=lambda item: item.score).id
        plan = OrganizationPlan(
            id=f"plan-{len(self.world.organization_plans)+1:04d}",
            city_id=city_id, actor_id=actor_id, created_quarter=current,
            horizon_quarter=max(node.latest_quarter for node in nodes),
            objective=str(payload.get("objective") or "推进当前议题"),
            alternatives=alternatives,
            selected_strategy=selected_strategy,
            nodes=nodes,
            assumptions=[
                *list(payload.get("assumptions", [])),
                *([str(payload["branch_condition"])] if payload.get("branch_condition") else []),
            ],
            rationale=str(payload.get("rationale") or "根据当前状态选择可执行路径"),
            provider=provider, fallback=fallback,
        )
        self.world.organization_plans.append(plan)
        return plan

    def active_plan(self, actor_id: str) -> OrganizationPlan | None:
        for plan in reversed(self.world.organization_plans):
            if plan.actor_id == actor_id and plan.status == "active":
                if self.world.quarter > plan.horizon_quarter:
                    plan.status = "expired"
                    self._transfer_plan_lesson(plan, "计划超出期限，需重新规划")
                    continue
                return plan
        return None

    def current_plan_node(self, plan: OrganizationPlan) -> OrganizationPlanNode | None:
        for node in plan.nodes:
            if node.status == "pending" and self.world.quarter > node.latest_quarter:
                node.status = "deviated"
                node.deviation_reason = "超过计划最晚执行季度"
                plan.review_history.append({
                    "quarter": self.world.quarter, "node_id": node.id,
                    "outcome": "deadline_missed", "reason": node.deviation_reason,
                })
        pending = [node for node in plan.nodes if node.status == "pending"]
        if not pending:
            plan.status = "completed"
            self._transfer_plan_lesson(plan, "计划节点已完成或形成可解释偏离")
            return None
        for index, node in enumerate(plan.nodes):
            if node.status != "pending" or self.world.quarter < node.earliest_quarter:
                continue
            previous_ok = index == 0 or plan.nodes[index - 1].status in {"completed", "deviated", "skipped"}
            window_open = bool(self.active_windows(plan.city_id))
            if previous_ok or window_open:
                return node
        return pending[0] if pending[0].earliest_quarter <= self.world.quarter else None

    def review_plan_action(
        self, plan: OrganizationPlan | None, node: OrganizationPlanNode | None,
        record: OrganizationActionRecord,
    ) -> None:
        if not plan or not node:
            return
        record.plan_id = plan.id
        record.plan_node_id = node.id
        if record.decision == "act" and record.authorized:
            node.actual_action_id = record.action_id
            node.executed_quarter = self.world.quarter
            if record.action_id in {node.action_id, f"novel:{record.open_action_proposal_id}"} or (
                node.action_id == "propose_open_action" and record.open_action_proposal_id
            ):
                node.status = "completed"
                outcome = "executed_as_planned"
            else:
                node.status = "deviated"
                node.deviation_reason = f"实际执行{record.action_id}，原计划为{node.action_id}"
                record.deviation_reason = node.deviation_reason
                outcome = "action_deviation"
        elif record.decision in {"wait", "deferred"}:
            outcome = record.decision
        else:
            node.status = "deviated"
            node.deviation_reason = record.blocked_reason or "动作未获授权"
            record.deviation_reason = node.deviation_reason
            outcome = "blocked"
        plan.review_history.append({
            "quarter": self.world.quarter, "node_id": node.id,
            "planned_action": node.action_id, "actual_action": record.action_id,
            "outcome": outcome, "reason": record.deviation_reason or record.blocked_reason,
        })

    def validate_open_action(
        self, actor_id: str, city_id: str, payload: dict[str, Any],
        provider: str, fallback: bool,
    ) -> OpenActionProposal:
        actor = self.world.agents[actor_id]
        proposal = OpenActionProposal(
            id=f"open-action-{len(self.world.open_action_proposals)+1:04d}",
            quarter=self.world.quarter, city_id=city_id, actor_id=actor_id,
            title=str(payload.get("title") or "未命名组织行动"),
            mechanism=str(payload.get("mechanism") or "strategic_delay"),
            target_actor_id=payload.get("target_actor_id"),
            requested_effects={
                key: float(value) for key, value in payload.get("requested_effects", {}).items()
                if isinstance(value, (int, float))
            },
            resource_request={
                key: float(value) for key, value in payload.get("resource_request", {}).items()
                if isinstance(value, (int, float))
            },
            rationale=str(payload.get("rationale") or "提出新的组织协调手段"),
            provider=provider, fallback=fallback,
        )
        allowed_mechanisms = ROLE_MECHANISMS.get(actor.role, set())
        forbidden_resources = {
            key: value for key, value in proposal.resource_request.items()
            if value > 0 and key not in {"staff_time", "meeting_slots"}
        }
        invalid_effects = set(proposal.requested_effects) - set(EFFECT_CAPS)
        if proposal.mechanism not in allowed_mechanisms:
            proposal.status = "rejected"
            proposal.validation_reason = f"{actor.role.value}无权使用{proposal.mechanism}机制"
        elif forbidden_resources:
            proposal.status = "rejected"
            proposal.validation_reason = f"新行动不得创造财政或物质资源：{sorted(forbidden_resources)}"
        elif invalid_effects:
            proposal.status = "rejected"
            proposal.validation_reason = f"存在不可执行状态维度：{sorted(invalid_effects)}"
        else:
            proposal.status = "authorized"
            proposal.validation_reason = "职责、资源与状态效果均通过规则审查"
            proposal.executed_effects = {
                key: round(max(-cap, min(cap, value)), 4)
                for key, value in proposal.requested_effects.items()
                if (cap := EFFECT_CAPS.get(key)) is not None
            }
            self._apply_open_effects(city_id, proposal.executed_effects)
        self.world.open_action_proposals.append(proposal)
        return proposal

    def _apply_open_effects(self, city_id: str, effects: dict[str, float]) -> None:
        state = self.world.organization_processes[city_id]
        state.agenda_priority = min(
            1.0, max(0.0, state.agenda_priority + effects.get("agenda_priority_delta", 0))
        )
        state.coalition_support = min(
            1.0, max(0.0, state.coalition_support + effects.get("coalition_support_delta", 0))
        )
        state.procedural_completeness = min(
            1.0,
            max(0.0, state.procedural_completeness + effects.get("procedural_completeness_delta", 0)),
        )
        state.attention_budget = min(
            4, max(1, state.attention_budget + int(effects.get("attention_budget_delta", 0)))
        )

    def learn_from_action(self, record: OrganizationActionRecord) -> None:
        learning = self.learning(record.actor_id)
        learning.action_attempts[record.action_id] = learning.action_attempts.get(record.action_id, 0) + 1
        success = record.authorized and record.decision == "act"
        if success:
            learning.action_successes[record.action_id] = learning.action_successes.get(record.action_id, 0) + 1
        reward = 0.08 if success else -0.05
        reward += min(0.12, sum(value for value in record.effects.values() if value > 0) * 0.2)
        prior = learning.strategy_preferences.get(record.action_id, 0.5)
        learning.strategy_preferences[record.action_id] = round(
            min(1.0, max(0.0, prior * 0.78 + (0.5 + reward) * 0.22)), 3
        )
        if record.target_actor_id:
            trust = learning.trust_by_actor.get(record.target_actor_id, 0.5)
            learning.trust_by_actor[record.target_actor_id] = round(
                min(1.0, max(0.0, trust + (0.035 if success else -0.04))), 3
            )
        attempts = learning.action_attempts[record.action_id]
        successes = learning.action_successes.get(record.action_id, 0)
        if attempts >= 3 and successes / attempts >= 0.66:
            learning.routines[record.action_id] = round(successes / attempts, 3)
        lesson = (
            f"Q{record.quarter} {record.action_name}"
            f"{'得到执行' if success else '未执行'}；偏离={record.deviation_reason or '无'}"
        )
        if not learning.lessons or learning.lessons[-1] != lesson:
            learning.lessons.append(lesson)
            learning.lessons = learning.lessons[-20:]

    def record_veto(self, city_id: str, rationale: str) -> None:
        investment_id = f"{city_id}_investment"
        learning = self.learning(investment_id)
        learning.veto_count += 1
        finance_id = f"{city_id}_finance"
        trust = learning.trust_by_actor.get(finance_id, 0.5)
        learning.trust_by_actor[finance_id] = round(max(0.0, trust - 0.025), 3)
        learning.strategy_preferences["negotiate_phasing"] = min(
            1.0, learning.strategy_preferences.get("negotiate_phasing", 0.5) + 0.08
        )
        lesson = f"第{learning.veto_count}次财政否决：{rationale}"
        learning.lessons.append(lesson)
        if learning.veto_count >= 3:
            transferable = "连续财政否决后，应由高现金方案转向分期、试点或联盟论证"
            if transferable not in learning.transferable_lessons:
                learning.transferable_lessons.append(transferable)

    def record_successful_coordination(self, city_id: str) -> None:
        investment = self.learning(f"{city_id}_investment")
        investment.successful_coordination_count += 1
        finance_id = f"{city_id}_finance"
        investment.trust_by_actor[finance_id] = round(
            min(1.0, investment.trust_by_actor.get(finance_id, 0.5) + 0.04), 3
        )

    def record_enterprise_response(self, city_id: str, response: str) -> None:
        updates = {
            "accept": {"commitment_reliability": 0.08},
            "counter": {"bargaining_intensity": 0.08},
            "terminate": {"exit_sensitivity": 0.1},
        }[response]
        for suffix in ("investment", "leader"):
            learning = self.learning(f"{city_id}_{suffix}")
            for key, delta in updates.items():
                learning.firm_type_beliefs[key] = round(
                    min(1.0, learning.firm_type_beliefs.get(key, 0.5) * 0.82 + (0.5 + delta) * 0.18),
                    3,
                )

    def _leadership_succession(self, city_id: str) -> None:
        leader_id = f"{city_id}_leader"
        agent = self.world.agents.get(leader_id)
        if not agent:
            return
        learning = self.learning(leader_id)
        inheritance = 0.6
        keep = max(1, round(len(agent.memories) * inheritance)) if agent.memories else 0
        agent.memories = agent.memories[-keep:] if keep else []
        agent.last_reflection = "负责人调整：继承制度性档案，但个人关系与策略偏好部分重置"
        learning.leadership_generation += 1
        learning.inherited_memory_ratio = inheritance
        learning.trust_by_actor = {
            actor_id: round(0.5 + (trust - 0.5) * inheritance, 3)
            for actor_id, trust in learning.trust_by_actor.items()
        }
        learning.strategy_preferences = {
            action_id: round(0.5 + (score - 0.5) * inheritance, 3)
            for action_id, score in learning.strategy_preferences.items()
        }
        learning.lessons.append("领导更替后保留组织惯例与制度档案，弱化个人关系记忆")

    def _transfer_plan_lesson(self, plan: OrganizationPlan, reason: str) -> None:
        learning = self.learning(plan.actor_id)
        deviations = sum(node.status == "deviated" for node in plan.nodes)
        lesson = f"计划{plan.id}（{plan.selected_strategy}）结束：{reason}；偏离{deviations}个节点"
        if lesson not in learning.transferable_lessons:
            learning.transferable_lessons.append(lesson)
            learning.transferable_lessons = learning.transferable_lessons[-10:]

    @staticmethod
    def payload(value: Any) -> dict[str, Any]:
        if hasattr(value, "model_dump"):
            return value.model_dump()
        if hasattr(value, "__dataclass_fields__"):
            return asdict(value)
        return dict(value)
