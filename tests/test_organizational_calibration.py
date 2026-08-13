import json

from fastapi.testclient import TestClient

from insidegov.api import app
from insidegov.organizational_calibration import (
    hefei_nio_behavior_benchmarks,
    run_hefei_nio_organization_calibration,
)

client = TestClient(app)


def test_case_codebook_separates_calibration_holdout_and_unobservable_events():
    benchmarks = hefei_nio_behavior_benchmarks()
    assert {item.split for item in benchmarks} == {
        "calibration", "holdout", "unverifiable",
    }
    unobservable = [item for item in benchmarks if item.split == "unverifiable"]
    assert unobservable
    assert all(not item.quantitative and item.matcher is None for item in unobservable)
    assert all(item.sources for item in benchmarks)


def test_behavior_calibration_selects_mode_without_using_holdout(tmp_path):
    report = run_hefei_nio_organization_calibration(
        seeds=[11, 42],
        quarters=16,
        output_dir=tmp_path,
    )
    assert report["selected_process_mode"] == "hybrid"
    assert "holdout outcomes excluded" in report["selection_rule"]
    assert report["selected_mode_quality"]["calibration_score_mean"] > 90
    assert report["selected_mode_quality"]["holdout_score_mean"] < 100
    summaries = {item["process_mode"]: item for item in report["mode_summary"]}
    assert summaries["hybrid"]["selection_score"] > summaries["formal"]["selection_score"]
    assert summaries["hybrid"]["selection_score"] > summaries["informal"]["selection_score"]
    assert report["quality_gaps"]
    assert any(
        item["benchmark_id"] == "early_cash_injection"
        for item in report["quality_gaps"]
    )
    assert report["diagnostics"]["zero_score_variation_across_seeds"] is True
    assert (tmp_path / "report.json").exists()
    assert (tmp_path / "report.md").exists()
    saved = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert saved["selected_process_mode"] == "hybrid"


def test_behavior_calibration_api_returns_source_backed_report():
    response = client.get(
        "/cases/hefei-nio/organization-calibration",
        params={"seeds": "42", "modes": "formal,hybrid", "quarters": 16},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["evaluation_type"] == "organizational_behavior_calibration_with_holdout"
    assert payload["selected_process_mode"] == "hybrid"
    assert any(
        item["evidence_status"] == "not_publicly_observable"
        for item in payload["benchmarks"]
    )


def test_formal_mode_no_longer_leaks_informal_discretionary_actions():
    report = run_hefei_nio_organization_calibration(
        seeds=[42], candidate_modes=["formal", "hybrid"], quarters=16,
    )
    formal = next(item for item in report["runs"] if item["process_mode"] == "formal")
    hybrid = next(item for item in report["runs"] if item["process_mode"] == "hybrid")
    assert formal["calibration_score"] < hybrid["calibration_score"]
