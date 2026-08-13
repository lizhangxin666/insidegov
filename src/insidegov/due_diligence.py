from __future__ import annotations

import copy
import random
from dataclasses import asdict
from typing import Any

from .agents import CognitiveProvider, DeterministicCognition, build_cognition
from .models import (
    AgentActionAudit,
    DueDiligenceCase,
    EvidenceItem,
    ProjectRiskProfile,
    WorldState,
)

DIMENSIONS = ("financing", "technology", "market", "governance", "execution")
PROFILE_FIELDS = {
    "financing": "financing_capacity",
    "technology": "technology_maturity",
    "market": "market_validation",
    "governance": "governance_reliability",
    "execution": "execution_capacity",
}
DIMENSION_NAMES = {
    "financing": "资金闭合",
    "technology": "技术成熟",
    "market": "市场验证",
    "governance": "治理信用",
    "execution": "交付能力",
}
ACTION_SPECS: dict[str, dict[str, Any]] = {
    "request_financing_documents": {
        "dimension": "financing", "actor": "city_qing_finance",
        "source": "enterprise_material", "reliability": 0.34, "cost": 0.18, "days": 3,
    },
    "verify_funding_sources": {
        "dimension": "financing", "actor": "city_qing_finance",
        "source": "independent_verification", "reliability": 0.82, "cost": 0.72, "days": 8,
    },
    "technical_expert_review": {
        "dimension": "technology", "actor": "city_qing_technical",
        "source": "industry_expert", "reliability": 0.84, "cost": 0.86, "days": 9,
    },
    "request_technical_materials": {
        "dimension": "technology", "actor": "city_qing_technical",
        "source": "enterprise_material", "reliability": 0.38, "cost": 0.24, "days": 4,
    },
    "customer_contract_check": {
        "dimension": "market", "actor": "city_qing_investment",
        "source": "counterparty_check", "reliability": 0.78, "cost": 0.65, "days": 7,
    },
    "request_market_materials": {
        "dimension": "market", "actor": "city_qing_investment",
        "source": "enterprise_material", "reliability": 0.32, "cost": 0.18, "days": 3,
    },
    "credit_and_litigation_check": {
        "dimension": "governance", "actor": "city_qing_legal",
        "source": "public_registry", "reliability": 0.90, "cost": 0.42, "days": 4,
    },
    "request_governance_statement": {
        "dimension": "governance", "actor": "city_qing_legal",
        "source": "enterprise_material", "reliability": 0.36, "cost": 0.16, "days": 3,
    },
    "team_delivery_reference": {
        "dimension": "execution", "actor": "city_qing_technical",
        "source": "third_party_reference", "reliability": 0.76, "cost": 0.58, "days": 6,
    },
    "request_delivery_plan": {
        "dimension": "execution", "actor": "city_qing_investment",
        "source": "enterprise_material", "reliability": 0.35, "cost": 0.18, "days": 3,
    },
    "red_team_challenge": {
        "dimension": None, "actor": "city_qing_legal",
        "source": "cross_department_red_team", "reliability": 0.88, "cost": 0.95, "days": 7,
    },
}

PROGRAMS = {
    "light_screen": {
        "max_rounds": 2,
        "actions": [
            "request_financing_documents", "request_technical_materials",
            "request_market_materials", "request_governance_statement", "request_delivery_plan",
        ],
        "min_rounds": 1,
    },
    "clarification_only": {
        "max_rounds": 4,
        "actions": [
            "request_financing_documents", "request_technical_materials",
            "request_market_materials", "request_governance_statement", "request_delivery_plan",
        ],
        "min_rounds": 2,
    },
    "independent_verification": {
        "max_rounds": 5,
        "actions": [
            "verify_funding_sources", "technical_expert_review", "customer_contract_check",
            "credit_and_litigation_check", "team_delivery_reference",
        ],
        "min_rounds": 3,
    },
    "red_team": {
        "max_rounds": 6,
        "actions": [
            "verify_funding_sources", "technical_expert_review", "customer_contract_check",
            "credit_and_litigation_check", "team_delivery_reference", "red_team_challenge",
        ],
        "min_rounds": 4,
    },
    "adaptive_staged": {
        "max_rounds": 5,
        "actions": list(ACTION_SPECS),
        "min_rounds": 2,
    },
}


def protocol_due_diligence_program(protocol: str) -> str:
    if protocol.upper().startswith("M"):
        from .negotiation_agents import conversation_mechanism_traits
        traits = conversation_mechanism_traits(protocol)
        if traits.get("pre_commitment_consultation"):
            return "independent_verification"
        if traits.get("mutual_confirmation"):
            return "adaptive_staged"
        return "light_screen"
    return {
        "free": "light_screen",
        "policy_match": "light_screen",
        "clarify_first": "adaptive_staged",
        "paraphrase_confirm": "clarification_only",
        "constraints_first": "independent_verification",
        "multi_option": "light_screen",
        "phased_commitment": "adaptive_staged",
    }.get(protocol, "light_screen")


class DueDiligenceEngine:
    """Evidence-gated project screening without exposing hidden quality labels."""

    def __init__(
        self,
        world: WorldState,
        cognition: CognitiveProvider | None = None,
    ) -> None:
        self.world = world
        self.cognition = cognition or build_cognition(world.policy_mode, world.model_name)

    def assess(
        self,
        firm_id: str,
        program: str | None = None,
        threshold: float | None = None,
    ) -> DueDiligenceCase:
        existing = next((item for item in self.world.due_diligence_cases if item.firm_id == firm_id), None)
        if existing:
            return existing
        selected_program = program or self.world.due_diligence_program
        if selected_program == "protocol_linked":
            selected_program = protocol_due_diligence_program(self.world.negotiation_protocol)
        if selected_program not in PROGRAMS:
            raise ValueError(f"unknown due diligence program: {selected_program}")
        profile = self.world.project_risk_profiles[firm_id]
        firm = self.world.firms[firm_id]
        stated = self.world.stated_needs[firm_id]
        trust = firm.perceived_credibility.get("city_qing", 0.5)
        prior = min(0.78, max(0.12, 0.24 + stated.exaggeration * 0.34 + (1 - trust) * 0.10))
        risk = {
            "financing": min(0.9, prior + stated.exaggeration * 0.10),
            "technology": min(0.9, prior + (0.10 if stated.category == "expansion" else 0.0)),
            "market": prior,
            "governance": max(0.08, prior - 0.05),
            "execution": prior,
        }
        uncertainty_by_dimension = {dimension: 0.78 for dimension in DIMENSIONS}
        config = PROGRAMS[selected_program]
        evidence: list[EvidenceItem] = []
        turns: list[dict[str, Any]] = []
        available_actions = list(config["actions"])
        for round_index in range(1, int(config["max_rounds"]) + 1):
            candidates = self._rank_actions(
                available_actions, risk, uncertainty_by_dimension, evidence,
            )[:3]
            if round_index > int(config["min_rounds"]):
                candidates.append("stop_and_decide")
            coordinator = self.world.agents["city_qing_investment"]
            observation = self._observation(
                firm_id, selected_program, round_index, risk,
                uncertainty_by_dimension, evidence,
            )
            observation["observable_pressure_signals"] = [
                event.detail for event in self.world.events
                if event.kind == "compiled_pressure_event" and event.target_id == firm_id
            ]
            action_id, rationale, provider, fallback, suggestion = self._choose(
                coordinator, candidates, observation,
            )
            if action_id == "stop_and_decide":
                turns.append({
                    "round": round_index, "actor_id": coordinator.id,
                    "action_id": action_id, "rationale": rationale,
                })
                break
            spec = ACTION_SPECS[action_id]
            reviewer = self.world.agents[spec["actor"]]
            dimension = spec["dimension"] or max(
                DIMENSIONS, key=lambda item: risk[item] * uncertainty_by_dimension[item]
            )
            item = self._generate_evidence(
                profile, firm_id, action_id, dimension, reviewer.id, round_index,
            )
            evidence.append(item)
            self._update_belief(risk, uncertainty_by_dimension, item)
            turns.append({
                "round": round_index, "actor_id": reviewer.id,
                "action_id": action_id, "rationale": rationale,
                "evidence_id": item.id, "source_type": item.source_type,
            })
            self._audit(
                reviewer, observation, suggestion,
                {
                    "action_id": action_id, "dimension": dimension,
                    "evidence_id": item.id, "observed_quality": item.observed_quality,
                    "source_type": item.source_type,
                },
                {
                    "hidden_profile_access": False,
                    "evidence_reliability": item.reliability,
                    "belief_after": round(risk[dimension], 3),
                },
                rationale, provider, fallback,
            )
            if action_id in available_actions:
                available_actions.remove(action_id)
            if not available_actions:
                break
        estimated = self._failure_probability(risk, evidence)
        uncertainty = sum(uncertainty_by_dimension.values()) / len(DIMENSIONS)
        decision_threshold = threshold if threshold is not None else self.world.due_diligence_threshold
        decision, rationale, decision_turn = self._decide(
            firm_id, selected_program, estimated, uncertainty, risk,
            evidence, decision_threshold,
        )
        turns.append(decision_turn)
        actual_probability = self.actual_failure_probability(profile)
        outcome_rng = random.Random(f"insidegov:due-diligence:{self.world.seed}:{firm_id}:outcome")
        actual_outcome = "failed" if outcome_rng.random() < actual_probability else "succeeded"
        diligence_cost = round(sum(item.cost for item in evidence), 3)
        elapsed_days = sum(item.elapsed_days for item in evidence)
        avoided, fiscal_loss, missed = self._settle_counterfactual_value(
            profile, decision, actual_outcome,
        )
        case = DueDiligenceCase(
            id=f"dd-{len(self.world.due_diligence_cases)+1:04d}",
            firm_id=firm_id,
            program=selected_program,
            prior_failure_probability=round(prior, 4),
            estimated_failure_probability=round(estimated, 4),
            uncertainty=round(uncertainty, 4),
            decision=decision,
            rationale=rationale,
            rounds=len(evidence),
            diligence_cost=diligence_cost,
            elapsed_days=elapsed_days,
            evidence=evidence,
            risk_by_dimension={key: round(value, 4) for key, value in risk.items()},
            agent_turns=turns,
            actual_failure_probability=round(actual_probability, 4),
            actual_outcome=actual_outcome,
            avoided_fiscal_loss=avoided,
            realized_fiscal_loss=fiscal_loss,
            missed_opportunity=missed,
        )
        self.world.due_diligence_cases.append(case)
        return case

    def run_all(self, program: str | None = None, threshold: float | None = None) -> list[DueDiligenceCase]:
        return [self.assess(firm_id, program, threshold) for firm_id in self.world.firms]

    def _rank_actions(
        self,
        actions: list[str],
        risk: dict[str, float],
        uncertainty: dict[str, float],
        evidence: list[EvidenceItem],
    ) -> list[str]:
        checked = {(item.action_id, item.dimension) for item in evidence}

        def value(action_id: str) -> float:
            spec = ACTION_SPECS[action_id]
            if action_id == "red_team_challenge":
                dimension = max(DIMENSIONS, key=lambda key: risk[key] * uncertainty[key])
            else:
                dimension = spec["dimension"]
            novelty = 0.0 if (action_id, dimension) in checked else 1.0
            information_gain = float(spec["reliability"]) * uncertainty[dimension]
            expected_loss = risk[dimension] * 0.62 + 0.18
            return novelty * information_gain * expected_loss - float(spec["cost"]) * 0.025

        return sorted(actions, key=value, reverse=True)

    @staticmethod
    def _observation(
        firm_id: str,
        program: str,
        round_index: int,
        risk: dict[str, float],
        uncertainty: dict[str, float],
        evidence: list[EvidenceItem],
    ) -> dict[str, Any]:
        return {
            "firm_id": firm_id,
            "program": program,
            "round": round_index,
            "risk_by_dimension": {key: round(value, 3) for key, value in risk.items()},
            "uncertainty_by_dimension": {
                key: round(value, 3) for key, value in uncertainty.items()
            },
            "evidence_seen": [
                {
                    "dimension": item.dimension, "source_type": item.source_type,
                    "observed_quality": item.observed_quality,
                    "reliability": item.reliability, "conflict": item.conflict,
                }
                for item in evidence
            ],
            "hidden_quality_label_available": False,
        }

    def _choose(self, agent, candidates: list[str], observation: dict[str, Any]):
        memories = [memory.content for memory in agent.memories[-3:]]
        try:
            choice = self.cognition.choose_organization_action(
                agent, candidates, observation, memories,
            )
            action_id = choice.action_id if choice.action_id in candidates else candidates[0]
            return (
                action_id, choice.rationale,
                self.cognition.model_name or self.cognition.mode, False,
                choice.model_dump() if hasattr(choice, "model_dump") else asdict(choice),
            )
        except Exception as exc:  # noqa: BLE001 - retain autonomous run with auditable fallback
            fallback = DeterministicCognition()
            choice = fallback.choose_organization_action(agent, candidates, observation, memories)
            return (
                choice.action_id, choice.rationale, "deterministic-fallback", True,
                {"action_id": choice.action_id, "rationale": choice.rationale,
                 "error": f"{type(exc).__name__}: {str(exc)[:240]}"},
            )

    def _generate_evidence(
        self,
        profile: ProjectRiskProfile,
        firm_id: str,
        action_id: str,
        dimension: str,
        reviewer_id: str,
        round_index: int,
    ) -> EvidenceItem:
        spec = ACTION_SPECS[action_id]
        actual_quality = float(getattr(profile, PROFILE_FIELDS[dimension]))
        rng = random.Random(
            f"insidegov:evidence:{self.world.seed}:{firm_id}:{action_id}:{dimension}"
        )
        claim = min(1.0, max(0.0,
            actual_quality
            + (1 - actual_quality) * (1 - profile.candor) * 0.78
            + rng.uniform(-0.035, 0.035)
        ))
        reliability = float(spec["reliability"])
        if spec["source"] == "enterprise_material":
            observed = claim + rng.uniform(-0.045, 0.045)
        else:
            observed = actual_quality + rng.uniform(
                -(1 - reliability) * 0.22, (1 - reliability) * 0.22,
            )
        observed = min(1.0, max(0.0, observed))
        conflict = abs(claim - observed)
        return EvidenceItem(
            id=f"evidence-{len(self.world.due_diligence_cases)+1:03d}-{round_index:02d}",
            firm_id=firm_id,
            round=round_index,
            requested_by=reviewer_id,
            action_id=action_id,
            dimension=dimension,
            source_type=str(spec["source"]),
            observed_quality=round(observed, 4),
            reliability=round(reliability, 3),
            claim_value=round(claim, 4),
            conflict=round(conflict, 4),
            cost=float(spec["cost"]),
            elapsed_days=int(spec["days"]),
            summary=(
                f"{DIMENSION_NAMES[dimension]}证据：质量 {observed:.2f}，"
                f"来源可靠度 {reliability:.2f}，与企业主张差异 {conflict:.2f}"
            ),
        )

    @staticmethod
    def _update_belief(
        risk: dict[str, float], uncertainty: dict[str, float], evidence: EvidenceItem,
    ) -> None:
        dimension = evidence.dimension
        weight = evidence.reliability * (0.62 + uncertainty[dimension] * 0.28)
        evidence_risk = 1 - evidence.observed_quality
        risk[dimension] = min(0.98, max(0.02,
            risk[dimension] * (1 - weight) + evidence_risk * weight
        ))
        if evidence.conflict > 0.20:
            risk["governance"] = min(0.98, risk["governance"] + evidence.conflict * 0.42)
        uncertainty[dimension] = max(0.06,
            uncertainty[dimension] * (1 - evidence.reliability * 0.62)
        )

    @staticmethod
    def _failure_probability(
        risk: dict[str, float], evidence: list[EvidenceItem],
    ) -> float:
        weighted = (
            risk["financing"] * 0.24 + risk["technology"] * 0.22
            + risk["market"] * 0.20 + risk["governance"] * 0.14
            + risk["execution"] * 0.20
        )
        conflict = max((item.conflict * item.reliability for item in evidence), default=0.0)
        return min(0.95, max(0.03, weighted + conflict * 0.22))

    def _decide(
        self,
        firm_id: str,
        program: str,
        estimated: float,
        uncertainty: float,
        risk: dict[str, float],
        evidence: list[EvidenceItem],
        threshold: float,
    ) -> tuple[str, str, dict[str, Any]]:
        legal_red_flag = any(
            item.dimension == "governance" and item.reliability >= 0.75
            and item.observed_quality < 0.18
            for item in evidence
        )
        if legal_red_flag:
            candidates = ["reject", "defer"]
        elif estimated >= threshold:
            candidates = (
                ["conditional_pilot", "reject", "defer"]
                if program == "adaptive_staged" and uncertainty >= 0.26
                else ["reject", "conditional_pilot", "defer"]
            )
        elif uncertainty >= 0.50:
            if program == "adaptive_staged":
                candidates = ["conditional_pilot", "defer", "approve"]
            elif program in {"light_screen", "clarification_only"}:
                candidates = ["approve", "defer", "reject"]
            else:
                candidates = ["defer", "approve", "reject"]
        elif estimated >= threshold * 0.72:
            candidates = ["conditional_pilot", "approve", "defer"]
        else:
            candidates = ["approve", "conditional_pilot", "defer"]
        leader = self.world.agents["city_qing_leader"]
        observation = {
            "firm_id": firm_id,
            "estimated_failure_probability": round(estimated, 4),
            "uncertainty": round(uncertainty, 4),
            "risk_by_dimension": {key: round(value, 3) for key, value in risk.items()},
            "decision_threshold": threshold,
            "evidence_count": len(evidence),
            "legal_red_flag": legal_red_flag,
            "hidden_quality_label_available": False,
        }
        decision, rationale, provider, fallback, suggestion = self._choose(
            leader, candidates, observation,
        )
        if legal_red_flag and decision != "reject":
            rule_adjustment = {"before": decision, "after": "reject", "reason": "verified_legal_red_flag"}
            decision = "reject"
        else:
            rule_adjustment = {"before": decision, "after": decision, "reason": "authorized"}
        self._audit(
            leader, observation, suggestion,
            {"decision": decision, "estimated_failure_probability": round(estimated, 4)},
            rule_adjustment, rationale, provider, fallback,
        )
        return decision, rationale, {
            "round": len(evidence) + 1,
            "actor_id": leader.id,
            "action_id": decision,
            "rationale": rationale,
            "estimated_failure_probability": round(estimated, 4),
            "uncertainty": round(uncertainty, 4),
        }

    def _audit(
        self, agent, observation: dict, suggestion: dict, executed: dict,
        adjustment: dict, rationale: str, provider: str, fallback: bool,
    ) -> None:
        self.world.action_audits.append(AgentActionAudit(
            id=f"audit-{len(self.world.action_audits)+1:05d}",
            quarter=self.world.quarter,
            agent_id=agent.id,
            action_type="evidence_gated_due_diligence",
            observation=copy.deepcopy(observation),
            private_context_used=copy.deepcopy(agent.private_facts),
            retrieved_memories=[memory.content for memory in agent.memories[-3:]],
            llm_suggestion=copy.deepcopy(suggestion),
            rule_adjustment=copy.deepcopy(adjustment),
            executed_action=copy.deepcopy(executed),
            rationale=rationale,
            reflection=(
                "本轮只使用可见主张与核验证据；后续根据信息价值决定继续调查或停止。"
            ),
            provider=provider,
            fallback=fallback,
            outcome="executed",
        ))

    @staticmethod
    def actual_failure_probability(profile: ProjectRiskProfile) -> float:
        latent_risk = (
            (1 - profile.financing_capacity) * 0.24
            + (1 - profile.technology_maturity) * 0.22
            + (1 - profile.market_validation) * 0.20
            + (1 - profile.governance_reliability) * 0.14
            + (1 - profile.execution_capacity) * 0.20
        )
        return min(0.92, max(0.04, (latent_risk - 0.12) * 1.32))

    @staticmethod
    def _settle_counterfactual_value(
        profile: ProjectRiskProfile, decision: str, outcome: str,
    ) -> tuple[float, float, float]:
        full_loss = profile.requested_support
        opportunity = profile.strategic_value * profile.expected_jobs / 100
        if decision == "reject":
            return (
                round(full_loss, 3) if outcome == "failed" else 0.0,
                0.0,
                round(opportunity, 3) if outcome == "succeeded" else 0.0,
            )
        if decision == "defer":
            return (
                round(full_loss * 0.85, 3) if outcome == "failed" else 0.0,
                round(full_loss * 0.05, 3),
                round(opportunity * 0.35, 3) if outcome == "succeeded" else 0.0,
            )
        if decision == "conditional_pilot":
            return (
                round(full_loss * 0.78, 3) if outcome == "failed" else 0.0,
                round(full_loss * 0.22, 3) if outcome == "failed" else 0.0,
                round(opportunity * 0.08, 3) if outcome == "succeeded" else 0.0,
            )
        return (
            0.0,
            round(full_loss, 3) if outcome == "failed" else 0.0,
            0.0,
        )


def due_diligence_metrics(cases: list[DueDiligenceCase]) -> dict[str, float | int]:
    flagged = {"reject", "conditional_pilot"}
    tp = sum(item.actual_outcome == "failed" and item.decision in flagged for item in cases)
    fn = sum(item.actual_outcome == "failed" and item.decision not in flagged for item in cases)
    fp = sum(item.actual_outcome == "succeeded" and item.decision in flagged for item in cases)
    tn = sum(item.actual_outcome == "succeeded" and item.decision not in flagged for item in cases)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    brier = sum(
        (item.estimated_failure_probability - (1.0 if item.actual_outcome == "failed" else 0.0)) ** 2
        for item in cases
    ) / max(len(cases), 1)
    return {
        "n": len(cases), "true_positive": tp, "false_negative": fn,
        "false_positive": fp, "true_negative": tn,
        "precision": round(precision, 4), "recall": round(recall, 4),
        "specificity": round(specificity, 4), "brier_score": round(brier, 4),
        "avg_rounds": round(sum(item.rounds for item in cases) / max(len(cases), 1), 3),
        "avg_elapsed_days": round(sum(item.elapsed_days for item in cases) / max(len(cases), 1), 3),
        "diligence_cost": round(sum(item.diligence_cost for item in cases), 3),
        "avoided_fiscal_loss": round(sum(item.avoided_fiscal_loss for item in cases), 3),
        "realized_fiscal_loss": round(sum(item.realized_fiscal_loss for item in cases), 3),
        "missed_opportunity": round(sum(item.missed_opportunity for item in cases), 3),
    }
