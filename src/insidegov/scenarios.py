from __future__ import annotations

import random

from .models import (
    AgentRole,
    AgentState,
    CityState,
    DepartmentState,
    EntBelief,
    FirmState,
    FirmType,
    GovBelief,
    LatentNeed,
    OrganizationProcessState,
    Phase,
    PlatformState,
    ProjectRiskProfile,
    StatedNeed,
    TalentState,
    TalentType,
    TechDemand,
    UniversityState,
    WorldState,
)


def _departments(prefix: str) -> list[DepartmentState]:
    return [
        DepartmentState(f"{prefix}_leader", "市领导", "增长、就业与风险平衡", 0.66, 1.0),
        DepartmentState(f"{prefix}_investment", "招商部门", "促成项目签约落地", 0.82, 0.78),
        DepartmentState(f"{prefix}_finance", "财政部门", "控制财政成本与或有风险", 0.28, 0.86),
        DepartmentState(f"{prefix}_park", "产业园区", "提高土地利用与集聚水平", 0.64, 0.58),
    ]


def create_full_lifecycle_world(seed: int = 42, world_id: str = "baseline") -> WorldState:
    """Create a reproducible but genuinely seed-sensitive policy world.

    Each labelled draw uses its own RNG stream.  This keeps an existing actor's
    initial state stable when a new city or supplier is added later, while making
    different seeds represent different fiscal, industrial and belief conditions.
    """

    def draw(label: str) -> random.Random:
        return random.Random(f"insidegov:{seed}:{label}")

    def vary(label: str, value: float, spread: float, digits: int = 2) -> float:
        return round(value * (1 + draw(label).uniform(-spread, spread)), digits)

    def shift(
        label: str, value: float, spread: float, lower: float, upper: float, digits: int = 3,
    ) -> float:
        return round(min(upper, max(lower, value + draw(label).uniform(-spread, spread))), digits)

    def seeded_city(
        city_id: str,
        name: str,
        fiscal_budget: float,
        available_budget: float,
        committed_expenditure: float,
        debt: float,
        industrial_land: float,
        talent_pool: float,
        supply_chain: float,
        administrative_capacity: float,
        environmental_capacity: float,
        credibility: float,
        term: int,
        gdp_weight: float,
        employment_weight: float,
        risk_weight: float,
        prefix: str,
    ) -> CityState:
        return CityState(
            city_id,
            name,
            vary(f"{city_id}:fiscal_budget", fiscal_budget, 0.055),
            vary(f"{city_id}:available_budget", available_budget, 0.085),
            vary(f"{city_id}:committed", committed_expenditure, 0.10),
            vary(f"{city_id}:debt", debt, 0.09),
            vary(f"{city_id}:land", industrial_land, 0.07),
            shift(f"{city_id}:talent", talent_pool, 13.0, 32.0, 98.0, 2),
            shift(f"{city_id}:supply", supply_chain, 17.0, 22.0, 98.0, 2),
            shift(f"{city_id}:admin", administrative_capacity, 8.0, 45.0, 98.0, 2),
            shift(f"{city_id}:environment", environmental_capacity, 6.0, 40.0, 98.0, 2),
            shift(f"{city_id}:credibility", credibility, 0.14, 0.48, 0.98),
            max(3, term + draw(f"{city_id}:term").choice([-2, -1, 0, 1, 2])),
            shift(f"{city_id}:gdp_weight", gdp_weight, 0.035, 0.20, 0.55),
            shift(f"{city_id}:employment_weight", employment_weight, 0.03, 0.15, 0.42),
            shift(f"{city_id}:risk_weight", risk_weight, 0.035, 0.08, 0.45),
            _departments(prefix),
        )

    cities = {
        "city_hai": seeded_city(
            "city_hai", "海州市", 160.0, 82.0, 16.0, 120.0, 560.0, 67.0, 58.0,
            82.0, 72.0, 0.82, 10, 0.36, 0.27, 0.22, "hai",
        ),
        "city_lin": seeded_city(
            "city_lin", "临江市", 215.0, 126.0, 21.0, 168.0, 430.0, 84.0, 76.0,
            88.0, 63.0, 0.91, 6, 0.31, 0.24, 0.34, "lin",
        ),
        "city_yun": seeded_city(
            "city_yun", "云麓市", 112.0, 64.0, 11.0, 72.0, 720.0, 55.0, 43.0,
            71.0, 86.0, 0.74, 14, 0.44, 0.32, 0.14, "yun",
        ),
    }
    anchor_credibility = {
        city_id: shift(
            f"firm_nova:{city_id}:prior_belief", city.objective_credibility, 0.19, 0.32, 0.99,
        )
        for city_id, city in cities.items()
    }
    firms: dict[str, FirmState] = {
        "firm_nova": FirmState(
            "firm_nova", "星澜显示", FirmType.ANCHOR, 180.0, 92.0, 220.0, 2600, 120.0,
            86.0,
            shift("firm_nova:policy_sensitivity", 0.48, 0.07, 0.30, 0.68),
            shift("firm_nova:cluster_sensitivity", 0.78, 0.11, 0.48, 0.95),
            shift("firm_nova:credibility_sensitivity", 0.83, 0.09, 0.55, 0.98),
            shift("firm_nova:risk_tolerance", 0.55, 0.10, 0.25, 0.82),
            shift("firm_nova:private_intent", 0.88, 0.10, 0.55, 0.98),
            shift("firm_nova:minimum_utility", 68.0, 5.5, 56.0, 79.0, 2),
            perceived_credibility=anchor_credibility,
        )
    }
    supplier_types = [FirmType.SUPPLIER, FirmType.TECHNOLOGY, FirmType.OPPORTUNISTIC]
    for index in range(1, 13):
        kind = supplier_types[(index - 1) % len(supplier_types)]
        firms[f"supplier_{index:02d}"] = FirmState(
            id=f"supplier_{index:02d}",
            name=f"链企 {index:02d}",
            firm_type=kind,
            investment_capacity=12.0 + index * 1.8,
            cash=8.0 + index,
            land_need=12.0 + index * 1.3,
            jobs_capacity=100 + index * 22,
            production_capacity=8.0 + index * 1.5,
            technology=48.0 + index * 2.5,
            policy_sensitivity=0.78 if kind == FirmType.OPPORTUNISTIC else 0.38,
            cluster_sensitivity=0.82 if kind == FirmType.SUPPLIER else 0.58,
            credibility_sensitivity=0.68 if kind == FirmType.TECHNOLOGY else 0.48,
            risk_tolerance=0.4 + (index % 4) * 0.12,
            private_intent=shift(
                f"supplier_{index:02d}:private_intent",
                0.55 + (index % 5) * 0.08, 0.10, 0.32, 0.98,
            ),
            minimum_utility=shift(
                f"supplier_{index:02d}:minimum_utility",
                58.0 + (index % 3) * 4, 6.0, 48.0, 76.0, 2,
            ),
            supplier_of="firm_nova",
            perceived_credibility={
                city_id: shift(
                    f"supplier_{index:02d}:{city_id}:prior_belief",
                    city.objective_credibility, 0.11, 0.35, 0.99,
                )
                for city_id, city in cities.items()
            },
        )
    agents: dict[str, AgentState] = {}
    for city in cities.values():
        agents[f"{city.id}_leader"] = AgentState(
            id=f"{city.id}_leader", name=f"{city.name}市领导", role=AgentRole.CITY_LEADER,
            owner_id=city.id, goals=["促成高质量项目落地", "兼顾就业与产业升级", "维护长期政府信用"],
            private_facts={"political_horizon": city.leadership_term_remaining, "growth_weight": city.gdp_weight},
            traits={"risk_aversion": city.risk_weight, "short_termism": max(0.1, 1-city.leadership_term_remaining/20), "trust_sensitivity": 0.58},
        )
        agents[f"{city.id}_finance"] = AgentState(
            id=f"{city.id}_finance", name=f"{city.name}财政局", role=AgentRole.FINANCE,
            owner_id=city.id, goals=["控制当期财政支出", "约束隐性债务", "确保承诺可兑现"],
            private_facts={
                "reserve_floor": round(
                    city.available_budget
                    * shift(f"{city.id}:reserve_ratio", 0.34, 0.055, 0.26, 0.43), 2,
                ),
                "stress_limit": shift(f"{city.id}:stress_limit", 0.72, 0.08, 0.58, 0.86),
            },
            traits={"risk_aversion": 0.82, "short_termism": 0.45, "trust_sensitivity": 0.74},
        )
        agents[f"{city.id}_investment"] = AgentState(
            id=f"{city.id}_investment", name=f"{city.name}招商局", role=AgentRole.INVESTMENT,
            owner_id=city.id, goals=["争取龙头项目签约", "提高政策包的企业吸引力", "完成年度招商任务"],
            private_facts={
                "signing_target": shift(f"{city.id}:signing_target", 1.0, 0.18, 0.75, 1.25),
                "cash_preference": shift(
                    f"{city.id}:cash_preference", 0.55 + (100-city.supply_chain)/500,
                    0.09, 0.42, 0.88,
                ),
                "competitive_intensity": shift(
                    f"{city.id}:competitive_intensity", 0.62 + (100-city.supply_chain)/400,
                    0.10, 0.48, 0.92,
                ),
            },
            traits={"risk_aversion": 0.24, "short_termism": 0.78, "trust_sensitivity": 0.42},
        )
        agents[f"{city.id}_legal"] = AgentState(
            id=f"{city.id}_legal", name=f"{city.name}司法审查机构", role=AgentRole.LEGAL,
            owner_id=city.id, goals=["保证权限合法", "识别程序瑕疵", "提高承诺可执行性"],
            private_facts={"review_capacity": city.administrative_capacity / 100},
            traits={"risk_aversion": 0.72, "short_termism": 0.18, "trust_sensitivity": 0.55},
        )
        agents[f"{city.id}_park"] = AgentState(
            id=f"{city.id}_park", name=f"{city.name}产业园区", role=AgentRole.PARK,
            owner_id=city.id, goals=["形成产业集聚", "提高土地利用率", "协调项目执行"],
            private_facts={"land_pressure": max(0.0, 1 - city.industrial_land / 800)},
            traits={"risk_aversion": 0.38, "short_termism": 0.58, "trust_sensitivity": 0.66},
        )
    agents["firm_nova_board"] = AgentState(
        id="firm_nova_board", name="星澜显示董事会", role=AgentRole.ENTERPRISE,
        owner_id="firm_nova", goals=["提高长期投资回报", "降低政策与建设风险", "获得稳定供应链"],
        private_facts={
            "true_intent": firms["firm_nova"].private_intent,
            "minimum_utility": firms["firm_nova"].minimum_utility,
            "second_phase_probability": shift(
                "firm_nova:second_phase_probability", 0.62, 0.15, 0.30, 0.88,
            ),
        },
        traits={"risk_aversion": 0.63, "short_termism": 0.28, "trust_sensitivity": 0.83},
    )
    latent_need = LatentNeed(
        firm_id="firm_nova",
        problem="在可控财政与履约风险下建设高世代显示产线并形成稳定供应链",
        preferred_mode="phased_investment",
        deadline=12,
        budget=firms["firm_nova"].investment_capacity,
        constraints=["首期现金流可控", "政策兑现绑定建设节点", "供应商能够持续进入"],
        commitment=firms["firm_nova"].private_intent,
        required_tools={
            "subsidy": firms["firm_nova"].policy_sensitivity,
            "equity": 0.72,
            "credit_support": 0.55,
            "land_discount": 0.64,
            "talent_support": 0.48,
        },
        truth={
            "problem": 1.0, "target": 0.95, "deadline": 0.86,
            "budget": 0.82, "mode": 0.94, "constraint": 0.88,
            "commitment": firms["firm_nova"].private_intent,
        },
    )
    stated_need = StatedNeed(
        firm_id="firm_nova",
        text="计划建设显示产业项目，希望获得有竞争力的综合政策与快速审批支持",
        category="expansion",
        clarity=0.46,
        disclosed={
            "problem": 0.62, "target": 0.55, "deadline": 0.42,
            "budget": 0.30, "mode": 0.28, "constraint": 0.20, "commitment": 0.24,
        },
        exaggeration=shift("firm_nova:need_exaggeration", 0.18, 0.09, 0.04, 0.35),
    )
    return WorldState(
        id=world_id,
        name="地方产业发展全生命周期",
        seed=seed,
        quarter=0,
        phase=Phase.RECRUITMENT,
        cities=cities,
        firms=firms,
        agents=agents,
        promises=[],
        negotiations=[],
        external_negotiations=[],
        events=[],
        traces=[],
        action_audits=[],
        organization_actions=[],
        history=[],
        interventions=[],
        negotiation_protocol="clarify_first",
        latent_needs={"firm_nova": latent_need},
        stated_needs={"firm_nova": stated_need},
        gov_beliefs={
            city_id: GovBelief(firm_id="firm_nova") for city_id in cities
        },
        ent_beliefs={
            city_id: EntBelief(
                firm_id="firm_nova",
                trust=firms["firm_nova"].perceived_credibility[city_id],
            ) for city_id in cities
        },
        organization_processes={
            city_id: OrganizationProcessState(city_id=city_id)
            for city_id in cities
        },
    )


def create_talent_world(
    seed: int = 42,
    world_id: str = "talent-baseline",
    expression_mode: str = "plain",
    interpreter_enabled: bool = False,
    mode: str = "deterministic",
) -> WorldState:
    """高校人才与技术对接场景。

    一个小企业集中的城市，面对两所高校的人才供给。人才拥有学术羁绊、
    身份顾虑、报酬诉求与风险偏好等私有信息；政府通过政策工具包与表达
    方式（官话/人话）影响人才的理解与信任；可选的中介平台提供翻译撮合，
    降低跨语言体系的对接成本。
    """
    city = CityState(
        "city_qing", "青禾市", 9000.0, 4600.0, 600.0, 3800.0, 320.0, 74.0, 52.0,
        78.0, 70.0, 0.80, 8, 0.34, 0.30, 0.20, _departments("qing")
    )
    cities = {"city_qing": city}

    universities = {
        "uni_qing": UniversityState(
            "uni_qing", "青禾理工大学", {"tech": 0.88, "eng": 0.72, "mgmt": 0.55},
            0.82, 0.45,
        ),
        "uni_yun": UniversityState(
            "uni_yun", "云麓大学", {"tech": 0.68, "eng": 0.60, "mgmt": 0.74},
            0.66, 0.38,
        ),
    }

    talents: dict[str, TalentState] = {
        "talent_young_1": TalentState(
            "talent_young_1", "周然", TalentType.JUNIOR_FACULTY, "uni_qing",
            {"tech": 0.90, "eng": 0.62, "mgmt": 0.30},
            {"identity": 0.85, "academic": 0.88, "compensation": 0.55, "risk": 0.60},
            0.55, 78.0, 0.95, opportunity_cost=72.0,
        ),
        "talent_young_2": TalentState(
            "talent_young_2", "林蔚", TalentType.JUNIOR_FACULTY, "uni_qing",
            {"tech": 0.72, "eng": 0.85, "mgmt": 0.42},
            {"identity": 0.80, "academic": 0.75, "compensation": 0.62, "risk": 0.52},
            0.62, 66.0, 0.92, opportunity_cost=64.0,
        ),
        "talent_young_3": TalentState(
            "talent_young_3", "苏宸", TalentType.JUNIOR_FACULTY, "uni_yun",
            {"tech": 0.78, "eng": 0.66, "mgmt": 0.38},
            {"identity": 0.78, "academic": 0.80, "compensation": 0.50, "risk": 0.55},
            0.58, 70.0, 0.93, opportunity_cost=66.0,
        ),
        "talent_prof_1": TalentState(
            "talent_prof_1", "陈鹤鸣", TalentType.SENIOR_PROFESSOR, "uni_qing",
            {"tech": 0.95, "eng": 0.70, "mgmt": 0.66},
            {"identity": 0.15, "academic": 0.55, "compensation": 0.35, "risk": 0.30},
            0.88, 88.0, 0.35, opportunity_cost=80.0,
        ),
        "talent_prof_2": TalentState(
            "talent_prof_2", "顾明远", TalentType.SENIOR_PROFESSOR, "uni_yun",
            {"tech": 0.86, "eng": 0.68, "mgmt": 0.72},
            {"identity": 0.12, "academic": 0.62, "compensation": 0.30, "risk": 0.28},
            0.85, 84.0, 0.30, opportunity_cost=78.0,
        ),
        "talent_exp_1": TalentState(
            "talent_exp_1", "沈砚", TalentType.INDUSTRY_EXPERT, None,
            {"tech": 0.66, "eng": 0.92, "mgmt": 0.80},
            {"identity": 0.05, "academic": 0.05, "compensation": 0.70, "risk": 0.35},
            0.90, 30.0, 0.98, opportunity_cost=58.0,
        ),
    }
    for talent in talents.values():
        talent.trust = {"firm_clean": 0.55, "firm_control": 0.55, "firm_bio": 0.55, "city_qing": 0.62}
    for university in universities.values():
        university.talent_ids = [talent_id for talent_id, talent in talents.items() if talent.university_id == university.id]

    firms: dict[str, FirmState] = {
        "firm_clean": FirmState(
            id="firm_clean", name="清源材料", firm_type=FirmType.TECHNOLOGY,
            investment_capacity=38.0, cash=14.0, land_need=18.0, jobs_capacity=120,
            production_capacity=6.0, technology=25.0, policy_sensitivity=0.62,
            cluster_sensitivity=0.50, credibility_sensitivity=0.74, risk_tolerance=0.52,
            private_intent=0.66, minimum_utility=50.0, knowledge=25.0,
            tech_demand=TechDemand(
                description="相变储能材料从实验室走向中试与量产",
                vector={"tech": 0.85, "eng": 0.75, "mgmt": 0.30},
                budget=60.0, form="joint_lab", clarity=0.55,
            ),
        ),
        "firm_control": FirmState(
            id="firm_control", name="睿控装备", firm_type=FirmType.TECHNOLOGY,
            investment_capacity=32.0, cash=11.0, land_need=12.0, jobs_capacity=90,
            production_capacity=5.0, technology=40.0, policy_sensitivity=0.55,
            cluster_sensitivity=0.48, credibility_sensitivity=0.66, risk_tolerance=0.58,
            private_intent=0.62, minimum_utility=50.0, knowledge=40.0,
            tech_demand=TechDemand(
                description="工业嵌入式控制算法的工程化与现场适配",
                vector={"tech": 0.55, "eng": 0.90, "mgmt": 0.40},
                budget=48.0, form="full_time", clarity=0.70,
            ),
        ),
        "firm_bio": FirmState(
            id="firm_bio", name="蓝芯生物", firm_type=FirmType.TECHNOLOGY,
            investment_capacity=28.0, cash=9.0, land_need=10.0, jobs_capacity=70,
            production_capacity=4.0, technology=22.0, policy_sensitivity=0.58,
            cluster_sensitivity=0.52, credibility_sensitivity=0.70, risk_tolerance=0.50,
            private_intent=0.60, minimum_utility=50.0, knowledge=22.0,
            tech_demand=TechDemand(
                description="生物快速检测的信号处理与试剂稳定化",
                vector={"tech": 0.80, "eng": 0.60, "mgmt": 0.45},
                budget=42.0, form="open_call", clarity=0.60,
            ),
        ),
    }

    agents: dict[str, AgentState] = {}
    agents["city_qing_leader"] = AgentState(
        id="city_qing_leader", name="青禾市市领导", role=AgentRole.CITY_LEADER,
        owner_id=city.id, goals=["促成技术成果在本地落地", "兼顾就业与创新生态", "维护政策兑现信用"],
        private_facts={"political_horizon": 8, "growth_weight": 0.34},
        traits={"risk_aversion": 0.30, "short_termism": 0.42, "trust_sensitivity": 0.62},
    )
    agents["city_qing_finance"] = AgentState(
        id="city_qing_finance", name="青禾市财政局", role=AgentRole.FINANCE,
        owner_id=city.id, goals=["控制人才专项支出", "确保安家与项目经费可兑现", "约束或有负债"],
        private_facts={"reserve_floor": round(city.available_budget * 0.30, 2), "stress_limit": 0.72},
        traits={"risk_aversion": 0.80, "short_termism": 0.44, "trust_sensitivity": 0.72},
    )
    agents["city_qing_investment"] = AgentState(
        id="city_qing_investment", name="青禾市人才办", role=AgentRole.INVESTMENT,
        owner_id=city.id, goals=["促成人才签约落地", "提高政策包吸引力", "完成年度引才任务"],
        private_facts={"signing_target": 3.0, "cash_preference": 0.55, "competitive_intensity": 0.30},
        traits={"risk_aversion": 0.26, "short_termism": 0.70, "trust_sensitivity": 0.44},
    )
    for firm_id, firm in firms.items():
        agents[f"{firm_id}_board"] = AgentState(
            id=f"{firm_id}_board", name=f"{firm.name}团队", role=AgentRole.ENTERPRISE,
            owner_id=firm_id, goals=["获得能落地的技术能力", "控制人才成本", "快速形成产品"],
            private_facts={"demand": firm.tech_demand.vector if firm.tech_demand else {},
                           "budget": firm.tech_demand.budget if firm.tech_demand else 30.0,
                           "clarity": firm.tech_demand.clarity if firm.tech_demand else 0.5},
            traits={"risk_aversion": 0.60, "short_termism": 0.52, "trust_sensitivity": 0.66},
        )
    for uni_id, university in universities.items():
        agents[f"{uni_id}_dean"] = AgentState(
            id=f"{uni_id}_dean", name=f"{university.name}科研处", role=AgentRole.UNIVERSITY,
            owner_id=uni_id, goals=["推动成果转化", "保障教师学术考核", "控制人才流失风险"],
            private_facts={"assessment_pressure": university.assessment_pressure,
                           "industry_support": university.industry_support},
            traits={"risk_aversion": 0.55, "short_termism": 0.40, "trust_sensitivity": 0.60},
        )
    for talent_id, talent in talents.items():
        agents[talent_id] = AgentState(
            id=talent_id, name=talent.name, role=AgentRole.TALENT,
            owner_id=talent_id, goals=["职业发展", "学术与产业的平衡", "降低转型风险"],
            private_facts={"opportunity_cost": talent.opportunity_cost,
                           "concerns": talent.concerns, "academic_value": talent.academic_value},
            traits={"risk_aversion": 0.42 + talent.concerns["risk"] * 0.4,
                    "short_termism": 0.30, "trust_sensitivity": 0.58 + talent.concerns["identity"] * 0.3},
        )
    platform = PlatformState("platform_link", "青禾产学研对接平台", 0.85, 0.70, 5.0)
    agents["platform_link"] = AgentState(
        id="platform_link", name="产学研对接平台", role=AgentRole.PLATFORM,
        owner_id=platform.id, goals=["提高对接成功率", "降低双方理解成本", "促成更多技术交易"],
        private_facts={"translation_power": platform.translation_power,
                       "information_coverage": platform.information_coverage},
        traits={"risk_aversion": 0.45, "short_termism": 0.35, "trust_sensitivity": 0.68},
    )

    return WorldState(
        id=world_id,
        name="高校人才与技术对接",
        seed=seed,
        quarter=0,
        phase=Phase.RECRUITMENT,
        cities=cities,
        firms=firms,
        agents=agents,
        promises=[],
        negotiations=[],
        external_negotiations=[],
        events=[],
        traces=[],
        action_audits=[],
        organization_actions=[],
        history=[],
        interventions=[],
        talents=talents,
        universities=universities,
        platform=platform,
        expression_mode=expression_mode,
        interpreter_enabled=interpreter_enabled,
        policy_mode=mode,
    )


def create_negotiation_world(
    seed: int = 42,
    world_id: str = "negotiation-baseline",
    protocol: str = "free",
    language_style: str = "plain",
    mode: str = "deterministic",
) -> WorldState:
    """Build the shared eight-firm counterfactual negotiation world."""
    world = create_talent_world(seed, world_id, mode=mode)
    world.name = "政企协商与可执行承诺实验室"
    world.phase = Phase.NEGOTIATION
    world.negotiation_protocol = protocol
    world.language_style = language_style
    world.talents, world.universities, world.platform = {}, {}, None
    world.latent_needs, world.stated_needs = {}, {}
    world.gov_beliefs, world.ent_beliefs = {}, {}
    world.agents["city_qing_legal"] = AgentState(
        id="city_qing_legal", name="青禾市法务与信用审查组", role=AgentRole.LEGAL,
        owner_id="city_qing", goals=["核验主体与实控人", "识别材料矛盾", "守住合规红线"],
        private_facts={"hard_red_line": 0.78, "verification_budget": 4.0},
        traits={"risk_aversion": 0.84, "short_termism": 0.18, "trust_sensitivity": 0.36},
    )
    world.agents["city_qing_technical"] = AgentState(
        id="city_qing_technical", name="青禾市行业技术评审组", role=AgentRole.PARK,
        owner_id="city_qing", goals=["验证技术成熟度", "核验市场和量产条件", "避免热度替代证据"],
        private_facts={"pilot_preference": 0.68, "verification_budget": 5.0},
        traits={"risk_aversion": 0.62, "short_termism": 0.22, "trust_sensitivity": 0.30},
    )

    profiles = [
        # 最后一列是企业自己知道的资金投入能力，不是政府可见的质量标签。
        ("firm_bio", "蓝芯生物", "talent_shortage", "flexible", "建立高校柔性研发合作", 0.38, 0.12, 0.62),
        ("firm_chip", "微核传感", "talent_shortage", "pilot", "完成传感芯片中试验证", 0.42, 0.10, 0.62),
        ("firm_data", "澄数科技", "digitalization", "project", "完成工业数据治理项目", 0.62, 0.08, 0.62),
        ("firm_clean", "清源材料", "consulting", "diagnosis", "诊断材料量产良率问题", 0.66, 0.06, 0.62),
        ("firm_control", "睿控装备", "expansion", "capacity", "扩建智能控制产线", 0.68, 0.08, 0.62),
        ("firm_med", "禾康器械", "consulting", "diagnosis", "完成医疗器械工程验证", 0.59, 0.10, 0.62),
        ("firm_robot", "灵虎机器人", "digitalization", "digital", "升级产线数字控制系统", 0.40, 0.24, 0.58),
        ("firm_risky", "高能电池", "expansion", "pilot", "验证尚未成熟的高能电池技术", 0.78, 0.55, 0.15),
    ]
    firms: dict[str, FirmState] = {}
    toolsets = {
        "flexible": {"joint_rnd": 0.9, "tech_contract": 0.8},
        "pilot": {"pilot_voucher": 0.9, "tech_contract": 0.7, "rnd_subsidy": 0.6},
        "project": {"digital_subsidy": 0.8, "tech_contract": 0.8},
        "digital": {"digital_subsidy": 0.9, "tech_contract": 0.7},
        "diagnosis": {"tech_contract": 0.9, "rnd_subsidy": 0.6},
        "capacity": {"industry_fund": 0.8, "equipment_subsidy": 0.8, "tax_credit": 0.6},
    }
    for index, profile in enumerate(profiles):
        firm_id, name, category, preferred_mode, problem, trust, exaggeration, commitment = profile
        firm = world.firms.get(firm_id) or FirmState(
            firm_id, name, FirmType.TECHNOLOGY, 28.0 + index * 2, 9.0 + index,
            10.0, 70 + index * 8, 4.0, 25.0 + index * 3,
            0.58, 0.52, 0.70, 0.50, 0.60, 50.0,
        )
        firm.name = name
        firm.perceived_credibility = {"city_qing": trust}
        firms[firm_id] = firm
        world.agents[f"{firm_id}_board"] = AgentState(
            id=f"{firm_id}_board", name=f"{name}决策团队", role=AgentRole.ENTERPRISE,
            owner_id=firm_id, goals=["解决真实经营问题", "控制合作成本", "保护商业边界"],
            private_facts={
                "true_mode": preferred_mode,
                "own_commitment": commitment,
            },
            traits={"risk_aversion": 0.58, "short_termism": 0.48, "trust_sensitivity": 0.72},
        )
        world.latent_needs[firm_id] = LatentNeed(
            firm_id, problem, preferred_mode, 12, 42.0 + index * 2,
            ["不接受全职引才", "核心数据与客户名单不得披露"] if preferred_mode in {"flexible", "pilot"} else ["分期验收"],
            commitment, toolsets[preferred_mode],
            {"problem": 0.96, "target": 0.90, "deadline": 0.78, "budget": 0.72,
             "mode": 0.94, "constraint": 0.86, "commitment": commitment},
            unfeasible=False,
        )
        disclosed = 0.14 if trust < 0.50 else 0.48
        world.stated_needs[firm_id] = StatedNeed(
            firm_id, f"企业希望政府帮助解决{problem}相关困难", category,
            0.38 if trust < 0.50 else 0.62,
            {"problem": disclosed, "target": disclosed, "deadline": disclosed * 0.8,
             "budget": disclosed * 0.55, "mode": disclosed * 0.30,
             "constraint": disclosed * 0.22, "commitment": disclosed * 0.20},
            exaggeration,
        )
        world.gov_beliefs[firm_id] = GovBelief(firm_id)
        world.ent_beliefs[firm_id] = EntBelief(firm_id, trust=trust)
    world.firms = firms
    # These profiles generate evidence and ex-post outcomes.  Government agents
    # never receive them directly; they only observe claims and requested checks.
    risk_values = {
        "firm_bio": (0.74, 0.78, 0.66, 0.82, 0.72, 0.80, 0.76, 150, 7.0),
        "firm_chip": (0.68, 0.74, 0.64, 0.76, 0.70, 0.74, 0.82, 180, 8.0),
        "firm_data": (0.82, 0.84, 0.80, 0.86, 0.78, 0.90, 0.70, 120, 5.0),
        "firm_clean": (0.76, 0.72, 0.74, 0.80, 0.82, 0.88, 0.72, 210, 8.0),
        "firm_control": (0.80, 0.86, 0.78, 0.84, 0.86, 0.84, 0.86, 420, 12.0),
        "firm_med": (0.70, 0.76, 0.71, 0.78, 0.74, 0.86, 0.68, 160, 6.0),
        # Low-trust and genuinely fragile: useful for separating distrust from risk.
        "firm_robot": (0.46, 0.62, 0.38, 0.58, 0.50, 0.72, 0.60, 240, 9.0),
        # Persuasive/high-trust but weak fundamentals and low candor.
        "firm_risky": (0.28, 0.24, 0.34, 0.42, 0.38, 0.24, 0.88, 680, 18.0),
    }
    world.project_risk_profiles = {
        firm_id: ProjectRiskProfile(firm_id, *values)
        for firm_id, values in risk_values.items()
    }
    return world
