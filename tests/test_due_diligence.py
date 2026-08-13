from insidegov.api import _public_world
from insidegov.due_diligence import DueDiligenceEngine, due_diligence_metrics
from insidegov.due_diligence_experiments import run_due_diligence_matrix
from insidegov.scenarios import create_negotiation_world
from insidegov.serde import world_from_dict


def _cases(seed: int, program: str, threshold: float = 0.5):
    world = create_negotiation_world(seed, f"test-{program}-{seed}", "free")
    world.due_diligence_program = program
    return world, DueDiligenceEngine(world).run_all(program, threshold)


def test_agents_never_receive_hidden_risk_profile() -> None:
    world, cases = _cases(3, "adaptive_staged")
    assert cases
    for audit in world.action_audits:
        if audit.action_type != "evidence_gated_due_diligence":
            continue
        assert audit.observation["hidden_quality_label_available"] is False
        assert "financing_capacity" not in audit.observation
        assert audit.rule_adjustment.get("hidden_profile_access") is False or (
            audit.rule_adjustment.get("reason") in {"authorized", "verified_legal_red_flag"}
        )


def test_independent_evidence_separates_claim_from_observation() -> None:
    _, cases = _cases(3, "independent_verification")
    risky = next(item for item in cases if item.firm_id == "firm_risky")
    assert risky.evidence
    assert any(item.source_type != "enterprise_material" for item in risky.evidence)
    assert any(item.conflict > 0.15 for item in risky.evidence)
    assert risky.estimated_failure_probability > risky.prior_failure_probability


def test_programs_trade_accuracy_for_cost_and_reversibility() -> None:
    report = run_due_diligence_matrix(seeds=[3, 11, 23, 42], thresholds=[0.35, 0.5, 0.75])
    summary = {item["id"]: item for item in report["program_summary"]}
    light = summary["light_screen"]["metrics"]
    verified = summary["independent_verification"]["metrics"]
    adaptive = summary["adaptive_staged"]["metrics"]
    assert verified["recall"]["mean"] > light["recall"]["mean"]
    assert verified["diligence_cost"]["mean"] > light["diligence_cost"]["mean"]
    assert adaptive["missed_opportunity"]["mean"] < verified["missed_opportunity"]["mean"]
    assert len(report["threshold_curve"]) == 3
    assert report["threshold_curve"][0]["false_positive_rate"] >= report["threshold_curve"][-1]["false_positive_rate"]


def test_due_diligence_metrics_count_both_error_types() -> None:
    _, cases = _cases(3, "independent_verification")
    metrics = due_diligence_metrics(cases)
    assert metrics["true_positive"] > 0
    assert metrics["false_positive"] >= 0
    assert metrics["true_positive"] + metrics["false_negative"] == sum(
        item.actual_outcome == "failed" for item in cases
    )


def test_due_diligence_round_trip() -> None:
    world, _ = _cases(3, "adaptive_staged")
    restored = world_from_dict(world.to_dict())
    assert restored.project_risk_profiles.keys() == world.project_risk_profiles.keys()
    assert len(restored.due_diligence_cases) == len(world.due_diligence_cases)
    assert restored.due_diligence_cases[0].evidence[0].source_type


def test_public_world_redacts_outcome_generating_profile() -> None:
    world = create_negotiation_world(3, "redaction-test", "free")
    public = _public_world(world)
    profile = public["project_risk_profiles"]["firm_risky"]
    assert profile["redacted"] is True
    assert "technology_maturity" not in profile
    assert "technology_maturity" in profile["fields"]
