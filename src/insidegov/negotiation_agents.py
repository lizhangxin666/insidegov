"""政企协商机制实验室——认知层。

政府与企业拥有不同的语言体系、知识结构与私有信息。本模块实现五种可替换
的协商推理步骤：

- diagnose:   政府决定「追问 / 复述 / 披露约束 / 直接提案」，由协商机制决定；
- answer:     企业回应追问，策略性决定披露多少（商业秘密、夸大倾向）；
- confirm:    企业复述确认政府的理解，纠正关键误解（复述确认机制的核心）；
- propose:    政府基于当前理解生成政策方案包（单方案 / 多方案 / 分阶段）；
- evaluate:   企业评估方案（感知匹配度、理解、可行性、信任），决定接受/还价/终止。

认知层只提出结构化行动；引擎拥有客观真相（真实需求、理解差距、匹配度、
财政成本、履约结果），负责验证与结算。LLM 模式复用同一协议，失败降级到
确定性基线。
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

from .models import AgentState, CityState, FirmState, GovBelief, LatentNeed, StatedNeed, WorldState

# 合作方式 → 政策工具族（政府理解企业模式后应使用的工具）
MODE_TOOLS: dict[str, list[str]] = {
    "fulltime": ["talent_recruit", "relocation"],
    "flexible": ["joint_rnd", "tech_contract"],
    "pilot": ["pilot_voucher", "tech_contract", "rnd_subsidy"],
    "diagnosis": ["tech_contract", "rnd_subsidy"],
    "capacity": ["industry_fund", "equipment_subsidy", "tax_credit"],
    "project": ["digital_subsidy", "tech_contract"],
    "digital": ["digital_subsidy", "tech_contract"],
}
# 表面分类 → 默认工具族：企业说「缺人才」就默认全职引才，这是错位的来源
CATEGORY_TOOLS: dict[str, list[str]] = {
    "talent_shortage": ["talent_recruit", "relocation"],
    "digitalization": ["digital_subsidy", "tech_contract"],
    "expansion": ["industry_fund", "equipment_subsidy", "tax_credit"],
    "consulting": ["tech_contract", "rnd_subsidy"],
}
# 澄清追问的顺序：问题本质与合作方式最优先
CLARIFY_PRIORITY = ["problem", "mode", "target", "deadline", "constraint", "budget", "commitment"]


class DiagnoseAction(BaseModel):
    next_action: str  # clarify / paraphrase / disclose / propose
    questions: list[str] = Field(default_factory=list)
    components: dict[str, float] = Field(default_factory=dict)
    rationale: str


class DiscloseAction(BaseModel):
    components: dict[str, float] = Field(default_factory=dict)
    text: str
    rationale: str


class ConfirmAction(BaseModel):
    confirmed: bool
    correction: str | None = None
    components: dict[str, float] = Field(default_factory=dict)
    rationale: str


class ProposalAction(BaseModel):
    options: list[dict[str, Any]] = Field(default_factory=list)
    rationale: str


class EvaluateAction(BaseModel):
    response: str  # accept / counter / terminate
    perceived_fit: float = Field(ge=0, le=1)
    understanding: float = Field(ge=0, le=1)
    feasibility: float = Field(ge=0, le=1)
    trust_delta: float = Field(ge=-1, le=1)
    counter_tools: dict[str, float] = Field(default_factory=dict)
    rationale: str


class NegotiationCognitiveProvider(ABC):
    mode = "deterministic"
    model_name: str | None = None

    @abstractmethod
    def diagnose(
        self,
        agent: AgentState,
        city: CityState,
        firm: FirmState,
        stated: StatedNeed,
        belief: GovBelief,
        protocol: str,
        round_index: int,
        world: WorldState,
    ) -> DiagnoseAction:
        raise NotImplementedError

    @abstractmethod
    def answer(
        self,
        agent: AgentState,
        latent: LatentNeed,
        stated: StatedNeed,
        questions: list[str],
        world: WorldState,
    ) -> DiscloseAction:
        raise NotImplementedError

    @abstractmethod
    def confirm(
        self,
        agent: AgentState,
        latent: LatentNeed,
        belief: GovBelief,
        world: WorldState,
    ) -> ConfirmAction:
        raise NotImplementedError

    @abstractmethod
    def propose(
        self,
        agent: AgentState,
        city: CityState,
        firm: FirmState,
        stated: StatedNeed,
        belief: GovBelief,
        protocol: str,
        world: WorldState,
    ) -> ProposalAction:
        raise NotImplementedError

    @abstractmethod
    def evaluate(
        self,
        agent: AgentState,
        latent: LatentNeed,
        stated: StatedNeed,
        option: dict[str, Any],
        trust: float,
        world: WorldState,
    ) -> EvaluateAction:
        raise NotImplementedError


class DeterministicNegotiationCognition(NegotiationCognitiveProvider):
    """可复现基线：规则化策略，体现机制差异而非语言天赋。"""

    # ---------------- 政府：诊断策略 ---------------- #
    def diagnose(
        self,
        agent: AgentState,
        city: CityState,
        firm: FirmState,
        stated: StatedNeed,
        belief: GovBelief,
        protocol: str,
        round_index: int,
        world: WorldState,
    ) -> DiagnoseAction:
        if protocol == "policy_match":
            return DiagnoseAction(
                next_action="propose", rationale="政策匹配：按关键词立即推荐，不追问"
            )
        if protocol == "clarify_first":
            if self._understanding_ok(belief):
                return DiagnoseAction(next_action="propose", rationale="需求已澄清，进入提案")
            # 分批追问：第 n 轮问优先序列的第 n 段，避免重复问已披露成分
            questions = [c for c in CLARIFY_PRIORITY[round_index * 3: round_index * 3 + 3]]
            if not questions:
                return DiagnoseAction(next_action="propose", rationale="需求已澄清，进入提案")
            return DiagnoseAction(
                next_action="clarify", questions=questions,
                rationale=f"澄清优先：第 {round_index + 1} 轮追问 {len(questions)} 个成分",
            )
        if protocol == "paraphrase_confirm":
            return DiagnoseAction(
                next_action="paraphrase",
                rationale="复述确认：复述当前理解并请企业确认",
            )
        if protocol == "constraints_first":
            if round_index == 0:
                return DiagnoseAction(
                    next_action="disclose",
                    rationale="约束先行：先披露政府权限与预算边界",
                )
            return DiagnoseAction(next_action="propose", rationale="双方约束已披露，进入提案")
        # free / multi_option / phased_commitment
        return DiagnoseAction(next_action="propose", rationale="按当前理解直接提案")

    def answer(
        self,
        agent: AgentState,
        latent: LatentNeed,
        stated: StatedNeed,
        questions: list[str],
        world: WorldState,
    ) -> DiscloseAction:
        strategic = stated.exaggeration
        secrecy = 0.25 if any(
            ("秘密" in c or "数据" in c or "名单" in c) for c in latent.constraints
        ) else 0.10
        components: dict[str, float] = {}
        for component in questions:
            if component in ("constraint", "commitment"):
                # 商业机密与真实投入是最敏感的两类信息
                openness = max(0.08, 0.80 - strategic * 0.55 - secrecy)
                if component == "commitment":
                    openness *= max(0.20, 1.0 - strategic * 0.85)  # 夸大企业最隐瞒真实投入
            else:
                # 问题本质、目标、期限、预算、合作方式通常愿意说清
                openness = max(0.15, 0.85 - strategic * 0.35 - 0.08)
            components[component] = round(openness, 3)
        return DiscloseAction(
            components=components,
            text=f"回应追问：披露 {', '.join(questions)} 的真实情况（程度见 components）",
            rationale="在商业风险与匹配收益之间策略性决定披露程度",
        )

    def confirm(
        self,
        agent: AgentState,
        latent: LatentNeed,
        belief: GovBelief,
        world: WorldState,
    ) -> ConfirmAction:
        alignment = self._mean(belief.components.values())
        if alignment >= 0.72:
            return ConfirmAction(
                confirmed=True, rationale="政府复述与真实需求基本一致"
            )
        corrections = {
            c: 1.0 for c in ("problem", "mode", "target")
            if belief.components.get(c, 0.0) < 0.70
        }
        return ConfirmAction(
            confirmed=False,
            correction=f"真实需要是：以{latent.preferred_mode}方式在{latent.deadline}个月内解决「{latent.problem}」",
            components=corrections,
            rationale="纠正政府复述中的关键误解",
        )

    # ---------------- 政府：提案 ---------------- #
    def propose(
        self,
        agent: AgentState,
        city: CityState,
        firm: FirmState,
        stated: StatedNeed,
        belief: GovBelief,
        protocol: str,
        world: WorldState,
    ) -> ProposalAction:
        if belief.components.get("mode", 0.0) >= 0.50 and belief.perceived_mode:
            toolset = MODE_TOOLS.get(belief.perceived_mode, CATEGORY_TOOLS.get(stated.category, ["tech_contract"]))
        else:
            toolset = CATEGORY_TOOLS.get(stated.category, ["tech_contract"])
        strength = min(0.95, 0.55 + 0.35 * belief.confidence)
        base_tools = {tool: round(strength, 2) for tool in toolset}

        if protocol == "multi_option":
            # 生成覆盖不同工具族的候选，给企业真正的比较空间：
            # 人才引进族 / 当前理解族 / 合作攻关族（柔性合作兜底）
            strength_soft = round(max(0.35, strength - 0.15), 2)
            options = [
                {
                    "label": "人才引进方案", "tools": {
                        t: round(min(1.0, strength * 0.95), 2)
                        for t in CATEGORY_TOOLS.get(stated.category, ["tech_contract"])
                    },
                    "conditions": ["企业自有投入不低于 40%"], "phased": False,
                },
                {
                    "label": "均衡方案", "tools": base_tools,
                    "conditions": ["企业自有投入不低于 50%", "按季度提交验收材料"], "phased": False,
                },
                {
                    "label": "合作攻关方案", "tools": {
                        "tech_contract": strength_soft, "joint_rnd": strength_soft,
                        "rnd_subsidy": round(strength_soft * 0.8, 2),
                    },
                    "conditions": ["企业自有投入不低于 60%", "分两期验收后拨付"], "phased": True,
                },
            ]
        elif protocol == "phased_commitment":
            options = [{
                "label": "分阶段方案",
                "tools": {t: round(s * 0.55, 2) for t, s in base_tools.items()},
                "conditions": ["首期拨付 40%，验收达标后追加", "先小规模试点再规模化"], "phased": True,
            }]
        else:
            options = [{
                "label": "标准方案", "tools": base_tools,
                "conditions": ["企业自有投入不低于 50%"], "phased": False,
            }]

        for option in options:
            option["language_style"] = self._style_for(protocol, world.language_style)
            option["discloses_limits"] = protocol in ("constraints_first", "phased_commitment") or world.language_style == "frank"
        return ProposalAction(
            options=options,
            rationale=f"基于当前理解（置信 {belief.confidence:.2f}）生成方案包",
        )

    def evaluate(
        self,
        agent: AgentState,
        latent: LatentNeed,
        stated: StatedNeed,
        option: dict[str, Any],
        trust: float,
        world: WorldState,
    ) -> EvaluateAction:
        offered = set(option.get("tools", {}))
        required_total = sum(latent.required_tools.values()) or 1.0
        coverage = sum(
            weight for tool, weight in latent.required_tools.items() if tool in offered
        ) / required_total
        mode_conflict = any(
            tool in ("talent_recruit", "relocation")
            for tool in offered
        ) and latent.preferred_mode in ("flexible", "pilot", "diagnosis", "project")
        constraint_conflict = any(
            "全职" in c for c in latent.constraints
        ) and "talent_recruit" in offered
        gov_support = sum(
            TOOL_COST.get(tool, 0.0) * value for tool, value in option.get("tools", {}).items()
        )
        budget_ok = min(1.0, (gov_support + latent.budget * latent.commitment * 0.4) / max(latent.budget, 1.0))
        perceived_fit = (
            coverage * 0.55
            + budget_ok * 0.20
            + (0.15 if not mode_conflict else 0.0)
            + (0.10 if not constraint_conflict else 0.0)
        )
        feasibility = 1.0 if not (mode_conflict or constraint_conflict) else 0.35
        understanding = self._language_understanding(option.get("language_style", world.language_style))
        trust_after = trust + (0.06 if option.get("discloses_limits") else 0.0) + (0.05 if option.get("phased") else 0.0)
        score = perceived_fit * 0.45 + understanding * 0.20 + trust_after * 0.20 + feasibility * 0.15
        # 亟需资金的夸大/高风险企业更看重支持力度而非匹配（若政府未识别，容易误签）
        needy = latent.unfeasible or stated.exaggeration > 0.25
        if needy:
            support_norm = min(1.0, sum(
                TOOL_COST.get(tool, 0.0) * value for tool, value in option.get("tools", {}).items()
            ) / 15.0)
            score = support_norm * 0.40 + understanding * 0.15 + trust_after * 0.25 + feasibility * 0.20
            accept_bar, counter_bar = 0.50, 0.40
        else:
            accept_bar, counter_bar = 0.60, 0.48
        if perceived_fit < 0.30 and score < counter_bar:
            response = "terminate"
        elif score >= accept_bar:
            response = "accept"
        elif score >= counter_bar:
            response = "counter"
        else:
            response = "terminate"
        counter_tools = {
            tool: 0.60 for tool in latent.required_tools if tool not in offered
        } if response == "counter" else {}
        return EvaluateAction(
            response=response,
            perceived_fit=round(perceived_fit, 3),
            understanding=round(understanding, 3),
            feasibility=round(feasibility, 3),
            trust_delta=round(trust_after - trust, 3),
            counter_tools=counter_tools,
            rationale=(
                "方案匹配且条件可接受，同意合作" if response == "accept"
                else "方案覆盖不足，提出补充条件" if response == "counter"
                else "方案与真实需求错位，终止协商"
            ),
        )

    # ---------------- 工具函数 ---------------- #
    @staticmethod
    def _understanding_ok(belief: GovBelief) -> bool:
        values = list(belief.components.values())
        return bool(values) and sum(values) / len(values) >= 0.70

    @staticmethod
    def _mean(values) -> float:
        values = list(values)
        return sum(values) / len(values) if values else 0.0

    @staticmethod
    def _style_for(protocol: str, world_style: str) -> str:
        if protocol == "constraints_first":
            return "frank"
        if protocol in ("clarify_first", "phased_commitment"):
            return "plain"
        if protocol == "policy_match":
            return "formal" if world_style != "plain" else world_style
        return world_style

    @staticmethod
    def _language_understanding(style: str) -> float:
        return {"formal": 0.55, "plain": 0.78, "frank": 0.75}.get(style, 0.70)


TOOL_COST = {
    "talent_recruit": 8.0, "relocation": 6.0, "joint_rnd": 4.0, "pilot_voucher": 2.0,
    "tech_contract": 3.0, "rnd_subsidy": 2.5, "equipment_subsidy": 5.0,
    "industry_fund": 10.0, "digital_subsidy": 1.5, "tax_credit": 0.8,
}


class DeepSeekNegotiationCognition(NegotiationCognitiveProvider):
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
        self.fallback = DeterministicNegotiationCognition()
        self.response_cache: dict[str, dict[str, Any]] = {}

    def _ask(self, role: str, schema: type[BaseModel], payload: dict[str, Any]) -> BaseModel:
        system = (
            "你是中国政企互动沙盘中「协商机制实验室」的独立行动者。"
            "政府只能根据企业表达与已披露信息形成理解，不得臆测企业私有底线；"
            "企业知道自己的真实需求，但要策略性决定披露多少。输出严格 JSON。"
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

    def _context(self, agent: AgentState, extra: dict[str, Any]) -> dict[str, Any]:
        return {
            "agent": {"name": agent.name, "goals": agent.goals, "traits": agent.traits,
                      "private_information": agent.private_facts},
            **extra,
        }

    def diagnose(self, agent, city, firm, stated, belief, protocol, round_index, world) -> DiagnoseAction:
        return self._ask(  # type: ignore[return-value]
            "政府：决定下一步协商动作（追问/复述/披露约束/提案）",
            DiagnoseAction,
            self._context(agent, {
                "protocol": protocol, "round": round_index, "expression": stated.text,
                "current_understanding": belief.components, "perceived_mode": belief.perceived_mode,
                "allowed_next": ["clarify", "paraphrase", "disclose", "propose"],
                "output_schema": DiagnoseAction.model_json_schema(),
            }),
        )

    def answer(self, agent, latent, stated, questions, world) -> DiscloseAction:
        return self._ask(  # type: ignore[return-value]
            "企业：回应政府追问，决定披露程度",
            DiscloseAction,
            self._context(agent, {
                "questions": questions, "my_real_need": latent.model_dump(),
                "output_schema": DiscloseAction.model_json_schema(),
            }),
        )

    def confirm(self, agent, latent, belief, world) -> ConfirmAction:
        return self._ask(  # type: ignore[return-value]
            "企业：复核政府的复述，确认或修正",
            ConfirmAction,
            self._context(agent, {
                "government_paraphrase": belief.components,
                "my_real_need": latent.model_dump(),
                "output_schema": ConfirmAction.model_json_schema(),
            }),
        )

    def propose(self, agent, city, firm, stated, belief, protocol, world) -> ProposalAction:
        return self._ask(  # type: ignore[return-value]
            "政府：基于当前理解生成政策方案包",
            ProposalAction,
            self._context(agent, {
                "protocol": protocol, "expression": stated.text,
                "understanding": belief.components, "perceived_mode": belief.perceived_mode,
                "budget_headroom": city.available_budget,
                "allowed_tools": list(TOOL_COST),
                "output_schema": ProposalAction.model_json_schema(),
            }),
        )

    def evaluate(self, agent, latent, stated, option, trust, world) -> EvaluateAction:
        return self._ask(  # type: ignore[return-value]
            "企业：评估政策方案，决定接受/还价/终止",
            EvaluateAction,
            self._context(agent, {
                "proposal": option, "my_trust_in_government": trust,
                "allowed_responses": ["accept", "counter", "terminate"],
                "output_schema": EvaluateAction.model_json_schema(),
            }),
        )


def build_negotiation_cognition(mode: str | None = None, model_name: str | None = None) -> NegotiationCognitiveProvider:
    requested = (mode or os.getenv("INSIDEGOV_POLICY", "deterministic")).lower()
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if requested == "llm" and api_key:
        return DeepSeekNegotiationCognition(
            api_key=api_key,
            model_name=model_name or os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        )
    return DeterministicNegotiationCognition()
