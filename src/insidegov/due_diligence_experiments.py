from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import asdict

from .due_diligence import PROGRAMS, DueDiligenceEngine, due_diligence_metrics
from .scenarios import create_negotiation_world

DEFAULT_DUE_DILIGENCE_SEEDS = [3, 11, 23, 42, 57, 89, 101, 137]
SUMMARY_METRICS = (
    "precision", "recall", "specificity", "brier_score", "avg_rounds",
    "avg_elapsed_days", "diligence_cost", "avoided_fiscal_loss",
    "realized_fiscal_loss", "missed_opportunity",
)


def run_due_diligence_matrix(
    seeds: list[int] | None = None,
    programs: list[str] | None = None,
    thresholds: list[float] | None = None,
    mode: str = "deterministic",
    model_name: str | None = None,
) -> dict:
    selected_seeds = seeds or DEFAULT_DUE_DILIGENCE_SEEDS
    selected_programs = programs or list(PROGRAMS)
    unknown = [item for item in selected_programs if item not in PROGRAMS]
    if unknown:
        raise ValueError(f"unknown due diligence program(s): {', '.join(unknown)}")
    threshold_values = thresholds or [0.25, 0.35, 0.45, 0.50, 0.55, 0.65, 0.75]
    if any(value <= 0.0 or value >= 1.0 for value in threshold_values):
        raise ValueError("due diligence thresholds must be between 0 and 1")
    runs: list[dict] = []
    for program in selected_programs:
        for seed in selected_seeds:
            world = create_negotiation_world(
                seed, f"due-diligence-{program}-{seed}", "free", "plain", mode,
            )
            world.model_name = model_name
            world.due_diligence_program = program
            cases = DueDiligenceEngine(world).run_all(program)
            metrics = due_diligence_metrics(cases)
            action_counts = Counter(
                turn["action_id"]
                for case in cases for turn in case.agent_turns
                if turn.get("action_id")
            )
            runs.append({
                "program": program,
                "seed": seed,
                **metrics,
                "action_counts": dict(action_counts),
                "cases": [_case_payload(world, item) for item in cases],
                "agent_runtime": {
                    "providers": sorted({
                        item.provider for item in world.action_audits if item.provider
                    }),
                    "audited_agent_decisions": len(world.action_audits),
                    "fallback_count": sum(bool(item.fallback) for item in world.action_audits),
                },
            })
    summary = []
    for program in selected_programs:
        rows = [row for row in runs if row["program"] == program]
        summary.append({
            "id": program,
            "name": _program_name(program),
            "description": _program_description(program),
            "runs": len(rows),
            "metrics": {
                metric: {
                    "mean": round(statistics.fmean(float(row[metric]) for row in rows), 5),
                    "variance": round(statistics.pvariance(float(row[metric]) for row in rows), 5),
                }
                for metric in SUMMARY_METRICS
            },
            "action_counts": dict(sum(
                (Counter(row["action_counts"]) for row in rows), Counter()
            )),
        })
    threshold_curve = _threshold_sensitivity(selected_seeds, threshold_values)
    return {
        "schema_version": "1.0",
        "research_question": (
            "企业质量未知、披露具有策略性且尽调有成本时，何种证据获取与承诺程序"
            "能最小化误签、误拒和调查成本？"
        ),
        "configuration": {
            "seeds": selected_seeds,
            "programs": selected_programs,
            "thresholds": threshold_values,
            "mode": mode,
            "model_name": model_name,
            "hidden_label_visible_to_agents": False,
        },
        "agent_runtime": {
            "mode": mode,
            "model_name": model_name,
            "providers": sorted({
                provider for run in runs
                for provider in run["agent_runtime"]["providers"]
            }),
            "audited_agent_decisions": sum(
                run["agent_runtime"]["audited_agent_decisions"] for run in runs
            ),
            "fallback_count": sum(
                run["agent_runtime"]["fallback_count"] for run in runs
            ),
            "fixed_for_public_experience": mode == "llm",
        },
        "program_summary": summary,
        "program_runs": runs,
        "threshold_curve": threshold_curve,
        "decision_definitions": {
            "approve": "证据支持正式协商",
            "conditional_pilot": "只批准可逆试点，达标后再追加",
            "defer": "补充证据后重新议程化",
            "reject": "签约前否决",
        },
        "metric_definitions": {
            "false_positive": "实际成功，但被否决或降为风险试点",
            "false_negative": "实际失败，但程序批准或仅暂缓",
            "brier_score": "事前失败概率与事后结果之间的校准误差，越低越好",
        },
        "interpretation_boundary": (
            "潜在因子和结果由模拟参数生成；该矩阵验证程序内部判别力，"
            "在真实招商应用前仍需历史项目留出验证与专家编码。"
        ),
    }


def _threshold_sensitivity(seeds: list[int], thresholds: list[float]) -> list[dict]:
    rows = []
    for threshold in thresholds:
        all_cases = []
        for seed in seeds:
            world = create_negotiation_world(
                seed, f"threshold-{threshold}-{seed}", "free",
            )
            world.due_diligence_threshold = threshold
            cases = DueDiligenceEngine(world).run_all(
                "independent_verification", threshold,
            )
            all_cases.extend(cases)
        metrics = due_diligence_metrics(all_cases)
        failed = metrics["true_positive"] + metrics["false_negative"]
        succeeded = metrics["true_negative"] + metrics["false_positive"]
        rows.append({
            "threshold": threshold,
            "true_positive_rate": round(metrics["true_positive"] / failed, 4) if failed else 0.0,
            "false_positive_rate": round(metrics["false_positive"] / succeeded, 4) if succeeded else 0.0,
            "precision": metrics["precision"],
            "specificity": metrics["specificity"],
            "realized_fiscal_loss": metrics["realized_fiscal_loss"],
            "missed_opportunity": metrics["missed_opportunity"],
        })
    return rows


def _case_payload(world, case) -> dict:
    firm = world.firms[case.firm_id]
    return {
        **asdict(case),
        "firm_name": firm.name,
        "initial_trust": firm.perceived_credibility.get("city_qing", 0.5),
        "evidence_chain": [item.summary for item in case.evidence],
        "decision_used_hidden_label": False,
    }


def _program_name(program: str) -> str:
    return {
        "light_screen": "轻量筛查",
        "clarification_only": "只做企业澄清",
        "independent_verification": "独立证据核验",
        "red_team": "跨部门反方审查",
        "adaptive_staged": "自适应尽调＋分阶段承诺",
    }[program]


def _program_description(program: str) -> str:
    return {
        "light_screen": "低成本、快速，但主要依赖企业材料。",
        "clarification_only": "增加追问轮次，仍缺少外部交叉验证。",
        "independent_verification": "分别核验资金、技术、市场、治理与团队。",
        "red_team": "在独立核验后增加反方挑战，优先寻找失败解释。",
        "adaptive_staged": "根据当前风险与不确定性自主选择下一项证据，并保留可逆试点。",
    }[program]
