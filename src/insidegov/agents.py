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
    concerns: list[str]
    conditions: list[str] = Field(default_factory=list)
    rationale: str


class ResolutionAction(BaseModel):
    resolution: str
    subsidy: float = Field(ge=0)
    equity: float = Field(ge=0)
    land_discount: float = Field(ge=0, le=0.8)
    credit_support: float = Field(ge=0)
    approval_speed: float = Field(ge=0, le=1)
    talent_support: float = Field(ge=0, le=1)
    rationale: str

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
        aggressiveness = 1 + agent.traits.get("short_termism", 0.4) * 0.08
        return OfferAction(
            subsidy=package.subsidy * aggressiveness,
            equity=package.equity * aggressiveness,
            land_discount=package.land_discount,
            credit_support=package.credit_support,
            approval_speed=package.approval_speed,
            talent_support=package.talent_support,
            rationale="在增长、就业和政府信用之间形成可执行的招商报价",
            evidence=[
                f"剩余可用财力 {city.available_budget:.1f}",
                f"财政压力 {city.fiscal_pressure:.0%}",
                f"领导任期剩余 {city.leadership_term_remaining} 季度",
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
        maximum = round(min(spendable * 0.42, city.available_budget * 0.19) * risk_discount, 2)
        approved = proposal.fiscal_cost <= maximum and city.fiscal_pressure <= stress_limit
        concerns = []
        if proposal.fiscal_cost > maximum:
            concerns.append("政策包超过本轮财政承受上限")
        if city.fiscal_pressure > stress_limit:
            concerns.append("债务与已承诺支出导致压力超阈值")
        if not concerns:
            concerns.append("需绑定项目进度和就业条件")
        return FinanceAction(
            approved=approved,
            maximum_fiscal_cost=maximum,
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
        if proposal.fiscal_cost <= review.maximum_fiscal_cost:
            scale = 1.0
            resolution = "approved"
        else:
            scale = review.maximum_fiscal_cost / max(proposal.fiscal_cost, 0.01)
            resolution = "modified_after_finance_veto"
        return ResolutionAction(
            resolution=resolution,
            subsidy=proposal.subsidy * scale,
            equity=proposal.equity * scale,
            land_discount=min(proposal.land_discount, 0.52),
            credit_support=proposal.credit_support * scale,
            approval_speed=proposal.approval_speed,
            talent_support=proposal.talent_support,
            rationale=(
                "采纳财政局上限并改为条件性、分期兑现"
                if scale < 1
                else "财政承受力内批准，保留履约条件"
            ),
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

    def _ask(self, role: str, schema: type[BaseModel], payload: dict[str, Any]) -> BaseModel:
        system = (
            "你是中国地方政企互动沙盘中的一个独立行动者。"
            "你只能根据所给私有信息、局部观察与记忆决策，不得臆测其他主体的私有底线。"
            "输出严格 JSON，不要 Markdown，所有金额单位为亿元。"
        )
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
            return schema.model_validate_json(content)
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
            "市领导：提出招商政策包",
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
                "hard_rule": "最终财政成本不得超过财政局上限",
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
