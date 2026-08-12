from __future__ import annotations

import json
import os
import re
from abc import ABC, abstractmethod
from typing import Any

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
    rationale: str
    evidence: list[str] = Field(default_factory=list)

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
    maximum_fiscal_cost: float = Field(ge=0)
    maximum_subsidy: float = Field(ge=0)
    maximum_equity: float = Field(ge=0)
    maximum_credit_support: float = Field(ge=0)
    maximum_first_period_payment: float = Field(ge=0)
    concerns: list[str]
    conditions: list[str] = Field(default_factory=list)
    rationale: str


class TrancheAction(BaseModel):
    item: str
    amount: float = Field(ge=0)
    due_offset: int = Field(ge=1, le=12)
    condition: str


class ResolutionAction(BaseModel):
    resolution: str
    subsidy: float = Field(ge=0)
    equity: float = Field(ge=0)
    land_discount: float = Field(ge=0, le=0.8)
    credit_support: float = Field(ge=0)
    approval_speed: float = Field(ge=0, le=1)
    talent_support: float = Field(ge=0, le=1)
    payment_schedule: list[TrancheAction]
    rationale: str

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


class LocationAction(BaseModel):
    city_id: str
    confidence: float = Field(ge=0, le=1)
    rationale: str
    evidence: list[str] = Field(default_factory=list)


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

    def __init__(
        self,
        api_key: str,
        model_name: str = "deepseek-v4-flash",
        base_url: str = "https://api.deepseek.com",
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY is required for LLM mode")
        self.api_key = api_key
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=45)
        self.fallback = DeterministicCognition()
        self.response_cache: dict[str, dict[str, Any]] = {}

    def _ask(self, role: str, schema: type[BaseModel], payload: dict[str, Any]) -> BaseModel:
        system = (
            "你是中国地方政企互动沙盘中的一个独立行动者。"
            "你只能根据所给私有信息、局部观察与记忆决策，不得臆测其他主体的私有底线。"
            "输出严格 JSON，不要 Markdown，所有金额单位为亿元。"
        )
        cache_key = json.dumps({"role": role, "schema": schema.__name__, "payload": payload}, ensure_ascii=False, sort_keys=True)
        if cache_key in self.response_cache:
            return schema.model_validate(self.response_cache[cache_key])
        body = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps({"role": role, **payload}, ensure_ascii=False)},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        response = self.client.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=body,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.MULTILINE).strip()
        try:
            result = schema.model_validate_json(content)
            self.response_cache[cache_key] = result.model_dump()
            return result
        except (ValidationError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid structured action from {self.model_name}") from exc

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
        return self._ask(
            "招商局：根据签约目标和竞争压力提出政策包",
            OfferAction,
            {**self._context(agent, observation, memories), "output_schema": OfferAction.model_json_schema()},
        )  # type: ignore[return-value]

    def review_offer(
        self,
        agent: AgentState,
        city: CityState,
        proposal: PolicyPackage,
        observation: dict[str, Any],
        memories: list[str],
    ) -> FinanceAction:
        return self._ask(
            "财政局：独立审核并可以否决政策包",
            FinanceAction,
            {
                **self._context(agent, observation, memories),
                "proposal": _package_dict(proposal),
                "proposal_fiscal_cost": proposal.fiscal_cost,
                "output_schema": FinanceAction.model_json_schema(),
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
        return self._ask(
            "市领导：处理财政否决并作出最终协调决定",
            ResolutionAction,
            {
                **self._context(agent, observation, memories),
                "proposal": _package_dict(proposal),
                "finance_review": review.model_dump(),
                "hard_rule": (
                    "最终总成本、现金、股权、信贷和首期支付均不得超过财政局各自上限；"
                    "必须输出分期兑现计划，且分项金额与最终政策包一致"
                ),
                "output_schema": ResolutionAction.model_json_schema(),
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
                    "output_schema": Reflection.model_json_schema(),
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
