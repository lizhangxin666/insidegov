from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class Phase(StrEnum):
    RECRUITMENT = "recruitment"
    DELIVERY = "delivery"
    INDUSTRIALIZATION = "industrialization"


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
    events: list[Event]
    traces: list[DecisionTrace]
    history: list[MetricsSnapshot]
    interventions: list[Intervention]
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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
