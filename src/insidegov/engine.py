from __future__ import annotations

import copy
import math
import random
import uuid

import httpx

from .agents import (
    CognitiveProvider,
    DeterministicCognition,
    FinanceAction,
    build_cognition,
)
from .models import (
    DecisionTrace,
    Event,
    FirmState,
    Intervention,
    MemoryRecord,
    MetricsSnapshot,
    NegotiationRound,
    Phase,
    PolicyPackage,
    Promise,
    PromiseStatus,
    WorldState,
)
from .policies import DecisionPolicy


class SimulationEngine:
    def __init__(
        self,
        world: WorldState,
        policy: DecisionPolicy | None = None,
        cognition: CognitiveProvider | None = None,
    ):
        self.world = world
        self.policy = policy
        self.cognition = cognition or build_cognition(world.policy_mode, world.model_name)
        self.world.policy_mode = self.cognition.mode
        self.world.model_name = self.cognition.model_name
        self.random = random.Random(world.seed)

    def step(self) -> WorldState:
        self.world.quarter += 1
        self._apply_interventions()
        self._update_phase()
        self._update_market()
        if self.world.phase == Phase.RECRUITMENT:
            self._run_recruitment()
        else:
            self._advance_anchor_project()
            self._settle_promises()
            if self.world.phase == Phase.INDUSTRIALIZATION:
                self._run_supplier_entry()
                self._run_production()
        self._record_metrics()
        return self.world

    def run(self, quarters: int) -> WorldState:
        for _ in range(quarters):
            self.step()
        return self.world

    def branch(self, branch_id: str | None = None) -> SimulationEngine:
        cloned = copy.deepcopy(self.world)
        cloned.parent_id = self.world.id
        cloned.id = branch_id or f"branch-{uuid.uuid4().hex[:8]}"
        cloned.name = f"{self.world.name} / 分支"
        return SimulationEngine(cloned, self.policy, self.cognition)

    def intervene(self, kind: str, target: str, value: float, quarter: int | None = None) -> None:
        self.world.interventions.append(
            Intervention(quarter or self.world.quarter + 1, kind, target, value)
        )

    def _update_phase(self) -> None:
        if self.world.selected_city_id is None:
            self.world.phase = Phase.RECRUITMENT
        elif self.world.firms["firm_nova"].operating:
            self.world.phase = Phase.INDUSTRIALIZATION
        else:
            self.world.phase = Phase.DELIVERY

    def _apply_interventions(self) -> None:
        for item in self.world.interventions:
            if item.quarter != self.world.quarter:
                continue
            if item.kind == "fiscal_shock" and item.target in self.world.cities:
                city = self.world.cities[item.target]
                loss = city.available_budget * min(max(item.value, 0), 0.9)
                city.available_budget -= loss
                self._event("external_shock", "财政冲击", f"{city.name}可用财力减少 {loss:.1f} 亿元", city.id, severity="warning")
            elif item.kind == "demand_shock":
                self.world.demand_multiplier *= max(0.1, 1 + item.value)
                self._event("external_shock", "需求冲击", f"市场需求发生 {item.value:+.0%} 变化", severity="warning")
            elif item.kind == "credibility_boost" and item.target in self.world.cities:
                city = self.world.cities[item.target]
                city.objective_credibility = min(1.0, city.objective_credibility + item.value)
                self._event("intervention", "履约保障机制", f"{city.name}建立专项履约保障", city.id)

    def _run_recruitment(self) -> None:
        anchor = self.world.firms["firm_nova"]
        for city in self.world.cities.values():
            leader = self.world.agents[f"{city.id}_leader"]
            finance = self.world.agents[f"{city.id}_finance"]
            leader_observation = self._leader_observation(city, anchor)
            proposal_action = self._cognitive_call(
                "propose_offer",
                leader,
                city,
                anchor,
                self.world,
                leader_observation,
                self._retrieve_memories(leader, "招商 政策包 财政"),
            )
            proposal = proposal_action.to_package(city.id)
            finance_observation = self._finance_observation(city, proposal)
            if self.world.mechanisms.get("internal_governance", True):
                review = self._cognitive_call(
                    "review_offer",
                    finance,
                    city,
                    proposal,
                    finance_observation,
                    self._retrieve_memories(finance, "审核 底线 债务"),
                )
                review.maximum_fiscal_cost = min(
                    review.maximum_fiscal_cost, self._hard_finance_limit(city, finance)
                )
                review.approved = review.approved and proposal.fiscal_cost <= review.maximum_fiscal_cost
                resolution = self._cognitive_call(
                    "resolve_offer",
                    leader,
                    city,
                    proposal,
                    review,
                    leader_observation,
                    self._retrieve_memories(leader, "财政否决 协调"),
                )
                offer = resolution.to_package(city.id)
                offer = self._enforce_offer_limit(offer, review.maximum_fiscal_cost)
                resolution_name = resolution.resolution
            else:
                review = FinanceAction(
                    approved=True,
                    maximum_fiscal_cost=proposal.fiscal_cost,
                    concerns=["消融实验：财政审核机制关闭"],
                    rationale="消融实验直接批准",
                )
                offer = proposal
                resolution_name = "approved_without_internal_governance"
            city.active_offer = offer
            anchor.observed_offers[city.id] = offer
            self.world.negotiations.append(NegotiationRound(
                id=f"negotiation-{len(self.world.negotiations)+1:04d}",
                quarter=self.world.quarter, city_id=city.id, firm_id=anchor.id,
                proposal_cost=round(proposal.fiscal_cost, 3),
                finance_limit=round(review.maximum_fiscal_cost, 3),
                finance_approved=review.approved, concerns=review.concerns,
                resolution=resolution_name, final_cost=round(offer.fiscal_cost, 3),
                policy_mode=self.world.policy_mode,
            ))
            self._remember(
                leader, "decision",
                f"提案成本 {proposal.fiscal_cost:.1f}，财政上限 {review.maximum_fiscal_cost:.1f}，最终 {offer.fiscal_cost:.1f}",
                0.75, [finance.id, anchor.id],
            )
            self._remember(
                finance, "review", f"审核 {city.name}政策包：{'通过' if review.approved else '否决或核减'}",
                0.72, [leader.id, anchor.id],
            )
            self._trace(
                leader.id, "coordinate_internal_offer", finance.id,
                ["市领导招商提案", "财政局独立审核", "财政局私有储备底线"],
                leader.goals, proposal_action.evidence, review.concerns,
                ["接受财政上限", "调整现金/基金结构", "撤回政策包"],
                {"proposal_cost": proposal.fiscal_cost, "finance_limit": review.maximum_fiscal_cost},
                f"{resolution_name}，最终成本 {offer.fiscal_cost:.1f}",
            )
            self._trace_offer(city.id, anchor.id, offer)
            review_label = "通过" if review.approved else "否决后核减"
            self._event(
                "negotiation", f"{city.name}完成内部协调",
                f"财政审核{review_label}；提案 {proposal.fiscal_cost:.1f} → 最终 {offer.fiscal_cost:.1f} 亿元",
                leader.id, finance.id, "warning" if not review.approved else "info",
            )
            self._event("offer", f"{city.name}提交政策包", f"财政成本 {offer.fiscal_cost:.1f} 亿元，工业用地折让 {offer.land_discount:.0%}", city.id, anchor.id)
        if self.world.quarter >= 3:
            scores = {city_id: self._firm_city_utility(anchor, city_id) for city_id in self.world.cities}
            board = self.world.agents["firm_nova_board"]
            decision = self._cognitive_call(
                "select_location", board, anchor, scores,
                self._enterprise_observation(anchor, scores),
                self._retrieve_memories(board, "选址 履约 风险"),
            )
            selected_id = decision.city_id if decision.city_id in scores else max(scores, key=scores.get)  # type: ignore[arg-type]
            selected_score = scores[selected_id]
            if selected_score >= anchor.minimum_utility:
                self._select_city(anchor, selected_id, scores)
                self._remember(
                    board, "decision", f"选择 {self.world.cities[selected_id].name}：{decision.rationale}",
                    0.95, [selected_id], valence=0.4,
                )

    def _firm_city_utility(self, firm: FirmState, city_id: str) -> float:
        city = self.world.cities[city_id]
        offer = firm.observed_offers[city_id]
        credibility = firm.perceived_credibility.get(city_id, 0.7)
        policy_value = offer.subsidy * 0.6 + offer.equity * 0.36 + offer.land_discount * 42
        fundamentals = city.supply_chain * firm.cluster_sensitivity + city.talent_pool * 0.28
        institution = credibility * 100 * firm.credibility_sensitivity + offer.approval_speed * 12
        fiscal_risk = city.fiscal_pressure * 25 * firm.credibility_sensitivity
        return round((policy_value * firm.policy_sensitivity + fundamentals + institution - fiscal_risk) / 1.65, 2)

    def _select_city(self, anchor: FirmState, city_id: str, scores: dict[str, float]) -> None:
        city = self.world.cities[city_id]
        offer = city.active_offer
        assert offer is not None
        self.world.selected_city_id = city_id
        anchor.location = city_id
        city.landed_firms.append(anchor.id)
        city.industrial_land -= anchor.land_need
        city.committed_expenditure += offer.fiscal_cost
        for item, amount, due in [
            ("equity", offer.equity, self.world.quarter + 1),
            ("subsidy", offer.subsidy, self.world.quarter + 3),
            ("credit_support", offer.credit_support * 0.08, self.world.quarter + 5),
        ]:
            self.world.promises.append(Promise(
                id=f"promise-{len(self.world.promises)+1:03d}", city_id=city_id, firm_id=anchor.id,
                item=item, amount=amount, due_quarter=due,
                condition="project_progress>=0.30" if item == "subsidy" else "contract_signed",
            ))
        alternatives = [f"{self.world.cities[c].name}: {s:.1f}" for c, s in scores.items()]
        self._trace(anchor.id, "select_location", city_id,
            ["三座城市最终政策包", "企业尽调信息", "各城市履约历史"],
            ["长期供应链效率", "政策预期价值", "项目执行确定性"],
            [f"效用得分 {scores[city_id]:.1f}", f"感知可信度 {anchor.perceived_credibility[city_id]:.0%}"],
            ["投资不可逆", "高世代产线建设周期长"], alternatives,
            {"investment": anchor.investment_capacity, "jobs": float(anchor.jobs_capacity)},
            f"选择{city.name}并签署有条件投资协议")
        self._event("location", f"{anchor.name}选择{city.name}", "项目进入签约与建设阶段；承诺将按合同节点兑现", anchor.id, city.id, "success")

    def _advance_anchor_project(self) -> None:
        anchor = self.world.firms["firm_nova"]
        if anchor.location is None or anchor.operating:
            return
        city = self.world.cities[anchor.location]
        funding_factor = 0.75 + (1 - city.fiscal_pressure) * 0.35
        increment = min(0.24, 0.13 * funding_factor + city.administrative_capacity / 1400)
        anchor.project_progress = min(1.0, anchor.project_progress + increment)
        invested = min(anchor.cash, anchor.investment_capacity * increment * 0.55)
        anchor.cash -= invested
        if anchor.project_progress >= 1.0:
            anchor.operating = True
            city.employment += anchor.jobs_capacity
            city.supply_chain = min(100.0, city.supply_chain + 8.0)
            self._event("milestone", "龙头产线投产", f"{anchor.name}完成建设，形成 {anchor.production_capacity:.0f} 单位产能", anchor.id, city.id, "success")
        else:
            self._event("progress", "项目建设推进", f"{anchor.name}项目进度达到 {anchor.project_progress:.0%}", anchor.id, city.id)

    def _settle_promises(self) -> None:
        anchor = self.world.firms["firm_nova"]
        for promise in self.world.promises:
            if promise.status == PromiseStatus.FULFILLED or promise.due_quarter > self.world.quarter:
                continue
            city = self.world.cities[promise.city_id]
            condition_met = promise.condition == "contract_signed" or anchor.project_progress >= 0.30
            if not condition_met:
                continue
            due = promise.amount - promise.paid_amount
            payment = min(due, max(0.0, city.available_budget - city.debt * 0.01))
            if payment >= due - 1e-9:
                city.available_budget -= payment
                city.committed_expenditure = max(0.0, city.committed_expenditure - payment)
                anchor.cash += payment
                promise.paid_amount += payment
                promise.status = PromiseStatus.FULFILLED
                city.objective_credibility = min(1.0, city.objective_credibility + 0.012)
                self._update_perceptions(city.id, +0.016)
                self._event("promise", "政策承诺按期兑现", f"{city.name}支付 {payment:.1f} 亿元 {promise.item}", city.id, anchor.id, "success")
            else:
                if payment > 0:
                    city.available_budget -= payment
                    anchor.cash += payment
                    promise.paid_amount += payment
                promise.status = PromiseStatus.DELAYED
                promise.delayed_quarters += 1
                promise.due_quarter += 1
                city.objective_credibility = max(0.25, city.objective_credibility - 0.045)
                self._update_perceptions(city.id, -0.065)
                self._event("promise", "政策承诺延期", f"{city.name}未能足额支付 {due:.1f} 亿元 {promise.item}", city.id, anchor.id, "danger")

    def _update_perceptions(self, city_id: str, delta: float) -> None:
        if not self.world.mechanisms.get("credibility_diffusion", True):
            return
        for firm in self.world.firms.values():
            old = firm.perceived_credibility.get(city_id, 0.7)
            diffusion = 1.0 if firm.id == "firm_nova" else 0.55
            firm.perceived_credibility[city_id] = min(1.0, max(0.1, old + delta * diffusion))

    def _run_supplier_entry(self) -> None:
        if not self.world.mechanisms.get("supplier_spillover", True):
            return
        city_id = self.world.selected_city_id
        if city_id is None:
            return
        city = self.world.cities[city_id]
        anchor = self.world.firms["firm_nova"]
        for firm in self.world.firms.values():
            if firm.supplier_of != anchor.id or firm.location is not None:
                continue
            credibility = firm.perceived_credibility[city_id]
            attractiveness = (
                city.supply_chain * firm.cluster_sensitivity
                + credibility * 100 * firm.credibility_sensitivity
                + city.talent_pool * 0.18
                + firm.private_intent * 18
                - city.fiscal_pressure * 12
            )
            threshold = firm.minimum_utility + self.random.uniform(-7, 7)
            if attractiveness / 1.55 >= threshold and city.industrial_land >= firm.land_need:
                firm.location = city_id
                firm.operating = True
                firm.project_progress = 1.0
                city.industrial_land -= firm.land_need
                city.employment += firm.jobs_capacity
                city.supply_chain = min(100.0, city.supply_chain + 1.4)
                city.landed_firms.append(firm.id)
                self._trace(firm.id, "follow_anchor", city_id,
                    ["龙头订单预期", "园区企业数量", "政府履约传播"],
                    ["接近核心客户", "降低运输成本", "控制政策风险"],
                    [f"供应链完整度 {city.supply_chain:.1f}", f"感知可信度 {credibility:.0%}"],
                    ["迁移成本", "订单尚未完全确定"], ["暂缓投资", "异地扩产"],
                    {"jobs": float(firm.jobs_capacity)}, f"进入{city.name}供应链园区")
                self._event("entry", f"{firm.name}进入园区", "龙头订单与集聚效应提高了本地投资价值", firm.id, city.id, "success")

    def _run_production(self) -> None:
        operating = [firm for firm in self.world.firms.values() if firm.operating]
        total_capacity = sum(firm.production_capacity for firm in operating)
        utilization = min(1.0, self.world.market_demand / max(total_capacity, 1.0))
        self.world.market_price = max(0.42, min(1.35, 0.72 + self.world.market_demand / max(total_capacity, 1.0) * 0.34))
        for firm in operating:
            firm.utilization = utilization
            revenue = firm.production_capacity * utilization * self.world.market_price
            cost = firm.production_capacity * (0.54 - min(0.12, len(operating) * 0.006))
            firm.profit = revenue - cost
            if firm.location:
                city = self.world.cities[firm.location]
                tax = max(0.0, firm.profit * 0.16)
                city.tax_revenue += tax
                city.available_budget += tax
                city.industrial_output += revenue
        if utilization < 0.68:
            self._event("market", "产能利用率预警", f"行业利用率降至 {utilization:.0%}，地方政府面临救助压力", severity="warning")

    def _update_market(self) -> None:
        trend = 100 + self.world.quarter * 3.4
        cycle = math.sin((self.world.quarter + self.world.seed % 7) / 2.4) * 11
        self.world.market_demand = max(45.0, (trend + cycle) * self.world.demand_multiplier)

    def _record_metrics(self) -> None:
        operating = [firm for firm in self.world.firms.values() if firm.operating]
        capacity = sum(firm.production_capacity for firm in operating)
        utilization = sum(firm.utilization for firm in operating) / len(operating) if operating else 0.0
        self.world.history.append(MetricsSnapshot(
            quarter=self.world.quarter,
            phase=self.world.phase,
            total_employment=sum(city.employment for city in self.world.cities.values()),
            total_tax_revenue=round(sum(city.tax_revenue for city in self.world.cities.values()), 3),
            total_committed_expenditure=round(sum(city.committed_expenditure for city in self.world.cities.values()), 3),
            average_credibility=round(sum(city.objective_credibility for city in self.world.cities.values()) / len(self.world.cities), 4),
            cluster_size=len(operating), capacity=round(capacity, 3), demand=round(self.world.market_demand, 3),
            utilization=round(utilization, 4), market_price=round(self.world.market_price, 4),
        ))

    def _leader_observation(self, city, anchor) -> dict:
        return {
            "quarter": self.world.quarter,
            "city": city.name,
            "available_budget": city.available_budget,
            "fiscal_pressure_band": "high" if city.fiscal_pressure > 0.65 else "medium",
            "supply_chain": city.supply_chain,
            "talent_pool": city.talent_pool,
            "industrial_land": city.industrial_land,
            "target_firm_jobs": anchor.jobs_capacity,
            "target_firm_investment": anchor.investment_capacity,
            "competing_offer_costs": {
                item.name: item.active_offer.fiscal_cost
                for item in self.world.cities.values() if item.active_offer
            },
        }

    def _finance_observation(self, city, proposal) -> dict:
        return {
            "available_budget": city.available_budget,
            "committed_expenditure": city.committed_expenditure,
            "debt": city.debt,
            "fiscal_pressure": city.fiscal_pressure,
            "proposal_cost": proposal.fiscal_cost if proposal else 0.0,
        }

    def _enterprise_observation(self, firm, scores) -> dict:
        offers = {}
        for city_id, offer in firm.observed_offers.items():
            city = self.world.cities[city_id]
            offers[city_id] = {
                "city_name": city.name, "fiscal_cost": offer.fiscal_cost,
                "land_discount": offer.land_discount, "supply_chain": city.supply_chain,
                "talent_pool": city.talent_pool,
                "perceived_credibility": firm.perceived_credibility.get(city_id, 0.7),
                "utility_score": scores[city_id],
            }
        return {"offers_and_due_diligence": offers, "decision_is_irreversible": True}

    def _hard_finance_limit(self, city, finance) -> float:
        reserve = float(finance.private_facts.get("reserve_floor", city.available_budget * 0.34))
        return round(max(0.0, min(
            (city.available_budget - reserve) * 0.42,
            city.available_budget * 0.19,
        )), 2)

    @staticmethod
    def _enforce_offer_limit(offer: PolicyPackage, limit: float) -> PolicyPackage:
        if offer.fiscal_cost <= limit:
            return offer
        scale = max(0.0, limit / max(offer.fiscal_cost, 0.01))
        offer.subsidy = round(offer.subsidy * scale, 2)
        offer.equity = round(offer.equity * scale, 2)
        offer.credit_support = round(offer.credit_support * scale, 2)
        return offer

    def _cognitive_call(self, method: str, *args):
        cognitive_args = args
        if not self.world.mechanisms.get("private_information", True) and args:
            actor = copy.copy(args[0])
            if hasattr(actor, "private_facts"):
                actor.private_facts = {}
                cognitive_args = (actor, *args[1:])
        try:
            return getattr(self.cognition, method)(*cognitive_args)
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            if isinstance(self.cognition, DeterministicCognition):
                raise
            failed_model = self.cognition.model_name or "DeepSeek"
            self._event(
                "model_fallback", "认知模型降级",
                f"{failed_model} 未返回可用结构化行动，本步改用确定性策略（{type(exc).__name__}）",
                severity="warning",
            )
            fallback = DeterministicCognition()
            return getattr(fallback, method)(*cognitive_args)

    def _retrieve_memories(self, agent, query: str, limit: int = 4) -> list[str]:
        terms = set(query.split())
        scored = []
        for memory in agent.memories:
            overlap = sum(term in memory.content for term in terms)
            recency = 1 / (1 + max(0, self.world.quarter - memory.quarter))
            scored.append((memory.importance * 0.65 + recency * 0.2 + overlap * 0.15, memory))
        return [item.content for _, item in sorted(scored, key=lambda x: x[0], reverse=True)[:limit]]

    def _remember(
        self, agent, kind: str, content: str, importance: float,
        source_ids: list[str], valence: float = 0.0,
    ) -> None:
        agent.memories.append(MemoryRecord(
            id=f"{agent.id}-memory-{len(agent.memories)+1:03d}",
            quarter=self.world.quarter, kind=kind, content=content,
            importance=importance, valence=valence, source_ids=source_ids,
        ))
        if len(agent.memories) > 40:
            agent.memories = agent.memories[-40:]
        agent.last_reflection = self.cognition.reflect(agent, kind, content)

    def _trace_offer(self, city_id: str, firm_id: str, offer: PolicyPackage) -> None:
        city = self.world.cities[city_id]
        self._trace(city_id, "offer_policy_package", firm_id,
            ["企业投资与就业承诺", "竞争城市上一轮政策", "本级财政与土地状态"],
            ["招商落地", "就业增长", "控制财政风险"],
            [f"可用财力 {city.available_budget:.1f}", f"供应链基础 {city.supply_chain:.1f}"],
            [f"财政压力 {city.fiscal_pressure:.0%}", f"剩余工业用地 {city.industrial_land:.0f} 亩"],
            ["维持原政策", "提高现金补贴", "强化基金与人才支持"],
            {"fiscal_cost": offer.fiscal_cost, "land_discount": offer.land_discount}, "政策包已通过内部约束检查")

    def _trace(self, actor_id: str, action: str, target_id: str | None,
               observations: list[str], goals: list[str], evidence: list[str], constraints: list[str],
               alternatives: list[str], expected: dict[str, float], outcome: str) -> None:
        self.world.traces.append(DecisionTrace(
            id=f"trace-{len(self.world.traces)+1:04d}", quarter=self.world.quarter,
            actor_id=actor_id, action=action, target_id=target_id, observations=observations,
            goals=goals, evidence=evidence, constraints=constraints, alternatives=alternatives,
            expected_effects=expected, outcome=outcome,
        ))

    def _event(self, kind: str, title: str, detail: str, actor_id: str | None = None,
               target_id: str | None = None, severity: str = "info") -> None:
        self.world.events.append(Event(self.world.quarter, kind, title, detail, actor_id, target_id, severity))
