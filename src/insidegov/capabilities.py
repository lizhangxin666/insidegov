"""Role capabilities and hard prohibitions for open organization actions.

The catalog in :mod:`insidegov.organization` contains standard, reproducible
action templates.  It is not the upper bound of what an organization may
propose.  This module defines the smaller set of things the authority engine
must actually police: jurisdiction, information access, resource authority,
mandatory approvals and globally forbidden state mutations.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .models import AgentRole


@dataclass(frozen=True, slots=True)
class RoleCapability:
    domains: frozenset[str]
    information_scopes: frozenset[str]
    resource_authorities: frozenset[str]
    approval_authorities: frozenset[str]
    prohibitions: frozenset[str]
    arenas: frozenset[str] = frozenset({"formal", "informal"})


COMMON_INFORMATION = frozenset({
    "public_information", "disclosed_project_information", "own_private_information",
})


ROLE_CAPABILITIES: dict[AgentRole, RoleCapability] = {
    AgentRole.INVESTMENT: RoleCapability(
        domains=frozenset({
            "enterprise_contact", "project_coordination", "agenda_advocacy",
            "industry_evidence", "pilot_design",
        }),
        information_scopes=COMMON_INFORMATION | {"enterprise_voluntary_disclosure"},
        resource_authorities=frozenset({"propose_policy_package", "request_coordination_time"}),
        approval_authorities=frozenset(),
        prohibitions=frozenset({
            "approve_budget", "modify_fiscal_floor", "override_legal_review",
            "force_enterprise_acceptance",
        }),
        arenas=frozenset({"formal", "informal", "public"}),
    ),
    AgentRole.FINANCE: RoleCapability(
        domains=frozenset({
            "fiscal_review", "cashflow_design", "risk_assessment",
            "project_coordination", "expert_consultation",
        }),
        information_scopes=COMMON_INFORMATION | {"fiscal_private_information"},
        resource_authorities=frozenset({"recommend_fiscal_limit", "request_coordination_time"}),
        approval_authorities=frozenset({"approve_within_fiscal_limit"}),
        prohibitions=frozenset({
            "select_enterprise_location", "promise_enterprise_investment",
            "override_collective_decision", "force_fund_investment",
        }),
    ),
    AgentRole.CITY_LEADER: RoleCapability(
        domains=frozenset({
            "collective_coordination", "agenda_advocacy", "pilot_design",
            "project_coordination", "upward_coordination",
        }),
        information_scopes=COMMON_INFORMATION | {"department_submitted_information"},
        resource_authorities=frozenset({"request_budget_review", "request_coordination_time"}),
        approval_authorities=frozenset({"start_formal_process", "authorize_pilot"}),
        prohibitions=frozenset({
            "create_unbudgeted_funds", "override_verified_illegality",
            "force_fund_investment", "force_enterprise_acceptance",
        }),
        arenas=frozenset({"formal", "informal", "public"}),
    ),
    AgentRole.PARK: RoleCapability(
        domains=frozenset({
            "site_readiness", "project_coordination", "industry_evidence",
            "enterprise_service", "pilot_design",
        }),
        information_scopes=COMMON_INFORMATION | {"site_and_delivery_information"},
        resource_authorities=frozenset({"recommend_site_plan", "request_coordination_time"}),
        approval_authorities=frozenset(),
        prohibitions=frozenset({"approve_budget", "modify_fiscal_floor", "allocate_unapproved_land"}),
    ),
    AgentRole.LEGAL: RoleCapability(
        domains=frozenset({"legal_review", "risk_assessment", "expert_consultation"}),
        information_scopes=COMMON_INFORMATION | {"submitted_legal_materials"},
        resource_authorities=frozenset({"request_coordination_time"}),
        approval_authorities=frozenset({"issue_legal_opinion"}),
        prohibitions=frozenset({"approve_budget", "rewrite_policy_goal", "waive_verified_illegality"}),
        arenas=frozenset({"formal"}),
    ),
    AgentRole.FUND: RoleCapability(
        domains=frozenset({"fund_investment", "project_due_diligence", "expert_consultation"}),
        information_scopes=COMMON_INFORMATION | {"fund_due_diligence_information"},
        resource_authorities=frozenset({"invest_from_own_fund_pool"}),
        approval_authorities=frozenset({"approve_fund_investment"}),
        prohibitions=frozenset({"spend_city_budget", "guarantee_government_payment"}),
    ),
    AgentRole.ENTERPRISE: RoleCapability(
        domains=frozenset({"enterprise_decision", "negotiation", "voluntary_disclosure"}),
        information_scopes=COMMON_INFORMATION | {"enterprise_private_information"},
        resource_authorities=frozenset({"commit_own_resources"}),
        approval_authorities=frozenset({"accept_enterprise_contract"}),
        prohibitions=frozenset({"approve_government_budget", "read_fiscal_private_information"}),
        arenas=frozenset({"formal", "informal", "market"}),
    ),
    AgentRole.TALENT: RoleCapability(
        domains=frozenset({"talent_decision", "negotiation", "voluntary_disclosure"}),
        information_scopes=COMMON_INFORMATION | {"talent_private_information"},
        resource_authorities=frozenset({"commit_own_time"}),
        approval_authorities=frozenset({"accept_talent_contract"}),
        prohibitions=frozenset({"approve_government_budget", "commit_university_resources"}),
        arenas=frozenset({"formal", "informal", "market"}),
    ),
    AgentRole.UNIVERSITY: RoleCapability(
        domains=frozenset({"research_cooperation", "expert_consultation", "talent_support"}),
        information_scopes=COMMON_INFORMATION | {"university_internal_information"},
        resource_authorities=frozenset({"recommend_lab_resources", "commit_authorized_research_time"}),
        approval_authorities=frozenset({"approve_university_cooperation"}),
        prohibitions=frozenset({"approve_government_budget", "disclose_talent_private_information"}),
        arenas=frozenset({"formal", "informal"}),
    ),
    AgentRole.PLATFORM: RoleCapability(
        domains=frozenset({"information_translation", "matching", "project_coordination"}),
        information_scopes=COMMON_INFORMATION | {"authorized_matching_information"},
        resource_authorities=frozenset({"request_coordination_time"}),
        approval_authorities=frozenset(),
        prohibitions=frozenset({"approve_contract", "rewrite_source_information"}),
        arenas=frozenset({"formal", "informal", "market"}),
    ),
}


GLOBAL_PROHIBITIONS = frozenset({
    "create_money", "create_land", "fabricate_evidence",
    "read_unauthorized_private_information", "rewrite_past_events",
    "modify_random_state", "skip_mandatory_legal_procedure",
    "directly_set_project_outcome", "directly_set_production_capacity",
})

SENSITIVE_INFORMATION_SCOPES = frozenset({
    "fiscal_private_information", "enterprise_private_information",
    "fund_due_diligence_information", "unpublished_legal_opinion",
    "talent_private_information", "university_internal_information",
    "hidden_quality_label", "random_state",
})


# Material resources may be requested.  A request is compiled into a proposal
# or approval task; it never becomes an immediate world-state mutation.
MATERIAL_RESOURCE_KEYS = frozenset({
    "cash", "budget", "subsidy", "equity", "land", "credit",
    "fund_capital", "loan", "guarantee",
})
NON_MATERIAL_RESOURCE_KEYS = frozenset({
    "staff_time", "meeting_slots", "coordination_days", "expert_days",
})


MECHANISM_DOMAINS = {
    "upward_endorsement": "agenda_advocacy",
    "association_coalition": "industry_evidence",
    "demonstration_project": "pilot_design",
    "meeting_window": "agenda_advocacy",
    "strategic_delay": "project_coordination",
    "cross_department_taskforce": "project_coordination",
    "expert_consultation": "expert_consultation",
}


MECHANISM_PRIMITIVES = {
    "upward_endorsement": ("send_message", "request_information", "schedule_meeting"),
    "association_coalition": ("send_message", "request_information", "schedule_meeting"),
    "demonstration_project": ("create_proposal", "request_approval"),
    "meeting_window": ("open_agenda", "schedule_meeting"),
    "strategic_delay": ("wait", "record_reason"),
    "cross_department_taskforce": ("create_proposal", "schedule_meeting"),
    "expert_consultation": ("request_information", "schedule_meeting"),
}


def capability_payload() -> list[dict[str, object]]:
    rows = []
    for role, capability in ROLE_CAPABILITIES.items():
        item = asdict(capability)
        rows.append({
            "role": role.value,
            **{key: sorted(value) if isinstance(value, frozenset) else value for key, value in item.items()},
        })
    return rows
