from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class Phase(StrEnum):
    RECRUITMENT = "recruitment"
    DELIVERY = "delivery"
    INDUSTRIALIZATION = "industrialization"
    TALENT = "talent"
    NEGOTIATION = "negotiation"


class FirmType(StrEnum):
    ANCHOR = "anchor"
    SUPPLIER = "supplier"
    OPPORTUNISTIC = "opportunistic"
    TECHNOLOGY = "technology"


class AgentRole(StrEnum):
    CITY_LEADER = "city_leader"
    INVESTMENT = "investment"
    FINANCE = "finance"
    ENTERPRISE = "enterprise"
    TALENT = "talent"
    UNIVERSITY = "university"
    PLATFORM = "platform"


class TalentType(StrEnum):
    JUNIOR_FACULTY = "junior_faculty"
    SENIOR_PROFESSOR = "senior_professor"
    INDUSTRY_EXPERT = "industry_expert"


class ExpressionMode(StrEnum):
    FORMAL = "formal"
    PLAIN = "plain"


class TalentConcern(StrEnum):
    IDENTITY = "identity"
    ACADEMIC = "academic"
    COMPENSATION = "compensation"
    RISK = "risk"


class ContractStatus(StrEnum):
    ACTIVE = "active"
    FULFILLED = "fulfilled"
    BREACHED = "breached"
    TERMINATED = "terminated"


class PromiseStatus(StrEnum):
    PENDING = "pending"
    FULFILLED = "fulfilled"
    DELAYED = "delayed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class PaymentTranche:
    item: str
    amount: float
    due_offset: int
    condition: str


@dataclass(slots=True)
class PolicyPackage:
    city_id: str
    subsidy: float
    equity: float
    land_discount: float
    credit_support: float
    approval_speed: float
    talent_support: float
    conditions: dict[str, float] = field(default_factory=dict)
    payment_schedule: list[PaymentTranche] = field(default_factory=list)

    @property
    def fiscal_cost(self) -> float:
        return self.subsidy + self.equity + self.credit_support * 0.08


@dataclass(slots=True)
class DepartmentState:
    id: str
    name: str
    goal: str
    risk_tolerance: float
    influence: float


@dataclass(slots=True)
class CityState:
    id: str
    name: str
    fiscal_budget: float
    available_budget: float
    committed_expenditure: float
    debt: float
    industrial_land: float
    talent_pool: float
    supply_chain: float
    administrative_capacity: float
    environmental_capacity: float
    objective_credibility: float
    leadership_term_remaining: int
    gdp_weight: float
    employment_weight: float
    risk_weight: float
    departments: list[DepartmentState]
    tax_revenue: float = 0.0
    employment: int = 0
    industrial_output: float = 0.0
    landed_firms: list[str] = field(default_factory=list)
    active_offer: PolicyPackage | None = None

    @property
    def fiscal_pressure(self) -> float:
        obligations = self.committed_expenditure + self.debt * 0.04
        return min(1.0, obligations / max(self.available_budget + self.tax_revenue, 1.0))


@dataclass(slots=True)
class FirmState:
    id: str
    name: str
    firm_type: FirmType
    investment_capacity: float
    cash: float
    land_need: float
    jobs_capacity: int
    production_capacity: float
    technology: float
    policy_sensitivity: float
    cluster_sensitivity: float
    credibility_sensitivity: float
    risk_tolerance: float
    private_intent: float
    minimum_utility: float
    supplier_of: str | None = None
    location: str | None = None
    project_progress: float = 0.0
    operating: bool = False
    utilization: float = 0.0
    profit: float = 0.0
    perceived_credibility: dict[str, float] = field(default_factory=dict)
    observed_offers: dict[str, PolicyPackage] = field(default_factory=dict)
    tech_demand: TechDemand | None = None
    knowledge: float = 0.0


@dataclass(slots=True)
class Promise:
    id: str
    city_id: str
    firm_id: str
    item: str
    amount: float
    due_quarter: int
    condition: str
    status: PromiseStatus = PromiseStatus.PENDING
    paid_amount: float = 0.0
    delayed_quarters: int = 0


@dataclass(slots=True)
class DecisionTrace:
    id: str
    quarter: int
    actor_id: str
    action: str
    target_id: str | None
    observations: list[str]
    goals: list[str]
    evidence: list[str]
    constraints: list[str]
    alternatives: list[str]
    expected_effects: dict[str, float]
    outcome: str


@dataclass(slots=True)
class AgentActionAudit:
    """Auditable link from agent cognition to deterministic execution."""

    id: str
    quarter: int
    agent_id: str
    action_type: str
    observation: dict[str, Any]
    private_context_used: dict[str, Any]
    retrieved_memories: list[str]
    llm_suggestion: dict[str, Any]
    rule_adjustment: dict[str, Any]
    executed_action: dict[str, Any]
    rationale: str
    reflection: str
    provider: str
    fallback: bool = False
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    outcome: str = "proposed"


@dataclass(slots=True)
class Event:
    quarter: int
    kind: str
    title: str
    detail: str
    actor_id: str | None = None
    target_id: str | None = None
    severity: str = "info"


@dataclass(slots=True)
class Intervention:
    quarter: int
    kind: str
    target: str
    value: float
    operation: str = "set"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class InterventionChange:
    target: str
    operation: str
    value: float
    description: str


@dataclass(slots=True)
class InterventionPlan:
    id: str
    source_text: str
    effective_quarter: int
    changes: list[InterventionChange]
    status: str = "draft"
    permanent: bool = True
    assumptions: list[str] = field(default_factory=list)
    promise_priority: str | None = None


@dataclass(slots=True)
class MemoryRecord:
    id: str
    quarter: int
    kind: str
    content: str
    importance: float
    valence: float = 0.0
    source_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AgentState:
    id: str
    name: str
    role: AgentRole
    owner_id: str
    goals: list[str]
    private_facts: dict[str, float | str | bool]
    traits: dict[str, float]
    memories: list[MemoryRecord] = field(default_factory=list)
    last_reflection: str = "尚无历史行动"


@dataclass(slots=True)
class NegotiationRound:
    id: str
    quarter: int
    city_id: str
    firm_id: str
    proposal_cost: float
    finance_limit: float
    finance_approved: bool
    concerns: list[str]
    resolution: str
    final_cost: float
    policy_mode: str
    proposer_id: str = ""
    reviewer_id: str = ""
    coordinator_id: str = ""
    proposal_tools: dict[str, float] = field(default_factory=dict)
    finance_tool_limits: dict[str, float] = field(default_factory=dict)
    final_tools: dict[str, float] = field(default_factory=dict)
    payment_schedule: list[PaymentTranche] = field(default_factory=list)
    turns: list[dict[str, str | float | bool]] = field(default_factory=list)


@dataclass(slots=True)
class ExternalNegotiationRound:
    """Enterprise-facing round wrapped around one government's internal meeting."""

    id: str
    quarter: int
    city_id: str
    firm_id: str
    protocol: str
    stated_need: str
    government_questions: list[str]
    disclosed_components: dict[str, float]
    belief_before: dict[str, float]
    belief_after: dict[str, float]
    belief_confidence: float
    internal_negotiation_id: str
    government_offer: dict[str, float]
    enterprise_response: str
    counter_terms: dict[str, float]
    enterprise_rationale: str
    utility: float
    minimum_utility: float
    outcome: str


@dataclass(slots=True)
class MetricsSnapshot:
    quarter: int
    phase: Phase
    total_employment: int
    total_tax_revenue: float
    total_committed_expenditure: float
    average_credibility: float
    cluster_size: int
    capacity: float
    demand: float
    utilization: float
    market_price: float
    talent_hired: int = 0
    tech_progress: float = 0.0
    match_rate: float = 0.0
    avg_understanding: float = 0.0
    avg_trust: float = 0.0
    # 协商机制实验室指标
    agreements: int = 0
    terminated: int = 0
    avg_gap_final: float = 0.0
    avg_policy_fit: float = 0.0
    fulfillment_rate: float = 0.0
    regret_rate: float = 0.0
    total_gov_cost: float = 0.0
    total_ent_commitment: float = 0.0


@dataclass(slots=True)
class WorldState:
    id: str
    name: str
    seed: int
    quarter: int
    phase: Phase
    cities: dict[str, CityState]
    firms: dict[str, FirmState]
    agents: dict[str, AgentState]
    promises: list[Promise]
    negotiations: list[NegotiationRound]
    external_negotiations: list[ExternalNegotiationRound]
    events: list[Event]
    traces: list[DecisionTrace]
    action_audits: list[AgentActionAudit]
    history: list[MetricsSnapshot]
    interventions: list[Intervention]
    intervention_plans: list[InterventionPlan] = field(default_factory=list)
    random_state: Any | None = None
    branched_from_quarter: int | None = None
    parameter_provenance: dict[str, dict[str, Any]] = field(default_factory=dict)
    market_demand: float = 100.0
    demand_multiplier: float = 1.0
    market_price: float = 1.0
    selected_city_id: str | None = None
    parent_id: str | None = None
    policy_mode: str = "deterministic"
    model_name: str | None = None
    mechanisms: dict[str, bool] = field(default_factory=lambda: {
        "private_information": True,
        "internal_governance": True,
        "credibility_diffusion": True,
        "supplier_spillover": True,
    })
    talents: dict[str, TalentState] = field(default_factory=dict)
    universities: dict[str, UniversityState] = field(default_factory=dict)
    platform: PlatformState | None = None
    talent_contracts: list[TalentContract] = field(default_factory=list)
    talent_negotiations: list[TalentNegotiation] = field(default_factory=list)
    expression_mode: str = "plain"
    interpreter_enabled: bool = False
    # 协商机制实验室
    negotiation_protocol: str = "free"
    language_style: str = "plain"
    latent_needs: dict[str, LatentNeed] = field(default_factory=dict)
    stated_needs: dict[str, StatedNeed] = field(default_factory=dict)
    gov_beliefs: dict[str, GovBelief] = field(default_factory=dict)
    ent_beliefs: dict[str, EntBelief] = field(default_factory=dict)
    negotiation_records: list[NegotiationRecord] = field(default_factory=list)
    cooperation_executions: list[CooperationExecution] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TechDemand:
    """结构化技术需求:企业把模糊诉求翻译成能力向量。"""

    description: str
    vector: dict[str, float]
    budget: float
    form: str
    clarity: float


@dataclass(slots=True)
class UniversityState:
    id: str
    name: str
    strength: dict[str, float]
    assessment_pressure: float
    industry_support: float
    talent_ids: list[str] = field(default_factory=list)
    lab_funding: float = 0.0


@dataclass(slots=True)
class PlatformState:
    id: str
    name: str
    translation_power: float
    information_coverage: float
    match_fee: float


@dataclass(slots=True)
class TalentState:
    id: str
    name: str
    talent_type: TalentType
    university_id: str | None
    capability: dict[str, float]
    concerns: dict[str, float]
    interpretation_skill: float
    academic_value: float
    participation: float
    status: str = "available"
    employer_id: str | None = None
    contract_id: str | None = None
    trust: dict[str, float] = field(default_factory=dict)
    opportunity_cost: float = 60.0
    withdrawn_quarters: int = 0


@dataclass(slots=True)
class TalentOffer:
    firm_id: str
    city_id: str
    annual_salary: float
    tools: dict[str, float] = field(default_factory=dict)
    language_mode: str = "plain"
    explanation: str = ""
    total_cost: float = 0.0


@dataclass(slots=True)
class TalentContract:
    id: str
    quarter: int
    talent_id: str
    firm_id: str
    city_id: str
    university_id: str | None
    offer: TalentOffer
    status: str = "active"
    progress: float = 0.0
    paid: float = 0.0
    follow_through: float = 0.5
    due_quarter: int = 0


@dataclass(slots=True)
class TalentNegotiation:
    id: str
    quarter: int
    firm_id: str
    talent_id: str
    city_id: str
    rounds: int
    outcome: str
    understanding_final: float
    trust_after: float
    applied_tools: dict[str, float]
    language_mode: str
    interpreter_used: bool
    turns: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------- #
# 协商机制实验室：理解差距 / 政策匹配 / 双边协商数据契约
# ---------------------------------------------------------------------- #


class NegotiationProtocol(StrEnum):
    FREE = "free"
    POLICY_MATCH = "policy_match"
    CLARIFY_FIRST = "clarify_first"
    PARAPHRASE_CONFIRM = "paraphrase_confirm"
    CONSTRAINTS_FIRST = "constraints_first"
    MULTI_OPTION = "multi_option"
    PHASED_COMMITMENT = "phased_commitment"


@dataclass(slots=True)
class LatentNeed:
    firm_id: str
    problem: str
    preferred_mode: str
    deadline: int
    budget: float
    constraints: list[str]
    commitment: float
    required_tools: dict[str, float]
    truth: dict[str, float]
    unfeasible: bool = False

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class StatedNeed:
    firm_id: str
    text: str
    category: str
    clarity: float
    disclosed: dict[str, float]
    exaggeration: float = 0.0


@dataclass(slots=True)
class GovBelief:
    firm_id: str
    components: dict[str, float] = field(default_factory=dict)
    confidence: float = 0.0
    perceived_mode: str = ""


@dataclass(slots=True)
class EntBelief:
    firm_id: str
    trust: float = 0.5
    perceived_constraints: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class NegotiationRecord:
    id: str
    quarter: int
    firm_id: str
    protocol: str
    rounds: int
    outcome: str
    fail_reason: str | None
    gap_initial: float
    gap_final: float
    policy_fit: float
    understanding_final: float
    trust_after: float
    semantic_alignment: float
    incentive_alignment: float
    gov_cost: float
    ent_commitment: float
    language_style: str
    clarification_asked: int = 0
    paraphrases: int = 0
    turns: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class CooperationExecution:
    id: str
    record_id: str
    firm_id: str
    quarter: int
    success_prob: float
    status: str = "active"
