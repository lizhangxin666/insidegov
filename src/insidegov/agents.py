from __future__ import annotations

import json
import os
import re
import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from .models import AgentState, CityState, FirmState, PolicyPackage, WorldState
from .policies import DeterministicPolicy


class OfferAction(BaseModel):
    subsidy: float = Field(ge=0)
    equity: float = Field(ge=0)
    land_discount: float = Field(ge=0, le=0.8)
    credit_support: float = Field(ge=0)
    approval_speed: float = Field(ge=0, le=1)
    talent_support: float = Field(ge=0, le=1)
    rationale: str = Field(max_length=160)
    evidence: list[str] = Field(default_factory=list, max_length=3)

    def to_package(self, city_id: str) -> PolicyPackage:
        return PolicyPackage(
            city_id=city_id,
            subsidy=round(self.subsidy, 2),
            equity=round(self.equity, 2),
            land_discount=round(self.land_discount, 3),
            credit_support=round(self.credit_support, 2),
            approval_speed=round(self.approval_speed, 3),
            talent_support=round(self.talent_support, 3),
            conditions={"investment": 150.0, "jobs": 2200.0, "progress": 0.55},
        )


class FinanceAction(BaseModel):
    approved: bool
    maximum_fiscal_cost: float = Field(default=0, ge=0)
    maximum_subsidy: float = Field(default=0, ge=0)
    maximum_equity: float = Field(default=0, ge=0)
    maximum_credit_support: float = Field(default=0, ge=0)
    maximum_first_period_payment: float = Field(default=0, ge=0)
    concerns: list[str] = Field(default_factory=list, max_length=5)
    conditions: list[str] = Field(default_factory=list, max_length=3)
    rationale: str = Field(max_length=140)


class TrancheAction(BaseModel):
    item: str
    amount: float = Field(ge=0)
    due_offset: int = Field(ge=1, le=12)
    condition: str = Field(max_length=60)


class ResolutionAction(BaseModel):
    resolution: Literal["approved", "restructured_after_tool_veto", "withdrawn"]
    subsidy: float = Field(ge=0)
    equity: float = Field(ge=0)
    land_discount: float = Field(ge=0, le=0.8)
    credit_support: float = Field(ge=0)
    approval_speed: float = Field(ge=0, le=1)
    talent_support: float = Field(ge=0, le=1)
    payment_schedule: list[TrancheAction] = Field(default_factory=list, max_length=8)
    rationale: str = Field(max_length=160)

    def to_package(self, city_id: str) -> PolicyPackage:
        from .models import PaymentTranche

        return PolicyPackage(
            city_id=city_id,
            subsidy=round(self.subsidy, 2),
            equity=round(self.equity, 2),
            land_discount=round(self.land_discount, 3),
            credit_support=round(self.credit_support, 2),
            approval_speed=round(self.approval_speed, 3),
            talent_support=round(self.talent_support, 3),
            conditions={"investment": 150.0, "jobs": 2200.0, "progress": 0.55},
            payment_schedule=[PaymentTranche(**row.model_dump()) for row in self.payment_schedule],
        )


def _repair_structured_payload(schema: type[BaseModel], content: str) -> dict[str, Any] | None:
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    if schema is ResolutionAction:
        data.setdefault("resolution", "restructured_after_tool_veto")
        if data["resolution"] not in {"approved", "restructured_after_tool_veto", "withdrawn"}:
            data["resolution"] = "restructured_after_tool_veto"
        for key in ("subsidy", "equity", "land_discount", "credit_support"):
            data[key] = max(0.0, float(data.get(key) or 0.0))
        for key in ("approval_speed", "talent_support"):
            data[key] = min(1.0, max(0.0, float(data.get(key) or 0.0)))
        data.setdefault("payment_schedule", [])
        data.setdefault("rationale", "接受财政约束并调整政策工具组合")
    if schema is FinanceAction:
        data.setdefault("approved", False)
        data.setdefault("concerns", ["财政风险需控制"])
        data.setdefault("conditions", ["分期兑现"])
        data.setdefault("rationale", "财政仅表达审核态度，数值上限由规则引擎填充")
    if schema is OrganizationInitiativeChoice:
        decision_aliases = {
            "行动": "act", "发起": "act", "执行": "act",
            "等待": "wait", "暂缓": "wait", "不行动": "wait",
        }
        data["decision"] = decision_aliases.get(
            str(data.get("decision", "")).strip(), data.get("decision", "wait")
        )
        if data["decision"] not in {"act", "wait"}:
            data["decision"] = "wait"
        if data["decision"] == "wait":
            data["action_id"] = "wait"
        data["urgency"] = min(1.0, max(0.0, float(data.get("urgency") or 0.5)))
        data.setdefault("rationale", "根据当前组织注意力与职责边界作出时点判断")
    if schema is EnterpriseResponseAction:
        response_aliases = {
            "接受": "accept", "同意": "accept", "accept_offer": "accept",
            "还价": "counter", "反提案": "counter", "counteroffer": "counter",
            "退出": "terminate", "拒绝": "terminate", "reject": "terminate",
        }
        data["response"] = response_aliases.get(
            str(data.get("response", "")).strip(), data.get("response", "counter")
        )
        if data["response"] not in {"accept", "counter", "terminate"}:
            data["response"] = "counter"
        if not isinstance(data.get("counter_terms"), dict):
            data["counter_terms"] = {}
        else:
            data["counter_terms"] = {
                str(key): float(value)
                for key, value in data["counter_terms"].items()
                if isinstance(value, (int, float))
            }
        data["confidence"] = min(1.0, max(0.0, float(data.get("confidence") or 0.6)))
        data.setdefault("rationale", "基于效用、信息充分度和等待成本作出回应")
    if schema is NegotiationTimingAction:
        timing_aliases = {
            "立即选址": "select_now", "现在选择": "select_now", "select": "select_now",
            "继续谈判": "continue_negotiating", "等待": "continue_negotiating",
            "全部退出": "exit_all", "退出": "exit_all", "terminate_all": "exit_all",
        }
        data["decision"] = timing_aliases.get(
            str(data.get("decision", "")).strip(),
            data.get("decision", "continue_negotiating"),
        )
        if data["decision"] not in {"select_now", "continue_negotiating", "exit_all"}:
            data["decision"] = "continue_negotiating"
        data["confidence"] = min(1.0, max(0.0, float(data.get("confidence") or 0.6)))
        data.setdefault("rationale", "权衡等待的信息价值与选址机会成本")
    if schema is OrganizationPlanAction:
        alternatives = data.get("alternatives")
        if not isinstance(alternatives, list):
            alternatives = []
        alternatives = [item for item in alternatives if isinstance(item, dict)][:3]
        while len(alternatives) < 2:
            index = len(alternatives) + 1
            alternatives.append({
                "id": f"strategy_{index}", "name": f"备选路径{index}",
                "approach": "在职责与硬约束内分阶段推进",
                "benefits": ["保持可执行性"], "risks": ["需要后续验证"],
                "score": 0.5,
            })
        for index, item in enumerate(alternatives, start=1):
            item.setdefault("id", f"strategy_{index}")
            item.setdefault("name", f"备选路径{index}")
            item.setdefault("approach", "分阶段推进")
            item.setdefault("benefits", [])
            item.setdefault("risks", [])
            item["score"] = min(1.0, max(0.0, float(item.get("score") or 0.5)))
        data["alternatives"] = alternatives
        steps = data.get("steps")
        if not isinstance(steps, list):
            steps = []
        steps = [item for item in steps if isinstance(item, dict)][:5]
        while len(steps) < 2:
            index = len(steps) + 1
            steps.append({
                "id": f"s{index}", "title": f"计划节点{index}",
                "action_id": "propose_open_action", "earliest_offset": index - 1,
                "latest_offset": index + 1, "preconditions": [],
                "expected_effects": {},
            })
        for index, item in enumerate(steps, start=1):
            item.setdefault("id", f"s{index}")
            item.setdefault("title", f"计划节点{index}")
            item.setdefault("action_id", "propose_open_action")
            item["earliest_offset"] = min(8, max(0, int(item.get("earliest_offset") or index - 1)))
            item["latest_offset"] = min(
                12, max(item["earliest_offset"], int(item.get("latest_offset") or index + 1))
            )
            item.setdefault("preconditions", [])
            item.setdefault("expected_effects", {})
        data["steps"] = steps
        data.setdefault("objective", "推进当前组织议题")
        data.setdefault("selected_strategy", alternatives[0]["id"])
        data.setdefault("assumptions", [])
        data.setdefault("rationale", "比较多条路径后选择可执行方案")
    if schema is CompactOrganizationPlanAction:
        alternatives = data.get("alternatives")
        alternatives = [item for item in alternatives if isinstance(item, dict)][:3] \
            if isinstance(alternatives, list) else []
        while len(alternatives) < 2:
            index = len(alternatives) + 1
            alternatives.append({
                "id": f"strategy_{index}", "approach": "分阶段推进",
                "risk": "需要后续验证", "score": 0.5,
            })
        for index, item in enumerate(alternatives, start=1):
            item.setdefault("id", f"strategy_{index}")
            item.setdefault("approach", "分阶段推进")
            item.setdefault("risk", "需要后续验证")
            item["score"] = min(1.0, max(0.0, float(item.get("score") or 0.5)))
        data["alternatives"] = alternatives
        sequence = data.get("action_sequence")
        sequence = [str(item) for item in sequence][:4] if isinstance(sequence, list) else []
        while len(sequence) < 2:
            sequence.append("propose_open_action")
        data["action_sequence"] = sequence
        data.setdefault("objective", "推进当前组织议题")
        data.setdefault("selected_strategy", alternatives[0]["id"])
        data.setdefault("branch_condition", "关键假设失效时重新规划")
        data.setdefault("assumptions", [])
        data.setdefault("rationale", "比较两条路径后选择可执行序列")
    if schema is NovelOrganizationAction:
        aliases = {
            "邀请上级背书": "upward_endorsement", "上级背书": "upward_endorsement",
            "行业协会联盟": "association_coalition", "协会联盟": "association_coalition",
            "示范项目": "demonstration_project", "会议窗口": "meeting_window",
            "战略等待": "strategic_delay", "跨部门工作组": "cross_department_taskforce",
            "专家论证": "expert_consultation",
        }
        mechanism = str(data.get("mechanism", "strategic_delay")).strip()
        data["mechanism"] = aliases.get(mechanism, mechanism)
        data.setdefault("title", "提出新的组织协调手段")
        data.setdefault("intent", data["title"])
        data.setdefault("domain", "project_coordination")
        data.setdefault("arena", "informal")
        target_ids = data.get("target_actor_ids")
        if not isinstance(target_ids, list):
            target = data.get("target_actor_id")
            target_ids = [target] if target else []
        data["target_actor_ids"] = [str(item) for item in target_ids[:6] if item]
        information = data.get("requested_information")
        data["requested_information"] = (
            [str(item) for item in information[:6]] if isinstance(information, list) else []
        )
        claims = data.get("authority_claims")
        data["authority_claims"] = (
            [str(item) for item in claims[:6]] if isinstance(claims, list) else []
        )
        data.setdefault("timing", "current_round")
        data["reversibility"] = min(
            1.0, max(0.0, float(data.get("reversibility") or 1.0))
        )
        for key in ("requested_effects", "resource_request"):
            value = data.get(key)
            data[key] = {
                str(item_key): float(item_value)
                for item_key, item_value in value.items()
                if isinstance(item_value, (int, float))
            } if isinstance(value, dict) else {}
        data.setdefault("rationale", "在职责边界内利用当前机会窗口")
    return data


class LocationAction(BaseModel):
    city_id: str
    confidence: float = Field(ge=0, le=1)
    rationale: str
    evidence: list[str] = Field(default_factory=list)


class OrganizationActionChoice(BaseModel):
    action_id: str = Field(min_length=2, max_length=80)
    confidence: float = Field(default=0.6, ge=0, le=1)
    rationale: str = Field(max_length=140)


class OrganizationInitiativeChoice(BaseModel):
    decision: Literal["act", "wait"]
    action_id: str = Field(default="wait", min_length=2, max_length=80)
    urgency: float = Field(default=0.5, ge=0, le=1)
    target_actor_id: str | None = Field(default=None, max_length=100)
    rationale: str = Field(max_length=160)


class ProcedureTransitionChoice(BaseModel):
    transition: Literal[
        "start_formal_process",
        "continue_informal_coordination",
        "pause_formal_process",
        "return_for_revision",
        "re_agenda",
        "resume_formal_process",
        "keep_closed",
        "abandon_proposal",
        "proceed_formal_review",
        "authorize_informal_offer",
    ]
    rationale: str = Field(max_length=180)


class EnterpriseResponseAction(BaseModel):
    response: Literal["accept", "counter", "terminate"]
    counter_terms: dict[str, float] = Field(default_factory=dict)
    confidence: float = Field(default=0.6, ge=0, le=1)
    rationale: str = Field(max_length=180)


class NegotiationTimingAction(BaseModel):
    decision: Literal["select_now", "continue_negotiating", "exit_all"]
    confidence: float = Field(default=0.6, ge=0, le=1)
    rationale: str = Field(max_length=180)


class PlanStrategyOptionAction(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    name: str = Field(max_length=80)
    approach: str = Field(max_length=180)
    benefits: list[str] = Field(default_factory=list, max_length=3)
    risks: list[str] = Field(default_factory=list, max_length=3)
    score: float = Field(default=0.5, ge=0, le=1)


class OrganizationPlanNodeAction(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    title: str = Field(max_length=100)
    action_id: str = Field(max_length=80)
    earliest_offset: int = Field(default=0, ge=0, le=8)
    latest_offset: int = Field(default=2, ge=0, le=12)
    preconditions: list[str] = Field(default_factory=list, max_length=4)
    on_success: str | None = Field(default=None, max_length=40)
    on_failure: str | None = Field(default=None, max_length=40)
    expected_effects: dict[str, float] = Field(default_factory=dict)


class OrganizationPlanAction(BaseModel):
    objective: str = Field(max_length=160)
    alternatives: list[PlanStrategyOptionAction] = Field(min_length=2, max_length=3)
    selected_strategy: str = Field(max_length=40)
    steps: list[OrganizationPlanNodeAction] = Field(min_length=2, max_length=5)
    assumptions: list[str] = Field(default_factory=list, max_length=5)
    rationale: str = Field(max_length=200)


class CompactPlanOptionAction(BaseModel):
    id: str = Field(min_length=1, max_length=32)
    approach: str = Field(max_length=100)
    risk: str = Field(max_length=80)
    score: float = Field(default=0.5, ge=0, le=1)


class CompactOrganizationPlanAction(BaseModel):
    objective: str = Field(max_length=100)
    alternatives: list[CompactPlanOptionAction] = Field(min_length=2, max_length=3)
    selected_strategy: str = Field(max_length=32)
    action_sequence: list[str] = Field(min_length=2, max_length=4)
    branch_condition: str = Field(max_length=100)
    assumptions: list[str] = Field(default_factory=list, max_length=3)
    rationale: str = Field(max_length=120)


class NovelOrganizationAction(BaseModel):
    title: str = Field(max_length=100)
    intent: str = Field(default="", max_length=180)
    mechanism: str = Field(min_length=2, max_length=80, pattern=r"^[a-z][a-z0-9_\-]*$")
    domain: str = Field(default="project_coordination", min_length=2, max_length=80)
    arena: Literal["formal", "informal", "public", "market"] = "informal"
    target_actor_id: str | None = Field(default=None, max_length=100)
    target_actor_ids: list[str] = Field(default_factory=list, max_length=6)
    requested_information: list[str] = Field(default_factory=list, max_length=6)
    authority_claims: list[str] = Field(default_factory=list, max_length=6)
    requested_effects: dict[str, float] = Field(default_factory=dict)
    resource_request: dict[str, float] = Field(default_factory=dict)
    timing: str = Field(default="current_round", max_length=80)
    reversibility: float = Field(default=1.0, ge=0, le=1)
    rationale: str = Field(max_length=180)


class CognitiveProvider(ABC):
    mode = "deterministic"
    model_name: str | None = None

    @abstractmethod
    def propose_offer(
        self,
        agent: AgentState,
        city: CityState,
        firm: FirmState,
        world: WorldState,
        observation: dict[str, Any],
        memories: list[str],
    ) -> OfferAction:
        raise NotImplementedError

    @abstractmethod
    def review_offer(
        self,
        agent: AgentState,
        city: CityState,
        proposal: PolicyPackage,
        observation: dict[str, Any],
        memories: list[str],
    ) -> FinanceAction:
        raise NotImplementedError

    @abstractmethod
    def resolve_offer(
        self,
        agent: AgentState,
        city: CityState,
        proposal: PolicyPackage,
        review: FinanceAction,
        observation: dict[str, Any],
        memories: list[str],
    ) -> ResolutionAction:
        raise NotImplementedError

    @abstractmethod
    def select_location(
        self,
        agent: AgentState,
        firm: FirmState,
        scores: dict[str, float],
        observation: dict[str, Any],
        memories: list[str],
    ) -> LocationAction:
        raise NotImplementedError

    def reflect(self, agent: AgentState, action: str, outcome: str) -> str:
        return f"{agent.name}复盘：{action}已执行；{outcome}。下轮将根据新证据调整。"

    def choose_organization_action(
        self,
        agent: AgentState,
        candidates: list[str],
        observation: dict[str, Any],
        memories: list[str],
    ) -> OrganizationActionChoice:
        return OrganizationActionChoice(
            action_id=candidates[0],
            confidence=0.55,
            rationale="在当前权限和可见信息下选择优先行动",
        )

    def choose_organization_initiative(
        self,
        agent: AgentState,
        candidates: list[str],
        observation: dict[str, Any],
        memories: list[str],
    ) -> OrganizationInitiativeChoice:
        planned = str(observation.get("plan_current_action", ""))
        if planned in candidates:
            choice = OrganizationActionChoice(
                action_id=planned,
                confidence=0.8,
                rationale=f"按已保存的多步计划执行当前节点 {planned}",
            )
        else:
            choice = self.choose_organization_action(agent, candidates, observation, memories)
        return OrganizationInitiativeChoice(
            decision="act",
            action_id=choice.action_id,
            urgency=0.6,
            rationale=choice.rationale,
        )

    def choose_procedure_transition(
        self,
        agent: AgentState,
        candidates: list[str],
        observation: dict[str, Any],
        memories: list[str],
    ) -> ProcedureTransitionChoice:
        return ProcedureTransitionChoice(
            transition=candidates[0],
            rationale="按当前程序状态进入下一合法节点",
        )

    def respond_to_offer(
        self,
        agent: AgentState,
        observation: dict[str, Any],
        memories: list[str],
    ) -> EnterpriseResponseAction:
        utility = float(observation["utility"])
        minimum = float(observation["minimum_utility"])
        if utility >= minimum:
            return EnterpriseResponseAction(
                response="accept", confidence=0.7, rationale="方案达到最低投资门槛"
            )
        return EnterpriseResponseAction(
            response="terminate", confidence=0.7, rationale="方案未达到最低投资门槛"
        )

    def decide_negotiation_timing(
        self,
        agent: AgentState,
        observation: dict[str, Any],
        memories: list[str],
    ) -> NegotiationTimingAction:
        return NegotiationTimingAction(
            decision="continue_negotiating",
            confidence=0.55,
            rationale="继续收集竞争城市报价与履约信息",
        )

    def create_organization_plan(
        self,
        agent: AgentState,
        allowed_actions: list[str],
        observation: dict[str, Any],
        memories: list[str],
    ) -> OrganizationPlanAction:
        return OrganizationPlanAction(
            objective=agent.goals[0] if agent.goals else "推进当前议题",
            alternatives=[
                PlanStrategyOptionAction(
                    id="formal_first", name="正式程序优先", approach="补齐材料后进入正式审查",
                    benefits=["程序完整"], risks=["耗时较长"], score=0.62,
                ),
                PlanStrategyOptionAction(
                    id="coordinate_first", name="协调优先", approach="先降低信息与部门冲突再送审",
                    benefits=["减少否决"], risks=["可能错过窗口"], score=0.68,
                ),
            ],
            selected_strategy="coordinate_first",
            steps=[
                OrganizationPlanNodeAction(
                    id="s1", title="先形成可执行边界",
                    action_id=allowed_actions[0], earliest_offset=0, latest_offset=1,
                ),
                OrganizationPlanNodeAction(
                    id="s2", title="根据反馈推进下一阶段",
                    action_id=allowed_actions[-1], earliest_offset=1, latest_offset=3,
                    preconditions=["前一步已完成"],
                ),
            ],
            assumptions=["财政与领导注意力可能变化"],
            rationale="先比较程序推进与协调推进两条路径，再选择更可执行的组合",
        )

    def propose_novel_organization_action(
        self,
        agent: AgentState,
        observation: dict[str, Any],
        memories: list[str],
    ) -> NovelOrganizationAction:
        return NovelOrganizationAction(
            title="建立跨部门项目工作组",
            mechanism="cross_department_taskforce",
            target_actor_id=f"{agent.owner_id}_leader",
            requested_effects={"coalition_support_delta": 0.08},
            resource_request={},
            rationale="用临时协调结构降低跨部门信息损耗",
        )


class DeterministicCognition(CognitiveProvider):
    """Reproducible heterogeneous baseline with the same structured action protocol."""

    def __init__(self) -> None:
        self.policy = DeterministicPolicy()

    def propose_offer(
        self,
        agent: AgentState,
        city: CityState,
        firm: FirmState,
        world: WorldState,
        observation: dict[str, Any],
        memories: list[str],
    ) -> OfferAction:
        package = self.policy.create_offer(city, firm, world)
        competition = float(agent.private_facts.get("competitive_intensity", 0.6))
        cash_preference = float(agent.private_facts.get("cash_preference", 0.55))
        aggressiveness = 1 + competition * 0.32 + agent.traits.get("short_termism", 0.4) * 0.12
        return OfferAction(
            subsidy=package.subsidy * aggressiveness * (0.8 + cash_preference * 0.4),
            equity=package.equity * (1 + competition * 0.12),
            land_discount=package.land_discount,
            credit_support=package.credit_support,
            approval_speed=package.approval_speed,
            talent_support=package.talent_support,
            rationale="为完成招商签约目标，优先增强企业易感知的现金和基金支持",
            evidence=[
                f"剩余可用财力 {city.available_budget:.1f}",
                f"财政压力 {city.fiscal_pressure:.0%}",
                f"招商竞争强度 {competition:.0%}",
            ],
        )

    def choose_organization_action(
        self,
        agent: AgentState,
        candidates: list[str],
        observation: dict[str, Any],
        memories: list[str],
    ) -> OrganizationActionChoice:
        preferred: list[str]
        if agent.role.value == "investment":
            preferred = [
                "preconsult_finance" if not observation.get("finance_preconsulted") else "frame_strategic_project",
                "clarify_need", "request_materials", "mobilize_park_coalition",
            ]
        elif agent.role.value == "finance":
            preferred = [
                "disclose_fiscal_boundary" if observation.get("fiscal_pressure", 0) > 0.2 else "negotiate_phasing",
                "negotiate_phasing", "risk_assessment", "fiscal_guardrail",
            ]
        elif agent.role.value == "city_leader":
            preferred = [
                "broker_compromise" if observation.get("coalition_support", 0) < 0.5 else "authorize_pilot",
                "authorize_pilot", "collective_deliberation",
            ]
        else:
            preferred = ["mobilize_park_coalition", *candidates]
        selected = next((item for item in preferred if item in candidates), candidates[0])
        return OrganizationActionChoice(
            action_id=selected,
            confidence=0.72,
            rationale=f"{agent.name}依据本部门目标、当前财政压力与协作状态，在授权动作中选择 {selected}",
        )

    def choose_organization_initiative(
        self,
        agent: AgentState,
        candidates: list[str],
        observation: dict[str, Any],
        memories: list[str],
    ) -> OrganizationInitiativeChoice:
        planned = str(observation.get("plan_current_action", ""))
        if planned in candidates:
            choice = OrganizationActionChoice(
                action_id=planned,
                confidence=0.8,
                rationale=f"按已保存的多步计划执行当前节点 {planned}",
            )
        else:
            choice = self.choose_organization_action(agent, candidates, observation, memories)
        urgency = 0.52
        if agent.role.value == "investment":
            urgency += 0.18 + float(observation.get("negotiation_pressure", 0)) * 0.12
        elif agent.role.value == "finance":
            urgency += float(observation.get("fiscal_pressure", 0)) * 0.55
        elif agent.role.value == "city_leader":
            urgency += abs(
                float(observation.get("agenda_priority", 0.5))
                - float(observation.get("coalition_support", 0.35))
            ) * 0.4
        elif agent.role.value == "park":
            urgency += (1 - float(observation.get("coalition_support", 0.35))) * 0.25
        decision = "wait" if urgency < 0.56 else "act"
        return OrganizationInitiativeChoice(
            decision=decision,
            action_id=choice.action_id if decision == "act" else "wait",
            urgency=min(0.95, urgency),
            target_actor_id=(
                f"{agent.owner_id}_finance"
                if choice.action_id == "preconsult_finance" else None
            ),
            rationale=choice.rationale if decision == "act" else "当前议题紧迫度不足，暂不占用组织注意力",
        )

    def choose_procedure_transition(
        self,
        agent: AgentState,
        candidates: list[str],
        observation: dict[str, Any],
        memories: list[str],
    ) -> ProcedureTransitionChoice:
        status = str(observation.get("formal_status", "dormant"))
        preferred = {
            "dormant": "start_formal_process",
            "completed": "re_agenda",
            "paused": "resume_formal_process",
            "returned": "resume_formal_process",
            "active": "proceed_formal_review",
        }.get(status, candidates[0])
        transition = preferred if preferred in candidates else candidates[0]
        return ProcedureTransitionChoice(
            transition=transition,
            rationale=f"{agent.name}根据程序状态{status}、议程压力和部门协调结果推进至{transition}",
        )

    def respond_to_offer(
        self,
        agent: AgentState,
        observation: dict[str, Any],
        memories: list[str],
    ) -> EnterpriseResponseAction:
        utility = float(observation["utility"])
        minimum = float(observation["minimum_utility"])
        gap = utility - minimum
        round_number = int(observation.get("negotiation_round", 1))
        if gap < -8:
            return EnterpriseResponseAction(
                response="terminate", confidence=0.82,
                rationale="报价与最低门槛差距过大，继续协商的机会成本高",
            )
        if gap >= 10 and round_number >= 3:
            return EnterpriseResponseAction(
                response="accept", confidence=min(0.94, 0.65 + gap / 100),
                rationale=(
                    "连续多轮报价明显超过最低门槛，等待的边际价值已经不足，"
                    "可以进入跨城市择优"
                ),
            )
        offer = observation.get("offer", {})
        increment = 1.0 if observation.get("prior_counter") else 1.5
        return EnterpriseResponseAction(
            response="counter",
            counter_terms={
                "subsidy_floor": round(float(offer.get("subsidy", 0)) + increment, 2),
                "equity_floor": round(float(offer.get("equity", 0)) + 0.8, 2),
                "require_phased_delivery": 1.0,
            },
            confidence=0.7,
            rationale="信息或履约保障尚不足，继续还价比立即接受或退出更有价值",
        )

    def decide_negotiation_timing(
        self,
        agent: AgentState,
        observation: dict[str, Any],
        memories: list[str],
    ) -> NegotiationTimingAction:
        accepted = observation.get("accepted_city_ids", [])
        round_number = int(observation.get("negotiation_round", 1))
        active = int(observation.get("active_negotiations", 0))
        if accepted and (round_number >= 3 or active == 0):
            return NegotiationTimingAction(
                decision="select_now", confidence=0.84,
                rationale="已有可接受报价，继续等待的边际信息价值低于选址机会成本",
            )
        if not accepted and active == 0:
            return NegotiationTimingAction(
                decision="exit_all", confidence=0.8,
                rationale="所有城市均已终止且没有可接受报价",
            )
        return NegotiationTimingAction(
            decision="continue_negotiating", confidence=0.68,
            rationale="仍有城市处于还价或程序调整阶段，继续等待下一轮报价",
        )

    def create_organization_plan(
        self,
        agent: AgentState,
        allowed_actions: list[str],
        observation: dict[str, Any],
        memories: list[str],
    ) -> OrganizationPlanAction:
        role = agent.role.value
        veto_count = int(observation.get("veto_count", 0))
        active_windows = observation.get("active_windows", [])
        templates = {
            "investment": ["preconsult_finance", "mobilize_park_coalition", "frame_strategic_project"],
            "finance": ["disclose_fiscal_boundary", "negotiate_phasing", "risk_assessment"],
            "park": ["mobilize_park_coalition", "propose_open_action", "clarify_need"],
            "city_leader": ["broker_compromise", "authorize_pilot", "collective_deliberation"],
        }
        sequence = [item for item in templates.get(role, allowed_actions) if item in allowed_actions]
        if not sequence:
            sequence = allowed_actions[:2]
        if veto_count >= 2 and "propose_open_action" in allowed_actions:
            sequence = [sequence[0], "propose_open_action", *sequence[1:]]
        sequence = sequence[:4]
        while len(sequence) < 2:
            sequence.append(sequence[-1])
        strategy = (
            "phased_adaptation" if veto_count >= 2
            else "window_acceleration" if active_windows
            else "coordinate_then_formalize"
        )
        return OrganizationPlanAction(
            objective=agent.goals[0] if agent.goals else "推进当前组织议题",
            alternatives=[
                PlanStrategyOptionAction(
                    id="formal_first", name="直接正式推进",
                    approach="优先补齐程序并进入审查", benefits=["责任清晰"],
                    risks=["可能遭遇早期否决"], score=0.56,
                ),
                PlanStrategyOptionAction(
                    id="coordinate_then_formalize", name="先协调后正式化",
                    approach="先探测边界和组织联盟，再进入正式程序",
                    benefits=["降低否决概率"], risks=["增加时间成本"], score=0.72,
                ),
                PlanStrategyOptionAction(
                    id="phased_adaptation", name="分阶段适应",
                    approach="在重复否决后改用试点、分期或新型组织手段",
                    benefits=["可逆且可学习"], risks=["初期规模较小"],
                    score=0.82 if veto_count >= 2 else 0.58,
                ),
            ],
            selected_strategy=strategy,
            steps=[
                OrganizationPlanNodeAction(
                    id=f"s{index}", title=f"执行 {action_id}", action_id=action_id,
                    earliest_offset=index - 1, latest_offset=index + 1,
                    preconditions=[] if index == 1 else [f"s{index-1}已完成或窗口发生"],
                    on_success=f"s{index+1}" if index < len(sequence) else None,
                    on_failure="replan",
                    expected_effects={"coordination": round(0.08 + index * 0.02, 2)},
                )
                for index, action_id in enumerate(sequence, start=1)
            ],
            assumptions=["财政硬约束不会被非正式行动绕过", "机会窗口可能改变行动时点"],
            rationale="比较直接送审、先协调和分阶段适应三条路径，并根据否决历史与机会窗口选择",
        )

    def propose_novel_organization_action(
        self,
        agent: AgentState,
        observation: dict[str, Any],
        memories: list[str],
    ) -> NovelOrganizationAction:
        windows = {item.get("kind") for item in observation.get("active_windows", [])}
        if agent.role.value == "investment" and "major_meeting" in windows:
            return NovelOrganizationAction(
                title="借重大会议设置项目专场",
                mechanism="meeting_window",
                target_actor_id=f"{agent.owner_id}_leader",
                requested_effects={"agenda_priority_delta": 0.12, "attention_budget_delta": 1},
                resource_request={}, rationale="会议窗口可集中领导与部门注意力",
            )
        if agent.role.value in {"investment", "park"}:
            return NovelOrganizationAction(
                title="邀请行业协会参与供应链论证",
                mechanism="association_coalition",
                target_actor_id=f"{agent.owner_id}_leader",
                requested_effects={"coalition_support_delta": 0.1},
                resource_request={}, rationale="用外部产业证据扩大同级支持",
            )
        if agent.role.value == "city_leader":
            return NovelOrganizationAction(
                title="设立跨部门示范项目工作组",
                mechanism="cross_department_taskforce",
                target_actor_id=f"{agent.owner_id}_investment",
                requested_effects={"coalition_support_delta": 0.1, "procedural_completeness_delta": 0.06},
                resource_request={}, rationale="以临时组织承接试点并降低协调摩擦",
            )
        return NovelOrganizationAction(
            title="邀请独立专家评估分期方案",
            mechanism="expert_consultation",
            target_actor_id=f"{agent.owner_id}_leader",
            requested_effects={"procedural_completeness_delta": 0.08},
            resource_request={}, rationale="用外部专业判断降低信息不对称",
        )

    def review_offer(
        self,
        agent: AgentState,
        city: CityState,
        proposal: PolicyPackage,
        observation: dict[str, Any],
        memories: list[str],
    ) -> FinanceAction:
        reserve_floor = float(agent.private_facts.get("reserve_floor", city.available_budget * 0.25))
        stress_limit = float(agent.private_facts.get("stress_limit", 0.8))
        spendable = max(0.0, city.available_budget - reserve_floor)
        risk_discount = max(0.3, 1 - city.fiscal_pressure * agent.traits["risk_aversion"])
        maximum = round(min(spendable * 0.34, city.available_budget * 0.19) * risk_discount, 2)
        cash_limit = round(min(spendable * 0.11, city.available_budget * 0.065) * risk_discount, 2)
        equity_limit = round(min(spendable * 0.19, city.available_budget * 0.105) * risk_discount, 2)
        credit_limit = round(min(30.0, city.available_budget * 0.21) * risk_discount, 2)
        first_period_limit = round(min(spendable * 0.12, city.available_budget * 0.075), 2)
        approved = (
            proposal.fiscal_cost <= maximum
            and proposal.subsidy <= cash_limit
            and proposal.equity <= equity_limit
            and proposal.credit_support <= credit_limit
            and city.fiscal_pressure <= stress_limit
        )
        concerns = []
        if proposal.fiscal_cost > maximum:
            concerns.append("政策包超过本轮财政承受上限")
        if proposal.subsidy > cash_limit:
            concerns.append(f"现金补贴 {proposal.subsidy:.1f} 亿超过 {cash_limit:.1f} 亿上限")
        if proposal.equity > equity_limit:
            concerns.append(f"股权投资 {proposal.equity:.1f} 亿超过 {equity_limit:.1f} 亿上限")
        if city.fiscal_pressure > stress_limit:
            concerns.append("债务与已承诺支出导致压力超阈值")
        if not concerns:
            concerns.append("需绑定项目进度和就业条件")
        return FinanceAction(
            approved=approved,
            maximum_fiscal_cost=maximum,
            maximum_subsidy=cash_limit,
            maximum_equity=equity_limit,
            maximum_credit_support=credit_limit,
            maximum_first_period_payment=first_period_limit,
            concerns=concerns,
            conditions=["按建设进度分期支付", "就业和投资未达标则核减"],
            rationale="保留财政储备底线，并使每项承诺具备现金流可行性",
        )

    def resolve_offer(
        self,
        agent: AgentState,
        city: CityState,
        proposal: PolicyPackage,
        review: FinanceAction,
        observation: dict[str, Any],
        memories: list[str],
    ) -> ResolutionAction:
        subsidy = min(proposal.subsidy, review.maximum_subsidy)
        rejected_cash = max(0.0, proposal.subsidy - subsidy)
        equity = min(proposal.equity + rejected_cash * 0.65, review.maximum_equity)
        credit = min(proposal.credit_support, review.maximum_credit_support)
        raw_cost = subsidy + equity + credit * 0.08
        if raw_cost > review.maximum_fiscal_cost:
            equity = max(0.0, equity - (raw_cost - review.maximum_fiscal_cost))
        changed = (
            abs(subsidy - proposal.subsidy) > 0.01
            or abs(equity - proposal.equity) > 0.01
            or abs(credit - proposal.credit_support) > 0.01
        )
        resolution = "restructured_after_tool_veto" if changed else "approved"
        first_equity = min(equity, review.maximum_first_period_payment * 0.65)
        first_cash = min(
            subsidy * 0.4,
            max(0.0, review.maximum_first_period_payment - first_equity),
        )
        later_equity = max(0.0, equity - first_equity)
        later_cash = max(0.0, subsidy - first_cash)
        schedule = [
            TrancheAction(item="equity", amount=first_equity, due_offset=1, condition="contract_signed"),
            TrancheAction(item="subsidy", amount=first_cash, due_offset=1, condition="equipment_ordered"),
        ]
        if later_equity > 0:
            schedule.append(TrancheAction(
                item="equity", amount=later_equity, due_offset=2,
                condition="equipment_ordered",
            ))
        if later_cash > 0:
            schedule.append(TrancheAction(
                item="subsidy", amount=later_cash, due_offset=3,
                condition="project_progress>=0.55",
            ))
        if credit > 0:
            schedule.append(TrancheAction(
                item="credit_support", amount=credit * 0.08, due_offset=5,
                condition="production_commissioned",
            ))
        return ResolutionAction(
            resolution=resolution,
            subsidy=subsidy,
            equity=equity,
            land_discount=min(proposal.land_discount, 0.52),
            credit_support=credit,
            approval_speed=proposal.approval_speed,
            talent_support=proposal.talent_support,
            payment_schedule=schedule,
            rationale="接受现金上限，将部分招商强度转为股权工具，并按签约、设备、进度和投产节点分期兑现",
        )

    def select_location(
        self,
        agent: AgentState,
        firm: FirmState,
        scores: dict[str, float],
        observation: dict[str, Any],
        memories: list[str],
    ) -> LocationAction:
        city_id, score = max(scores.items(), key=lambda item: item[1])
        ordered = sorted(scores.values(), reverse=True)
        margin = score - ordered[1] if len(ordered) > 1 else score
        return LocationAction(
            city_id=city_id,
            confidence=min(0.96, 0.55 + max(0, margin) / 80),
            rationale="综合政策价值、产业配套、履约可信度与财政风险后择优",
            evidence=[f"{city}: {value:.1f}" for city, value in scores.items()],
        )


class DeepSeekCognition(CognitiveProvider):
    mode = "llm"
    request_deadline_seconds = 30.0

    def __init__(
        self,
        api_key: str,
        model_name: str = "deepseek-v4-flash",
        base_url: str = "https://api.deepseek.com",
        client: httpx.Client | None = None,
        request_timeout: float = 45.0,
        structured_retries: int = 2,
        diagnostics_path: str | Path | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY is required for LLM mode")
        self.api_key = api_key
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self.structured_retries = max(0, structured_retries)
        self.diagnostics_path = Path(diagnostics_path) if diagnostics_path else None
        self.request_deadline_seconds = request_timeout + 10.0
        timeout = httpx.Timeout(
            connect=min(8.0, request_timeout),
            read=request_timeout,
            write=min(8.0, request_timeout),
            pool=min(8.0, request_timeout),
        )
        limits = httpx.Limits(max_connections=4, max_keepalive_connections=0)
        self.client = client or httpx.Client(timeout=timeout, limits=limits, trust_env=False)
        self.fallback = DeterministicCognition()
        self.response_cache: dict[str, dict[str, Any]] = {}
        self.diagnostics: list[dict[str, Any]] = []

    def _ask(self, role: str, schema: type[BaseModel], payload: dict[str, Any]) -> BaseModel:
        system = (
            "你是中国地方政企互动沙盘中的一个独立行动者。"
            "你只能根据所给私有信息、局部观察与记忆决策，不得臆测其他主体的私有底线。"
            "输出严格 JSON，不要 Markdown，所有金额单位为亿元。"
        )
        cache_key = json.dumps({"role": role, "schema": schema.__name__, "payload": payload}, ensure_ascii=False, sort_keys=True)
        if cache_key in self.response_cache:
            return schema.model_validate(self.response_cache[cache_key])
        body: dict[str, Any] = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps({"role": role, **payload}, ensure_ascii=False)},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        last_error: Exception | None = None
        for attempt in range(1, self.structured_retries + 2):
            started_at = time.monotonic()
            diagnostic: dict[str, Any] = {
                "timestamp": datetime.now(UTC).isoformat(), "model": self.model_name,
                "role": role, "schema": schema.__name__, "attempt": attempt,
            }
            try:
                response = self.client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=body,
                )
                diagnostic["elapsed_seconds"] = round(time.monotonic() - started_at, 3)
                diagnostic["http_status"] = response.status_code
                response.raise_for_status()
                response_data = response.json()
                choice = response_data["choices"][0]
                message = choice["message"]
                content = message.get("content") or ""
                diagnostic.update({
                    "finish_reason": choice.get("finish_reason"),
                    "usage": response_data.get("usage", {}),
                    "content_length": len(content),
                    "reasoning_length": len(message.get("reasoning_content") or ""),
                })
                content = re.sub(
                    r"^```(?:json)?|```$", "", content.strip(), flags=re.MULTILINE
                ).strip()
                if not content:
                    raise ValueError("empty content")
                try:
                    result = schema.model_validate_json(content)
                except ValidationError:
                    repaired = _repair_structured_payload(schema, content)
                    if repaired is None:
                        raise
                    diagnostic["repaired"] = True
                    result = schema.model_validate(repaired)
                diagnostic["outcome"] = "success"
                self._record_diagnostic(diagnostic)
                self.response_cache[cache_key] = result.model_dump()
                return result
            except (httpx.HTTPError, ValidationError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                diagnostic.setdefault("elapsed_seconds", round(time.monotonic() - started_at, 3))
                diagnostic["outcome"] = "retry" if attempt <= self.structured_retries else "failed"
                diagnostic["error_type"] = type(exc).__name__
                diagnostic["error"] = str(exc).splitlines()[0][:500]
                self._record_diagnostic(diagnostic)
                last_error = exc
                if attempt <= self.structured_retries:
                    body["messages"] = [
                        *body["messages"],
                        {"role": "user", "content": (
                            "上一次输出为空或未通过结构校验。请重新生成，只返回严格符合"
                            f" {schema.__name__} JSON Schema 的完整 JSON 对象。"
                        )},
                    ]
        latest = self.diagnostics[-1]
        detail = ", ".join(
            f"{key}={latest.get(key)}" for key in (
                "error_type", "finish_reason", "http_status", "content_length",
                "reasoning_length", "elapsed_seconds",
            ) if latest.get(key) is not None
        )
        raise ValueError(
            f"structured action failed after {self.structured_retries + 1} attempts "
            f"from {self.model_name} ({detail})"
        ) from last_error

    def _record_diagnostic(self, diagnostic: dict[str, Any]) -> None:
        self.diagnostics.append(diagnostic)
        if self.diagnostics_path:
            self.diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
            with self.diagnostics_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(diagnostic, ensure_ascii=False) + "\n")

    @staticmethod
    def _context(
        agent: AgentState, observation: dict[str, Any], memories: list[str]
    ) -> dict[str, Any]:
        return {
            "name": agent.name,
            "goals": agent.goals,
            "traits": agent.traits,
            "private_information": agent.private_facts,
            "local_observation": observation,
            "retrieved_memories": memories,
        }

    def propose_offer(
        self,
        agent: AgentState,
        city: CityState,
        firm: FirmState,
        world: WorldState,
        observation: dict[str, Any],
        memories: list[str],
    ) -> OfferAction:
        output_contract = {
            "subsidy": "现金补贴；招商竞争强度更高时，总政策强度不得降低",
            "equity": "股权投资；可用来替代过高现金",
            "credit_support": "信贷支持",
            "land_discount": "0到0.8",
            "approval_speed": "0到1",
            "talent_support": "0到1",
            "rationale": "不超过70字",
            "evidence": "最多3条",
        }
        return self._ask(
            "招商局：根据签约目标和竞争压力提出政策包",
            OfferAction,
            {
                **self._context(agent, observation, memories),
                "output_contract": output_contract,
                "calibration_rule": (
                    "若private_information.competitive_intensity更高，"
                    "subsidy + equity + credit_support*0.08 不得低于低竞争情形。"
                ),
            },
        )  # type: ignore[return-value]

    def choose_organization_initiative(
        self,
        agent: AgentState,
        candidates: list[str],
        observation: dict[str, Any],
        memories: list[str],
    ) -> OrganizationInitiativeChoice:
        return self._ask(
            f"{agent.role.value}组织：决定此刻是否主动占用组织注意力并发起行动",
            OrganizationInitiativeChoice,
            {
                **self._context(agent, observation, memories),
                "allowed_action_ids": candidates,
                "hard_rules": [
                    "decision只能是act或wait",
                    "若decision为act，action_id必须严格来自allowed_action_ids",
                    "若decision为wait，action_id必须填写wait",
                    "不得代替其他部门行动，也不得绕过财政、合同和生产规则",
                ],
                "output_contract": {
                    "decision": "act | wait",
                    "action_id": "act时选一个allowed_action_ids；wait时填wait",
                    "urgency": "0到1，代表本部门此刻争夺组织注意力的紧迫度",
                    "target_actor_id": "可选，本行动希望影响或沟通的主体",
                    "rationale": "不超过70字，解释为何现在行动或为何等待",
                },
            },
        )  # type: ignore[return-value]

    def choose_procedure_transition(
        self,
        agent: AgentState,
        candidates: list[str],
        observation: dict[str, Any],
        memories: list[str],
    ) -> ProcedureTransitionChoice:
        return self._ask(
            "市领导：根据议程、部门协调和当前程序状态决定程序下一步",
            ProcedureTransitionChoice,
            {
                **self._context(agent, observation, memories),
                "allowed_transitions": candidates,
                "hard_rule": "transition必须严格来自allowed_transitions；暂停、退回和重新议程化都是真实可选结果。",
                "output_contract": {
                    "transition": "allowed_transitions中的一个",
                    "rationale": "不超过80字，说明议程压力、风险和协调依据",
                },
            },
        )  # type: ignore[return-value]

    def respond_to_offer(
        self,
        agent: AgentState,
        observation: dict[str, Any],
        memories: list[str],
    ) -> EnterpriseResponseAction:
        return self._ask(
            "企业董事会：决定现在接受、还价还是退出该城市谈判",
            EnterpriseResponseAction,
            {
                **self._context(agent, observation, memories),
                "hard_rules": [
                    "response只能是accept、counter或terminate",
                    "counter时只填写可量化的counter_terms",
                    "规则引擎会阻止低于企业最低效用门槛的accept",
                ],
                "output_contract": {
                    "response": "accept | counter | terminate",
                    "counter_terms": "还价时给出subsidy_floor、equity_floor和require_phased_delivery等数值",
                    "confidence": "0到1",
                    "rationale": "不超过80字，说明信息充分度、效用差距与等待成本",
                },
            },
        )  # type: ignore[return-value]

    def decide_negotiation_timing(
        self,
        agent: AgentState,
        observation: dict[str, Any],
        memories: list[str],
    ) -> NegotiationTimingAction:
        return self._ask(
            "企业董事会：决定本轮是否立即选址、继续等待竞争报价或全部退出",
            NegotiationTimingAction,
            {
                **self._context(agent, observation, memories),
                "hard_rules": [
                    "decision只能是select_now、continue_negotiating或exit_all",
                    "没有已接受城市时不能select_now",
                    "必须权衡信息价值、机会成本和剩余活跃谈判",
                ],
                "output_contract": {
                    "decision": "select_now | continue_negotiating | exit_all",
                    "confidence": "0到1",
                    "rationale": "不超过80字",
                },
            },
        )  # type: ignore[return-value]

    def create_organization_plan(
        self,
        agent: AgentState,
        allowed_actions: list[str],
        observation: dict[str, Any],
        memories: list[str],
    ) -> OrganizationPlanAction:
        return self._ask(
            f"{agent.role.value}组织：比较策略路径并给出紧凑的跨季度行动序列",
            CompactOrganizationPlanAction,
            {
                **self._context(agent, observation, memories),
                "allowed_action_ids": allowed_actions,
                "hard_rules": [
                    "只比较2条不同策略，selected_strategy必须等于某个alternatives.id",
                    "action_sequence只填2到4个allowed_action_ids",
                    "不得创造预算或保证其他主体配合",
                ],
                "output_contract": {
                    "objective": "一句话目标",
                    "alternatives": "正好2项；每项只含id、approach、risk、score",
                    "selected_strategy": "一个alternatives.id",
                    "action_sequence": "2到4个allowed_action_ids",
                    "branch_condition": "一句话说明何时偏离原序列并重规划",
                    "assumptions": "最多3条短句",
                    "rationale": "不超过60字",
                },
            },
        )  # type: ignore[return-value]

    def propose_novel_organization_action(
        self,
        agent: AgentState,
        observation: dict[str, Any],
        memories: list[str],
    ) -> NovelOrganizationAction:
        return self._ask(
            f"{agent.role.value}组织：提出动作目录之外但职责范围以内的新组织手段",
            NovelOrganizationAction,
            {
                **self._context(agent, observation, memories),
                "example_mechanisms_not_exhaustive": [
                    "upward_endorsement", "association_coalition",
                    "demonstration_project", "meeting_window", "strategic_delay",
                    "cross_department_taskforce", "expert_consultation",
                ],
                "executable_effect_dimensions": [
                    "agenda_priority_delta", "coalition_support_delta",
                    "procedural_completeness_delta", "approval_speed_bonus",
                    "credibility_delta", "attention_budget_delta",
                ],
                "hard_rules": [
                    "mechanism可以提出新的英文snake_case名称，不局限于示例目录",
                    "可以申请现金、股权、土地或信贷，但申请只会生成审批事项，不能直接改变世界",
                    "不得伪造证据、读取无权私有信息或代替其他主体作最终决定",
                    "不得跳过法定程序；requested_effects只是申请并由规则引擎限幅",
                ],
                "output_contract": {
                    "title": "具体且可观察的新组织行动",
                    "intent": "希望解决的组织问题",
                    "mechanism": "已有示例或新提出的英文snake_case机制",
                    "domain": "所属职责领域",
                    "arena": "formal/informal/public/market之一",
                    "target_actor_ids": "需要沟通或共同决策的主体，最多6个",
                    "requested_information": "所需信息；不得要求未授权私有真值",
                    "authority_claims": "行动希望由本组织直接作出的决定或授权；没有则为空",
                    "requested_effects": "只申请可执行效果维度",
                    "resource_request": "可为空；资源申请将进入协调或审批，不直接执行",
                    "timing": "希望采取行动的时点",
                    "reversibility": "0到1，越高越容易撤回",
                    "rationale": "不超过80字",
                },
            },
        )  # type: ignore[return-value]

    def choose_organization_action(
        self,
        agent: AgentState,
        candidates: list[str],
        observation: dict[str, Any],
        memories: list[str],
    ) -> OrganizationActionChoice:
        return self._ask(
            f"{agent.role.value}组织：从本部门权限内选择下一步组织行动",
            OrganizationActionChoice,
            {
                **self._context(agent, observation, memories),
                "allowed_action_ids": candidates,
                "hard_rule": "action_id必须严格来自allowed_action_ids；不得代替其他部门行动或绕过财政、合同和生产规则。",
                "output_contract": {
                    "action_id": "allowed_action_ids中的一个",
                    "confidence": "0到1",
                    "rationale": "不超过60字，解释目标、信息和关系权衡",
                },
            },
        )  # type: ignore[return-value]

    def review_offer(
        self,
        agent: AgentState,
        city: CityState,
        proposal: PolicyPackage,
        observation: dict[str, Any],
        memories: list[str],
    ) -> FinanceAction:
        output_contract = {
            "approved": "boolean: 是否愿意放行招商局方案；数值上限由规则引擎填充",
            "concerns": "最多3条，每条不超过30字",
            "conditions": "最多3条，每条不超过30字",
            "rationale": "不超过60字",
        }
        return self._ask(
            "财政局：独立审核并可以否决政策包",
            FinanceAction,
            {
                **self._context(agent, observation, memories),
                "proposal": _package_dict(proposal),
                "proposal_fiscal_cost": proposal.fiscal_cost,
                "output_contract": output_contract,
                "rule_engine_note": (
                    "不要计算或猜测财政数值上限；maximum_* 字段可省略或填0，"
                    "规则引擎将按财政底线确定性填充。"
                ),
            },
        )  # type: ignore[return-value]

    def resolve_offer(
        self,
        agent: AgentState,
        city: CityState,
        proposal: PolicyPackage,
        review: FinanceAction,
        observation: dict[str, Any],
        memories: list[str],
    ) -> ResolutionAction:
        hard_caps = {
            "maximum_fiscal_cost": review.maximum_fiscal_cost,
            "maximum_subsidy": review.maximum_subsidy,
            "maximum_equity": review.maximum_equity,
            "maximum_credit_support": review.maximum_credit_support,
            "maximum_first_period_payment": review.maximum_first_period_payment,
        }
        output_contract = {
            "resolution": "approved | restructured_after_tool_veto | withdrawn",
            "subsidy": "现金补贴，必须不超过maximum_subsidy",
            "equity": "股权投资，必须不超过maximum_equity",
            "credit_support": "信贷支持，必须不超过maximum_credit_support",
            "approval_speed": "0到1",
            "talent_support": "0到1",
            "rationale": "不超过70字；解释协调取舍",
        }
        return self._ask(
            "市领导：处理财政否决并作出最终协调决定",
            ResolutionAction,
            {
                **self._context(agent, observation, memories),
                "proposal": _package_dict(proposal),
                "finance_review": {
                    "approved": review.approved,
                    "concerns": review.concerns,
                    "conditions": review.conditions,
                    "rationale": review.rationale,
                },
                "hard_caps": hard_caps,
                "hard_rule": (
                    "最终总成本、现金、股权和信贷均不得超过hard_caps；"
                    "不要输出分期兑现计划，规则引擎会确定性生成payment_schedule。"
                ),
                "output_contract": output_contract,
            },
        )  # type: ignore[return-value]

    def select_location(
        self,
        agent: AgentState,
        firm: FirmState,
        scores: dict[str, float],
        observation: dict[str, Any],
        memories: list[str],
    ) -> LocationAction:
        return self._ask(
            "企业董事会：在备选城市中做不可逆选址决策",
            LocationAction,
            {
                **self._context(agent, observation, memories),
                "rule_engine_utility_scores": scores,
                "allowed_city_ids": list(scores),
                "output_schema": LocationAction.model_json_schema(),
            },
        )  # type: ignore[return-value]

    def reflect(self, agent: AgentState, action: str, outcome: str) -> str:
        class Reflection(BaseModel):
            reflection: str

        try:
            result = self._ask(
                f"{agent.role}：行动后复盘",
                Reflection,
                {
                    "agent": self._context(agent, {}, []),
                    "action": action,
                    "outcome": outcome,
                    "output_contract": {"reflection": "不超过60字"},
                },
            )
            return result.reflection  # type: ignore[attr-defined]
        except (httpx.HTTPError, ValueError, KeyError):
            return super().reflect(agent, action, outcome)


def build_cognition(mode: str | None = None, model_name: str | None = None) -> CognitiveProvider:
    requested = (mode or os.getenv("INSIDEGOV_POLICY", "deterministic")).lower()
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if requested == "llm" and api_key:
        return DeepSeekCognition(
            api_key=api_key,
            model_name=model_name or os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        )
    return DeterministicCognition()


def _package_dict(package: PolicyPackage) -> dict[str, Any]:
    return {
        "city_id": package.city_id,
        "subsidy": package.subsidy,
        "equity": package.equity,
        "land_discount": package.land_discount,
        "credit_support": package.credit_support,
        "approval_speed": package.approval_speed,
        "talent_support": package.talent_support,
        "fiscal_cost": package.fiscal_cost,
    }
