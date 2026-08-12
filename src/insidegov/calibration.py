from __future__ import annotations

import copy
from dataclasses import asdict, dataclass

from .agents import CognitiveProvider, DeterministicCognition, FinanceAction
from .scenarios import create_full_lifecycle_world


@dataclass(slots=True)
class CalibrationResult:
    id: str
    role: str
    description: str
    passed: bool
    expected: str
    observed: str
    failure_reason: str | None = None


def run_calibration_suite(cognition: CognitiveProvider | None = None) -> list[dict]:
    """Behavioral unit tasks for every decision-making role.

    The tests assert directional behavior instead of exact wording, so the same
    suite can calibrate deterministic and LLM cognition providers.
    """
    provider = cognition or DeterministicCognition()
    world = create_full_lifecycle_world()
    city = world.cities["city_lin"]
    firm = world.firms["firm_nova"]
    investment = world.agents["city_lin_investment"]
    finance = world.agents["city_lin_finance"]
    leader = world.agents["city_lin_leader"]
    board = world.agents["firm_nova_board"]
    results: list[CalibrationResult] = []

    try:
        low_competition = copy.deepcopy(investment)
        low_competition.private_facts["competitive_intensity"] = 0.2
        high_competition = copy.deepcopy(investment)
        high_competition.private_facts["competitive_intensity"] = 0.95
        low_offer = provider.propose_offer(low_competition, city, firm, world, {}, [])
        high_offer = provider.propose_offer(high_competition, city, firm, world, {}, [])
        low_value = low_offer.to_package(city.id).fiscal_cost
        high_value = high_offer.to_package(city.id).fiscal_cost
        results.append(CalibrationResult(
            "investment_competition_response", "investment",
            "竞争压力升高时，招商局不应降低政策包强度",
            high_value >= low_value, "high >= low", f"{high_value:.2f} vs {low_value:.2f}",
            None if high_value >= low_value else "招商局对竞争压力反应方向错误",
        ))
    except Exception as exc:  # noqa: BLE001 - provider failures are calibration evidence
        results.append(_failed("investment_competition_response", "investment", exc))

    try:
        proposal = DeterministicCognition().propose_offer(
            investment, city, firm, world, {}, []
        ).to_package(city.id)
        low_city = copy.deepcopy(city)
        high_city = copy.deepcopy(city)
        high_city.committed_expenditure += 80
        low_review = provider.review_offer(finance, low_city, proposal, {}, [])
        high_review = provider.review_offer(finance, high_city, proposal, {}, [])
        passed = high_review.maximum_fiscal_cost <= low_review.maximum_fiscal_cost
        results.append(CalibrationResult(
            "finance_risk_sensitivity", "finance",
            "财政压力升高时，财政局的总承受上限不应上升",
            passed, "high <= low",
            f"{high_review.maximum_fiscal_cost:.2f} vs {low_review.maximum_fiscal_cost:.2f}",
            None if passed else "财政局在更高风险下放松了上限",
        ))
    except Exception as exc:  # noqa: BLE001 - provider failures are calibration evidence
        results.append(_failed("finance_risk_sensitivity", "finance", exc))

    try:
        proposal = DeterministicCognition().propose_offer(
            investment, city, firm, world, {}, []
        ).to_package(city.id)
        review = FinanceAction(
            approved=False, maximum_fiscal_cost=20, maximum_subsidy=8,
            maximum_equity=12, maximum_credit_support=20,
            maximum_first_period_payment=8, concerns=["现金超限"],
            rationale="校准审核",
        )
        resolution = provider.resolve_offer(leader, city, proposal, review, {}, [])
        package = resolution.to_package(city.id)
        first = sum(row.amount for row in package.payment_schedule if row.due_offset == 1)
        passed = (
            package.subsidy <= 8.01 and package.equity <= 12.01
            and package.credit_support <= 20.01 and first <= 8.01
            and len(package.payment_schedule) >= 2
        )
        results.append(CalibrationResult(
            "leader_veto_coordination", "city_leader",
            "市领导必须尊重工具上限并给出多期兑现方案",
            passed, "cash<=8, equity<=12, first<=8, tranches>=2",
            f"cash={package.subsidy:.2f}, equity={package.equity:.2f}, first={first:.2f}, tranches={len(package.payment_schedule)}",
            None if passed else "协调结果突破否决边界或未分期",
        ))
    except Exception as exc:  # noqa: BLE001 - provider failures are calibration evidence
        results.append(_failed("leader_veto_coordination", "city_leader", exc))

    try:
        choice = provider.select_location(
            board, firm, {"city_hai": 76.0, "city_lin": 70.0, "city_yun": 68.0}, {}, []
        ).city_id
        passed = choice == "city_hai"
        results.append(CalibrationResult(
            "enterprise_utility_consistency", "enterprise",
            "给定综合效用时，企业选择最高效用城市",
            passed, "city_hai", choice,
            None if passed else "企业选择与给定效用排序不一致",
        ))
    except Exception as exc:  # noqa: BLE001 - provider failures are calibration evidence
        results.append(_failed("enterprise_utility_consistency", "enterprise", exc))

    return [asdict(result) for result in results]


def _failed(test_id: str, role: str, exc: Exception) -> CalibrationResult:
    return CalibrationResult(
        test_id, role, "行为校准请求应返回有效结构化行动", False,
        "valid structured action", type(exc).__name__, f"{type(exc).__name__}: {exc}",
    )
