"""政企协商机制实验室——规则引擎。

引擎拥有全部客观真相：真实需求（LatentNeed）、理解差距（UnderstandingGap）、
政策匹配度（PolicyFit）、语义/激励对齐、财政成本与履约结果。认知层只提出
结构化行动（追问什么、披露多少、给什么方案、是否接受），引擎验证并结算。

七种协商机制通过同一个流程骨架分派：表达 →（按机制）诊断/澄清/复述/披露
→ 提案 → 评估 → 签约或终止。机制的差异体现在「信息披露路径」与「方案
生成方式」上：澄清/复述/约束披露让政府 belief 更接近真实需求（gap 下降），
但花费更多轮次；分阶段/约束先行降低误签与履约风险但更慢。

核心研究逻辑：
- 低质项目识别：澄清充分的机制能看清企业真实投入与风险（commitment、
  problem 对齐度高），从而在签约前叫停；表面匹配机制会误签并后期违约。
- 履约与后悔：签约不等于合作成功，fit、企业真实投入、夸大程度与是否
  分阶段共同决定履约概率，失败产生后悔与信任损失。
"""

from __future__ import annotations

import copy
import random
import uuid

import httpx

from .due_diligence import DueDiligenceEngine
from .models import (
    CooperationExecution,
    DecisionTrace,
    Event,
    GovBelief,
    Intervention,
    MemoryRecord,
    MetricsSnapshot,
    NegotiationRecord,
    Phase,
    WorldState,
)
from .negotiation_agents import (
    TOOL_COST,
    DeterministicNegotiationCognition,
    NegotiationCognitiveProvider,
    build_negotiation_cognition,
    conversation_mechanism_traits,
)

COMPONENTS = ["problem", "target", "deadline", "budget", "mode", "constraint", "commitment"]
MAX_NEGOTIATION_ROUNDS = 4
GOV_FISCAL_SHARE = 0.30  # 政府可支配中用于单个项目的上限比例


class NegotiationEngine:
    def __init__(
        self,
        world: WorldState,
        cognition: NegotiationCognitiveProvider | None = None,
    ):
        self.world = world
        self.cognition = cognition or build_negotiation_cognition(world.policy_mode, world.model_name)
        self.world.policy_mode = self.cognition.mode
        self.world.model_name = self.cognition.model_name
        self.world.phase = Phase.NEGOTIATION
        self.random = random.Random(world.seed)
        self.due_diligence = DueDiligenceEngine(world)

    def step(self) -> WorldState:
        self.world.quarter += 1
        self._apply_interventions()
        settled_firms = {r.firm_id for r in self.world.negotiation_records}
        for firm_id in self.world.firms:
            if firm_id in settled_firms:
                continue  # 每家企业在一轮实验中只协商一次
            self._negotiate(firm_id)
        self._settle_executions()
        self._record_metrics()
        return self.world

    def run(self, quarters: int) -> WorldState:
        for _ in range(quarters):
            self.step()
        return self.world

    def branch(self, branch_id: str | None = None) -> NegotiationEngine:
        cloned = copy.deepcopy(self.world)
        cloned.parent_id = self.world.id
        cloned.id = branch_id or f"negotiation-branch-{uuid.uuid4().hex[:8]}"
        cloned.name = f"{self.world.name} / 分支"
        return NegotiationEngine(cloned, self.cognition)

    def intervene(self, kind: str, target: str, value: float, quarter: int | None = None) -> None:
        self.world.interventions.append(Intervention(quarter or self.world.quarter + 1, kind, target, value))

    # ------------------------------------------------------------------ #
    # 单次协商主流程
    # ------------------------------------------------------------------ #
    def _negotiate(self, firm_id: str) -> NegotiationRecord | None:
        if firm_id not in self.world.latent_needs:
            return None
        latent = self.world.latent_needs[firm_id]
        stated = self.world.stated_needs[firm_id]
        protocol = self.world.negotiation_protocol
        mechanism_traits = conversation_mechanism_traits(protocol)
        city = self.world.cities["city_qing"]
        gov_agent = self.world.agents["city_qing_investment"]
        firm_agent = self.world.agents[f"{firm_id}_board"]
        firm = self.world.firms[firm_id]
        belief = self.world.gov_beliefs[firm_id]
        self._init_belief(belief, stated, latent)
        diligence = self.due_diligence.assess(firm_id)
        if diligence.decision == "reject":
            return self._terminate(
                firm_id,
                f"证据门控尽调否决：预计失败概率 {diligence.estimated_failure_probability:.0%}；"
                f"{diligence.rationale}",
                belief, self._gap(belief), [], 0, 0, 0.0, gov_agent,
            )
        if diligence.decision == "defer":
            return self._terminate(
                firm_id,
                f"证据不足，暂缓签约：不确定性 {diligence.uncertainty:.0%}；{diligence.rationale}",
                belief, self._gap(belief), [], 0, 0, 0.0, gov_agent,
            )

        turns: list[dict] = []
        clarifications = 0
        paraphrases = 0
        gap_initial = self._gap(belief)

        # ---- 阶段一：诊断与澄清（按机制分派） ----
        round_index = 0
        while round_index < MAX_NEGOTIATION_ROUNDS:
            diag = self._cognitive_call("diagnose", gov_agent, city, firm, stated, belief, protocol, round_index, self.world)
            # A compositional protocol constrains the legal sequence, not the
            # Agent's substantive judgment.  If an LLM skips a mandatory
            # consultation/confirmation step, the protocol gate repairs only
            # the next-action type and leaves later proposal content autonomous.
            if mechanism_traits:
                expected = DeterministicNegotiationCognition().diagnose(
                    gov_agent, city, firm, stated, belief, protocol, round_index, self.world,
                )
                if diag.next_action not in {
                    expected.next_action,
                    "propose" if expected.next_action == "clarify" and self._gap(belief) <= 0.12 else expected.next_action,
                }:
                    diag = expected
            round_index += 1
            if diag.next_action == "propose":
                break
            if diag.next_action == "clarify":
                clarifications += len(diag.questions)
                disclose = self._cognitive_call("answer", firm_agent, latent, stated, diag.questions, self.world)
                self._apply_disclose(belief, latent, disclose.components)
                turns.append({
                    "round": round_index, "actor": firm_id, "action": "disclose",
                    "components": dict(disclose.components), "text": disclose.text,
                })
            elif diag.next_action == "paraphrase":
                paraphrases += 1
                confirm = self._cognitive_call("confirm", firm_agent, latent, belief, self.world)
                self._apply_paraphrase(belief, latent, confirm)
                turns.append({
                    "round": round_index, "actor": firm_id,
                    "action": "confirm" if confirm.confirmed else "correct",
                    "correction": confirm.correction, "components": dict(confirm.components),
                })
            elif diag.next_action == "disclose":
                self._government_disclose(city, belief)
                disclose = self._cognitive_call("answer", firm_agent, latent, stated, ["constraint", "budget", "commitment"], self.world)
                self._apply_disclose(belief, latent, disclose.components)
                turns.append({
                    "round": round_index, "actor": firm_id, "action": "disclose_under_constraint_first",
                    "components": dict(disclose.components),
                })
            if self._gap(belief) <= 0.12:
                break

        # ---- 阶段二：提案 ----
        proposal = self._cognitive_call("propose", gov_agent, city, firm, stated, belief, protocol, self.world)
        options = proposal.options or []
        if not options:
            return self._terminate(firm_id, "政府未生成任何可行方案", belief, gap_initial,
                                   turns, clarifications, paraphrases, 0.0, gov_agent)
        if mechanism_traits.get("conditional_commitment"):
            for option in options:
                option["phased"] = True
                conditions = list(option.get("conditions", []))
                if "首期试点验收后再追加支持" not in conditions:
                    conditions.append("首期试点验收后再追加支持")
                option["conditions"] = conditions
                option["discloses_limits"] = True
        if protocol == "multi_option" and len(options) > 1:
            option = self._choose_option(firm_agent, latent, stated, options)
            self._apply_preference(belief, latent)
        else:
            option = options[0]
        if diligence.decision == "conditional_pilot":
            option["phased"] = True
            option["tools"] = {
                key: round(value * 0.35, 3)
                for key, value in option.get("tools", {}).items()
            }
            option["due_diligence_condition"] = "pilot_before_full_commitment"
        fit = self._true_fit(latent, option)
        trust = firm.perceived_credibility.get("city_qing", 0.55)

        # ---- 阶段三：企业评估与还价 ----
        evaluation = self._cognitive_call("evaluate", firm_agent, latent, stated, option, trust, self.world)
        turns.append({
            "round": round_index + 1, "actor": firm_id, "action": evaluation.response,
            "perceived_fit": evaluation.perceived_fit, "rationale": evaluation.rationale,
        })
        if evaluation.response == "accept":
            return self._sign(firm_id, latent, stated, option, belief, evaluation,
                              gap_initial, fit, turns, clarifications, paraphrases, trust, gov_agent)
        if evaluation.response == "counter":
            for tool, strength in (evaluation.counter_tools or {}).items():
                if tool in TOOL_COST:
                    option["tools"][tool] = max(option["tools"].get(tool, 0.0), strength)
            turns.append({"round": round_index + 2, "actor": "city_qing_investment", "action": "补充条件"})
            evaluation2 = self._cognitive_call("evaluate", firm_agent, latent, stated, option, min(1.0, trust + 0.02), self.world)
            turns.append({
                "round": round_index + 2, "actor": firm_id, "action": evaluation2.response,
                "rationale": evaluation2.rationale,
            })
            if evaluation2.response == "accept":
                return self._sign(firm_id, latent, stated, option, belief, evaluation2,
                                  gap_initial, fit, turns, clarifications, paraphrases, trust, gov_agent)
            return self._terminate(firm_id, "还价后仍未达成一致", belief, gap_initial,
                                   turns, clarifications, paraphrases, fit, gov_agent)
        return self._terminate(firm_id, evaluation.rationale or "企业认为方案与需求错位",
                               belief, gap_initial, turns, clarifications, paraphrases, fit, gov_agent)

    # ------------------------------------------------------------------ #
    # 结算：签约 / 终止
    # ------------------------------------------------------------------ #
    def _sign(
        self, firm_id, latent, stated, option, belief, evaluation,
        gap_initial, fit, turns, clarifications, paraphrases, trust, gov_agent,
    ) -> NegotiationRecord:
        firm = self.world.firms[firm_id]
        city = self.world.cities["city_qing"]
        gov_cost = round(sum(TOOL_COST.get(t, 0.0) * v for t, v in option.get("tools", {}).items()), 2)
        ent_commit = round(latent.commitment * (1 - stated.exaggeration * 0.5), 3)
        headroom = city.available_budget * GOV_FISCAL_SHARE
        overpromise = max(0.0, gov_cost / max(headroom, 1.0) - 0.5)
        # 分阶段承诺：政府不一次性承诺全部资金，财政过度承诺风险下降，
        # 因此激励对齐更高（这是分阶段机制的本体价值，而非语言或理解）
        incentive = round(max(0.0, min(1.0,
            1 - 0.7 * stated.exaggeration - overpromise
            + (0.10 if option.get("phased") else 0.0)
        )), 3)
        gap_final = self._gap(belief)
        semantic = round(1.0 - gap_final, 3)
        style = option.get("language_style", self.world.language_style)
        risk_profile = self.world.project_risk_profiles.get(firm_id)
        latent_failure_risk = (
            self.due_diligence.actual_failure_probability(risk_profile)
            if risk_profile is not None else 0.35
        )
        success_prob = round(max(0.05, min(0.95,
            0.35 + fit * 0.30 + ent_commit * 0.25
            + (0.15 if option.get("phased") else 0.0)
            - 0.30 * stated.exaggeration - 0.35 * latent_failure_risk
        )), 4)

        record = NegotiationRecord(
            id=f"nrec-{len(self.world.negotiation_records)+1:04d}",
            quarter=self.world.quarter, firm_id=firm_id, protocol=self.world.negotiation_protocol,
            rounds=max(1, len(turns)), outcome="accepted", fail_reason=None,
            gap_initial=gap_initial, gap_final=gap_final, policy_fit=fit,
            understanding_final=evaluation.understanding,
            trust_after=round(min(1.0, trust + evaluation.trust_delta), 3),
            semantic_alignment=semantic, incentive_alignment=incentive,
            gov_cost=gov_cost, ent_commitment=ent_commit, language_style=style,
            clarification_asked=clarifications, paraphrases=paraphrases, turns=turns,
        )
        self.world.negotiation_records.append(record)
        self.world.cooperation_executions.append(CooperationExecution(
            id=f"cexec-{len(self.world.cooperation_executions)+1:04d}",
            record_id=record.id, firm_id=firm_id, quarter=self.world.quarter,
            success_prob=success_prob,
        ))
        city.committed_expenditure = round(city.committed_expenditure + gov_cost, 2)
        firm.perceived_credibility["city_qing"] = round(min(1.0, trust + (0.05 if option.get("discloses_limits") else 0.02)), 3)
        self._trace(
            "city_qing_investment", "sign_agreement", firm_id,
            [f"理解差距 {gap_final:.2f}", f"匹配度 {fit:.2f}", f"轮次 {len(turns)}"],
            ["促成可履约合作", "控制财政风险"],
            [f"激励对齐 {incentive:.2f}", f"企业真实投入 {ent_commit:.2f}"],
            ["财政可支配", "部门审批权限"], ["终止", "继续协商"],
            {"gov_cost": gov_cost, "fit": fit}, f"{firm.name}达成合作（{len(turns)} 轮）",
        )
        self._event(
            "deal", f"{firm.name}与政府达成合作",
            f"支持 {gov_cost:.1f} 万 / 企业投入 {ent_commit:.2f} / 匹配度 {fit:.2f} / "
            f"{'分阶段' if option.get('phased') else '一次性'}承诺",
            "city_qing_investment", firm_id, "success",
        )
        self._remember(gov_agent, "negotiation", f"{firm.name}：gap {gap_initial:.2f}→{gap_final:.2f}，fit {fit:.2f}", 0.7, [firm_id])
        return record

    def _terminate(self, firm_id, reason, belief, gap_initial, turns,
                   clarifications, paraphrases, fit, gov_agent) -> NegotiationRecord:
        gap_final = self._gap(belief)
        record = NegotiationRecord(
            id=f"nrec-{len(self.world.negotiation_records)+1:04d}",
            quarter=self.world.quarter, firm_id=firm_id, protocol=self.world.negotiation_protocol,
            rounds=max(1, len(turns) or 1), outcome="terminated", fail_reason=reason,
            gap_initial=gap_initial, gap_final=gap_final, policy_fit=fit,
            understanding_final=0.0, trust_after=0.0, semantic_alignment=round(1 - gap_final, 3),
            incentive_alignment=0.0, gov_cost=0.0, ent_commitment=0.0,
            language_style=self.world.language_style,
            clarification_asked=clarifications, paraphrases=paraphrases, turns=turns,
        )
        self.world.negotiation_records.append(record)
        self._event(
            "no_deal", f"{self.world.firms[firm_id].name}未达成合作",
            reason, "city_qing_investment", firm_id, "info",
        )
        self._remember(gov_agent, "negotiation", f"{self.world.firms[firm_id].name}未达成：{reason}", 0.5, [firm_id])
        return record

    # ------------------------------------------------------------------ #
    # 理解差距：belief 初始化与更新
    # ------------------------------------------------------------------ #
    def _init_belief(self, belief: GovBelief, stated, latent) -> None:
        for component in COMPONENTS:
            disclosed = stated.disclosed.get(component, 0.0)
            truth = latent.truth.get(component, 0.70)
            belief.components[component] = round(truth * disclosed * (0.45 + 0.55 * stated.clarity), 3)
        belief.confidence = round(0.35 + 0.35 * stated.clarity, 3)
        belief.perceived_mode = self._infer_mode(stated.category)

    @staticmethod
    def _infer_mode(category: str) -> str:
        return {
            "talent_shortage": "fulltime",
            "digitalization": "project",
            "expansion": "capacity",
            "consulting": "diagnosis",
        }.get(category, "flexible")

    def _apply_disclose(self, belief: GovBelief, latent, components: dict[str, float]) -> None:
        for component, level in components.items():
            truth = latent.truth.get(component, 0.70)
            current = belief.components.get(component, 0.0)
            belief.components[component] = round(min(truth, current + level * (truth - current)), 3)
            if component == "mode" and level >= 0.50:
                belief.perceived_mode = latent.preferred_mode
        belief.confidence = round(min(1.0, belief.confidence + 0.06 * len(components)), 3)

    def _apply_paraphrase(self, belief: GovBelief, latent, confirm) -> None:
        if confirm.confirmed:
            for component in belief.components:
                current = belief.components[component]
                belief.components[component] = round(min(latent.truth.get(component, 0.70), current + 0.12), 3)
        else:
            for component in (confirm.components or {}):
                belief.components[component] = round(latent.truth.get(component, 0.70), 3)
                if component == "mode":
                    belief.perceived_mode = latent.preferred_mode
            belief.confidence = round(min(1.0, belief.confidence + 0.08), 3)

    def _government_disclose(self, city, belief: GovBelief) -> None:
        """约束先行：政府先公开权限与预算边界，提高后续方案的可信与可行性。"""
        belief.confidence = round(min(1.0, belief.confidence + 0.10), 3)
        self._event(
            "disclosure", "政府披露权限与预算边界",
            f"可用专项 {city.available_budget:.0f} 万，单项目上限为可支配的 {GOV_FISCAL_SHARE:.0%}，"
            "大额事项需部门会签", "city_qing_investment", severity="info",
        )

    def _apply_preference(self, belief: GovBelief, latent) -> None:
        """多方案协商：企业比较后反馈偏好，隐含揭示合作方式与目标。"""
        for component in ("mode", "target"):
            truth = latent.truth.get(component, 0.70)
            belief.components[component] = round(min(truth, belief.components.get(component, 0.0) + 0.28), 3)
        belief.perceived_mode = latent.preferred_mode
        belief.confidence = round(min(1.0, belief.confidence + 0.08), 3)

    @staticmethod
    def _gap(belief: GovBelief) -> float:
        values = [belief.components.get(c, 0.0) for c in COMPONENTS]
        return round(1.0 - sum(values) / len(values), 4)

    def _true_fit(self, latent, option: dict) -> float:
        offered = set(option.get("tools", {}))
        required_total = sum(latent.required_tools.values()) or 1.0
        coverage = sum(w for t, w in latent.required_tools.items() if t in offered) / required_total
        gov_support = sum(TOOL_COST.get(t, 0.0) * v for t, v in option.get("tools", {}).items())
        budget_ok = min(1.0, (gov_support + latent.budget * latent.commitment * 0.4) / max(latent.budget, 1.0))
        mode_ok = 1.0 if (
            latent.preferred_mode == "fulltime" or not any(t in ("talent_recruit", "relocation") for t in offered)
        ) else 0.4
        constraint_ok = 0.4 if (
            any("全职" in c for c in latent.constraints) and "talent_recruit" in offered
        ) else 1.0
        return round(0.5 * coverage + 0.2 * budget_ok + 0.15 * mode_ok + 0.15 * constraint_ok, 4)

    def _choose_option(self, firm_agent, latent, stated, options: list[dict]) -> dict:
        """企业比较多个方案：优先覆盖，其次成本，最后配套条件。"""
        def score(option: dict) -> float:
            offered = set(option.get("tools", {}))
            required_total = sum(latent.required_tools.values()) or 1.0
            coverage = sum(w for t, w in latent.required_tools.items() if t in offered) / required_total
            cost = sum(TOOL_COST.get(t, 0.0) * v for t, v in option.get("tools", {}).items())
            phased = 0.06 if option.get("phased") else 0.0
            return coverage * 100 - cost * 0.4 + phased
        return max(options, key=score)

    # ------------------------------------------------------------------ #
    # 履约结算
    # ------------------------------------------------------------------ #
    def _settle_executions(self) -> None:
        for execution in self.world.cooperation_executions:
            if execution.status != "active":
                continue
            if self.random.random() < execution.success_prob:
                execution.status = "fulfilled"
                self._fulfill(execution)
            else:
                execution.status = "failed"
                self._fail(execution)

    def _fulfill(self, execution: CooperationExecution) -> None:
        firm = self.world.firms[execution.firm_id]
        city = self.world.cities["city_qing"]
        record = self._record_of(execution.record_id)
        firm.knowledge = min(100.0, firm.knowledge + 8.0 + (record.policy_fit if record else 0.0) * 12.0)
        firm.profit = max(0.0, firm.profit + 30.0)
        city.employment += 60
        city.tax_revenue += 18.0
        city.objective_credibility = min(1.0, city.objective_credibility + 0.01)
        firm.perceived_credibility["city_qing"] = min(1.0, firm.perceived_credibility.get("city_qing", 0.55) + 0.05)
        self._event("milestone", f"{firm.name}合作履约成功", "问题解决、就业与税收提升", firm.id, severity="success")

    def _fail(self, execution: CooperationExecution) -> None:
        firm = self.world.firms[execution.firm_id]
        city = self.world.cities["city_qing"]
        record = self._record_of(execution.record_id)
        city.objective_credibility = max(0.2, city.objective_credibility - 0.02)
        firm.perceived_credibility["city_qing"] = max(0.05, firm.perceived_credibility.get("city_qing", 0.55) - 0.08)
        self._event(
            "regret", f"{firm.name}合作履约失败",
            f"支持 {record.gov_cost if record else 0:.1f} 万未达预期，匹配度 {record.policy_fit if record else 0:.2f}",
            firm.id, severity="danger",
        )

    def _record_of(self, record_id: str) -> NegotiationRecord | None:
        for record in self.world.negotiation_records:
            if record.id == record_id:
                return record
        return None

    # ------------------------------------------------------------------ #
    # 指标
    # ------------------------------------------------------------------ #
    def _record_metrics(self) -> None:
        records = self.world.negotiation_records
        accepted = [r for r in records if r.outcome == "accepted"]
        terminated = [r for r in records if r.outcome == "terminated"]
        closed = [e for e in self.world.cooperation_executions if e.status != "active"]
        fulfilled = [e for e in closed if e.status == "fulfilled"]
        regret = [r for r in records if r.outcome == "accepted" and r.policy_fit < 0.50]
        self.world.history.append(MetricsSnapshot(
            quarter=self.world.quarter, phase=Phase.NEGOTIATION,
            total_employment=sum(c.employment for c in self.world.cities.values()),
            total_tax_revenue=round(sum(c.tax_revenue for c in self.world.cities.values()), 3),
            total_committed_expenditure=round(
                sum(c.committed_expenditure for c in self.world.cities.values()), 3
            ),
            average_credibility=round(
                sum(c.objective_credibility for c in self.world.cities.values())
                / max(len(self.world.cities), 1), 4
            ),
            cluster_size=len(accepted), capacity=0.0,
            demand=round(self.world.market_demand, 3), utilization=0.0, market_price=1.0,
            agreements=len(accepted), terminated=len(terminated),
            avg_gap_final=round(sum(r.gap_final for r in records) / len(records), 4) if records else 0.0,
            avg_policy_fit=round(sum(r.policy_fit for r in accepted) / len(accepted), 4) if accepted else 0.0,
            fulfillment_rate=round(len(fulfilled) / len(closed), 4) if closed else 0.0,
            regret_rate=round(len(regret) / len(accepted), 4) if accepted else 0.0,
            total_gov_cost=round(sum(r.gov_cost for r in accepted), 2),
            total_ent_commitment=round(sum(r.ent_commitment for r in accepted), 4),
        ))

    # ------------------------------------------------------------------ #
    # 干预
    # ------------------------------------------------------------------ #
    def _apply_interventions(self) -> None:
        for item in self.world.interventions:
            if item.quarter != self.world.quarter:
                continue
            if item.kind == "language_reform":
                self.world.language_style = "plain"
                self._event("intervention", "政策语言改革", "政府改用直白表达并主动披露限制", severity="success")
            elif item.kind == "credibility_shock":
                city = self.world.cities.get(item.target, self.world.cities["city_qing"])
                city.objective_credibility = max(0.2, city.objective_credibility - item.value)
                for firm in self.world.firms.values():
                    firm.perceived_credibility["city_qing"] = max(
                        0.05, firm.perceived_credibility.get("city_qing", 0.55) - 0.10
                    )
                self._event("external_shock", "履约丑闻", "某企业反映补贴拖欠，政企信任下降", severity="danger")

    # ------------------------------------------------------------------ #
    # 基础设施：认知调用、记忆、追溯、事件（与主引擎一致）
    # ------------------------------------------------------------------ #
    def _cognitive_call(self, method: str, *args):
        try:
            return getattr(self.cognition, method)(*args)
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            if isinstance(self.cognition, DeterministicNegotiationCognition):
                raise
            failed_model = self.cognition.model_name or "DeepSeek"
            self._event(
                "model_fallback", "认知模型降级",
                f"{failed_model} 未返回可用结构化行动，本步改用确定性策略（{type(exc).__name__}）",
                severity="warning",
            )
            fallback = DeterministicNegotiationCognition()
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
        agent.last_reflection = self.cognition.reflect(agent, kind, content) if hasattr(self.cognition, "reflect") else content

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
