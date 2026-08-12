import json

from insidegov.demo import create_hefei_nio_demo
from insidegov.engine import SimulationEngine
from insidegov.experiments import run_experiment_matrix
from insidegov.reporting import ExperimentReportRepository
from insidegov.repository import WorldRepository
from insidegov.scenarios import create_full_lifecycle_world


def test_guided_demo_is_generated_from_common_history_and_persisted(tmp_path):
    repository = WorldRepository(tmp_path / "worlds")
    bundle = create_hefei_nio_demo(repository, seed=42, fiscal_multiplier=0.5)
    baseline = bundle["baseline"]
    branch = bundle["branch"]
    assert bundle["source"] == "live_deterministic_simulation"
    assert baseline.parent_id == branch.parent_id
    assert baseline.branched_from_quarter == branch.branched_from_quarter == 3
    assert baseline.quarter == branch.quarter == 16
    assert repository.load(baseline.id) is not None
    assert repository.snapshot_quarters(branch.id) == list(range(3, 17))
    assert len(bundle["replay"]["steps"]) == 6
    assert bundle["replay"]["synthetic_private_audit"]
    assert bundle["replay"]["internal_negotiation"]["final_tools"][
        "total_equity_support"
    ] == 70.0
    assert bundle["comparison"]["delta"]


def test_experiment_report_repository_drills_into_seed_world(tmp_path):
    report_root = tmp_path / "reports"
    matrix_root = tmp_path / "matrix-worlds"
    report_root.mkdir()
    matrix_root.mkdir()
    world = SimulationEngine(create_full_lifecycle_world(11, "matrix-deterministic-seed-11")).run(4)
    (matrix_root / f"{world.id}.json").write_text(
        json.dumps(world.to_dict(), ensure_ascii=False, default=str), encoding="utf-8"
    )
    report = run_experiment_matrix(
        seeds=[11, 23], quarters=4, include_llm=False, save_report=False,
    )
    report_id = "p1-matrix-test"
    (report_root / f"{report_id}.json").write_text(
        json.dumps(report, ensure_ascii=False, default=str), encoding="utf-8"
    )
    repository = ExperimentReportRepository(
        report_root=report_root,
        matrix_root=matrix_root,
        bundled_artifact=tmp_path / "missing.json",
    )
    loaded = repository.load(report_id)
    assert loaded is not None
    first = loaded["strategy_runs"][0]
    assert first["world_id"] == "matrix-deterministic-seed-11"
    assert first["world_available"] is True
    assert repository.load_world(first["world_id"]) is not None


def test_bundled_public_report_keeps_seed_drilldown_without_private_archives(tmp_path):
    repository = ExperimentReportRepository(
        report_root=tmp_path / "missing-reports",
        matrix_root=tmp_path / "missing-worlds",
    )
    summaries = repository.list()
    bundled = next(item for item in summaries if item["id"] == "p1-public-runs")
    assert bundled["kind"] == "p1_matrix"
    assert bundled["strategy_runs"] == 10
    report = repository.load("p1-public-runs")
    assert report is not None
    assert len(report["ablation_runs"]) == 25
    assert report["failure_cases"][0]["seed"] == 57
    assert all(not item["world_available"] for item in report["strategy_runs"])
