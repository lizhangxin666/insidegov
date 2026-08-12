"""Talent-scenario cognition layer.

Four replaceable reasoning steps mirror the communication-and-negotiation loop:
- compose_demand: 企业把模糊诉求翻译成结构化需求向量（需求的精准表达）；
- design_policy: 政府根据需求向量与候选人公开画像设计政策工具组合与语言模式（信任与信息）；
- interpret_offer: 候选人解读 offer，受理解度与信任影响，决定接受 / 要价 / 拒绝（相互理解）；
- broker_match: 中介平台做双语翻译与信息线索，降低跨语系对接成本（翻译 / 中介机制）。

The cognition layer only proposes structured actions; the engine validates and
settles every change. DeepSeek mode reuses the same schema-validated protocol
and falls back to the deterministic baseline on any failure.
"""

from __future__ import annotations

import json
import os
import re
import time
from abc import ABC, abstractmethod
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError

from .models import AgentState, CityState, FirmState, PlatformState, TalentState, WorldState


class DemandAction(BaseModel):
    vector: dict[str, float]
    budget: float = Field(ge=0)
    form: str
    clarity: float = Field(ge=0, le=1)
    description: str
    rationale: str


class PolicyResponseAction(BaseModel):
    tools: dict[str, float] = Field(default_factory=dict)
    annual_salary: float = Field(ge=0)
    language_mode: str
    provide_explanation: bool
    explanation: str
    rationale: str


class TalentReactionAction(BaseModel):
    response: str
    understood: float = Field(ge=0, le=1)
    trust_delta: float = Field(ge=-1, le=1)
    counter_tools: dict[str, float] = Field(default_factory=dict)
    counter_salary: float = Field(ge=0, default=0)
    rationale: str


class MatchAction(BaseModel):
    translation_notes: str
    truth_clues: list[str]
    suggested_tools: list[str]
    rationale: str


class TalentCognitiveProvider(ABC):
    mode = "deterministic"
    model_name: str | None = None

    @abstractmethod
    def compose_demand(
        self,
        agent: AgentState,
        firm: FirmState,
        world: WorldState,
        observation: dict[str, Any],
        memories: list[str],
    ) -> DemandAction:
        raise NotImplementedError

    @abstractmethod
    def design_policy(
        self,
        agent: AgentState,
        city: CityState,
        firm: FirmState,
        talent: TalentState,
        demand: DemandAction,
        world: WorldState,
        observation: dict[str, Any],
        memories: list[str],
    ) -> PolicyResponseAction:
        raise NotImplementedError

    @abstractmethod
    def interpret_offer(
        self,
        agent: AgentState,
        talent: TalentState,
        offer: dict[str, Any],
        world: WorldState,
        observation: dict[str, Any],
        memories: list[str],
    ) -> TalentReactionAction:
        raise NotImplementedError

    @abstractmethod
    def broker_match(
        self,
        agent: AgentState,
        platform: PlatformState,
        demand: DemandAction,
        talent: TalentState,
        world: WorldState,
        observation: dict[str, Any],
        memories: list[str],
    ) -> MatchAction:
        raise NotImplementedError

    def reflect(self, agent: AgentState, action: str, outcome: str) -> str:
        return f"{agent.name}复盘：{action}已执行；{outcome}。下轮将根据新证据调整。"


class DeterministicTalentCognition(TalentCognitiveProvider):
    """Reproducible baseline with heterogeneous thresholds per talent."""

    def compose_demand(
        self,
        agent: AgentState,
        firm: FirmState,
        world: WorldState,
        observation: dict[str, Any],
        memories: list[str],
    ) -> DemandAction:
        assert firm.tech_demand is not None
        demand = firm.tech_demand
        return DemandAction(
            vector=dict(demand.vector),
            budget=demand.budget,
            form=demand.form,
            clarity=demand.clarity,
            description=demand.description,
            rationale="把技术瓶颈翻译成能力需求向量，便于与人才能力做结构匹配",
        )

    def design_policy(
        self,
        agent: AgentState,
        city: CityState,
        firm: FirmState,
        talent: TalentState,
        demand: DemandAction,
        world: WorldState,
        observation: dict[str, Any],
        memories: list[str],
    ) -> PolicyResponseAction:
        tools: dict[str, float] = {}
        # 私有顾虑不直接可见，只能通过公开画像推断（青年教师→身份+学术羁绊，
        # 教授→学术羁绊与投入度，产业专家→报酬）。
        inference = self._infer_concerns(talent)
        spendable = max(0.0, city.available_budget - city.available_budget * 0.30)
        relocation_cap = min(18.0, spendable * 0.10)
        if inference["identity"] > 0.5:
            tools["title_track"] = round(min(0.9, 0.45 + inference["identity"] * 0.4), 2)
        if inference["academic"] > 0.4:
            tools["lab_credit"] = round(min(0.9, 0.40 + inference["academic"] * 0.4), 2)
        if inference["compensation"] > 0.4 or talent.talent_type == "industry_expert":
            tools["relocation"] = round(min(relocation_cap, 6.0 + inference["compensation"] * 10), 2)
        if inference["risk"] > 0.4:
            tools["open_call"] = round(min(30.0, 8.0 + inference["risk"] * 22), 2)
        if not tools:
            tools["relocation"] = round(min(relocation_cap, 6.0), 2)
        plain = world.expression_mode == "plain"
        return PolicyResponseAction(
            tools=tools,
            annual_salary=round(demand.budget * 0.72, 2),
            language_mode=world.expression_mode,
            provide_explanation=plain,
            explanation=(
                f"该项政策覆盖人才在{'身份、学术、报酬、风险'[: max(4, len(tools))]}方面的顾虑，"
                "并明确兑现节奏" if plain else "按照政策口径发布，具体细则以文件为准"
            ),
            rationale="根据候选人公开画像选择政策工具，表达方式由语言模式决定",
        )

    def interpret_offer(
        self,
        agent: AgentState,
        talent: TalentState,
        offer: dict[str, Any],
        world: WorldState,
        observation: dict[str, Any],
        memories: list[str],
    ) -> TalentReactionAction:
        understanding = float(offer.get("understanding", 0.5))
        trust = float(offer.get("trust", 0.55))
        coverage = float(offer.get("coverage", 0.4))
        perceived = understanding * 0.35 + trust * 0.30 + coverage * 0.35
        risk_aversion = float(agent.traits.get("risk_aversion", 0.5))
        opportunity = float(agent.private_facts.get("opportunity_cost", 60.0)) / 100.0
        accept_bar = 0.58 + risk_aversion * 0.16 + opportunity * 0.18
        counter_bar = accept_bar - 0.14
        if perceived >= accept_bar:
            response = "accept"
        elif perceived >= counter_bar:
            response = "counter"
        else:
            response = "reject"
        uncovered = {
            concern: weight
            for concern, weight in talent.concerns.items()
            if weight > 0.45 and not self._tool_covers(offer.get("tools", {}), concern)
        }
        counter_tools = {
            self._tool_for(concern): round(min(1.0, 0.5 + weight * 0.4), 2)
            for concern, weight in uncovered.items()
        }
        return TalentReactionAction(
            response=response,
            understood=round(understanding, 3),
            trust_delta=round(0.12 * understanding - 0.08 * (1 - understanding), 3),
            counter_tools=counter_tools,
            counter_salary=round(float(offer.get("annual_salary", 0)) * 1.12, 2) if response == "counter" else 0.0,
            rationale=(
                "理解充分且顾虑被覆盖，愿意签约" if response == "accept"
                else "部分顾虑未覆盖，提出补充条件" if response == "counter"
                else "理解不足或顾虑过重，选择观望"
            ),
        )

    def broker_match(
        self,
        agent: AgentState,
        platform: PlatformState,
        demand: DemandAction,
        talent: TalentState,
        world: WorldState,
        observation: dict[str, Any],
        memories: list[str],
    ) -> MatchAction:
        suggested = [
            self._tool_for(concern)
            for concern, weight in talent.concerns.items()
            if weight > 0.45
        ]
        return MatchAction(
            translation_notes=(
                f"企业需求「{demand.description}」实质是量产与中试瓶颈，"
                f"对应人才 {talent.name} 的能力标签与技术经验"
            ),
            truth_clues=[
                f"{talent.name} 最在意的是{'职称通道' if talent.concerns.get('identity', 0) > 0.6 else '课题折算与考核'}",
                f"企业可接受的合作形式为 {demand.form}",
            ],
            suggested_tools=suggested,
            rationale="以第三方身份翻译双方语言，并披露可验证的真实诉求线索",
        )

    @staticmethod
    def _infer_concerns(talent: TalentState) -> dict[str, float]:
        # 公开画像：青年教师身份与学术羁绊高、教授学术羁绊中而投入度低、
        # 产业专家报酬诉求高——据此推断顾虑，无法看到私有精确值。
        if talent.talent_type == "junior_faculty":
            return {"identity": 0.70, "academic": 0.66, "compensation": 0.42, "risk": 0.48}
        if talent.talent_type == "senior_professor":
            return {"identity": 0.15, "academic": 0.55, "compensation": 0.30, "risk": 0.26}
        return {"identity": 0.05, "academic": 0.05, "compensation": 0.62, "risk": 0.34}

    @staticmethod
    def _tool_for(concern: str) -> str:
        mapping = {
            "identity": "title_track",
            "academic": "lab_credit",
            "compensation": "relocation",
            "risk": "open_call",
        }
        return mapping.get(concern, "relocation")

    @staticmethod
    def _tool_covers(tools: dict[str, float], concern: str) -> bool:
        tool = {
            "identity": "title_track",
            "academic": "lab_credit",
            "compensation": "relocation",
            "risk": "open_call",
        }.get(concern)
        return bool(tool) and tools.get(tool, 0) > 0.3


class DeepSeekTalentCognition(TalentCognitiveProvider):
    mode = "llm"
    request_deadline_seconds = 30.0

    def __init__(
        self,
        api_key: str,
        model_name: str = "deepseek-v4-flash",
        base_url: str = "https://api.deepseek.com",
        request_timeout: float = 20.0,
    ) -> None:
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY is required for LLM mode")
        self.api_key = api_key
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self.request_deadline_seconds = request_timeout + 10.0
        timeout = httpx.Timeout(connect=8.0, read=request_timeout, write=8.0, pool=8.0)
        self.client = httpx.Client(timeout=timeout, limits=httpx.Limits(max_connections=4, max_keepalive_connections=0), trust_env=False)
        self.fallback = DeterministicTalentCognition()
        self.response_cache: dict[str, dict[str, Any]] = {}

    def _ask(self, role: str, schema: type[BaseModel], payload: dict[str, Any]) -> BaseModel:
        system = (
            "你是中国政企互动沙盘中高校人才对接场景的独立行动者。"
            "你只能根据所给私有信息、局部观察与记忆决策，不得臆测他人私有底线。"
            "输出严格 JSON，不要 Markdown，金额单位为万元/年。"
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
            "max_tokens": 900,
            "response_format": {"type": "json_object"},
        }
        started_at = time.monotonic()
        response = self.client.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=body,
        )
        if time.monotonic() - started_at > self.request_deadline_seconds:
            raise httpx.TimeoutException(f"{self.model_name} exceeded deadline")
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.MULTILINE).strip()
        if not content:
            raise ValueError(f"empty structured action from {self.model_name}")
        try:
            result = schema.model_validate_json(content)
            self.response_cache[cache_key] = result.model_dump()
            return result
        except (ValidationError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid structured action from {self.model_name}") from exc

    @staticmethod
    def _context(agent: AgentState, observation: dict[str, Any], memories: list[str]) -> dict[str, Any]:
        return {
            "name": agent.name,
            "goals": agent.goals,
            "traits": agent.traits,
            "private_information": agent.private_facts,
            "local_observation": observation,
            "retrieved_memories": memories,
        }

    def compose_demand(
        self,
        agent: AgentState,
        firm: FirmState,
        world: WorldState,
        observation: dict[str, Any],
        memories: list[str],
    ) -> DemandAction:
        return self._ask(
            "企业：把技术瓶颈翻译成结构化能力需求",
            DemandAction,
            {**self._context(agent, observation, memories), "output_schema": DemandAction.model_json_schema()},
        )  # type: ignore[return-value]

    def design_policy(
        self,
        agent: AgentState,
        city: CityState,
        firm: FirmState,
        talent: TalentState,
        demand: DemandAction,
        world: WorldState,
        observation: dict[str, Any],
        memories: list[str],
    ) -> PolicyResponseAction:
        return self._ask(
            "政府人才办：设计政策工具组合并选择表达方式",
            PolicyResponseAction,
            {
                **self._context(agent, observation, memories),
                "demand": demand.model_dump(),
                "city_budget": city.available_budget,
                "expression_mode": world.expression_mode,
                "allowed_tools": ["relocation", "title_track", "lab_credit", "open_call", "interpreter"],
                "output_schema": PolicyResponseAction.model_json_schema(),
            },
        )  # type: ignore[return-value]

    def interpret_offer(
        self,
        agent: AgentState,
        talent: TalentState,
        offer: dict[str, Any],
        world: WorldState,
        observation: dict[str, Any],
        memories: list[str],
    ) -> TalentReactionAction:
        return self._ask(
            "人才：解读 offer 并决定接受 / 要价 / 拒绝",
            TalentReactionAction,
            {
                **self._context(agent, observation, memories),
                "offer": offer,
                "allowed_responses": ["accept", "counter", "reject"],
                "output_schema": TalentReactionAction.model_json_schema(),
            },
        )  # type: ignore[return-value]

    def broker_match(
        self,
        agent: AgentState,
        platform: PlatformState,
        demand: DemandAction,
        talent: TalentState,
        world: WorldState,
        observation: dict[str, Any],
        memories: list[str],
    ) -> MatchAction:
        return self._ask(
            "中介平台：翻译双方语言并提供可验证线索",
            MatchAction,
            {
                **self._context(agent, observation, memories),
                "demand": demand.model_dump(),
                "talent_public_profile": {
                    "name": talent.name, "type": talent.talent_type.value,
                    "capability": talent.capability,
                },
                "output_schema": MatchAction.model_json_schema(),
            },
        )  # type: ignore[return-value]

    def reflect(self, agent: AgentState, action: str, outcome: str) -> str:
        class Reflection(BaseModel):
            reflection: str

        try:
            result = self._ask(
                f"{agent.role}：行动后复盘",
                Reflection,
                {"agent": self._context(agent, {}, []), "action": action, "outcome": outcome,
                 "output_schema": Reflection.model_json_schema()},
            )
            return result.reflection  # type: ignore[attr-defined]
        except (httpx.HTTPError, ValueError, KeyError):
            return super().reflect(agent, action, outcome)


def build_talent_cognition(mode: str | None = None, model_name: str | None = None) -> TalentCognitiveProvider:
    requested = (mode or os.getenv("INSIDEGOV_POLICY", "deterministic")).lower()
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if requested == "llm" and api_key:
        return DeepSeekTalentCognition(
            api_key=api_key,
            model_name=model_name or os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        )
    return DeterministicTalentCognition()
