from __future__ import annotations

from dataclasses import asdict, dataclass

from .agents import DeterministicCognition
from .scenarios import create_full_lifecycle_world


@dataclass(slots=True)
class CalibrationResult:
    id: str
    description: str
    passed: bool
    low_condition: float | str
    high_condition: float | str


def run_calibration_suite() -> list[dict]:
    cognition = DeterministicCognition()
    world = create_full_lifecycle_world()
    city = world.cities["city_lin"]
    firm = world.firms["firm_nova"]
    finance = world.agents["city_lin_finance"]
    leader = world.agents["city_lin_leader"]

    proposal = cognition.propose_offer(leader, city, firm, world, {}, []).to_package(city.id)
    low_pressure = cognition.review_offer(finance, city, proposal, {}, []).maximum_fiscal_cost
    city.committed_expenditure += 80
    high_pressure = cognition.review_offer(finance, city, proposal, {}, []).maximum_fiscal_cost

    firm.perceived_credibility.update({"city_hai": 0.95, "city_lin": 0.55, "city_yun": 0.55})
    trust_choice = cognition.select_location(
        world.agents["firm_nova_board"], firm,
        {"city_hai": 76.0, "city_lin": 70.0, "city_yun": 68.0}, {}, [],
    ).city_id

    results = [
        CalibrationResult(
            "finance_risk_sensitivity",
            "财政压力升高时，财政局的政策包承受上限下降",
            high_pressure < low_pressure,
            low_pressure,
            high_pressure,
        ),
        CalibrationResult(
            "enterprise_utility_consistency",
            "企业在其他条件给定时选择效用最高城市",
            trust_choice == "city_hai",
            "city_hai",
            trust_choice,
        ),
    ]
    return [asdict(result) for result in results]
