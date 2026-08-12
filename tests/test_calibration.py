from insidegov.agents import DeterministicCognition
from insidegov.calibration import run_calibration_suite
from insidegov.experiments import run_ablation_matrix, run_experiment_matrix


def test_calibration_suite_passes():
    results = run_calibration_suite()
    assert results
    assert all(result["passed"] for result in results)


def test_ablation_matrix_changes_mechanisms_and_outcomes():
    results = run_ablation_matrix(42, 16)
    assert len(results) == 5
    assert results[2]["negotiation_rounds"] == 9
    assert results[-1]["cluster_size"] < results[0]["cluster_size"]


def test_multi_seed_matrix_reports_means_variance_and_failures(tmp_path):
    report = run_experiment_matrix(
        seeds=[11, 23, 42], quarters=12, include_llm=False, save_report=False,
    )
    row = report["strategy_summary"][0]
    assert row["attempted"] == 3
    assert row["successful"] == 3
    assert row["metrics"]["total_employment"]["mean"] is not None
    assert row["metrics"]["total_employment"]["variance"] is not None
    assert len(report["ablation_runs"]) == 15
    assert "失败案例" in report["markdown"]


def test_two_llm_strategies_are_recorded_as_failures_without_credentials(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    report = run_experiment_matrix(
        seeds=[11, 23], quarters=3, include_llm=True, save_report=False,
    )
    assert [row["id"] for row in report["strategy_summary"]] == [
        "deterministic", "deepseek-v4-flash", "deepseek-v4-pro",
    ]
    assert report["strategy_summary"][1]["successful"] == 0
    assert report["strategy_summary"][2]["successful"] == 0
    llm_failures = [case for case in report["failure_cases"] if "deepseek" in case["strategy"]]
    assert len(llm_failures) == 6
    assert sum(case["seed"] == "calibration" for case in llm_failures) == 2


def test_three_strategy_pipeline_runs_with_injected_llm_equivalents():
    report = run_experiment_matrix(
        seeds=[11, 23], quarters=3, include_llm=True, save_report=False,
        provider_factory=lambda _strategy: DeterministicCognition(),
    )
    assert len(report["strategy_summary"]) == 3
    assert all(row["successful"] == 2 for row in report["strategy_summary"])
    assert set(report["calibration"]) == {
        "deterministic", "deepseek-v4-flash", "deepseek-v4-pro",
    }
