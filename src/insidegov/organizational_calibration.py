"""Source-backed organizational behavior calibration and quality evaluation.

This module deliberately separates three things that are often mixed together:

1. public facts used to configure a case;
2. observable organizational behavior used for calibration;
3. later historical outcomes held out for validation.

Private conversations that are absent from public records are never scored as
historical ground truth.  They remain simulated mechanisms and are reported as
unverifiable rather than counted as either matches or errors.
"""

from __future__ import annotations

import json
import math
import statistics
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .agents import CognitiveProvider
from .cases import (
    NIO_2020_20F_URL,
    NIO_AGREEMENT_URL,
    NIO_FULFILLMENT_URL,
    create_hefei_nio_world,
)
from .engine import SimulationEngine
from .models import WorldState
from .serde import world_from_dict

NIO_SHAREHOLDERS_AGREEMENT_URL = (
    "https://www.sec.gov/Archives/edgar/data/1736541/"
    "000110465920061585/nio-20191231xex4d36.htm"
)
MOFCOM_FRAMEWORK_URL = (
    "https://tradeinservices.mofcom.gov.cn/article/news/gnxw/202002/99256.html"
)
MOFCOM_HEADQUARTERS_URL = (
    "https://tradeinservices.mofcom.gov.cn/article/shidian/jyjliu/202201/125856.html"
)
SASAC_COALITION_URL = (
    "https://wap.sasac.gov.cn/n2588025/n2588129/c18459830/content.html"
)


@dataclass(slots=True)
class HistoricalBehaviorBenchmark:
    id: str
    label: str
    historical_date: str
    split: str
    evidence_status: str
    weight: float
    observable_claim: str
    matcher: str | None
    sources: list[str]
    rationale: str
    quantitative: bool = True


@dataclass(slots=True)
class BehaviorMatch:
    benchmark_id: str
    label: str
    split: str
    score: float | None
    weight: float
    observed: str
    matched: bool | None
    evidence_status: str
    sources: list[str]
    note: str = ""


@dataclass(slots=True)
class WorldBehaviorEvaluation:
    world_id: str
    seed: int
    process_mode: str
    calibration_score: float
    holdout_score: float
    role_boundary_score: float
    evidence_discipline_score: float
    sequence_score: float
    composite_score: float
    matches: list[BehaviorMatch] = field(default_factory=list)
    unsupported_internal_actions: list[str] = field(default_factory=list)


def hefei_nio_behavior_benchmarks() -> list[HistoricalBehaviorBenchmark]:
    """Return the case codebook, including explicitly unobservable mechanisms."""

    return [
        HistoricalBehaviorBenchmark(
            id="framework_before_definitive",
            label="先框架协议、后正式投资协议",
            historical_date="2020-02-25 → 2020-04-29",
            split="calibration",
            evidence_status="direct_public_record",
            weight=1.2,
            observable_claim=(
                "2月先签总部落户合作框架，4月再由多方签署正式投资与股东协议。"
            ),
            matcher="framework_before_definitive",
            sources=[MOFCOM_FRAMEWORK_URL, NIO_SHAREHOLDERS_AGREEMENT_URL],
            rationale="校准分阶段议程化，而不是要求公开材料披露每次内部会商。",
        ),
        HistoricalBehaviorBenchmark(
            id="hybrid_mobilization_and_review",
            label="招商推动与正式治理并存",
            historical_date="2020-02 → 2020-04",
            split="calibration",
            evidence_status="triangulated_inference",
            weight=0.8,
            observable_claim=(
                "疫情期间持续远程招商并形成框架协议；最终协议包含多投资人、公司治理、"
                "出资条件和正式权利义务。"
            ),
            matcher="hybrid_mobilization_and_review",
            sources=[MOFCOM_FRAMEWORK_URL, NIO_SHAREHOLDERS_AGREEMENT_URL],
            rationale=(
                "只校准非正式动员与正式审查两类机制均出现，不宣称已知真实部门行动顺序。"
            ),
        ),
        HistoricalBehaviorBenchmark(
            id="multi_party_investor_coalition",
            label="多层级投资主体联合出资",
            historical_date="2020-04-29",
            split="calibration",
            evidence_status="direct_public_record",
            weight=1.3,
            observable_claim=(
                "股东协议列明国投招商、安徽省高新投、合肥市建投等投资主体共同参与。"
            ),
            matcher="multi_party_investor_coalition",
            sources=[NIO_SHAREHOLDERS_AGREEMENT_URL, SASAC_COALITION_URL],
            rationale="检验组织世界是否把70亿元错误建模为单一财政局现金支出。",
        ),
        HistoricalBehaviorBenchmark(
            id="equity_not_cash_subsidy",
            label="核心工具是股权投资而非无条件现金补贴",
            historical_date="2020-04-29",
            split="calibration",
            evidence_status="direct_public_record",
            weight=1.4,
            observable_claim="战略投资者以70亿元现金增资取得约24.1%股权。",
            matcher="equity_not_cash_subsidy",
            sources=[NIO_AGREEMENT_URL, NIO_2020_20F_URL],
            rationale="金额是已使用的结构校准点，因此不能再次作为留出预测证据。",
        ),
        HistoricalBehaviorBenchmark(
            id="five_equity_installments",
            label="股权资本分期而非一次性支付",
            historical_date="2020-04-29",
            split="calibration",
            evidence_status="direct_public_record",
            weight=1.2,
            observable_claim="战略投资者70亿元按35、15、10、5、5亿元五期投入。",
            matcher="five_equity_installments",
            sources=[NIO_AGREEMENT_URL, NIO_SHAREHOLDERS_AGREEMENT_URL],
            rationale="校准合同结构；不要求模拟恰好复制每一期金额。",
        ),
        HistoricalBehaviorBenchmark(
            id="performance_contingent_support",
            label="后续支持与经营绩效条件挂钩",
            historical_date="2020-04-29",
            split="calibration",
            evidence_status="direct_public_record",
            weight=1.0,
            observable_claim=(
                "经开区租金、金融与税收支持以产能、采购额和车辆销售等绩效目标为条件。"
            ),
            matcher="performance_contingent_support",
            sources=[NIO_2020_20F_URL],
            rationale="检验合同是否具有条件性，而不是把所有承诺在签约时立即兑现。",
        ),
        HistoricalBehaviorBenchmark(
            id="early_cash_injection",
            label="首两期投资基本按期到账",
            historical_date="2020-06",
            split="holdout",
            evidence_status="direct_public_record",
            weight=1.4,
            observable_claim="截至6月底，首两期50亿元中48亿元已到账。",
            matcher="early_cash_injection",
            sources=[NIO_FULFILLMENT_URL, NIO_2020_20F_URL],
            rationale="留出节点；用归一化早期履约里程碑检验，不参与模式选择。",
        ),
        HistoricalBehaviorBenchmark(
            id="headquarters_operational",
            label="总部从协议进入实际运营",
            historical_date="2020-10-09",
            split="holdout",
            evidence_status="direct_public_record",
            weight=1.0,
            observable_claim="蔚来中国总部于2020年10月正式启用。",
            matcher="headquarters_operational",
            sources=[MOFCOM_HEADQUARTERS_URL],
            rationale="用项目投产/运营里程碑检验组织承诺是否进入执行状态。",
        ),
        HistoricalBehaviorBenchmark(
            id="continued_cluster_cooperation",
            label="落地后继续推进产业链合作",
            historical_date="2021以后",
            split="holdout",
            evidence_status="triangulated_public_record",
            weight=0.8,
            observable_claim="政企继续推进智能电动汽车产业集群与上下游协同。",
            matcher="continued_cluster_cooperation",
            sources=[MOFCOM_HEADQUARTERS_URL, SASAC_COALITION_URL],
            rationale="只能验证方向和是否出现扩散，不能把全市产业增长归因给单一项目。",
        ),
        HistoricalBehaviorBenchmark(
            id="private_department_dialogue",
            label="财政局具体否决措辞与会前游说网络",
            historical_date="2020-02 → 2020-04",
            split="unverifiable",
            evidence_status="not_publicly_observable",
            weight=0.0,
            observable_claim="公开材料不足以恢复财政局、招商部门和市领导的逐轮内部对话。",
            matcher=None,
            sources=[NIO_SHAREHOLDERS_AGREEMENT_URL],
            rationale="模型可以生成该机制，但不得将其标为真实历史事实或纳入命中率。",
            quantitative=False,
        ),
    ]


def evaluate_hefei_nio_behavior(
    calibration_world: WorldState,
    holdout_world: WorldState,
) -> WorldBehaviorEvaluation:
    """Score one run against observable case behavior with an honest holdout."""

    matches = [
        _match_benchmark(item, calibration_world, holdout_world)
        for item in hefei_nio_behavior_benchmarks()
    ]
    calibration_score = _weighted_score(matches, "calibration")
    holdout_score = _weighted_score(matches, "holdout")
    role_boundary_score = _role_boundary_score(calibration_world)
    evidence_discipline_score, unsupported = _evidence_discipline(calibration_world)
    sequence_score = _sequence_score(calibration_world)
    composite = 100 * (
        0.35 * calibration_score
        + 0.35 * holdout_score
        + 0.12 * role_boundary_score
        + 0.10 * evidence_discipline_score
        + 0.08 * sequence_score
    )
    return WorldBehaviorEvaluation(
        world_id=holdout_world.id,
        seed=holdout_world.seed,
        process_mode=holdout_world.process_mode,
        calibration_score=round(calibration_score * 100, 2),
        holdout_score=round(holdout_score * 100, 2),
        role_boundary_score=round(role_boundary_score * 100, 2),
        evidence_discipline_score=round(evidence_discipline_score * 100, 2),
        sequence_score=round(sequence_score * 100, 2),
        composite_score=round(composite, 2),
        matches=matches,
        unsupported_internal_actions=unsupported,
    )


def run_hefei_nio_organization_calibration(
    seeds: Iterable[int] = (11, 23, 42, 57, 89),
    candidate_modes: Iterable[str] = ("formal", "informal", "hybrid"),
    quarters: int = 16,
    output_dir: str | Path | None = None,
    cognition_factory: Callable[[str, int], CognitiveProvider] | None = None,
) -> dict[str, Any]:
    """Select a process mode on calibration events, then report holdout quality.

    The winning mode is chosen *only* using the calibration split.  Later cash
    injection, headquarters operation and cluster cooperation never influence
    model selection.  This prevents the most obvious form of historical leakage.
    """

    seed_list = list(seeds)
    mode_list = list(candidate_modes)
    if not seed_list:
        raise ValueError("at least one seed is required")
    if not mode_list or set(mode_list) - {"formal", "informal", "hybrid"}:
        raise ValueError("candidate_modes must contain formal, informal or hybrid")
    if quarters < 9:
        raise ValueError("quarters must be at least 9 for holdout milestone evaluation")

    evaluations: list[WorldBehaviorEvaluation] = []
    for mode in mode_list:
        for seed in seed_list:
            world = create_hefei_nio_world(
                seed,
                world_id=f"hefei-nio-org-calibration-{mode}-{seed}",
            )
            world.process_mode = mode
            cognition = cognition_factory(mode, seed) if cognition_factory else None
            engine = SimulationEngine(world, cognition=cognition)
            for _ in range(3):
                engine.step()
            calibration_world = world_from_dict(engine.world.to_dict())
            for _ in range(quarters - 3):
                engine.step()
            evaluations.append(evaluate_hefei_nio_behavior(calibration_world, engine.world))

    mode_summary = [_summarize_mode(mode, evaluations) for mode in mode_list]
    # Mode selection sees calibration metrics and boundary validity only.  It does
    # not use holdout_score or final composite_score.
    selected = max(
        mode_summary,
        key=lambda row: (
            row["selection_score"],
            row["calibration_score_mean"],
            -row["calibration_score_stdev"],
        ),
    )
    selected_mode = selected["process_mode"]
    selected_runs = [item for item in evaluations if item.process_mode == selected_mode]
    benchmark_summary = _summarize_benchmarks(selected_runs)
    quality_gaps = [item for item in benchmark_summary if item["score_mean"] < 90]
    zero_variation = all(
        row["calibration_score_stdev"] == 0 and row["holdout_score_stdev"] == 0
        for row in mode_summary
    )
    report = {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "case": "2020合肥—蔚来",
        "evaluation_type": "organizational_behavior_calibration_with_holdout",
        "cognition_policy": (
            "injected_provider" if cognition_factory else "deterministic"
        ),
        "seeds": seed_list,
        "candidate_modes": mode_list,
        "calibration_cutoff": "2020-04-29 definitive agreements",
        "holdout_events": [
            "2020-06 early cash injection",
            "2020-10 headquarters operational",
            "post-deal cluster cooperation",
        ],
        "selected_process_mode": selected_mode,
        "selection_rule": (
            "highest mean calibration-split score with role-boundary and evidence-discipline "
            "guardrails; holdout outcomes excluded from selection"
        ),
        "mode_summary": mode_summary,
        "selected_mode_quality": {
            "calibration_score_mean": _mean(item.calibration_score for item in selected_runs),
            "holdout_score_mean": _mean(item.holdout_score for item in selected_runs),
            "composite_score_mean": _mean(item.composite_score for item in selected_runs),
            "composite_score_stdev": _stdev(item.composite_score for item in selected_runs),
        },
        "selected_mode_benchmark_summary": benchmark_summary,
        "quality_gaps": quality_gaps,
        "diagnostics": {
            "zero_score_variation_across_seeds": zero_variation,
            "interpretation": (
                "各seed行为得分完全一致，说明真实案例的强参数锚定和确定性策略压过了"
                "随机异质性；这提高复现性，但不能作为行为鲁棒性的充分证据。"
                if zero_variation else
                "不同seed产生了可观察质量差异，应结合均值、方差和失败轨迹解释。"
            ),
        },
        "benchmarks": [asdict(item) for item in hefei_nio_behavior_benchmarks()],
        "runs": [
            {
                **asdict(item),
                "matches": [asdict(match) for match in item.matches],
            }
            for item in evaluations
        ],
        "limitations": [
            "70亿元股权总量已用于结构校准，不能再作为独立预测成功证据。",
            "公开材料没有披露逐轮内部会商，模拟对话只代表机制假设。",
            "季度是归一化政策阶段，不与现实自然月机械对应。",
            "后续全市产业链增长不能被识别为蔚来项目的单独因果贡献。",
            "单案例只能做内部效度检查，跨案例外部效度仍需第二个案例。",
            "确定性案例在当前seed集合上的行为得分可能缺少变异，不能替代LLM与专家复核。",
        ],
    }
    report["markdown"] = render_organization_calibration_markdown(report)
    if output_dir is not None:
        root = Path(output_dir)
        root.mkdir(parents=True, exist_ok=True)
        (root / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (root / "report.md").write_text(report["markdown"], encoding="utf-8")
    return report


def render_organization_calibration_markdown(report: dict[str, Any]) -> str:
    selected = report["selected_mode_quality"]
    lines = [
        "# 2020合肥—蔚来：组织行为校准与质量评估",
        "",
        "## 结论",
        "",
        f"- 校准集选择的过程模式：**{report['selected_process_mode']}**；",
        f"- 校准行为得分：**{selected['calibration_score_mean']:.1f}/100**；",
        f"- 留出历史节点得分：**{selected['holdout_score_mean']:.1f}/100**；",
        (
            f"- 综合质量：**{selected['composite_score_mean']:.1f}/100** "
            f"（跨seed标准差 {selected['composite_score_stdev']:.2f}）。"
        ),
        "",
        (
            "模式只根据2020年4月29日前的行为证据选择；6月到账、10月总部启用和后续"
            "产业协同为留出验证，不参与选择。"
        ),
        "",
        "## 模式比较",
        "",
        "| 模式 | 校准行为 | 留出验证 | 角色边界 | 证据纪律 | 顺序 | 综合 |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report["mode_summary"]:
        lines.append(
            f"| {row['process_mode']} | {row['calibration_score_mean']:.1f} | "
            f"{row['holdout_score_mean']:.1f} | {row['role_boundary_score_mean']:.1f} | "
            f"{row['evidence_discipline_score_mean']:.1f} | {row['sequence_score_mean']:.1f} | "
            f"{row['composite_score_mean']:.1f} |"
        )
    lines.extend([
        "",
        "## 证据纪律",
        "",
        (
            "财政局具体否决措辞、会前游说对象和真实内部行动顺序没有公开记录，因此被编码为"
            "`not_publicly_observable`，不进入命中率。系统只能说“模拟生成了一个可能机制”，"
            "不能说“复现了真实内部对话”。"
        ),
        "",
        "## 未完全匹配的节点",
        "",
        "## 主要限制",
        "",
    ])
    gaps = report.get("quality_gaps", [])
    if gaps:
        insertion = [
            f"- {item['label']}：{item['score_mean']:.1f}/100；{item['observed_example']}"
            for item in gaps
        ]
        marker = lines.index("## 主要限制")
        lines[marker:marker] = insertion + [""]
    else:
        marker = lines.index("## 主要限制")
        lines[marker:marker] = ["- 当前阈值下没有低于90分的节点。", ""]
    lines.extend(f"- {item}" for item in report["limitations"])
    return "\n".join(lines) + "\n"


def _match_benchmark(
    benchmark: HistoricalBehaviorBenchmark,
    calibration_world: WorldState,
    holdout_world: WorldState,
) -> BehaviorMatch:
    if not benchmark.quantitative or benchmark.matcher is None:
        return BehaviorMatch(
            benchmark.id,
            benchmark.label,
            benchmark.split,
            None,
            benchmark.weight,
            "公开资料不可观察；不评分",
            None,
            benchmark.evidence_status,
            benchmark.sources,
            benchmark.rationale,
        )
    matcher = globals()[f"_match_{benchmark.matcher}"]
    score, observed, note = matcher(calibration_world, holdout_world)
    score = min(1.0, max(0.0, float(score)))
    return BehaviorMatch(
        benchmark.id,
        benchmark.label,
        benchmark.split,
        round(score, 4),
        benchmark.weight,
        observed,
        score >= 0.75,
        benchmark.evidence_status,
        benchmark.sources,
        note,
    )


def _match_framework_before_definitive(train: WorldState, _: WorldState):
    rounds = sorted({item.quarter for item in train.external_negotiations if item.city_id == "city_lin"})
    score = 0.55 * min(1.0, len(rounds) / 2) + 0.45 * (train.selected_city_id == "city_lin")
    return score, f"合肥对外协商季度={rounds}；Q3选址={train.selected_city_id}", "阶段而非自然月对齐"


def _match_hybrid_mobilization_and_review(train: WorldState, _: WorldState):
    actions = [
        item for item in train.organization_actions
        if item.city_id == "city_lin" and item.authorized
    ]
    informal_ids = {
        "preconsult_finance", "mobilize_park_coalition", "frame_strategic_project",
        "disclose_fiscal_boundary", "broker_compromise", "propose_open_action",
    }
    formal_ids = {"risk_assessment", "legality_review", "collective_deliberation"}
    informal = sum(item.action_id in informal_ids for item in actions)
    formal = sum(item.action_id in formal_ids for item in actions)
    score = (0.5 if informal else 0.0) + (0.5 if formal else 0.0)
    return score, f"非正式动员动作={informal}；正式审查动作={formal}", "不解释为真实逐轮行动"


def _match_multi_party_investor_coalition(train: WorldState, _: WorldState):
    funds = len(train.investment_funds)
    reviewed = {
        item.actor_id for item in train.organization_actions
        if item.city_id == "city_lin" and item.action_id == "fund_due_diligence"
        and item.authorized
    }
    score = 0.55 * min(1.0, funds / 3) + 0.45 * min(1.0, len(reviewed) / 3)
    return score, f"独立资金池={funds}；发生尽调的主体={len(reviewed)}", ""


def _match_equity_not_cash_subsidy(train: WorldState, _: WorldState):
    offer = train.cities["city_lin"].active_offer
    if offer is None:
        return 0.0, "未形成合肥报价", ""
    total_equity = offer.total_equity_support
    amount_score = max(0.0, 1 - abs(total_equity - 70.0) / 70.0)
    structure_score = min(1.0, total_equity / max(total_equity + offer.subsidy, 1.0))
    score = 0.65 * amount_score + 0.35 * structure_score
    return score, (
        f"股权支持={total_equity:.2f}亿元；补贴={offer.subsidy:.2f}亿元"
    ), "70亿元是结构校准点，不计入留出预测"


def _match_five_equity_installments(train: WorldState, _: WorldState):
    offer = train.cities["city_lin"].active_offer
    if offer is None:
        return 0.0, "未形成支付计划", ""
    rows = [item for item in offer.payment_schedule if "equity" in item.item]
    count_score = max(0.0, 1 - abs(len(rows) - 5) / 5)
    staged_score = 1.0 if len({item.due_offset for item in rows}) >= 3 else 0.5
    score = 0.65 * count_score + 0.35 * staged_score
    return score, (
        f"股权相关期次={len(rows)}；到期阶段={sorted({item.due_offset for item in rows})}"
    ), "只校准分期结构，不拟合每期金额"


def _match_performance_contingent_support(train: WorldState, _: WorldState):
    offer = train.cities["city_lin"].active_offer
    if offer is None:
        return 0.0, "未形成条件承诺", ""
    conditional = [
        item.condition for item in offer.payment_schedule
        if item.condition not in {"contract_signed", "unconditional"}
    ]
    score = min(1.0, len(set(conditional)) / 3)
    return score, f"条件节点={sorted(set(conditional))}", ""


def _match_early_cash_injection(_: WorldState, holdout: WorldState):
    early = [
        item for item in holdout.promises
        if item.city_id == "city_lin" and item.item == "external_equity"
        and item.due_quarter <= 5
    ]
    paid = sum(item.paid_amount for item in early)
    # Historical holdout is 48 of the first 50 billion.  The model is rewarded
    # for both substantial fulfillment and approximate timing, not exact identity.
    amount_score = max(0.0, 1 - abs(paid - 48.0) / 48.0)
    fulfillment_score = sum(item.paid_amount > 0 for item in early) / max(len(early), 1)
    score = 0.7 * amount_score + 0.3 * fulfillment_score
    return score, f"归一化早期外部股权到账={paid:.2f}亿元", "历史基准48亿元"


def _match_headquarters_operational(_: WorldState, holdout: WorldState):
    anchor = holdout.firms["firm_nova"]
    milestone_quarters = [
        item.quarter for item in holdout.events
        if item.kind == "milestone" and "投产" in item.title
    ]
    on_time = bool(milestone_quarters and min(milestone_quarters) <= 9)
    score = 1.0 if on_time else (0.65 if anchor.operating else min(0.6, anchor.project_progress))
    return score, (
        f"项目进度={anchor.project_progress:.1%}；首次投产里程碑="
        f"{min(milestone_quarters) if milestone_quarters else '无'}"
    ), "用Q9作为归一化总部运营节点"


def _match_continued_cluster_cooperation(_: WorldState, holdout: WorldState):
    final = holdout.history[-1]
    score = min(1.0, max(0.0, (final.cluster_size - 1) / 8))
    return score, f"Q{holdout.quarter}集群规模={final.cluster_size}", "只评价扩散方向"


def _sequence_score(world: WorldState) -> float:
    actions = [
        item for item in world.organization_actions
        if item.city_id == "city_lin" and item.authorized
    ]
    indexed = {
        "mobilization": min((item.quarter for item in actions if item.action_id in {
            "preconsult_finance", "mobilize_park_coalition", "frame_strategic_project",
            "request_materials", "clarify_need",
        }), default=99),
        "formal_review": min((item.quarter for item in actions if item.action_id in {
            "risk_assessment", "legality_review", "collective_deliberation",
        }), default=99),
        "fund_review": min((item.quarter for item in actions if item.action_id == "fund_due_diligence"), default=99),
    }
    present = sum(value < 99 for value in indexed.values()) / 3
    ordered = 1.0 if indexed["mobilization"] <= indexed["formal_review"] <= indexed["fund_review"] else 0.5
    return 0.7 * present + 0.3 * ordered


def _role_boundary_score(world: WorldState) -> float:
    relevant = [item for item in world.organization_actions if item.city_id == "city_lin"]
    if not relevant:
        return 0.0
    violations = 0
    for item in relevant:
        if item.action_id == "fund_due_diligence" and item.actor_role != "fund":
            violations += 1
        if item.action_id == "legality_review" and item.actor_role != "legal":
            violations += 1
        if item.action_id == "risk_assessment" and item.actor_role != "finance":
            violations += 1
        if item.action_id == "collective_deliberation" and item.actor_role != "city_leader":
            violations += 1
    return max(0.0, 1 - violations / len(relevant))


def _evidence_discipline(world: WorldState) -> tuple[float, list[str]]:
    relevant = [item for item in world.organization_actions if item.city_id == "city_lin"]
    if not relevant:
        return 0.0, ["没有组织行动可审计"]
    grounded = [item for item in relevant if item.evidence_ids]
    unsupported = [
        f"Q{item.quarter}:{item.actor_id}:{item.action_id}"
        for item in relevant if not item.evidence_ids
    ]
    # Internally generated rationales are acceptable only when kept in the audit
    # trail as simulation output.  They are not promoted into the benchmark.
    return len(grounded) / len(relevant), unsupported


def _weighted_score(matches: list[BehaviorMatch], split: str) -> float:
    rows = [item for item in matches if item.split == split and item.score is not None]
    denominator = sum(item.weight for item in rows)
    return sum(float(item.score) * item.weight for item in rows) / max(denominator, 1e-9)


def _summarize_mode(
    mode: str, evaluations: list[WorldBehaviorEvaluation]
) -> dict[str, Any]:
    rows = [item for item in evaluations if item.process_mode == mode]
    calibration = _mean(item.calibration_score for item in rows)
    boundary = _mean(item.role_boundary_score for item in rows)
    evidence = _mean(item.evidence_discipline_score for item in rows)
    sequence = _mean(item.sequence_score for item in rows)
    selection_score = 0.70 * calibration + 0.12 * boundary + 0.10 * evidence + 0.08 * sequence
    return {
        "process_mode": mode,
        "runs": len(rows),
        "selection_score": round(selection_score, 2),
        "calibration_score_mean": calibration,
        "calibration_score_stdev": _stdev(item.calibration_score for item in rows),
        "holdout_score_mean": _mean(item.holdout_score for item in rows),
        "holdout_score_stdev": _stdev(item.holdout_score for item in rows),
        "role_boundary_score_mean": boundary,
        "evidence_discipline_score_mean": evidence,
        "sequence_score_mean": sequence,
        "composite_score_mean": _mean(item.composite_score for item in rows),
        "composite_score_stdev": _stdev(item.composite_score for item in rows),
    }


def _summarize_benchmarks(
    evaluations: list[WorldBehaviorEvaluation],
) -> list[dict[str, Any]]:
    benchmark_rows: dict[str, list[BehaviorMatch]] = {}
    for evaluation in evaluations:
        for match in evaluation.matches:
            if match.score is not None:
                benchmark_rows.setdefault(match.benchmark_id, []).append(match)
    results = []
    for benchmark in hefei_nio_behavior_benchmarks():
        rows = benchmark_rows.get(benchmark.id, [])
        if not rows:
            continue
        results.append({
            "benchmark_id": benchmark.id,
            "label": benchmark.label,
            "split": benchmark.split,
            "score_mean": _mean(float(item.score) * 100 for item in rows),
            "score_stdev": _stdev(float(item.score) * 100 for item in rows),
            "observed_example": rows[0].observed,
            "evidence_status": benchmark.evidence_status,
        })
    return results


def _mean(values: Iterable[float]) -> float:
    rows = list(values)
    return round(statistics.fmean(rows), 2) if rows else math.nan


def _stdev(values: Iterable[float]) -> float:
    rows = list(values)
    return round(statistics.stdev(rows), 2) if len(rows) > 1 else 0.0
