from __future__ import annotations

from .models import (
    AgentActionAudit,
    AgentRole,
    AgentState,
    CityState,
    CooperationExecution,
    DecisionTrace,
    DepartmentState,
    DueDiligenceCase,
    EntBelief,
    Event,
    EvidenceItem,
    ExternalNegotiationRound,
    FirmState,
    FirmType,
    GovBelief,
    ImitationDecision,
    Intervention,
    InterventionChange,
    InterventionPlan,
    InvestmentFundState,
    LatentNeed,
    MemoryRecord,
    MetricsSnapshot,
    NegotiationRecord,
    NegotiationRound,
    OpenActionProposal,
    OpportunityWindow,
    OrganizationActionRecord,
    OrganizationLearningState,
    OrganizationPlan,
    OrganizationPlanNode,
    OrganizationProcessState,
    PaymentTranche,
    Phase,
    PlanStrategyOption,
    PlatformState,
    PolicyPackage,
    ProjectRiskProfile,
    Promise,
    PromiseStatus,
    RescueDecision,
    StatedNeed,
    TalentContract,
    TalentNegotiation,
    TalentOffer,
    TalentState,
    TalentType,
    TechDemand,
    UniversityState,
    WorldState,
)


def _offer(data: dict | None) -> PolicyPackage | None:
    if not data:
        return None
    item = dict(data)
    item["payment_schedule"] = [PaymentTranche(**row) for row in item.get("payment_schedule", [])]
    return PolicyPackage(**item)


def world_from_dict(data: dict) -> WorldState:
    cities = {}
    for city_id, raw in data["cities"].items():
        item = dict(raw)
        item["departments"] = [DepartmentState(**d) for d in item["departments"]]
        item["active_offer"] = _offer(item.get("active_offer"))
        cities[city_id] = CityState(**item)
    firms = {}
    for firm_id, raw in data["firms"].items():
        item = dict(raw)
        item["firm_type"] = FirmType(item["firm_type"])
        item["observed_offers"] = {key: _offer(value) for key, value in item["observed_offers"].items()}
        if item.get("tech_demand"):
            item["tech_demand"] = TechDemand(**item["tech_demand"])
        firms[firm_id] = FirmState(**item)
    agents = {}
    for agent_id, raw in data.get("agents", {}).items():
        item = dict(raw)
        item["role"] = AgentRole(item["role"])
        item["memories"] = [MemoryRecord(**m) for m in item.get("memories", [])]
        agents[agent_id] = AgentState(**item)
    for city in cities.values():
        investment_id = f"{city.id}_investment"
        if investment_id not in agents:
            agents[investment_id] = AgentState(
                id=investment_id, name=f"{city.name}招商局", role=AgentRole.INVESTMENT,
                owner_id=city.id,
                goals=["争取龙头项目签约", "提高政策包吸引力", "完成招商任务"],
                private_facts={"signing_target": 1.0, "cash_preference": 0.6, "competitive_intensity": 0.7},
                traits={"risk_aversion": 0.24, "short_termism": 0.78, "trust_sensitivity": 0.42},
            )
        legal_id = f"{city.id}_legal"
        if legal_id not in agents:
            agents[legal_id] = AgentState(
                id=legal_id, name=f"{city.name}司法审查机构", role=AgentRole.LEGAL,
                owner_id=city.id, goals=["保证权限合法", "识别程序瑕疵"],
                private_facts={"review_capacity": city.administrative_capacity / 100},
                traits={"risk_aversion": 0.72, "short_termism": 0.18, "trust_sensitivity": 0.55},
            )
        park_id = f"{city.id}_park"
        if park_id not in agents:
            agents[park_id] = AgentState(
                id=park_id, name=f"{city.name}产业园区", role=AgentRole.PARK,
                owner_id=city.id, goals=["形成产业集聚", "协调项目执行"],
                private_facts={"land_pressure": max(0.0, 1 - city.industrial_land / 800)},
                traits={"risk_aversion": 0.38, "short_termism": 0.58, "trust_sensitivity": 0.66},
            )
    return WorldState(
        id=data["id"], name=data["name"], seed=data["seed"], quarter=data["quarter"],
        phase=Phase(data["phase"]), cities=cities, firms=firms, agents=agents,
        promises=[Promise(**{**p, "status": PromiseStatus(p["status"])}) for p in data.get("promises", [])],
        negotiations=[NegotiationRound(**{
            **n,
            "payment_schedule": [PaymentTranche(**row) for row in n.get("payment_schedule", [])],
        }) for n in data.get("negotiations", [])],
        external_negotiations=[
            ExternalNegotiationRound(**item)
            for item in data.get("external_negotiations", [])
        ],
        events=[Event(**e) for e in data.get("events", [])],
        traces=[DecisionTrace(**t) for t in data.get("traces", [])],
        action_audits=[AgentActionAudit(**item) for item in data.get("action_audits", [])],
        organization_actions=[
            OrganizationActionRecord(**item)
            for item in data.get("organization_actions", [])
        ],
        organization_plans=[
            OrganizationPlan(**{
                **item,
                "alternatives": [
                    PlanStrategyOption(**row) for row in item.get("alternatives", [])
                ],
                "nodes": [
                    OrganizationPlanNode(**row) for row in item.get("nodes", [])
                ],
            })
            for item in data.get("organization_plans", [])
        ],
        open_action_proposals=[
            OpenActionProposal(**item) for item in data.get("open_action_proposals", [])
        ],
        opportunity_windows=[
            OpportunityWindow(**item) for item in data.get("opportunity_windows", [])
        ],
        organization_learning={
            key: OrganizationLearningState(**item)
            for key, item in data.get("organization_learning", {}).items()
        },
        history=[MetricsSnapshot(**{**h, "phase": Phase(h["phase"])}) for h in data.get("history", [])],
        interventions=[Intervention(**i) for i in data.get("interventions", [])],
        imitation_decisions=[
            ImitationDecision(**item) for item in data.get("imitation_decisions", [])
        ],
        rescue_decisions=[
            RescueDecision(**item) for item in data.get("rescue_decisions", [])
        ],
        intervention_plans=[InterventionPlan(**{
            **item,
            "changes": [InterventionChange(**change) for change in item.get("changes", [])],
        }) for item in data.get("intervention_plans", [])],
        investment_funds={
            key: InvestmentFundState(**item)
            for key, item in data.get("investment_funds", {}).items()
        },
        random_state=data.get("random_state"),
        branched_from_quarter=data.get("branched_from_quarter"),
        parameter_provenance=data.get("parameter_provenance", {}),
        market_demand=data.get("market_demand", 100.0), demand_multiplier=data.get("demand_multiplier", 1.0),
        market_price=data.get("market_price", 1.0), selected_city_id=data.get("selected_city_id"),
        recruitment_status=data.get("recruitment_status", "active"),
        negotiation_round_limit=data.get("negotiation_round_limit", 6),
        imitation_policy=data.get("imitation_policy", "adaptive"),
        rescue_policy=data.get("rescue_policy", "adaptive"),
        parent_id=data.get("parent_id"), policy_mode=data.get("policy_mode", "deterministic"),
        model_name=data.get("model_name"),
        process_mode=data.get("process_mode", "hybrid"),
        organization_processes={
            key: OrganizationProcessState(**item)
            for key, item in data.get("organization_processes", {}).items()
        } or {
            city_id: OrganizationProcessState(city_id=city_id)
            for city_id in cities
        },
        mechanisms=data.get("mechanisms", {
            "private_information": True, "internal_governance": True,
            "credibility_diffusion": True, "supplier_spillover": True,
            "city_imitation": True, "enterprise_exit": True,
            "government_rescue": True,
        }),
        talents={
            key: TalentState(**{**item, "talent_type": TalentType(item["talent_type"])})
            for key, item in data.get("talents", {}).items()
        },
        universities={key: UniversityState(**item) for key, item in data.get("universities", {}).items()},
        platform=PlatformState(**data["platform"]) if data.get("platform") else None,
        talent_contracts=[TalentContract(**{**item, "offer": TalentOffer(**item["offer"])}) for item in data.get("talent_contracts", [])],
        talent_negotiations=[TalentNegotiation(**item) for item in data.get("talent_negotiations", [])],
        expression_mode=data.get("expression_mode", "plain"),
        interpreter_enabled=data.get("interpreter_enabled", False),
        negotiation_protocol=data.get("negotiation_protocol", "free"),
        language_style=data.get("language_style", "plain"),
        latent_needs={key: LatentNeed(**item) for key, item in data.get("latent_needs", {}).items()},
        stated_needs={key: StatedNeed(**item) for key, item in data.get("stated_needs", {}).items()},
        gov_beliefs={key: GovBelief(**item) for key, item in data.get("gov_beliefs", {}).items()},
        ent_beliefs={key: EntBelief(**item) for key, item in data.get("ent_beliefs", {}).items()},
        negotiation_records=[NegotiationRecord(**item) for item in data.get("negotiation_records", [])],
        cooperation_executions=[CooperationExecution(**item) for item in data.get("cooperation_executions", [])],
        project_risk_profiles={
            key: ProjectRiskProfile(**item)
            for key, item in data.get("project_risk_profiles", {}).items()
        },
        due_diligence_cases=[DueDiligenceCase(**{
            **item,
            "evidence": [EvidenceItem(**row) for row in item.get("evidence", [])],
        }) for item in data.get("due_diligence_cases", [])],
        due_diligence_program=data.get("due_diligence_program", "protocol_linked"),
        due_diligence_threshold=data.get("due_diligence_threshold", 0.5),
        experience_directives=data.get("experience_directives", []),
    )
