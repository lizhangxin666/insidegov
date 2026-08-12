from __future__ import annotations

import copy
import math
import random
import uuid
from dataclasses import asdict, is_dataclass

import httpx

from .agents import (
    CognitiveProvider,
    DeterministicCognition,
    FinanceAction,
    build_cognition,
)
from .models import (
    AgentActionAudit,
    DecisionTrace,
    Event,
    ExternalNegotiationRound,
    FirmState,
    Intervention,
    MemoryRecord,
    MetricsSnapshot,
    NegotiationRound,
    PaymentTranche,
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
        if world.random_state is not None:
            self.random.setstate(self._tuple_state(world.random_state))
        self.world.random_state = self.random.getstate()
        self._last_cognition_meta: dict = {}

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
        self.world.random_state = self.random.getstate()
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
        cloned.branched_from_quarter = self.world.quarter
        return SimulationEngine(cloned, self.policy, self.cognition)

    def intervene(self, kind: str, target: str, value: float, quarter: int | None = None) -> None:
        self.world.interventions.append(
            Intervention(quarter or self.world.quarter + 1, kind, target, value)
        )

    @staticmethod
    def _tuple_state(value):
        if isinstance(value, list):
            return tuple(SimulationEngine._tuple_state(item) for item in value)
        return value

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
            elif item.kind == "budget_multiply" and item.target in self.world.cities:
                city = self.world.cities[item.target]
                before = city.available_budget
                city.available_budget = max(0.0, before * item.value)
                self._event(
                    "intervention", "财政参数调整",
                    f"{city.name}可用财力由 {before:.1f} 调整为 {city.available_budget:.1f} 亿元",
                    city.id, severity="warning" if item.value < 1 else "info",
                )
            elif item.kind == "budget_add" and item.target in self.world.cities:
                city = self.world.cities[item.target]
                city.available_budget = max(0.0, city.available_budget + item.value)
                self._event(
                    "intervention", "专项资金到位",
                    f"{city.name}新增可用专项资金 {item.value:.1f} 亿元",
                    city.id, severity="success",
                )

    def _run_recruitment(self) -> None:
        anchor = self.world.firms["firm_nova"]
        for city in self.world.cities.values():
            leader = self.world.agents[f"{city.id}_leader"]
            finance = self.world.agents[f"{city.id}_finance"]
            investment = self.world.agents[f"{city.id}_investment"]
            questions, disclosed, belief_before, belief_after = self._clarify_anchor_need(
                city.id, anchor
            )
            leader_observation = self._leader_observation(city, anchor)
            proposal_action = self._cognitive_call(
                "propose_offer",
                investment,
                city,
                anchor,
                self.world,
                leader_observation,
                self._retrieve_memories(investment, "招商 政策包 竞争"),
            )
            proposal = proposal_action.to_package(city.id)
            proposal_meta = self._last_cognition_meta.copy()
            prior_counter = next((
                item for item in reversed(self.world.external_negotiations)
                if item.city_id == city.id and item.firm_id == anchor.id
                and item.enterprise_response == "counter"
            ), None)
            if prior_counter:
                proposal.subsidy = max(
                    proposal.subsidy,
                    float(prior_counter.counter_terms.get("subsidy_floor", 0.0)),
                )
                proposal.equity = max(
                    proposal.equity,
                    float(prior_counter.counter_terms.get("equity_floor", 0.0)),
                )
                proposal.talent_support = min(1.0, proposal.talent_support + 0.04)
            fund_review = self._review_joint_investment(city, anchor, investment)
            proposal.external_equity = fund_review["approved_total"]
            proposal.fund_allocations = fund_review["allocations"]
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
                review_meta = self._last_cognition_meta.copy()
                review_suggestion = self._action_dict(review)
                hard_limits = self._hard_finance_constraints(city, finance)
                review.maximum_fiscal_cost = hard_limits["fiscal_cost"]
                review.maximum_subsidy = hard_limits["subsidy"]
                review.maximum_equity = hard_limits["equity"]
                review.maximum_credit_support = hard_limits["credit_support"]
                review.maximum_first_period_payment = hard_limits["first_period_payment"]
                review.approved = review.approved and self._offer_within_review(proposal, review)
                resolution = self._cognitive_call(
                    "resolve_offer",
                    leader,
                    city,
                    proposal,
                    review,
                    leader_observation,
                    self._retrieve_memories(leader, "财政否决 协调"),
                )
                resolution_meta = self._last_cognition_meta.copy()
                resolution_suggestion = self._action_dict(resolution)
                offer = resolution.to_package(city.id)
                offer = self._enforce_offer_constraints(offer, review)
                resolution_name = resolution.resolution
                resolution_rationale = resolution.rationale
            else:
                review = FinanceAction(
                    approved=True,
                    maximum_fiscal_cost=proposal.fiscal_cost,
                    maximum_subsidy=proposal.subsidy,
                    maximum_equity=proposal.equity,
                    maximum_credit_support=proposal.credit_support,
                    maximum_first_period_payment=proposal.subsidy + proposal.equity,
                    concerns=["消融实验：财政审核机制关闭"],
                    rationale="消融实验直接批准",
                )
                offer = proposal
                offer = self._enforce_offer_constraints(offer, review)
                resolution_name = "approved_without_internal_governance"
                resolution_rationale = "消融实验关闭内部治理，招商方案直接进入规则约束"
                review_meta = {"fallback": False, "diagnostics": []}
                review_suggestion = self._action_dict(review)
                resolution_meta = {"fallback": False, "diagnostics": []}
                resolution_suggestion = self._offer_tools(offer)
            offer.external_equity = proposal.external_equity
            offer.fund_allocations = copy.deepcopy(proposal.fund_allocations)
            for index, (fund_id, amount) in enumerate(offer.fund_allocations.items(), start=1):
                offer.payment_schedule.append(PaymentTranche(
                    "external_equity",
                    round(amount, 2),
                    min(3, index),
                    "contract_signed" if index == 1 else "equipment_ordered",
                    funding_source_id=fund_id,
                ))
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
                proposer_id=investment.id, reviewer_id=finance.id, coordinator_id=leader.id,
                proposal_tools=self._offer_tools(proposal),
                finance_tool_limits={
                    "subsidy": review.maximum_subsidy,
                    "equity": review.maximum_equity,
                    "credit_support": review.maximum_credit_support,
                    "first_period_payment": review.maximum_first_period_payment,
                },
                final_tools=self._offer_tools(offer),
                payment_schedule=copy.deepcopy(offer.payment_schedule),
                turns=[
                    {"actor_id": investment.id, "act": "proposal", "summary": proposal_action.rationale,
                     "amount": round(proposal.fiscal_cost, 3)},
                    *([{
                        "actor_id": "joint_investment_committee",
                        "act": "fund_review",
                        "summary": fund_review["rationale"],
                        "amount": fund_review["approved_total"],
                        "approved": fund_review["approved_total"] > 0,
                    }] if fund_review["requested_total"] > 0 else []),
                    {"actor_id": finance.id, "act": "review", "summary": review.rationale,
                     "approved": review.approved, "amount": review.maximum_fiscal_cost},
                    {"actor_id": leader.id, "act": "coordination", "summary": resolution.rationale if self.world.mechanisms.get("internal_governance", True) else "直接批准",
                     "amount": round(offer.fiscal_cost, 3)},
                ],
            ))
            internal_negotiation_id = self.world.negotiations[-1].id
            self._remember(
                investment, "proposal",
                f"提案现金 {proposal.subsidy:.1f}、股权 {proposal.equity:.1f}，总成本 {proposal.fiscal_cost:.1f}",
                0.75, [finance.id, anchor.id],
            )
            self._remember(
                finance, "review", f"审核 {city.name}政策包：{'通过' if review.approved else '否决或核减'}",
                0.72, [leader.id, anchor.id],
            )
            self._append_action_audit(
                investment, "propose_offer", leader_observation,
                proposal_meta.get("memories", []), self._action_dict(proposal_action),
                self._offer_tools(proposal), {}, proposal_action.rationale,
                investment.last_reflection, proposal_meta,
            )
            self._append_action_audit(
                finance, "review_offer", finance_observation,
                review_meta.get("memories", []), review_suggestion,
                self._action_dict(review), {
                    "source": "deterministic_finance_constraints",
                    "hard_limits": hard_limits if self.world.mechanisms.get("internal_governance", True) else {},
                    "note": "财政数值上限由规则引擎覆盖；LLM只表达审核态度和理由",
                }, review.rationale, finance.last_reflection, review_meta,
            )
            leader.last_reflection = self.cognition.reflect(
                leader, "coordinate_internal_offer",
                f"最终现金 {offer.subsidy:.1f}、股权 {offer.equity:.1f}，按节点分期兑现",
            )
            self._append_action_audit(
                leader, "resolve_offer", leader_observation,
                resolution_meta.get("memories", []), resolution_suggestion,
                self._offer_tools(offer), {
                    "source": "offer_constraint_enforcer",
                    "before": resolution_suggestion,
                    "after": self._offer_tools(offer),
                    "payment_schedule": [asdict(item) for item in offer.payment_schedule],
                }, resolution_rationale, leader.last_reflection,
                resolution_meta,
            )
            self._trace(
                leader.id, "coordinate_internal_offer", finance.id,
                ["招商局独立提案", "财政局工具级否决", "市领导协调", "财政局私有储备底线"],
                leader.goals, proposal_action.evidence, review.concerns,
                ["接受财政上限", "调整现金/基金结构", "撤回政策包"],
                {"proposal_cost": proposal.fiscal_cost, "finance_limit": review.maximum_fiscal_cost},
                f"{resolution_name}，最终现金 {offer.subsidy:.1f} + 股权 {offer.equity:.1f}，{len(offer.payment_schedule)} 期兑现",
            )
            self._trace_offer(city.id, anchor.id, offer)
            review_label = "通过" if review.approved else "工具级否决后重组"
            self._event(
                "negotiation", f"{city.name}完成内部协调",
                f"招商局提案现金 {proposal.subsidy:.1f}；财政审核{review_label}；最终现金 {offer.subsidy:.1f} + 股权 {offer.equity:.1f}，分 {len(offer.payment_schedule)} 期",
                investment.id, finance.id, "warning" if not review.approved else "info",
            )
            self._event("offer", f"{city.name}提交政策包", f"财政成本 {offer.fiscal_cost:.1f} 亿元，工业用地折让 {offer.land_discount:.0%}", city.id, anchor.id)
            utility = self._firm_city_utility(anchor, city.id)
            response, counter_terms, enterprise_rationale = self._enterprise_offer_response(
                anchor, city.id, utility
            )
            external = ExternalNegotiationRound(
                id=f"external-{len(self.world.external_negotiations)+1:04d}",
                quarter=self.world.quarter, city_id=city.id, firm_id=anchor.id,
                protocol=self.world.negotiation_protocol,
                stated_need=self.world.stated_needs[anchor.id].text,
                government_questions=questions,
                disclosed_components=disclosed,
                belief_before=belief_before,
                belief_after=belief_after,
                belief_confidence=self.world.gov_beliefs[city.id].confidence,
                internal_negotiation_id=internal_negotiation_id,
                government_offer=self._offer_tools(offer),
                enterprise_response=response,
                counter_terms=counter_terms,
                enterprise_rationale=enterprise_rationale,
                utility=utility,
                minimum_utility=anchor.minimum_utility,
                outcome="continue" if response == "counter" else response,
            )
            self.world.external_negotiations.append(external)
            self._append_action_audit(
                self.world.agents["firm_nova_board"], "evaluate_city_offer",
                self._enterprise_observation(anchor, {city.id: utility}), [],
                {"response": response, "counter_terms": counter_terms,
                 "rationale": enterprise_rationale},
                {"response": response, "counter_terms": counter_terms},
                {"source": "enterprise_acceptance_guard", "utility": utility,
                 "minimum_utility": anchor.minimum_utility},
                enterprise_rationale,
                f"Q{self.world.quarter}对{city.name}报价作出{response}回应",
                {"fallback": False, "diagnostics": []},
                outcome="responded",
            )
            self._event(
                "external_negotiation", f"{anchor.name}回应{city.name}报价",
                f"企业{response}；效用 {utility:.1f} / 门槛 {anchor.minimum_utility:.1f}；{enterprise_rationale}",
                anchor.id, city.id, "warning" if response == "counter" else "info",
            )
        if self.world.quarter >= 3:
            accepted_cities = {
                item.city_id for item in self.world.external_negotiations
                if item.quarter == self.world.quarter and item.enterprise_response == "accept"
            }
            scores = {
                city_id: self._firm_city_utility(anchor, city_id)
                for city_id in accepted_cities
            }
            if not scores:
                self._event(
                    "no_deal", "企业未接受任何城市最终报价",
                    "三座城市方案均未达到最低接受门槛，本轮招商终止",
                    anchor.id, severity="warning",
                )
                return
            board = self.world.agents["firm_nova_board"]
            decision = self._cognitive_call(
                "select_location", board, anchor, scores,
                self._enterprise_observation(anchor, scores),
                self._retrieve_memories(board, "选址 履约 风险"),
            )
            decision_meta = self._last_cognition_meta.copy()
            selected_id = decision.city_id if decision.city_id in scores else max(scores, key=scores.get)  # type: ignore[arg-type]
            selected_score = scores[selected_id]
            if selected_score >= anchor.minimum_utility:
                self._select_city(anchor, selected_id, scores)
                self._remember(
                    board, "decision", f"选择 {self.world.cities[selected_id].name}：{decision.rationale}",
                    0.95, [selected_id], valence=0.4,
                )
                self._append_action_audit(
                    board, "select_location", self._enterprise_observation(anchor, scores),
                    decision_meta.get("memories", []), self._action_dict(decision),
                    {"city_id": selected_id, "utility": selected_score}, {
                        "source": "location_utility_and_allowed_city_guard",
                        "utility_scores": scores,
                        "suggested_city_valid": decision.city_id in scores,
                    }, decision.rationale, board.last_reflection, decision_meta,
                    outcome="executed",
                )

    def _firm_city_utility(self, firm: FirmState, city_id: str) -> float:
        city = self.world.cities[city_id]
        offer = firm.observed_offers[city_id]
        credibility = firm.perceived_credibility.get(city_id, 0.7)
        if self.world.mechanisms.get("private_information", True):
            policy_sensitivity = firm.policy_sensitivity
            cluster_sensitivity = firm.cluster_sensitivity
            credibility_sensitivity = firm.credibility_sensitivity
            intent_adjustment = (firm.private_intent - 0.65) * 12
        else:
            # Public-information agents must act on population priors rather than
            # silently retaining the enterprise's hidden preference parameters.
            policy_sensitivity = 0.56
            cluster_sensitivity = 0.62
            credibility_sensitivity = 0.62
            intent_adjustment = 0.0
        policy_value = (
            offer.subsidy * 0.6
            + offer.total_equity_support * 0.36
            + offer.land_discount * 42
        )
        fundamentals = city.supply_chain * cluster_sensitivity + city.talent_pool * 0.28
        site_fit = (
            min(city.industrial_land / max(firm.land_need, 1.0), 3.0) * 4
            + city.environmental_capacity * 0.18 * firm.risk_tolerance
        )
        institution = credibility * 100 * credibility_sensitivity + offer.approval_speed * 12
        fiscal_risk = city.fiscal_pressure * 25 * credibility_sensitivity
        return round(
            (
                policy_value * policy_sensitivity
                + fundamentals
                + site_fit
                + institution
                + intent_adjustment
                - fiscal_risk
            ) / 1.65,
            2,
        )

    def _clarify_anchor_need(
        self, city_id: str, firm: FirmState,
    ) -> tuple[list[str], dict[str, float], dict[str, float], dict[str, float]]:
        latent = self.world.latent_needs.get(firm.id)
        stated = self.world.stated_needs.get(firm.id)
        belief = self.world.gov_beliefs.get(city_id)
        if not latent or not stated or not belief:
            return [], {}, {}, {}
        components = [
            "problem", "mode", "target", "deadline", "constraint", "budget", "commitment"
        ]
        if not belief.components:
            for component in components:
                truth = latent.truth.get(component, 0.7)
                belief.components[component] = round(
                    truth * stated.disclosed.get(component, 0.0)
                    * (0.45 + 0.55 * stated.clarity), 3,
                )
            belief.confidence = round(0.35 + 0.35 * stated.clarity, 3)
            belief.perceived_mode = "capacity"
        before = dict(belief.components)
        start = (self.world.quarter - 1) * 3
        questions = components[start:start + 3]
        disclosed: dict[str, float] = {}
        secrecy = 0.18 + stated.exaggeration * 0.4
        for component in questions:
            openness = max(0.12, 0.86 - secrecy)
            if component in {"constraint", "commitment"}:
                openness *= 0.72
            disclosed[component] = round(openness, 3)
            truth = latent.truth.get(component, 0.7)
            current = belief.components.get(component, 0.0)
            belief.components[component] = round(
                min(truth, current + (truth - current) * openness), 3
            )
        values = list(belief.components.values())
        belief.confidence = round(sum(values) / len(values), 3) if values else 0.0
        if belief.components.get("mode", 0) >= 0.55:
            belief.perceived_mode = latent.preferred_mode
        return questions, disclosed, before, dict(belief.components)

    def _enterprise_offer_response(
        self, firm: FirmState, city_id: str, utility: float,
    ) -> tuple[str, dict[str, float], str]:
        gap = utility - firm.minimum_utility
        if self.world.quarter >= 3:
            if gap >= 0:
                return "accept", {}, "最终方案达到最低接受门槛，进入跨城市择优"
            return "terminate", {}, "最终方案未达到最低接受门槛，退出该城市谈判"
        if gap >= 10 and self.world.quarter >= 2:
            return "accept", {}, "方案已覆盖核心需求，保留至最终跨城市比较"
        latest = self.world.external_negotiations
        prior_counter = next((
            item for item in reversed(latest)
            if item.city_id == city_id and item.firm_id == firm.id and item.counter_terms
        ), None)
        increment = 1.0 if prior_counter else 1.5
        counter = {
            "subsidy_floor": round(firm.observed_offers[city_id].subsidy + increment, 2),
            "equity_floor": round(firm.observed_offers[city_id].equity + 0.8, 2),
            "require_phased_delivery": 1.0,
        }
        return "counter", counter, "政策强度或履约保障仍不足，要求提高支持并绑定分期节点"

    def _select_city(self, anchor: FirmState, city_id: str, scores: dict[str, float]) -> None:
        city = self.world.cities[city_id]
        offer = city.active_offer
        assert offer is not None
        self.world.selected_city_id = city_id
        anchor.location = city_id
        city.landed_firms.append(anchor.id)
        city.industrial_land -= anchor.land_need
        city.committed_expenditure += offer.fiscal_cost
        for fund_id, amount in offer.fund_allocations.items():
            fund = self.world.investment_funds.get(fund_id)
            if fund is None or amount <= 0:
                continue
            committed = min(amount, fund.available_capital)
            fund.available_capital -= committed
            fund.committed_capital += committed
        schedule = offer.payment_schedule or [
            type("Tranche", (), {"item": "equity", "amount": offer.equity, "due_offset": 1, "condition": "contract_signed"})(),
            type("Tranche", (), {"item": "subsidy", "amount": offer.subsidy, "due_offset": 3, "condition": "project_progress>=0.55"})(),
            type("Tranche", (), {"item": "credit_support", "amount": offer.credit_support * 0.08, "due_offset": 5, "condition": "production_commissioned"})(),
        ]
        for tranche in schedule:
            self.world.promises.append(Promise(
                id=f"promise-{len(self.world.promises)+1:03d}", city_id=city_id, firm_id=anchor.id,
                item=tranche.item, amount=tranche.amount,
                due_quarter=self.world.quarter + tranche.due_offset,
                condition=tranche.condition,
                funding_source_id=getattr(tranche, "funding_source_id", None),
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
        disruption_risk = (
            0.025
            + city.fiscal_pressure * 0.09
            + (1 - city.objective_credibility) * 0.08
            + max(0.0, 75 - city.administrative_capacity) / 1000
        )
        if self.random.random() < disruption_risk:
            increment *= 0.55
            self._event(
                "progress",
                "项目节点短暂延误",
                f"{anchor.name}因审批、设备或资金节奏波动未完成当期计划",
                anchor.id,
                city.id,
                "warning",
            )
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
            condition_met = self._promise_condition_met(promise.condition, anchor)
            if not condition_met:
                continue
            due = promise.amount - promise.paid_amount
            if promise.funding_source_id:
                fund = self.world.investment_funds.get(promise.funding_source_id)
                payment = min(due, fund.committed_capital if fund else 0.0)
                if fund is not None and payment >= due - 1e-9:
                    fund.committed_capital = max(0.0, fund.committed_capital - payment)
                    anchor.cash += payment
                    promise.paid_amount += payment
                    promise.status = PromiseStatus.FULFILLED
                    city.objective_credibility = min(1.0, city.objective_credibility + 0.012)
                    self._update_perceptions(city.id, +0.018)
                    self._event(
                        "promise",
                        "联合产业基金按期出资",
                        f"{fund.name}支付 {payment:.1f} 亿元股权投资",
                        fund.id,
                        anchor.id,
                        "success",
                    )
                else:
                    promise.status = PromiseStatus.DELAYED
                    promise.delayed_quarters += 1
                    promise.due_quarter += 1
                    city.objective_credibility = max(0.25, city.objective_credibility - 0.035)
                    self._update_perceptions(city.id, -0.055)
                    self._event(
                        "promise",
                        "联合产业基金出资延期",
                        f"{promise.funding_source_id}未能足额支付 {due:.1f} 亿元",
                        promise.funding_source_id,
                        anchor.id,
                        "warning",
                    )
                continue
            finance = self.world.agents.get(f"{city.id}_finance")
            reserve_floor = (
                float(finance.private_facts.get("reserve_floor", city.available_budget * 0.34))
                if finance is not None
                else city.available_budget * 0.34
            )
            liquidity = max(0.0, city.available_budget - max(city.debt * 0.01, reserve_floor))
            administrative_delay = (
                promise.status != PromiseStatus.DELAYED
                and self.random.random()
                < 0.015
                + city.fiscal_pressure * 0.055
                + (1 - city.objective_credibility) * 0.06
            )
            payment = 0.0 if administrative_delay else min(due, liquidity)
            if payment >= due - 1e-9:
                city.available_budget -= payment
                city.committed_expenditure = max(0.0, city.committed_expenditure - payment)
                anchor.cash += payment
                promise.paid_amount += payment
                promise.status = PromiseStatus.FULFILLED
                city.objective_credibility = min(1.0, city.objective_credibility + 0.018)
                self._update_perceptions(city.id, +0.026)
                self._event("promise", "政策承诺按期兑现", f"{city.name}支付 {payment:.1f} 亿元 {promise.item}", city.id, anchor.id, "success")
            else:
                if payment > 0:
                    city.available_budget -= payment
                    anchor.cash += payment
                    promise.paid_amount += payment
                promise.status = PromiseStatus.DELAYED
                promise.delayed_quarters += 1
                promise.due_quarter += 1
                city.objective_credibility = max(0.25, city.objective_credibility - 0.055)
                self._update_perceptions(city.id, -0.085)
                self._event("promise", "政策承诺延期", f"{city.name}未能足额支付 {due:.1f} 亿元 {promise.item}", city.id, anchor.id, "danger")

    def _update_perceptions(self, city_id: str, delta: float) -> None:
        if not self.world.mechanisms.get("credibility_diffusion", True):
            return
        for firm in self.world.firms.values():
            old = firm.perceived_credibility.get(city_id, 0.7)
            diffusion = 1.0 if firm.id == "firm_nova" else 0.78
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
            # A supplier has one capital-budget window in the experiment horizon.
            # Re-evaluating every quarter would make all marginal firms eventually
            # enter and erase both seed variance and information-treatment effects.
            entry_rng = random.Random(
                f"insidegov:{self.world.seed}:{firm.id}:supplier-entry"
            )
            entry_quarter = entry_rng.randint(10, 16)
            if self.world.quarter != entry_quarter:
                continue
            credibility = firm.perceived_credibility[city_id]
            private_information = self.world.mechanisms.get("private_information", True)
            inferred_intent = firm.private_intent if private_information else 0.65
            information_gap = 0.0 if private_information else (
                18.0
                + abs(firm.private_intent - 0.65) * 10
                + abs(firm.minimum_utility - 63.0) * 0.25
            )
            credibility_uncertainty = (
                0.0
                if self.world.mechanisms.get("credibility_diffusion", True)
                else 12.0 + firm.credibility_sensitivity * 3
            )
            attractiveness = (
                city.supply_chain * firm.cluster_sensitivity
                + credibility * 100 * firm.credibility_sensitivity
                + city.talent_pool * 0.18
                + inferred_intent * 18
                - city.fiscal_pressure * 12
            )
            information_quality = 1.0 if private_information else 0.78
            if not self.world.mechanisms.get("credibility_diffusion", True):
                information_quality *= 0.84
            threshold = (
                firm.minimum_utility
                + information_gap
                + credibility_uncertainty
                + entry_rng.uniform(-7, 7)
            )
            if (
                attractiveness * information_quality / 1.55 >= threshold
                and city.industrial_land >= firm.land_need
            ):
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
        observation = {
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
        belief = self.world.gov_beliefs.get(city.id)
        if belief:
            observation["enterprise_need_belief"] = {
                "components": dict(belief.components),
                "confidence": belief.confidence,
                "perceived_mode": belief.perceived_mode,
            }
        prior_counter = next((
            item for item in reversed(self.world.external_negotiations)
            if item.city_id == city.id and item.firm_id == anchor.id
            and item.enterprise_response == "counter"
        ), None)
        if prior_counter:
            observation["enterprise_last_counter"] = dict(prior_counter.counter_terms)
        return observation

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
                "utility_score": scores.get(city_id),
            }
        return {"offers_and_due_diligence": offers, "decision_is_irreversible": True}

    def _hard_finance_limit(self, city, finance) -> float:
        return self._hard_finance_constraints(city, finance)["fiscal_cost"]

    def _hard_finance_constraints(self, city, finance) -> dict[str, float]:
        reserve = float(finance.private_facts.get("reserve_floor", city.available_budget * 0.34))
        spendable = max(0.0, city.available_budget - reserve)
        risk_discount = max(0.3, 1 - city.fiscal_pressure * finance.traits["risk_aversion"])
        return {
            "fiscal_cost": round(max(0.0, min(spendable * 0.34, city.available_budget * 0.19) * risk_discount), 2),
            "subsidy": round(min(spendable * 0.11, city.available_budget * 0.065) * risk_discount, 2),
            "equity": round(min(spendable * 0.19, city.available_budget * 0.105) * risk_discount, 2),
            "credit_support": round(min(30.0, city.available_budget * 0.21) * risk_discount, 2),
            "first_period_payment": round(min(spendable * 0.12, city.available_budget * 0.075), 2),
        }

    def _review_joint_investment(self, city, anchor, investment_agent) -> dict:
        target = max(
            0.0,
            float(investment_agent.private_facts.get("external_fund_target", 0.0)),
        )
        funds = [
            fund for fund in self.world.investment_funds.values()
            if fund.city_id == city.id and fund.available_capital > 0
        ]
        if target <= 0 or not funds:
            return {
                "requested_total": target,
                "approved_total": 0.0,
                "allocations": {},
                "rationale": "本轮没有可独立决策的联合产业基金参与",
            }
        project_score = (
            anchor.technology * 0.40
            + anchor.private_intent * 100 * 0.25
            + min(100.0, anchor.investment_capacity / 2.5) * 0.20
            + city.supply_chain * 0.15
        ) / 100
        allocations: dict[str, float] = {}
        remaining = target
        for fund in sorted(funds, key=lambda item: item.risk_tolerance, reverse=True):
            if project_score < fund.due_diligence_threshold:
                continue
            allocation = min(fund.available_capital, remaining)
            if allocation > 0:
                allocations[fund.id] = round(allocation, 2)
                remaining -= allocation
            if remaining <= 0.005:
                break
        approved = round(sum(allocations.values()), 2)
        return {
            "requested_total": round(target, 2),
            "approved_total": approved,
            "allocations": allocations,
            "project_score": round(project_score, 3),
            "rationale": (
                f"独立产业基金按项目质量和自身风控审核，申请 {target:.2f} 亿元，"
                f"核准 {approved:.2f} 亿元；该额度不占用市财政现金上限"
            ),
        }

    @staticmethod
    def _offer_tools(offer: PolicyPackage) -> dict[str, float]:
        return {
            "subsidy": round(offer.subsidy, 3),
            "equity": round(offer.equity, 3),
            "external_equity": round(offer.external_equity, 3),
            "total_equity_support": round(offer.total_equity_support, 3),
            "credit_support": round(offer.credit_support, 3),
            "land_discount": round(offer.land_discount, 3),
            "fiscal_cost": round(offer.fiscal_cost, 3),
        }

    @staticmethod
    def _offer_within_review(offer: PolicyPackage, review: FinanceAction) -> bool:
        return (
            offer.fiscal_cost <= review.maximum_fiscal_cost + 0.01
            and offer.subsidy <= review.maximum_subsidy + 0.01
            and offer.equity <= review.maximum_equity + 0.01
            and offer.credit_support <= review.maximum_credit_support + 0.01
        )

    def _enforce_offer_constraints(
        self, offer: PolicyPackage, review: FinanceAction
    ) -> PolicyPackage:
        offer.subsidy = round(min(offer.subsidy, review.maximum_subsidy), 2)
        offer.equity = round(min(offer.equity, review.maximum_equity), 2)
        offer.credit_support = round(min(offer.credit_support, review.maximum_credit_support), 2)
        if offer.fiscal_cost > review.maximum_fiscal_cost:
            overflow = offer.fiscal_cost - review.maximum_fiscal_cost
            offer.equity = round(max(0.0, offer.equity - overflow), 2)
        from .models import PaymentTranche

        equity_first = min(offer.equity, review.maximum_first_period_payment * 0.65)
        cash_first = min(
            offer.subsidy * 0.4,
            max(0.0, review.maximum_first_period_payment - equity_first),
        )
        offer.payment_schedule = [
            PaymentTranche("equity", round(equity_first, 2), 1, "contract_signed"),
            PaymentTranche("subsidy", round(cash_first, 2), 1, "equipment_ordered"),
        ]
        if offer.equity - equity_first > 0.01:
            offer.payment_schedule.append(PaymentTranche(
                "equity", round(offer.equity - equity_first, 2), 2, "equipment_ordered"
            ))
        if offer.subsidy - cash_first > 0.01:
            offer.payment_schedule.append(PaymentTranche(
                "subsidy", round(offer.subsidy - cash_first, 2), 3,
                "project_progress>=0.55",
            ))
        if offer.credit_support > 0.01:
            offer.payment_schedule.append(PaymentTranche(
                "credit_support_cost", round(offer.credit_support * 0.08, 2), 5,
                "production_commissioned",
            ))
        return offer

    @staticmethod
    def _promise_condition_met(condition: str, anchor: FirmState) -> bool:
        if condition == "contract_signed":
            return anchor.location is not None
        if condition == "equipment_ordered":
            return anchor.project_progress >= 0.12
        if condition == "production_commissioned":
            return anchor.operating
        if condition.startswith("project_progress>="):
            return anchor.project_progress >= float(condition.split(">=")[1])
        return False

    def _cognitive_call(self, method: str, *args):
        cognitive_args = args
        if not self.world.mechanisms.get("private_information", True) and args:
            actor = copy.copy(args[0])
            if hasattr(actor, "private_facts"):
                actor.private_facts = {}
                cognitive_args = (actor, *args[1:])
        diagnostic_start = len(getattr(self.cognition, "diagnostics", []))
        memories = list(cognitive_args[-1]) if cognitive_args and isinstance(cognitive_args[-1], list) else []
        try:
            result = getattr(self.cognition, method)(*cognitive_args)
            self._last_cognition_meta = {
                "fallback": False,
                "diagnostics": copy.deepcopy(
                    getattr(self.cognition, "diagnostics", [])[diagnostic_start:]
                ),
                "memories": memories,
            }
            return result
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            if isinstance(self.cognition, DeterministicCognition):
                raise
            failed_model = self.cognition.model_name or "DeepSeek"
            self._event(
                "model_fallback", "认知模型降级",
                f"{failed_model} 未返回可用结构化行动，本步改用确定性策略："
                f"{type(exc).__name__}: {str(exc)[:600]}",
                severity="warning",
            )
            fallback = DeterministicCognition()
            result = getattr(fallback, method)(*cognitive_args)
            self._last_cognition_meta = {
                "fallback": True,
                "diagnostics": copy.deepcopy(
                    getattr(self.cognition, "diagnostics", [])[diagnostic_start:]
                ),
                "memories": memories,
                "error": f"{type(exc).__name__}: {str(exc)[:600]}",
            }
            return result

    @staticmethod
    def _action_dict(action) -> dict:
        if hasattr(action, "model_dump"):
            return action.model_dump()
        if is_dataclass(action):
            return asdict(action)
        if isinstance(action, dict):
            return copy.deepcopy(action)
        return {"value": str(action)}

    def _append_action_audit(
        self, agent, action_type: str, observation: dict, memories: list[str],
        suggestion: dict, executed: dict, adjustment: dict, rationale: str,
        reflection: str, meta: dict, outcome: str = "executed",
    ) -> None:
        private_context = copy.deepcopy(agent.private_facts)
        if not self.world.mechanisms.get("private_information", True):
            private_context = {}
        self.world.action_audits.append(AgentActionAudit(
            id=f"audit-{len(self.world.action_audits)+1:05d}",
            quarter=self.world.quarter,
            agent_id=agent.id,
            action_type=action_type,
            observation=copy.deepcopy(observation),
            private_context_used=private_context,
            retrieved_memories=list(memories),
            llm_suggestion=copy.deepcopy(suggestion),
            rule_adjustment=copy.deepcopy(adjustment),
            executed_action=copy.deepcopy(executed),
            rationale=rationale,
            reflection=reflection,
            provider=self.cognition.model_name or self.cognition.mode,
            fallback=bool(meta.get("fallback")),
            diagnostics=copy.deepcopy(meta.get("diagnostics", [])),
            outcome=outcome,
        ))

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
