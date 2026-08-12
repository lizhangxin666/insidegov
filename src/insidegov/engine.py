from __future__ import annotations

import copy
import math
import random
import uuid

from .models import (
    DecisionTrace,
    Event,
    FirmState,
    Intervention,
    MetricsSnapshot,
    Phase,
    PolicyPackage,
    Promise,
    PromiseStatus,
    WorldState,
)
from .policies import DecisionPolicy, DeterministicPolicy


class SimulationEngine:
    def __init__(self, world: WorldState, policy: DecisionPolicy | None = None):
        self.world = world
        self.policy = policy or DeterministicPolicy()
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
        return SimulationEngine(cloned, self.policy)

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
            offer = self.policy.create_offer(city, anchor, self.world)
            city.active_offer = offer
            anchor.observed_offers[city.id] = offer
            self._trace_offer(city.id, anchor.id, offer)
            self._event("offer", f"{city.name}提交政策包", f"财政成本 {offer.fiscal_cost:.1f} 亿元，工业用地折让 {offer.land_discount:.0%}", city.id, anchor.id)
        if self.world.quarter >= 3:
            scores = {city_id: self._firm_city_utility(anchor, city_id) for city_id in self.world.cities}
            selected_id, selected_score = max(scores.items(), key=lambda item: item[1])
            if selected_score >= anchor.minimum_utility:
                self._select_city(anchor, selected_id, scores)

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
        for firm in self.world.firms.values():
            old = firm.perceived_credibility.get(city_id, 0.7)
            diffusion = 1.0 if firm.id == "firm_nova" else 0.55
            firm.perceived_credibility[city_id] = min(1.0, max(0.1, old + delta * diffusion))

    def _run_supplier_entry(self) -> None:
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
