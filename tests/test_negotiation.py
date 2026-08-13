"""Negotiation-lab tests: protocol dispatch, understanding gap, veto, alignment, pareto, H1-H7."""

import copy

import pytest

from insidegov.experiments import (
    _pareto_frontier,
    run_negotiation_comparison,
    run_negotiation_matrix,
)
from insidegov.models import NegotiationProtocol
from insidegov.negotiation_agents import ProposalAction
from insidegov.negotiation_engine import COMPONENTS, NegotiationEngine
from insidegov.scenarios import create_negotiation_world
from insidegov.serde import world_from_dict


def _run(seed: int = 42, protocol: str = "free", quarters: int = 2, language: str = "plain"):
    world = create_negotiation_world(
        seed, f"negotiation-test-{protocol}-s{seed}",
        protocol=protocol, language_style=language,
    )
    return NegotiationEngine(world).run(quarters)


def _accepted(world):
    return {r.firm_id: r for r in world.negotiation_records if r.outcome == "accepted"}


def test_llm_proposal_rejects_non_executable_tool_lists():
    with pytest.raises((TypeError, ValueError)):
        ProposalAction.model_validate({
            "rationale": "列出政策工具",
            "options": [{"label": "方案一", "tools": ["industry_fund", "tax_credit"]}],
        })


def test_seven_protocols_are_distinct():
    assert len(NegotiationProtocol) == 7
    ids = [protocol.value for protocol in NegotiationProtocol]
    assert ids == [
        "free", "policy_match", "clarify_first", "paraphrase_confirm",
        "constraints_first", "multi_option", "phased_commitment",
    ]


def test_protocol_dispatch_is_counterfactual():
    # 同一初始世界，仅切换机制：澄清优先必须触发追问并降低最终理解差距
    free = _run(42, protocol="free")
    clarify = _run(42, protocol="clarify_first")
    free_gap = sum(r.gap_final for r in free.negotiation_records) / len(free.negotiation_records)
    clarify_gap = sum(r.gap_final for r in clarify.negotiation_records) / len(clarify.negotiation_records)
    assert clarify_gap < free_gap
    assert any(r.clarification_asked > 0 for r in clarify.negotiation_records)
    assert all(r.clarification_asked == 0 for r in free.negotiation_records)


def test_init_belief_derives_from_stated_need():
    world = create_negotiation_world(42, "belief-probe")
    engine = NegotiationEngine(world)
    firm_id = "firm_bio"
    latent = world.latent_needs[firm_id]
    stated = world.stated_needs[firm_id]
    belief = world.gov_beliefs[firm_id]
    engine._init_belief(belief, stated, latent)
    for component in COMPONENTS:
        truth = latent.truth.get(component, 0.70)
        disclosed = stated.disclosed.get(component, 0.0)
        expected = round(truth * disclosed * (0.45 + 0.55 * stated.clarity), 3)
        assert belief.components[component] == expected
    assert belief.confidence == round(0.35 + 0.35 * stated.clarity, 3)


def test_disclose_moves_belief_toward_truth():
    world = create_negotiation_world(42, "belief-probe")
    engine = NegotiationEngine(world)
    firm_id = "firm_bio"
    latent = world.latent_needs[firm_id]
    stated = world.stated_needs[firm_id]
    belief = world.gov_beliefs[firm_id]
    engine._init_belief(belief, stated, latent)
    before = dict(belief.components)
    # 完整披露三个敏感成分：belief 应上升且不超过真实值
    engine._apply_disclose(belief, latent, {"constraint": 1.0, "budget": 1.0, "commitment": 1.0})
    for component in ("constraint", "budget", "commitment"):
        assert before[component] <= belief.components[component]
        assert belief.components[component] <= latent.truth.get(component, 0.70) + 1e-9
    # 披露提升政府信心
    assert belief.confidence > 0.5


def test_paraphrase_confirm_and_correct():
    world = create_negotiation_world(42, "belief-probe")
    engine = NegotiationEngine(world)
    firm_id = "firm_bio"
    latent = world.latent_needs[firm_id]
    stated = world.stated_needs[firm_id]
    belief = world.gov_beliefs[firm_id]
    engine._init_belief(belief, stated, latent)
    # 企业确认政府复述：belief 向 truth 提升（每次 +0.12，封顶 truth）
    class Confirm:
        def __init__(self) -> None:
            self.confirmed = True
            self.correction = None
            self.components: dict[str, float] = {}
    engine._apply_paraphrase(belief, latent, Confirm())
    assert all(
        belief.components[c] <= latent.truth.get(c, 0.70) + 1e-9 for c in COMPONENTS
    )
    # 企业纠正复述：涉及成分直接对齐 truth
    class Correct:
        def __init__(self) -> None:
            self.confirmed = False
            self.correction = "预算口径有误"
            self.components: dict[str, float] = {"budget": 1.0, "mode": 1.0}
    engine._apply_paraphrase(belief, latent, Correct())
    assert belief.components["budget"] == latent.truth["budget"]
    assert belief.components["mode"] == latent.truth["mode"]


def test_gap_and_true_fit_are_bounded_and_consistent():
    world = create_negotiation_world(42, "belief-probe")
    engine = NegotiationEngine(world)
    firm_id = "firm_bio"
    latent = world.latent_needs[firm_id]
    stated = world.stated_needs[firm_id]
    belief = world.gov_beliefs[firm_id]
    engine._init_belief(belief, stated, latent)
    gap = engine._gap(belief)
    assert 0.0 <= gap <= 1.0
    assert round(1.0 - sum(belief.components.values()) / len(COMPONENTS), 4) == gap
    # belief 完全等于真实需求（可理解上限）时，剩余差距 = 1 - mean(truth)
    # —— truth<1 的成分（预算、承诺）永远存在无法消除的残余模糊
    belief.components = {c: latent.truth.get(c, 0.70) for c in COMPONENTS}
    assert engine._gap(belief) == round(
        1.0 - sum(latent.truth.values()) / len(COMPONENTS), 4
    )
    # 数学上 belief 全满 → 零差距（相对「完美理解」的度量）
    belief.components = {c: 1.0 for c in COMPONENTS}
    assert engine._gap(belief) == 0.0
    # 匹配度在边界内，且覆盖真实需求工具的方案得分更高
    option = {"tools": dict(latent.required_tools)}
    full_fit = engine._true_fit(latent, option)
    sparse_fit = engine._true_fit(latent, {"tools": {}})
    assert 0.0 <= sparse_fit <= full_fit <= 1.0


def test_low_quality_project_veto_path():
    # 政府不读取 unfeasible 标签；不同证据程序形成批准、试点、否决三种路径。
    free = _run(42, protocol="free")
    free_case = next(c for c in free.due_diligence_cases if c.firm_id == "firm_risky")
    assert free_case.decision == "approve"
    assert free_case.uncertainty > 0.60

    clarify = _run(42, protocol="clarify_first")
    clarify_case = next(c for c in clarify.due_diligence_cases if c.firm_id == "firm_risky")
    assert clarify_case.decision == "conditional_pilot"
    assert clarify_case.estimated_failure_probability > free_case.estimated_failure_probability

    verified = _run(42, protocol="constraints_first")
    verified_case = next(c for c in verified.due_diligence_cases if c.firm_id == "firm_risky")
    risky = next(r for r in verified.negotiation_records if r.firm_id == "firm_risky")
    assert verified_case.decision == "reject"
    assert risky.outcome == "terminated"
    assert "证据门控尽调否决" in (risky.fail_reason or "")
    assert all(
        audit.observation.get("hidden_quality_label_available") is False
        for audit in verified.action_audits
        if audit.action_type == "evidence_gated_due_diligence"
    )


def test_phased_commitment_raises_incentive_alignment():
    # 同一初始世界：分阶段承诺通过降低财政过度承诺风险提升激励对齐
    free = _accepted(_run(42, protocol="free"))
    phased = _accepted(_run(42, protocol="phased_commitment"))
    assert free and phased
    common = set(free) & set(phased)
    assert common, "same world must negotiate the same common firms under both protocols"
    # 对共同签约企业：分阶段激励对齐不低于自由协商（+0.10 加成，1.0 封顶后持平）
    for firm_id in common:
        assert phased[firm_id].incentive_alignment >= free[firm_id].incentive_alignment
    mean_free = sum(r.incentive_alignment for r in free.values()) / len(free)
    mean_phased = sum(r.incentive_alignment for r in phased.values()) / len(phased)
    assert mean_phased > mean_free


def test_each_firm_negotiates_exactly_once():
    world = _run(42, protocol="paraphrase_confirm", quarters=4)
    firm_ids = [r.firm_id for r in world.negotiation_records]
    assert len(firm_ids) == len(set(firm_ids))
    assert len(firm_ids) == len(world.firms)


def test_reproducible_for_same_seed():
    a = _run(42, protocol="clarify_first")
    b = _run(42, protocol="clarify_first")
    a_records = [(r.firm_id, r.outcome, r.policy_fit, r.gap_final) for r in a.negotiation_records]
    b_records = [(r.firm_id, r.outcome, r.policy_fit, r.gap_final) for r in b.negotiation_records]
    assert a_records == b_records


def test_counterfactual_comparison_shape():
    results = run_negotiation_comparison(seed=42, quarters=2)
    assert len(results) == 7
    names = {row["name"] for row in results}
    assert names == {"自由协商", "政策匹配", "澄清优先", "复述确认", "约束先行", "多方案协商", "分阶段承诺"}
    assert all(row["successful"] for row in results)
    assert all(row["agreements"] + row["terminated"] == 8 for row in results)


def test_pareto_frontier_returns_non_dominated_points():
    # 手工构造：A 高匹配低成本 → 支配 B（同匹配低成本）与 C（低成本低匹配）
    summary = [
        {"id": "free", "name": "自由", "metrics": {"avg_policy_fit": {"mean": 0.60}, "total_gov_cost": {"mean": 50.0}}},
        {"id": "clarify", "name": "澄清", "metrics": {"avg_policy_fit": {"mean": 0.80}, "total_gov_cost": {"mean": 55.0}}},
        {"id": "phased", "name": "分阶段", "metrics": {"avg_policy_fit": {"mean": 0.65}, "total_gov_cost": {"mean": 28.0}}},
        {"id": "missing", "name": "缺数据", "metrics": {"avg_policy_fit": {"mean": None}, "total_gov_cost": {"mean": None}}},
    ]
    frontier = _pareto_frontier(summary)
    ids = {point["id"] for point in frontier}
    assert "missing" not in ids
    # 三个有效点互不支配（澄清匹配更高但成本更高；分阶段成本更低但匹配更低；自由被两者夹住）
    assert ids == {"clarify", "phased"}
    assert [p["cost"] for p in frontier] == sorted(p["cost"] for p in frontier)


def test_matrix_output_contract_and_hypotheses():
    report = run_negotiation_matrix(seeds=[11, 42], quarters=2, mode="deterministic", save_report=False)
    assert report["schema_version"] == "1.0"
    assert len(report["negotiation_summary"]) == 7
    assert len(report["negotiation_runs"]) == 7 * 2
    assert len(report["language_probe"]) == 2 * 2  # free × formal/plain × 2 seeds
    assert report["failure_cases"] == []
    # 帕累托前沿：非空、按成本升序
    assert report["pareto_frontier"]
    costs = [point["cost"] for point in report["pareto_frontier"]]
    assert costs == sorted(costs)
    # H1-H7 全部支持
    assert {h["id"] for h in report["hypotheses"]} == {f"H{i}" for i in range(1, 8)}
    assert all(h["supported"] for h in report["hypotheses"])
    # 关键机制模式：澄清优先匹配度最高、分阶段承诺成本最低
    by_id = {row["id"]: row for row in report["negotiation_summary"]}
    fit = {row_id: row["metrics"]["avg_policy_fit"]["mean"] for row_id, row in by_id.items()}
    cost = {row_id: row["metrics"]["total_gov_cost"]["mean"] for row_id, row in by_id.items()}
    assert fit["clarify_first"] > fit["free"]
    assert cost["phased_commitment"] < cost["free"]
    assert "markdown" in report and report["markdown"].startswith("# InsideGov")


def test_matrix_hypothesis_h7_group_heterogeneity():
    # H7 的直接证据：低信任企业澄清边际收益 >> 常规企业
    report = run_negotiation_matrix(seeds=[11, 42], quarters=2, save_report=False)
    h7 = next(h for h in report["hypotheses"] if h["id"] == "H7")
    gains = h7["evidence"]["clarify_marginal_gain_by_group"]
    assert gains["low_trust"] > gains["regular"] + 0.3
    assert h7["evidence"]["gain_spread"] > 0.10


def test_serde_round_trip_preserves_negotiation_world():
    world = _run(42, protocol="clarify_first", quarters=2)
    restored = world_from_dict(copy.deepcopy(world.to_dict()))
    assert restored.id == world.id
    assert restored.negotiation_protocol == world.negotiation_protocol
    assert restored.language_style == world.language_style
    assert set(restored.latent_needs) == set(world.latent_needs)
    assert set(restored.stated_needs) == set(world.stated_needs)
    assert set(restored.gov_beliefs) == set(world.gov_beliefs)
    assert len(restored.negotiation_records) == len(world.negotiation_records)
    assert len(restored.cooperation_executions) == len(world.cooperation_executions)
    # 重建后继续推演：已协商企业不重复协商，记录保持一致
    a = NegotiationEngine(restored).run(1)
    b = NegotiationEngine(world_from_dict(copy.deepcopy(world.to_dict()))).run(1)
    assert len(a.negotiation_records) == len(b.negotiation_records)
    assert [r.firm_id for r in a.negotiation_records] == [r.firm_id for r in b.negotiation_records]
