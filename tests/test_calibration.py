from insidegov.calibration import run_calibration_suite
from insidegov.experiments import run_ablation_matrix


def test_calibration_suite_passes():
    results = run_calibration_suite()
    assert results
    assert all(result["passed"] for result in results)


def test_ablation_matrix_changes_mechanisms_and_outcomes():
    results = run_ablation_matrix(42, 16)
    assert len(results) == 5
    assert results[2]["negotiation_rounds"] == 9
    assert results[-1]["cluster_size"] < results[0]["cluster_size"]
