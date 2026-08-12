"""Source-backed public cases used to calibrate demonstration worlds."""

from __future__ import annotations

from .models import Event
from .scenarios import create_full_lifecycle_world

NIO_AGREEMENT_URL = (
    "https://ir.nio.com/news-events/news-releases/news-release-details/"
    "nio-announces-entry-definitive-agreements/"
)
NIO_FULFILLMENT_URL = (
    "https://ir.nio.com/news-events/news-releases/news-release-details/"
    "nio-announces-substantial-completion-cash-injections/"
)
NIO_2020_20F_URL = (
    "https://www.sec.gov/Archives/edgar/data/1736541/"
    "000110465921046834/nio-20201231x20f.htm"
)
HEFEI_STATISTICS_URL = "http://www.tjcn.org/tjgb/12ah/36644.html"
XINHUA_CLUSTER_URL = "https://www.news.cn/fortune/2023-06/01/c_1129663466.htm"


def _source(
    evidence: str,
    value: float,
    provenance: str,
    source_url: str | None,
    confidence: float,
    mapping_note: str = "",
) -> dict:
    return {
        "evidence": evidence,
        "suggested_value": value,
        "final_value": value,
        "provenance": provenance,
        "source_url": source_url,
        "confidence": confidence,
        "mapping_note": mapping_note,
        "status": "confirmed_for_demo",
    }


def create_hefei_nio_world(seed: int = 42, world_id: str = "hefei-nio-2020"):
    """Calibrate the existing lifecycle model to the 2020 Hefei–NIO case.

    Public facts are retained separately from expert/model mappings. The simulator
    is not forced to reproduce the historical outcome; it must still negotiate,
    select a city, settle promises and evolve suppliers through the normal engine.
    """
    world = create_full_lifecycle_world(seed, world_id)
    world.name = "真实案例校准：2020合肥—蔚来"
    hefei = world.cities["city_lin"]
    hefei.name = "合肥市"
    hefei.fiscal_budget = 762.9
    hefei.available_budget = 190.725
    hefei.committed_expenditure = 20.0
    hefei.debt = 500.0
    hefei.industrial_land = 650.0
    hefei.talent_pool = 78.0
    hefei.supply_chain = 68.0
    hefei.administrative_capacity = 92.0
    hefei.environmental_capacity = 72.0
    hefei.objective_credibility = 0.92

    anchor = world.firms["firm_nova"]
    anchor.name = "蔚来中国"
    anchor.investment_capacity = 220.3
    anchor.cash = 42.6
    anchor.land_need = 140.0
    anchor.jobs_capacity = 2500
    anchor.production_capacity = 12.0
    anchor.technology = 88.0
    anchor.private_intent = 0.90
    anchor.minimum_utility = 68.0
    anchor.perceived_credibility["city_lin"] = 0.92
    world.agents["firm_nova_board"].name = "蔚来中国决策层"
    world.agents["firm_nova_board"].private_facts.update({
        "true_intent": 0.90,
        "historical_cash_commitment": 42.6,
        "historical_asset_consideration": 177.7,
    })
    world.agents["city_lin_finance"].private_facts.update({
        "reserve_floor": 86.0,
        "stress_limit": 0.76,
    })
    world.agents["city_lin_investment"].private_facts.update({
        "competitive_intensity": 0.88,
        "cash_preference": 0.28,
    })

    world.parameter_provenance = {
        "city_lin.fiscal_budget": _source(
            "2020年合肥一般公共预算收入762.90亿元；它是财政规模口径，不等于项目可动用资金。",
            762.9, "public_source", HEFEI_STATISTICS_URL, 0.90,
        ),
        "city_lin.available_budget": _source(
            "以一般公共预算收入的25%作为演示世界可调度财力；公开资料没有给出项目专属可用余额。",
            190.725, "expert_judgment", HEFEI_STATISTICS_URL, 0.45,
            "762.9×25%；必须做15%—35%敏感性分析。",
        ),
        "city_lin.objective_credibility": _source(
            "2020年6月首两期50亿元中已到账48亿元；2020年年报确认双方现金出资义务全部履行。",
            0.92, "expert_judgment", NIO_2020_20F_URL, 0.78,
            "把按期/最终履行记录映射为0—1初始信用，不是现实概率估计。",
        ),
        "city_lin.supply_chain": _source(
            "合肥已有江淮12万辆产能制造基地；到2022年全市新能源汽车上下游企业超过300家。",
            68.0, "expert_judgment", XINHUA_CLUSTER_URL, 0.62,
            "产业事实映射到0—100供应链指数。",
        ),
        "city_lin.talent_pool": _source(
            "公开协议仅说明总部、研发、销售、供应链和制造一体化布局，未给出可直接换算的人才池。",
            78.0, "model_assumption", NIO_AGREEMENT_URL, 0.30,
        ),
        "city_lin.administrative_capacity": _source(
            "协议在2020年二季度交割，6月底已基本完成前两期注资。",
            92.0, "expert_judgment", NIO_FULFILLMENT_URL, 0.65,
            "将交割与到账速度映射为0—100行政执行指数。",
        ),
        "firm_nova.investment_capacity": _source(
            "企业注入177.7亿元核心资产并投入42.6亿元现金，合计220.3亿元。",
            220.3, "public_source", NIO_AGREEMENT_URL, 0.98,
        ),
        "firm_nova.cash": _source(
            "蔚来承诺向蔚来中国投入42.6亿元现金。",
            42.6, "public_source", NIO_AGREEMENT_URL, 0.99,
        ),
        "firm_nova.production_capacity": _source(
            "2020年年报披露江淮合作工厂年产能12万辆。",
            12.0, "public_source", NIO_2020_20F_URL, 0.95,
            "模拟单位为万辆/年。",
        ),
        "firm_nova.jobs_capacity": _source(
            "年报披露公司全球全职员工7763人，但未披露该项目新增本地就业。",
            2500.0, "model_assumption", NIO_2020_20F_URL, 0.25,
            "不能把7763名全球员工直接当作合肥新增就业；演示值待地方就业数据校准。",
        ),
        "historical_contract.strategic_equity": _source(
            "战略投资者以现金向蔚来中国投资70亿元，取得合计24.1%股权。",
            70.0, "public_source", NIO_AGREEMENT_URL, 0.99,
            "用于历史对照，不直接写入Agent提案或规则结算。",
        ),
        "historical_contract.payment_schedule": {
            "evidence": "战略投资者五期投入：35、15、10、5、5亿元；截止日依次为交割后5个工作日、2020-06-30、2020-09-30、2020-12-31、2021-03-31。",
            "final_value": [35.0, 15.0, 10.0, 5.0, 5.0],
            "provenance": "public_source", "source_url": NIO_AGREEMENT_URL,
            "confidence": 0.99, "mapping_note": "历史核验基准，不强制模拟复制。",
            "status": "confirmed_for_demo",
        },
        "supplier.entry_window": _source(
            "2022年合肥新能源汽车新签约项目145个、全产业链企业300余家，但无法识别蔚来单独贡献。",
            7.0, "model_assumption", XINHUA_CLUSTER_URL, 0.35,
            "供应商在Q10—Q16进入，窗口宽度7季；需用企业级落地日期重校准。",
        ),
    }
    world.events.append(Event(
        quarter=0, kind="material_import", title="真实案例参数已装载",
        detail="2020合肥—蔚来公开事实与模型映射已分层；历史结果不会覆盖Agent决策。",
        severity="success",
    ))
    return world
