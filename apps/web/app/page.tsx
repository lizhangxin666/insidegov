"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { API_BASE, api, type Capability, type Metric, type World } from "./lib/api";

const phaseNames: Record<string, string> = {
  recruitment: "招商竞争", delivery: "承诺履约", industrialization: "产业演化",
};
const tones = ["amber", "cyan", "violet"];

export default function Home() {
  const [world, setWorld] = useState<World | null>(null);
  const [capability, setCapability] = useState<Capability | null>(null);
  const [worldList, setWorldList] = useState<Array<{ id: string; name: string; quarter: number; parent_id: string | null; policy_mode: string }>>([]);
  const [busy, setBusy] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState("");
  const [policyMode, setPolicyMode] = useState("deterministic");
  const [model, setModel] = useState("deepseek-v4-flash");
  const [detail, setDetail] = useState<"negotiations" | "trace" | "about" | null>(null);

  const remember = useCallback((next: World) => {
    setWorld(next);
    window.localStorage.setItem("insidegov_world_id", next.id);
  }, []);

  const refreshList = useCallback(async () => setWorldList(await api.listWorlds()), []);

  const create = useCallback(async (mode = policyMode, selectedModel = model) => {
    setBusy(true); setError("");
    try {
      remember(await api.createWorld(42, mode, selectedModel));
      await refreshList();
    } catch (caught) { setError(`无法连接模拟 API：${String(caught)}`); }
    finally { setBusy(false); }
  }, [model, policyMode, refreshList, remember]);

  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const caps = await api.capabilities();
        if (!alive) return;
        setCapability(caps); setModel(caps.default_model);
        const id = window.localStorage.getItem("insidegov_world_id");
        if (id) {
          try { remember(await api.getWorld(id)); }
          catch { await create("deterministic", caps.default_model); }
        } else await create("deterministic", caps.default_model);
        await refreshList();
      } catch (caught) { if (alive) setError(`后端未就绪：${String(caught)}`); }
    })();
    return () => { alive = false; };
  }, [create, refreshList, remember]);

  async function step() {
    if (!world || busy) return;
    setBusy(true); setError("");
    try {
      const next = await api.step(world.id);
      remember(next);
      if (next.quarter >= 16) setPlaying(false);
    }
    catch (caught) { setError(String(caught)); }
    finally { setBusy(false); }
  }

  useEffect(() => {
    if (!playing || !world || world.quarter >= 16) return;
    const timer = window.setTimeout(() => void step(), 700);
    return () => window.clearTimeout(timer);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, world?.quarter]);

  async function createBranch() {
    if (!world) return;
    setBusy(true);
    try { remember(await api.branch(world.id)); await refreshList(); }
    finally { setBusy(false); }
  }

  async function intervene(kind: string, target: string, value: number) {
    if (!world) return;
    setBusy(true);
    try {
      await api.intervene(world.id, kind, target, value);
      remember(await api.step(world.id));
    } finally { setBusy(false); }
  }

  const latest = world?.history.at(-1);
  const cities = world ? Object.values(world.cities) : [];
  const selected = world?.selected_city_id ? world.cities[world.selected_city_id] : null;
  const phase = world ? phaseNames[world.phase] : "准备中";
  const operating = world ? Object.values(world.firms).filter((firm) => firm.operating).length : 0;
  const history = useMemo(() => world?.history ?? [], [world]);

  if (!world) return <main className="boot-screen"><span className="seal">内</span><h1>InsideGov</h1><p>{error || "正在恢复世界…"}</p>{error && <button onClick={() => void create()}>重试连接</button>}</main>;

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand-lockup"><span className="seal">内</span><div><strong>InsideGov</strong><small>政企互动推演场</small></div></div>
        <div className="world-title"><span className="live-dot" />{world.name}<em>{world.id}</em></div>
        <nav><button className="ghost" onClick={() => setDetail("about")}>研究说明</button><a className="ghost" href={`${API_BASE}/worlds/${world.id}/export`}>导出实验</a><button className="avatar">研</button></nav>
      </header>
      {error && <div className="error-bar">{error}</div>}

      <section className="control-strip">
        <div className="time-block"><small>模拟时钟</small><strong>2030 Q{((world.quarter || 1) - 1) % 4 + 1}</strong><span>第 {world.quarter} / 16 季度</span></div>
        <div className="phase-track">{["招商竞争", "承诺履约", "产业演化"].map((item, index) => <div key={item} className={index <= (["招商竞争", "承诺履约", "产业演化"].indexOf(phase)) ? "done" : ""}><i>{index + 1}</i><span>{item}</span></div>)}</div>
        <div className="play-controls"><button disabled={busy} onClick={() => void create()} title="创建新世界">↺</button><button className="primary" disabled={busy} onClick={() => setPlaying(!playing)}>{playing ? "暂停" : "连续推演"}</button><button disabled={busy || world.quarter >= 16} onClick={() => void step()}>{busy ? "执行中…" : "推进一季 →"}</button></div>
      </section>

      <section className="dashboard-grid">
        <aside className="left-rail panel">
          <div className="panel-heading"><div><small>OBJECTIVE WORLD</small><h2>城市与资源</h2></div><span>{cities.length} 个政府</span></div>
          <div className="city-list">{cities.map((city, index) => <article className={`city-card ${world.selected_city_id === city.id ? "selected" : ""}`} key={city.id}>
            <div className="city-head"><span className={`city-mark ${tones[index]}`}>{city.name[0]}</span><div><h3>{city.name}</h3><p>{city.id}</p></div>{world.selected_city_id === city.id && <b>中标</b>}</div>
            <div className="mini-metrics"><span>可用财力<strong>{city.available_budget.toFixed(1)} 亿</strong></span><span>工业用地<strong>{city.industrial_land.toFixed(0)} 亩</strong></span></div>
            <label>供应链基础 <em>{city.supply_chain.toFixed(1)}</em><i><b style={{ width: `${city.supply_chain}%` }} /></i></label>
            <label>客观可信度 <em>{(city.objective_credibility * 100).toFixed(1)}%</em><i><b style={{ width: `${city.objective_credibility * 100}%` }} /></i></label>
            <div className="offer">最终政策成本 <strong>{city.active_offer ? fiscalCost(city.active_offer).toFixed(1) : "—"} 亿</strong></div>
          </article>)}</div>
          <button className="wide-button" onClick={() => setDetail("negotiations")}>查看提案—否决—协调</button>
        </aside>

        <section className="center-stage">
          <div className="metric-row">
            <Metric label="产业链企业" value={`${latest?.cluster_size ?? 0} 家`} delta="真实规则引擎状态" tone="cyan" />
            <Metric label="带动就业" value={(latest?.total_employment ?? 0).toLocaleString()} delta="直接与链企岗位" tone="amber" />
            <Metric label="平均制度信誉" value={`${((latest?.average_credibility ?? averageCredibility(cities)) * 100).toFixed(1)}%`} delta="随履约事件更新" tone="green" />
            <Metric label="产能利用率" value={`${((latest?.utilization ?? 0) * 100).toFixed(0)}%`} delta={(latest?.utilization ?? 1) < .68 && operating ? "低于安全阈值" : "供需基本匹配"} tone={(latest?.utilization ?? 1) < .68 && operating ? "red" : "violet"} />
          </div>

          <div className="world-map panel"><div className="panel-heading"><div><small>WORLD STATE</small><h2>产业世界态势</h2></div><div className="legend"><span>● 政府</span><span>◆ 龙头</span><span>· 链企</span></div></div>
            <div className="map-canvas"><div className="grid-lines" /><div className="flow flow-a" /><div className="flow flow-b" />
              <div className="map-city map-hai"><span>{cities[0]?.name[0]}</span><b>{cities[0]?.name}</b><small>{world.selected_city_id === cities[0]?.id ? "项目落地" : "竞争城市"}</small></div>
              <div className="map-city map-yun"><span>{cities[2]?.name[0]}</span><b>{cities[2]?.name}</b><small>{world.selected_city_id === cities[2]?.id ? "项目落地" : "竞争城市"}</small></div>
              <div className="cluster-core"><div className="rings"><i /><i /><i /></div><span className="anchor">◆</span><b>星澜显示</b><small>{selected ? `${selected.name} · ${world.firms.firm_nova.operating ? "已投产" : "建设中"}` : "正在选址"}</small>{Array.from({ length: Math.min(10, Math.max(0, operating - 1)) }, (_, i) => <i key={i} className={`supplier s${i + 1}`} />)}</div>
              <div className="map-caption"><strong>{phase}</strong><span>{world.policy_mode === "llm" ? `${world.model_name} 负责认知，规则引擎负责状态更新` : "确定性异质认知层 · 可复现基线"}</span></div>
            </div>
          </div>

          <div className="chart-panel panel"><div className="panel-heading"><div><small>EVOLUTION</small><h2>产能与需求演化</h2></div><span className="alert">安全阈值 68%</span></div><div className="chart-area">{history.length ? history.map((point) => <ChartBar key={point.quarter} point={point} />) : <div className="empty-chart">推进世界后生成季度数据</div>}</div><div className="chart-legend"><span><i className="cyan-box" />市场需求</span><span><i className="amber-box" />形成产能</span><strong>数据源：世界状态日志</strong></div></div>
        </section>

        <aside className="right-rail">
          <div className="panel experiment-panel"><div className="panel-heading"><div><small>COUNTERFACTUAL</small><h2>分支实验台</h2></div><span>{world.policy_mode}</span></div><p>先复制当前世界，再只改变一个条件。</p><div className="branch-list">{worldList.slice(0, 4).map((item, index) => <button key={item.id} className={item.id === world.id ? "active" : ""} onClick={() => void api.getWorld(item.id).then(remember)}><i>{String.fromCharCode(65 + index)}</i><span><strong>{item.id === world.id ? "当前世界" : item.parent_id ? "反事实分支" : "独立世界"}</strong><small>Q{item.quarter} · {item.policy_mode}</small></span><b>›</b></button>)}</div><button className="wide-button accent" disabled={busy} onClick={() => void createBranch()}>复制当前世界创建分支</button><div className="intervention-grid"><button onClick={() => void intervene("fiscal_shock", world.selected_city_id ?? "city_lin", .35)}>财政 -35%</button><button onClick={() => void intervene("demand_shock", "market", -.32)}>需求 -32%</button><button onClick={() => void intervene("credibility_boost", world.selected_city_id ?? "city_lin", .1)}>履约 +10%</button></div></div>
          <div className="panel event-panel"><div className="panel-heading"><div><small>EVENT STREAM</small><h2>世界事件流</h2></div><span>{world.events.length} 条</span></div><div className="events">{world.events.slice(-12).reverse().map((event, index) => <article key={`${event.quarter}-${index}`} className={event.severity}><time>Q{event.quarter}</time><div><small>{event.kind}</small><h3>{event.title}</h3><p>{event.detail}</p></div></article>)}</div></div>
        </aside>
      </section>

      <section className="trace-drawer panel"><div className="panel-heading"><div><small>DECISION TRACE</small><h2>可追溯决策链</h2></div><span>观察 → 证据 → 权衡 → 行动 → 结果</span></div><div className="trace-grid">{world.traces.slice(-4).reverse().map((trace, index) => <article key={trace.id}><span className="trace-no">0{index + 1}</span><div className="trace-who"><small>{trace.actor_id}</small><h3>{trace.action}</h3></div><div><small>调用证据</small><p>{trace.evidence.join(" · ")}</p></div><div><small>内部权衡</small><p>{trace.constraints.join(" · ")}</p></div><strong>{Object.values(trace.expected_effects)[0]?.toFixed?.(1) ?? "—"}</strong><button onClick={() => setDetail("trace")}>查看完整链条 →</button></article>)}</div></section>

      <footer><span>InsideGov v0.3 · 合成世界，不构成现实政策预测</span><span>{world.policy_mode === "llm" ? world.model_name : "确定性基线"} · Seed {world.seed} · 自动持久化</span></footer>

      {detail && <div className="modal-backdrop"><section className="modal panel"><button className="modal-close" onClick={() => setDetail(null)}>×</button>{detail === "about" ? <About capability={capability} mode={policyMode} model={model} setMode={setPolicyMode} setModel={setModel} create={create} /> : detail === "negotiations" ? <Negotiations world={world} /> : <Traces world={world} />}</section></div>}
    </main>
  );
}

function fiscalCost(offer: { subsidy: number; equity: number; credit_support: number }) { return offer.subsidy + offer.equity + offer.credit_support * .08; }
function averageCredibility(cities: Array<{ objective_credibility: number }>) { return cities.length ? cities.reduce((sum, city) => sum + city.objective_credibility, 0) / cities.length : 0; }
function Metric({ label, value, delta, tone }: { label: string; value: string; delta: string; tone: string }) { return <article className={`metric-card ${tone}`}><small>{label}</small><strong>{value}</strong><span>{delta}</span></article>; }
function ChartBar({ point }: { point: Metric }) { return <button title={`Q${point.quarter} 利用率 ${(point.utilization * 100).toFixed(0)}%`}><i className="demand" style={{ height: `${Math.min(92, point.demand / 2.1)}%` }} /><i className="capacity" style={{ height: `${Math.min(96, point.capacity / 3.1)}%` }} /><span>{point.quarter}</span></button>; }

function About({ capability, mode, model, setMode, setModel, create }: { capability: Capability | null; mode: string; model: string; setMode: (v: string) => void; setModel: (v: string) => void; create: (mode?: string, model?: string) => Promise<void> }) {
  return <><small>RESEARCH DESIGN</small><h2>双层模拟与模式设置</h2><p>大模型只负责私有观察下的理解、提案、否决、协调、选址与复盘；财政扣减、项目进度、履约和产能均由确定性引擎更新。</p><div className="settings"><label>认知模式<select value={mode} onChange={(e) => setMode(e.target.value)}><option value="deterministic">确定性异质基线</option><option value="llm" disabled={!capability?.llm_available}>DeepSeek 多智能体</option></select></label><label>模型<select value={model} onChange={(e) => setModel(e.target.value)}>{capability?.models.map((item) => <option key={item}>{item}</option>)}</select></label></div><p className="hint">{capability?.llm_available ? "服务端已识别 DeepSeek 凭据。" : "服务端未识别 DEEPSEEK_API_KEY，LLM 选项已锁定。"}</p><button className="wide-button accent" onClick={() => void create(mode, model)}>按此配置创建新世界</button></>;
}
function Negotiations({ world }: { world: World }) { return <><small>INTERNAL GOVERNANCE</small><h2>招商局提案 → 财政局否决 → 市领导协调</h2><div className="modal-list negotiation-list">{world.negotiations.slice().reverse().map((item) => <article key={item.id}><strong>Q{item.quarter} · {world.cities[item.city_id].name}</strong><span>招商局：现金 {money(item.proposal_tools?.subsidy)}，股权 {money(item.proposal_tools?.equity)}</span><span>财政局：现金上限 {money(item.finance_tool_limits?.subsidy)}，股权上限 {money(item.finance_tool_limits?.equity)}</span><span>市领导：现金 {money(item.final_tools?.subsidy)} + 股权 {money(item.final_tools?.equity)}</span><p>{item.concerns.join("；")}</p><div className="tranches">{item.payment_schedule?.map((row, index) => <i key={`${row.item}-${index}`}>Q+{row.due_offset} · {toolName(row.item)} {row.amount.toFixed(2)} 亿 · {row.condition}</i>)}</div></article>)}</div></>; }
function Traces({ world }: { world: World }) { return <><small>AUDIT LOG</small><h2>完整决策链</h2><div className="modal-list">{world.traces.slice().reverse().map((trace) => <article key={trace.id}><strong>{trace.actor_id} · {trace.action}</strong><p>{trace.evidence.join("；")}</p><span>{trace.outcome}</span></article>)}</div></>; }
function money(value?: number) { return value == null ? "—" : `${value.toFixed(2)} 亿`; }
function toolName(item: string) { return ({ subsidy: "现金", equity: "股权", credit_support: "信贷成本" } as Record<string, string>)[item] ?? item; }
