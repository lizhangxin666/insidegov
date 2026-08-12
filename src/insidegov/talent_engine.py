"""Talent-scenario engine: demand-policy-capability mapping, multi-round
negotiation, contract settlement and knowledge spillover.

Design contract:
- The cognition layer (talent_agents) proposes structured actions only;
- This engine owns all objective truth: matching scores, understanding,
  trust, coverage, fiscal costs, contract progress and knowledge spillover;
- Every action is traced; every meaningful step is remembered by the actor;
- Language mode (formal/plain) and interpreter toggle are world-level
  switches, so counterfactual comparison is a one-line world change.
"""

from __future__ import annotations

import copy
import math
import random
import uuid

import httpx

from .models import (
    DecisionTrace,
    Event,
    Intervention,
    MemoryRecord,
    MetricsSnapshot,
    Phase,
    TalentContract,
    TalentNegotiation,
    TalentOffer,
    WorldState,
)
from .talent_agents import (
    DemandAction,
    DeterministicTalentCognition,
    PolicyResponseAction,
    TalentCognitiveProvider,
    build_talent_cognition,
)

TOOL_COST = {"relocation": 1.0, "open_call": 0.35, "title_track": 1.0, "lab_credit": 0.6, "interpreter": 0.1}
CONCERN_TOOL = {
    "identity": "title_track",
    "academic": "lab_credit",
    "compensation": "relocation",
    "risk": "open_call",
}
MAX_NEGOTIATION_ROUNDS = 3
MAX_CONTRACTS_PER_FIRM = 2
CANDIDATES_PER_DEMAND = 3


class TalentSimulationEngine:
    def __init__(
        self,
        world: WorldState,
        cognition: TalentCognitiveProvider | None = None,
    ):
        self.world = world
        self.cognition = cognition or build_talent_cognition(world.policy_mode, world.model_name)
        self.world.policy_mode = self.cognition.mode
        self.world.model_name = self.cognition.model_name
        self.world.phase = Phase.TALENT
        self.random = random.Random(world.seed)

    def step(self) -> WorldState:
        self.world.quarter += 1
        self._apply_interventions()
        self._settle_contracts()
        self._run_matching_round()
        self._knowledge_spillover()
        self._update_market()
        self._record_metrics()
        return self.world

    def run(self, quarters: int) -> WorldState:
        for _ in range(quarters):
            self.step()
        return self.world

    def branch(self, branch_id: str | None = None) -> TalentSimulationEngine:
        cloned = copy.deepcopy(self.world)
        cloned.parent_id = self.world.id
        cloned.id = branch_id or f"talent-branch-{uuid.uuid4().hex[:8]}"
        cloned.name = f"{self.world.name} / 分支"
        return TalentSimulationEngine(cloned, self.cognition)

    def intervene(self, kind: str, target: str, value: float, quarter: int | None = None) -> None:
        self.world.interventions.append(Intervention(quarter or self.world.quarter + 1, kind, target, value))

    # ------------------------------------------------------------------ #
    # 回合主流程
    # ------------------------------------------------------------------ #
    def _run_matching_round(self) -> None:
        for firm in self.world.firms.values():
            if firm.tech_demand is None:
                continue
            active = [c for c in self.world.talent_contracts if c.firm_id == firm.id]
            if len(active) >= MAX_CONTRACTS_PER_FIRM:
                continue
            board = self.world.agents[f"{firm.id}_board"]
            demand = self._cognitive_call(
                "compose_demand", board, firm, self.world,
                self._demand_observation(firm),
                self._retrieve_memories(board, "需求 人才 匹配"),
            )
            if not isinstance(demand, DemandAction):
                continue
            self._remember(board, "demand", f"本轮表达需求：{demand.description}", 0.6, [firm.id])
            candidates = self._rank_candidates(demand)
            matched_this_round = False
            for talent in candidates:
                if talent.status != "available":
                    continue
                if self.world.quarter >= 14 and talent.withdrawn_quarters >= 2:
                    continue
                outcome = self._negotiate(firm, talent, demand)
                if outcome == "accepted":
                    matched_this_round = True
                if len([c for c in self.world.talent_contracts if c.firm_id == firm.id]) >= MAX_CONTRACTS_PER_FIRM:
                    break
            if not matched_this_round:
                self._event(
                    "matching", f"{firm.name}本轮未达成对接",
                    f"候选 {len(candidates)} 人，均未接受或政策覆盖不足", firm.id,
                )

    def _negotiate(self, firm, talent, demand: DemandAction) -> str:
        city = self.world.cities["city_qing"]
        talent_agent = self.world.agents[talent.id]
        investment = self.world.agents["city_qing_investment"]
        match = self.capability_match(demand.vector, talent.capability)
        if match < 0.25:
            return "rejected"

        # 政府设计政策工具包（语言模式由世界开关决定）
        policy = self._cognitive_call(
            "design_policy", investment, city, firm, talent, demand, self.world,
            self._policy_observation(city, firm, talent, demand),
            self._retrieve_memories(investment, "政策 工具 引才"),
        )
        if not isinstance(policy, PolicyResponseAction):
            return "rejected"

        # 平台翻译撮合（可选机制）
        match_action = None
        if self.world.interpreter_enabled and self.world.platform is not None:
            platform_agent = self.world.agents["platform_link"]
            match_action = self._cognitive_call(
                "broker_match", platform_agent, self.world.platform, demand, talent, self.world,
                self._platform_observation(demand, talent),
                self._retrieve_memories(platform_agent, "翻译 撮合 线索"),
            )

        tools = dict(policy.tools)
        annual_salary = min(demand.budget, policy.annual_salary)
        turns: list[dict] = []
        understanding, trust, coverage = self._offer_metrics(
            talent, demand, tools, annual_salary, policy, match_action
        )
        accepted = False
        outcome = "rejected"
        for round_index in range(1, MAX_NEGOTIATION_ROUNDS + 1):
            offer_dict = {
                "tools": tools, "annual_salary": annual_salary,
                "understanding": understanding, "trust": trust, "coverage": coverage,
                "match": match,
            }
            reaction = self._cognitive_call(
                "interpret_offer", talent_agent, talent, offer_dict, self.world,
                self._talent_observation(talent, offer_dict),
                self._retrieve_memories(talent_agent, "解读 offer 顾虑"),
            )
            turns.append({
                "round": round_index, "actor": talent.id, "response": reaction.response,
                "understood": round(understanding, 3), "trust": round(trust, 3),
                "coverage": round(coverage, 3), "rationale": reaction.rationale,
            })
            self._remember(
                talent_agent, "interpret",
                f"第 {round_index} 轮：理解度 {understanding:.2f}、信任 {trust:.2f}、覆盖 {coverage:.2f}，"
                f"回应 {reaction.response}",
                0.72, [firm.id, "city_qing"], valence=0.1 if reaction.response == "accept" else -0.05,
            )
            if reaction.response == "accept":
                accepted = True
                outcome = "accepted"
                break
            if reaction.response == "counter" and round_index < MAX_NEGOTIATION_ROUNDS:
                for tool, value in (reaction.counter_tools or {}).items():
                    if tool in TOOL_COST:
                        tools[tool] = max(tools.get(tool, 0), min(0.9, value))
                if reaction.counter_salary > 0:
                    annual_salary = min(demand.budget, max(annual_salary, reaction.counter_salary))
                understanding = min(1.0, understanding + 0.05)
                trust = min(1.0, trust + 0.03)
                continue
            outcome = "rejected"
            break

        if accepted:
            self._sign_contract(firm, talent, demand, tools, annual_salary, policy, match_action, match, turns)
        else:
            self._record_negotiation(firm, talent, demand, turns, outcome, understanding, trust, tools, policy, match_action)
            talent.withdrawn_quarters += 1
            self._event(
                "negotiation", f"{talent.name}与{firm.name}未谈成",
                turns[-1]["rationale"] if turns else "匹配不足", talent.id, firm.id,
                "warning" if outcome == "rejected" else "info",
            )
        return outcome

    def _sign_contract(
        self, firm, talent, demand, tools, annual_salary, policy,
        match_action, match, turns,
    ) -> None:
        city = self.world.cities["city_qing"]
        total_cost = self._tool_total_cost(tools)
        if city.available_budget - city.committed_expenditure < total_cost:
            tools = {key: value for key, value in tools.items() if key != "relocation"}
            total_cost = self._tool_total_cost(tools)
        offer = TalentOffer(
            firm_id=firm.id, city_id=city.id, annual_salary=round(annual_salary, 2),
            tools=tools, language_mode=policy.language_mode, explanation=policy.explanation,
            total_cost=round(total_cost, 2),
        )
        contract = TalentContract(
            id=f"tcontract-{len(self.world.talent_contracts)+1:03d}",
            quarter=self.world.quarter, talent_id=talent.id, firm_id=firm.id,
            city_id=city.id, university_id=talent.university_id, offer=offer,
            follow_through=talent.participation,
        )
        self.world.talent_contracts.append(contract)
        talent.status = "contracted"
        talent.employer_id = firm.id
        talent.contract_id = contract.id
        city.committed_expenditure += total_cost
        if talent.university_id:
            university = self.world.universities[talent.university_id]
            university.lab_funding += tools.get("lab_credit", 0) * 40.0
        firm.knowledge = min(100.0, firm.knowledge + 4.0)
        self._record_negotiation(firm, talent, demand, turns, "accepted", 1.0, 0.0, tools, policy, match_action)
        self._trace(
            talent.id, "accept_offer", firm.id,
            [f"能力匹配 {match:.2f}", f"政策工具 {list(tools)}", f"语言模式 {policy.language_mode}"],
            ["学术与产业平衡", "职业发展", "控制转型风险"],
            [f"理解度 {turns[-1]['understood']}", f"信任 {turns[-1]['trust']}"],
            ["机会成本", "学术考核压力"], ["继续观望", "接受更保守岗位"],
            {"salary": annual_salary, "cost": total_cost},
            f"{talent.name}与{firm.name}达成人才合作（{len(turns)} 轮协商）",
        )
        self._event(
            "deal", f"{firm.name}与{talent.name}达成合作",
            f"年薪 {annual_salary:.0f} 万，政策工具 {self._tools_label(tools)}，"
            f"{'经平台翻译撮合' if match_action is not None else '直接对接'}",
            talent.id, firm.id, "success",
        )

    def _record_negotiation(
        self, firm, talent, demand, turns, outcome, understanding, trust,
        tools, policy, match_action,
    ) -> None:
        self.world.talent_negotiations.append(TalentNegotiation(
            id=f"tnego-{len(self.world.talent_negotiations)+1:04d}",
            quarter=self.world.quarter, firm_id=firm.id, talent_id=talent.id,
            city_id="city_qing", rounds=len(turns) or 1, outcome=outcome,
            understanding_final=round(understanding, 3),
            trust_after=round(trust, 3), applied_tools=dict(tools),
            language_mode=policy.language_mode,
            interpreter_used=match_action is not None,
            turns=turns,
        ))

    # ------------------------------------------------------------------ #
    # 理解度 / 信任 / 覆盖度 —— 信任与信息系统的量化核心
    # ------------------------------------------------------------------ #
    def _offer_metrics(self, talent, demand, tools, annual_salary, policy, match_action) -> tuple[float, float, float]:
        understanding = self._understanding(talent, policy, match_action)
        trust = self._trust(talent, match_action)
        coverage = self._coverage(talent, tools, annual_salary, demand.budget)
        return understanding, trust, coverage

    def _understanding(self, talent, policy: PolicyResponseAction, match_action) -> float:
        base = 0.42
        mode_bonus = 0.20 if policy.language_mode == "plain" else 0.02
        explanation_bonus = 0.07 if policy.provide_explanation else 0.0
        skill_bonus = talent.interpretation_skill * 0.15
        interpreter_bonus = 0.0
        if match_action is not None and self.world.platform is not None:
            interpreter_bonus = self.world.platform.translation_power * 0.13
        return min(1.0, max(0.05, base + mode_bonus + explanation_bonus + skill_bonus + interpreter_bonus))

    def _trust(self, talent, match_action) -> float:
        city = self.world.cities["city_qing"]
        base = talent.trust.get("city_qing", 0.55)
        credibility_bonus = (city.objective_credibility - 0.5) * 0.30
        platform_bonus = 0.0
        if match_action is not None and self.world.platform is not None:
            platform_bonus = self.world.platform.information_coverage * 0.10
        return min(1.0, max(0.05, base + credibility_bonus + platform_bonus))

    def _coverage(self, talent, tools: dict[str, float], annual_salary: float, budget: float) -> float:
        weights = talent.concerns
        total_weight = sum(weights.values()) or 1.0
        tool_covered = 0.0
        for concern, weight in weights.items():
            tool = CONCERN_TOOL.get(concern)
            if tool is None:
                continue
            value = tools.get(tool, 0.0)
            covered = min(1.0, value / 0.6)
            tool_covered += weight * covered
        tool_score = tool_covered / total_weight
        salary_ratio = min(1.0, annual_salary / max(budget, 1.0))
        return min(1.0, tool_score * 0.75 + salary_ratio * 0.25)

    @staticmethod
    def capability_match(demand: dict[str, float], capability: dict[str, float]) -> float:
        dims = ["tech", "eng", "mgmt"]
        d = [demand.get(dim, 0.0) for dim in dims]
        c = [capability.get(dim, 0.0) for dim in dims]
        norm = math.sqrt(sum(x * x for x in d)) * math.sqrt(sum(x * x for x in c))
        if norm <= 1e-9:
            return 0.0
        return round(sum(a * b for a, b in zip(d, c)) / norm, 4)

    def _rank_candidates(self, demand: DemandAction) -> list:
        ranked = []
        for talent in self.world.talents.values():
            if talent.status != "available":
                continue
            match = self.capability_match(demand.vector, talent.capability)
            ranked.append((match + talent.participation * 0.05, talent))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [talent for _, talent in ranked[: CANDIDATES_PER_DEMAND * 2]]

    def _tool_total_cost(self, tools: dict[str, float]) -> float:
        return round(sum(TOOL_COST.get(tool, 0.0) * value for tool, value in tools.items()), 2)

    @staticmethod
    def _tools_label(tools: dict[str, float]) -> str:
        names = {
            "relocation": "安家补贴", "title_track": "职称通道", "lab_credit": "联合实验室",
            "open_call": "揭榜项目", "interpreter": "平台翻译",
        }
        return "、".join(f"{names.get(tool, tool)}{value:.2f}" for tool, value in tools.items())

    # ------------------------------------------------------------------ #
    # 合同兑现与知识外溢
    # ------------------------------------------------------------------ #
    def _settle_contracts(self) -> None:
        city = self.world.cities["city_qing"]
        for contract in self.world.talent_contracts:
            if contract.status != "active":
                continue
            talent = self.world.talents[contract.talent_id]
            firm = self.world.firms[contract.firm_id]
            match = self.capability_match(
                firm.tech_demand.vector if firm.tech_demand else {}, talent.capability
            )
            # 教授投入度低，转化慢；青年教师与产业专家转化快
            increment = min(0.22, 0.04 + match * 0.10 * contract.follow_through + 0.02)
            contract.progress = min(1.0, contract.progress + increment)
            # 分期兑现安家与揭榜经费
            relocation = contract.offer.tools.get("relocation", 0.0)
            open_call = contract.offer.tools.get("open_call", 0.0)
            installment = (relocation + open_call * 0.35) / 6.0
            if city.available_budget - city.committed_expenditure >= installment:
                city.available_budget -= installment
                contract.paid += installment
                city.committed_expenditure = max(0.0, city.committed_expenditure - installment)
                if contract.due_quarter == 0:
                    city.objective_credibility = min(1.0, city.objective_credibility + 0.004)
            else:
                contract.due_quarter += 1
                city.objective_credibility = max(0.25, city.objective_credibility - 0.02)
                talent.trust["city_qing"] = max(0.05, talent.trust.get("city_qing", 0.55) - 0.05)
                self._event(
                    "promise", "人才政策兑现延期",
                    f"{city.name}未能按期支付 {contract.id} 的安家/项目经费",
                    "city_qing", talent.id, "danger",
                )
            if contract.progress >= 1.0:
                contract.status = "fulfilled"
                firm.knowledge = min(100.0, firm.knowledge + 10.0 + match * 14.0)
                city.employment += 40
                city.tax_revenue += 12.0
                city.available_budget += 12.0
                if contract.university_id:
                    university = self.world.universities[contract.university_id]
                    university.assessment_pressure = max(
                        0.2, university.assessment_pressure - 0.06
                    )
                self._event(
                    "milestone", f"{firm.name}技术落地完成",
                    f"{talent.name}的成果完成转化，企业技术存量提升至 {firm.knowledge:.0f}",
                    talent.id, firm.id, "success",
                )
        # 观望过久的人才退出市场（进入/退出演化）
        for talent in self.world.talents.values():
            if talent.status == "available" and talent.withdrawn_quarters >= 4:
                talent.status = "withdrawn"
                self._event(
                    "exit", f"{talent.name}退出对接市场",
                    "多次协商未果，选择回到学术轨道或异地机会", talent.id,
                )

    def _knowledge_spillover(self) -> None:
        for firm in self.world.firms.values():
            if not firm.tech_demand:
                continue
            firm.knowledge = min(100.0, firm.knowledge + 0.05)
            for other in self.world.firms.values():
                if other.id != firm.id and other.knowledge < firm.knowledge:
                    other.knowledge = min(100.0, other.knowledge + 0.02)

    def _update_market(self) -> None:
        trend = 100 + self.world.quarter * 1.2
        cycle = math.sin((self.world.quarter + self.world.seed % 7) / 2.6) * 6
        self.world.market_demand = max(60.0, (trend + cycle) * self.world.demand_multiplier)

    def _record_metrics(self) -> None:
        hired = len([c for c in self.world.talent_contracts if c.status != "active"])
        contracts = len(self.world.talent_contracts)
        knowledge = sum(firm.knowledge for firm in self.world.firms.values()) / max(len(self.world.firms), 1)
        # 累计口径：对接成功率与平均理解度统计全部历史谈判，便于观察演化
        ngo = self.world.talent_negotiations
        understanding = sum(n.understanding_final for n in ngo) / len(ngo) if ngo else 0.0
        trust_vals = [t.trust.get("city_qing", 0.55) for t in self.world.talents.values()]
        avg_trust = sum(trust_vals) / len(trust_vals) if trust_vals else 0.0
        self.world.history.append(MetricsSnapshot(
            quarter=self.world.quarter, phase=Phase.TALENT,
            total_employment=sum(c.employment for c in self.world.cities.values()),
            total_tax_revenue=round(sum(c.tax_revenue for c in self.world.cities.values()), 3),
            total_committed_expenditure=round(
                sum(c.committed_expenditure for c in self.world.cities.values()), 3
            ),
            average_credibility=round(
                sum(c.objective_credibility for c in self.world.cities.values())
                / max(len(self.world.cities), 1), 4
            ),
            cluster_size=contracts, capacity=0.0, demand=round(self.world.market_demand, 3),
            utilization=0.0, market_price=1.0,
            talent_hired=hired, tech_progress=round(knowledge, 3),
            match_rate=round(len([n for n in ngo if n.outcome == "accepted"]) / len(ngo), 4) if ngo else 0.0,
            avg_understanding=round(understanding, 4),
            avg_trust=round(avg_trust, 4),
        ))

    # ------------------------------------------------------------------ #
    # 干预
    # ------------------------------------------------------------------ #
    def _apply_interventions(self) -> None:
        for item in self.world.interventions:
            if item.quarter != self.world.quarter:
                continue
            if item.kind == "language_reform":
                self.world.expression_mode = "plain"
                self._event("intervention", "政策语言改革", "政府政策改用直白表达并配解释材料", severity="success")
            elif item.kind == "platform_launch":
                self.world.interpreter_enabled = True
                self._event("intervention", "上线产学研对接平台", "引入第三方翻译与撮合机制", "platform_link", severity="success")
            elif item.kind == "fiscal_shock" and item.target in self.world.cities:
                city = self.world.cities[item.target]
                loss = city.available_budget * min(max(item.value, 0), 0.9)
                city.available_budget -= loss
                self._event("external_shock", "人才专项财政冲击", f"{city.name}人才经费减少 {loss:.0f} 万元", city.id, severity="warning")
            elif item.kind == "credibility_shock":
                self.world.cities["city_qing"].objective_credibility = max(
                    0.2, self.world.cities["city_qing"].objective_credibility - item.value
                )
                self._event("external_shock", "履约丑闻", "某企业反映政府补贴拖欠，人才信任下降", severity="danger")

    # ------------------------------------------------------------------ #
    # 观察构造（局部信息）
    # ------------------------------------------------------------------ #
    def _demand_observation(self, firm) -> dict:
        return {"quarter": self.world.quarter, "firm": firm.name, "knowledge": firm.knowledge}

    def _policy_observation(self, city, firm, talent, demand: DemandAction) -> dict:
        return {
            "city": city.name, "budget": city.available_budget, "pressure": city.fiscal_pressure,
            "firm": firm.name, "demand": demand.vector,
            "talent_public": {"name": talent.name, "type": talent.talent_type.value,
                              "capability": talent.capability},
            "expression_mode": self.world.expression_mode,
        }

    def _talent_observation(self, talent, offer: dict) -> dict:
        return {
            "name": talent.name, "offer": offer,
            "my_concerns_hint": "政策覆盖程度以实际 tools 为准",
            "expression_mode": self.world.expression_mode,
        }

    def _platform_observation(self, demand: DemandAction, talent) -> dict:
        return {
            "demand": demand.model_dump() if hasattr(demand, "model_dump") else dict(demand),
            "talent_public": {"name": talent.name, "type": talent.talent_type.value,
                              "capability": talent.capability},
        }

    # ------------------------------------------------------------------ #
    # 基础设施：认知调用、记忆、追溯、事件（与主引擎一致）
    # ------------------------------------------------------------------ #
    def _cognitive_call(self, method: str, *args):
        try:
            return getattr(self.cognition, method)(*args)
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            if isinstance(self.cognition, DeterministicTalentCognition):
                raise
            failed_model = self.cognition.model_name or "DeepSeek"
            self._event(
                "model_fallback", "认知模型降级",
                f"{failed_model} 未返回可用结构化行动，本步改用确定性策略（{type(exc).__name__}）",
                severity="warning",
            )
            fallback = DeterministicTalentCognition()
            return getattr(fallback, method)(*args)

    def _retrieve_memories(self, agent, query: str, limit: int = 4) -> list[str]:
        terms = set(query.split())
        scored = []
        for memory in agent.memories:
            overlap = sum(term in memory.content for term in terms)
            recency = 1 / (1 + max(0, self.world.quarter - memory.quarter))
            scored.append((memory.importance * 0.65 + recency * 0.2 + overlap * 0.15, memory))
        return [item.content for _, item in sorted(scored, key=lambda x: x[0], reverse=True)[:limit]]

    def _remember(self, agent, kind: str, content: str, importance: float,
                  source_ids: list[str], valence: float = 0.0) -> None:
        agent.memories.append(MemoryRecord(
            id=f"{agent.id}-memory-{len(agent.memories)+1:03d}",
            quarter=self.world.quarter, kind=kind, content=content,
            importance=importance, valence=valence, source_ids=source_ids,
        ))
        if len(agent.memories) > 40:
            agent.memories = agent.memories[-40:]
        agent.last_reflection = self.cognition.reflect(agent, kind, content)

    def _trace(self, actor_id: str, action: str, target_id: str | None,
               observations: list[str], goals: list[str], evidence: list[str],
               constraints: list[str], alternatives: list[str],
               expected: dict[str, float], outcome: str) -> None:
        self.world.traces.append(DecisionTrace(
            id=f"trace-{len(self.world.traces)+1:04d}", quarter=self.world.quarter,
            actor_id=actor_id, action=action, target_id=target_id, observations=observations,
            goals=goals, evidence=evidence, constraints=constraints, alternatives=alternatives,
            expected_effects=expected, outcome=outcome,
        ))

    def _event(self, kind: str, title: str, detail: str, actor_id: str | None = None,
               target_id: str | None = None, severity: str = "info") -> None:
        self.world.events.append(Event(self.world.quarter, kind, title, detail, actor_id, target_id, severity))
