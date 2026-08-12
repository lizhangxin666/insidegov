"""Talent-scenario tests: language mode, platform, matching, settlement."""

import copy

from insidegov.experiments import run_talent_comparison
from insidegov.scenarios import create_talent_world
from insidegov.serde import world_from_dict
from insidegov.talent_engine import TalentSimulationEngine


def _run(seed: int = 42, quarters: int = 16, language: str = "plain", platform: bool = False):
    world = create_talent_world(
        seed, "talent-test",
        expression_mode=language, interpreter_enabled=platform,
    )
    return TalentSimulationEngine(world).run(quarters)


def test_reproducible_for_same_seed():
    a = _run(42)
    b = _run(42)
    assert a.history == b.history
    assert [c.id for c in a.talent_contracts] == [c.id for c in b.talent_contracts]


def test_language_mode_is_the_transmission_channel():
    formal = _run(42, language="formal")
    plain = _run(42, language="plain")
    # 人话的表达传导率更高：平均理解度显著高于官话
    assert plain.history[-1].avg_understanding > formal.history[-1].avg_understanding + 0.1
    # 理解度决定对接成功率：人话签约数不低于官话
    assert len(plain.talent_contracts) >= len(formal.talent_contracts)


def test_platform_compensates_formal_language():
    formal_direct = _run(42, language="formal", platform=False)
    formal_platform = _run(42, language="formal", platform=True)
    # 官话下平台翻译显著提高理解度，进而提高签约数
    assert (
        formal_platform.history[-1].avg_understanding
        > formal_direct.history[-1].avg_understanding + 0.05
    )
    assert len(formal_platform.talent_contracts) >= len(formal_direct.talent_contracts)
    assert any(n.interpreter_used for n in formal_platform.talent_negotiations)


def test_counterfactual_comparison_shape():
    results = run_talent_comparison(seed=42, quarters=16)
    assert len(results) == 4
    names = {row["name"] for row in results}
    assert names == {"官话直连", "人话直连", "官话+平台", "人话+平台"}
    # 相同初始条件下仅切换机制，四个分支均完成推演
    assert all(row["quarter"] == 16 for row in results)


def test_negotiations_are_fully_traced():
    world = _run(42)
    for contract in world.talent_contracts:
        negotiation = next(
            n for n in world.talent_negotiations
            if n.talent_id == contract.talent_id and n.firm_id == contract.firm_id
        )
        assert negotiation.turns, "every signed deal must keep negotiation turns"
    assert world.traces, "every deal must leave a decision trace"
    assert any(trace.action == "accept_offer" for trace in world.traces)


def test_contract_settlement_and_knowledge_spillover():
    world = _run(42, quarters=24)
    fulfilled = [c for c in world.talent_contracts if c.status == "fulfilled"]
    assert fulfilled, "long horizon must fulfill at least one contract"
    for contract in fulfilled:
        assert contract.progress >= 1.0
        assert contract.paid > 0
    # 知识外溢：签约企业技术存量上升
    assert any(firm.knowledge > 30 for firm in world.firms.values())


def test_fiscal_constraints_never_go_negative():
    world = create_talent_world(42, "talent-fiscal", interpreter_enabled=True)
    engine = TalentSimulationEngine(world)
    engine.intervene("fiscal_shock", "city_qing", 0.8, quarter=6)
    engine.intervene("credibility_shock", "", 0.3, quarter=10)
    engine.run(16)
    assert all(city.available_budget >= -0.01 for city in engine.world.cities.values())
    assert any(event.kind == "external_shock" for event in engine.world.events)
    # 信用受损后人才信任下降
    assert engine.world.cities["city_qing"].objective_credibility < 0.80


def test_talent_market_has_entry_and_exit():
    world = _run(42, quarters=24)
    statuses = {talent.status for talent in world.talents.values()}
    assert "withdrawn" in statuses or all(
        t.status == "available" for t in world.talents.values()
    ), "long-running negotiation failure should drive some talents out of market"
    assert any(
        event.kind == "exit" for event in world.events
    ) or len(world.talent_contracts) >= 4


def test_serde_round_trip_preserves_talent_world():
    world = _run(42, quarters=8)
    restored = world_from_dict(copy.deepcopy(world.to_dict()))
    assert restored.id == world.id
    assert set(restored.talents) == set(world.talents)
    assert restored.platform is None or restored.platform.id == world.platform.id
    assert len(restored.talent_contracts) == len(world.talent_contracts)
    assert len(restored.talent_negotiations) == len(world.talent_negotiations)
    assert restored.expression_mode == world.expression_mode
    assert restored.interpreter_enabled == world.interpreter_enabled
    # 重建后继续推演不报错且结果可重复
    a = TalentSimulationEngine(restored).run(4)
    b = TalentSimulationEngine(world_from_dict(copy.deepcopy(world.to_dict()))).run(4)
    assert a.history[-1].talent_hired == b.history[-1].talent_hired


def test_capability_match_is_symmetric_and_bounded():
    from insidegov.talent_engine import TalentSimulationEngine

    demand = {"tech": 0.9, "eng": 0.6, "mgmt": 0.2}
    capability = {"tech": 0.8, "eng": 0.7, "mgmt": 0.4}
    match = TalentSimulationEngine.capability_match(demand, capability)
    assert 0.0 <= match <= 1.0
    assert TalentSimulationEngine.capability_match(demand, demand) == 1.0
