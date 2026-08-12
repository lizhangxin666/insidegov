"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { DemoReplay } from "./components/DemoReplay";
import { ReportCenter } from "./components/ReportCenter";
import { API_BASE, api, type AgentActionAudit, type CandidateWorld, type Capability, type InterventionPlan, type Interview, type Metric, type World } from "./lib/api";

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
  const [detail, setDetail] = useState<"demo" | "reports" | "negotiations" | "unified" | "trace" | "audit" | "counterfactual" | "interview" | "material" | "about" | null>(null);

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
        <nav><button className="ghost" onClick={() => setDetail("reports")}>实验结果</button><button className="ghost" onClick={() => setDetail("about")}>研究说明</button><a className="ghost" href={`${API_BASE}/worlds/${world.id}/export`}>导出实验</a><button className="avatar" aria-label="研究模式">研</button></nav>
      </header>
      {error && <div className="error-bar">{error}</div>}

      <section className="demo-banner">
        <div><small>COMPETITION DEMO · RULE-GENERATED</small><strong>从真实案例到反事实结果，六步验证博弈不是预写剧情</strong><span>合肥—蔚来公开参数卡 · 联合产业基金 · Agent 私有信息 · 跨期履约</span></div>
        <button data-testid="open-guided-demo" onClick={() => setDetail("demo")}>进入五分钟演示 →</button>
        <button onClick={() => setDetail("reports")}>查看实验报告</button>
      </section>

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
          <button className="wide-button" onClick={() => setDetail("unified")}>查看政企—政府内部—企业回应</button>
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
          <div className="panel experiment-panel"><div className="panel-heading"><div><small>COUNTERFACTUAL</small><h2>分支实验台</h2></div><span>{world.policy_mode}</span></div><p>从任意历史季度复制世界，再确认自然语言干预。</p><div className="branch-list">{worldList.slice(0, 4).map((item, index) => <button key={item.id} className={item.id === world.id ? "active" : ""} onClick={() => void api.getWorld(item.id).then(remember)}><i>{String.fromCharCode(65 + index)}</i><span><strong>{item.id === world.id ? "当前世界" : item.parent_id ? "反事实分支" : "独立世界"}</strong><small>Q{item.quarter} · {item.policy_mode}</small></span><b>›</b></button>)}</div><button className="wide-button accent" disabled={busy} onClick={() => setDetail("counterfactual")}>历史分支＋自然语言干预</button><div className="intervention-grid"><button onClick={() => setDetail("interview")}>采访 Agent</button><button onClick={() => setDetail("material")}>材料建世界</button><button onClick={() => setDetail("reports")}>实验报告</button><a href={`${API_BASE}/worlds/${world.id}/reports`} onClick={(e) => { e.preventDefault(); void fetch(`${API_BASE}/worlds/${world.id}/reports`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }).then((r) => r.text()).then((text) => { const blob = new Blob([text], { type: "text/html" }); window.open(URL.createObjectURL(blob), "_blank"); }); }}>世界报告</a></div></div>
          <div className="panel event-panel"><div className="panel-heading"><div><small>EVENT STREAM</small><h2>世界事件流</h2></div><span>{world.events.length} 条</span></div><div className="events">{world.events.slice(-12).reverse().map((event, index) => <article key={`${event.quarter}-${index}`} className={event.severity}><time>Q{event.quarter}</time><div><small>{event.kind}</small><h3>{event.title}</h3><p>{event.detail}</p></div></article>)}</div></div>
        </aside>
      </section>

      <section className="trace-drawer panel"><div className="panel-heading"><div><small>DECISION TRACE</small><h2>可追溯决策链</h2></div><button className="ghost" onClick={() => setDetail("audit")}>Agent 行动审计</button></div><div className="trace-grid">{world.traces.slice(-4).reverse().map((trace, index) => <article key={trace.id}><span className="trace-no">0{index + 1}</span><div className="trace-who"><small>{trace.actor_id}</small><h3>{trace.action}</h3></div><div><small>调用证据</small><p>{trace.evidence.join(" · ")}</p></div><div><small>内部权衡</small><p>{trace.constraints.join(" · ")}</p></div><strong>{Object.values(trace.expected_effects)[0]?.toFixed?.(1) ?? "—"}</strong><button onClick={() => setDetail("trace")}>查看完整链条 →</button></article>)}</div></section>

      <footer><span>InsideGov v0.5 · 政策实验与机制探索，不构成现实政策预测</span><span>{world.policy_mode === "llm" ? world.model_name : "确定性基线"} · Seed {world.seed} · 自动持久化</span></footer>

      {detail && <div className="modal-backdrop"><section className={`modal panel ${detail === "demo" || detail === "reports" ? "modal-wide" : ""}`}><button className="modal-close" aria-label="关闭弹窗" onClick={() => setDetail(null)}>×</button>{detail === "demo" ? <DemoReplay remember={remember} refreshList={refreshList} /> : detail === "reports" ? <ReportCenter remember={remember} /> : detail === "about" ? <About capability={capability} mode={policyMode} model={model} setMode={setPolicyMode} setModel={setModel} create={create} /> : detail === "negotiations" ? <Negotiations world={world} /> : detail === "unified" ? <UnifiedNegotiations world={world} /> : detail === "audit" ? <AuditTimeline world={world} /> : detail === "counterfactual" ? <CounterfactualLab world={world} remember={remember} refreshList={refreshList} /> : detail === "interview" ? <InterviewLab world={world} /> : detail === "material" ? <MaterialLab remember={remember} refreshList={refreshList} /> : <Traces world={world} />}</section></div>}
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
function Negotiations({ world }: { world: World }) { return <><small>INTERNAL GOVERNANCE</small><h2>招商局提案 → 产业基金审核 → 财政局否决 → 市领导协调</h2><div className="modal-list negotiation-list">{world.negotiations.slice().reverse().map((item) => <article key={item.id}><strong>Q{item.quarter} · {world.cities[item.city_id].name}</strong><span>招商局：现金 {money(item.proposal_tools?.subsidy)}，本级股权 {money(item.proposal_tools?.equity)}</span><span>联合基金：独立审核 {money(item.proposal_tools?.external_equity)}</span><span>财政局：现金上限 {money(item.finance_tool_limits?.subsidy)}，本级股权上限 {money(item.finance_tool_limits?.equity)}</span><span>最终：现金 {money(item.final_tools?.subsidy)} + 总股权 {money(item.final_tools?.total_equity_support)}</span><p>{item.concerns.join("；")}</p><div className="tranches">{item.payment_schedule?.map((row, index) => <i key={`${row.item}-${index}`}>Q+{row.due_offset} · {toolName(row.item)} {row.amount.toFixed(2)} 亿 · {row.condition}</i>)}</div></article>)}</div></>; }
function UnifiedNegotiations({ world }: { world: World }) { const internal = Object.fromEntries(world.negotiations.map((item) => [item.id, item])); return <><small>NESTED NEGOTIATION</small><h2>企业表达 → 政府澄清 → 内部会商 → 企业回应</h2><div className="modal-list negotiation-list">{world.external_negotiations.slice().reverse().map((item) => { const meeting = internal[item.internal_negotiation_id]; return <article key={item.id}><strong>Q{item.quarter} · {world.cities[item.city_id].name} · {item.enterprise_response}</strong><p><b>企业表面诉求：</b>{item.stated_need}</p><p><b>政府追问：</b>{item.government_questions.join("、") || "沿用已有理解"}</p><p><b>理解更新：</b>{brief(item.belief_before)} → {brief(item.belief_after)}（信心 {(item.belief_confidence * 100).toFixed(0)}%）</p>{meeting && <><span>招商局：现金 {money(meeting.proposal_tools.subsidy)}＋本级股权 {money(meeting.proposal_tools.equity)}</span><span>联合基金：{money(meeting.proposal_tools.external_equity)}</span><span>财政硬上限：现金 {money(meeting.finance_tool_limits.subsidy)}＋本级股权 {money(meeting.finance_tool_limits.equity)}</span><span>领导协调：现金 {money(meeting.final_tools.subsidy)}＋总股权 {money(meeting.final_tools.total_equity_support)}</span></>}<p><b>企业回应：</b>{item.enterprise_rationale}</p>{Object.keys(item.counter_terms).length > 0 && <p><b>还价条件：</b>{brief(item.counter_terms)}</p>}<small>效用 {item.utility.toFixed(1)} / 最低门槛 {item.minimum_utility.toFixed(1)} · 内部记录 {item.internal_negotiation_id}</small></article>; })}</div></>; }
function Traces({ world }: { world: World }) { return <><small>AUDIT LOG</small><h2>完整决策链</h2><div className="modal-list">{world.traces.slice().reverse().map((trace) => <article key={trace.id}><strong>{trace.actor_id} · {trace.action}</strong><p>{trace.evidence.join("；")}</p><span>{trace.outcome}</span></article>)}</div></>; }
function AuditTimeline({ world }: { world: World }) {
  const [quarter, setQuarter] = useState<number | "all">("all");
  const [agent, setAgent] = useState("all");
  const audits = world.action_audits ?? [];
  const quarters = Array.from(new Set(audits.map((item) => item.quarter))).sort((a, b) => a - b);
  const agents = Array.from(new Set(audits.map((item) => item.agent_id))).sort();
  const visible = audits.filter((item) => (quarter === "all" || item.quarter === quarter) && (agent === "all" || item.agent_id === agent));
  return <><small>P2.1 · AUDITABLE AGENTS</small><h2>观察 → 建议 → 规则修正 → 执行 → 复盘</h2><div className="settings"><label>季度<select value={quarter} onChange={(e) => setQuarter(e.target.value === "all" ? "all" : Number(e.target.value))}><option value="all">全部季度</option>{quarters.map((item) => <option key={item} value={item}>Q{item}</option>)}</select></label><label>Agent<select value={agent} onChange={(e) => setAgent(e.target.value)}><option value="all">全部 Agent</option>{agents.map((item) => <option key={item}>{item}</option>)}</select></label></div><div className="modal-list audit-list">{visible.slice().reverse().map((item) => <AuditCard key={item.id} item={item} />)}{!visible.length && <p className="hint">当前筛选条件下暂无认知行动。</p>}</div></>;
}
function AuditCard({ item }: { item: AgentActionAudit }) { const fields = item.private_context_used.fields_used; const fieldNames = Array.isArray(fields) ? fields.join("、") : ""; return <article><strong>Q{item.quarter} · {item.agent_id} · {item.action_type}</strong><span>{item.provider}{item.fallback ? " · 已降级" : " · 原生执行"}</span><p><b>当时观察：</b>{brief(item.observation)}</p><p><b>私有信息：</b>{"redacted" in item.private_context_used ? `默认脱敏；使用字段 ${fieldNames}` : "已记录"}</p><p><b>模型/策略建议：</b>{brief(item.llm_suggestion)}</p><p><b>规则修正：</b>{brief(item.rule_adjustment)}</p><p><b>最终执行：</b>{brief(item.executed_action)}</p><p><b>理由：</b>{item.rationale}</p><p><b>复盘：</b>{item.reflection}</p><small>诊断记录 {item.diagnostics.length} 条 · {item.outcome}</small></article>; }
function brief(value: unknown) { const text = JSON.stringify(value); return text.length > 240 ? `${text.slice(0, 237)}…` : text; }
function CounterfactualLab({ world, remember, refreshList }: { world: World; remember: (world: World) => void; refreshList: () => Promise<void> }) {
  const [quarter, setQuarter] = useState(Math.max(0, world.quarter - 1));
  const [text, setText] = useState("临江市财政收入下降30%，但上级提供5亿元专项资金，优先保障设备采购后的第二期补贴。");
  const [baseline, setBaseline] = useState<World | null>(null);
  const [branch, setBranch] = useState<World | null>(null);
  const [plan, setPlan] = useState<InterventionPlan | null>(null);
  const [delta, setDelta] = useState<Record<string, number> | null>(null);
  const [message, setMessage] = useState("");
  async function makeBranch() { const result = await api.createPair(world.id, quarter); setBaseline(result.baseline); setBranch(result.branch); setPlan(null); setDelta(null); setMessage(`已从Q${quarter}生成基线/干预副本，两者随机状态完全一致。`); await refreshList(); }
  async function parse() { if (!branch) return; setPlan(await api.draftIntervention(branch.id, text)); }
  async function confirm() { if (!branch || !plan) return; const result = await api.confirmIntervention(branch.id, plan.id); setPlan(result.plan); setMessage(`干预已确认，将从Q${plan.effective_quarter}按规则执行。`); }
  async function sync() { if (!baseline || !branch) return; const result = await api.syncPair(baseline.id, branch.id, 1); setBaseline(result.baseline); setBranch(result.branch); setDelta(result.comparison.delta); remember(result.branch); }
  return <><small>P2.2 · COUNTERFACTUAL</small><h2>历史节点复制与干预确认</h2><div className="settings"><label>复制季度<input type="number" min={0} max={world.quarter} value={quarter} onChange={(e) => setQuarter(Number(e.target.value))} /></label><button className="wide-button" onClick={() => void makeBranch()}>创建成对反事实世界</button></div><textarea value={text} onChange={(e) => setText(e.target.value)} rows={5} /><button className="wide-button accent" disabled={!branch} onClick={() => void parse()}>解析为候选干预</button>{plan && <article><strong>Q{plan.effective_quarter} 生效 · {plan.status === "confirmed" ? "已确认" : "待确认"}</strong>{plan.changes.map((item) => <p key={`${item.target}-${item.operation}`}>{item.description}：{item.target} {item.operation} {item.value}</p>)}{plan.assumptions.map((item) => <p key={item}>假设：{item}</p>)}<button className="wide-button accent" onClick={() => void confirm()}>确认并交给规则引擎</button></article>}<button className="wide-button" disabled={!baseline || !branch} onClick={() => void sync()}>基线与分支同步推进一季</button>{delta && <pre>{JSON.stringify(delta, null, 2)}</pre>}<p className="hint">{message}</p></>;
}
function InterviewLab({ world }: { world: World }) { const agents = Object.keys(world.action_audits.reduce((acc, item) => ({ ...acc, [item.agent_id]: true }), {} as Record<string, boolean>)); const [agent, setAgent] = useState(agents[0] ?? "city_lin_finance"); const [quarter, setQuarter] = useState(Math.min(1, world.quarter)); const [question, setQuestion] = useState("为什么否决现金加码？"); const [result, setResult] = useState<Interview | null>(null); return <><small>P2.3 · GROUNDED INTERVIEW</small><h2>采访指定历史节点的 Agent</h2><div className="settings"><label>Agent<select value={agent} onChange={(e) => setAgent(e.target.value)}>{agents.map((item) => <option key={item}>{item}</option>)}</select></label><label>季度<input type="number" min={0} max={world.quarter} value={quarter} onChange={(e) => setQuarter(Number(e.target.value))} /></label></div><textarea rows={3} value={question} onChange={(e) => setQuestion(e.target.value)} /><button className="wide-button accent" onClick={() => void api.interview(world.id, agent, quarter, question).then(setResult)}>基于当时证据回答</button>{result && <article><strong>{result.answer}</strong><p>当时已知：{result.knowledge_labels.known_at_the_time.join("；")}</p><p>当时未知：{result.knowledge_labels.unknown_at_the_time.join("；")}</p><small>证据：{result.evidence_audit_ids.join("、")}</small></article>}</>; }
function MaterialLab({ remember, refreshList }: { remember: (world: World) => void; refreshList: () => Promise<void> }) { const [filename, setFilename] = useState("政策材料.txt"); const [content, setContent] = useState(""); const [candidate, setCandidate] = useState<CandidateWorld | null>(null); async function confirm() { if (!candidate) return; const result = await api.confirmCandidate(candidate.id, candidate); remember(result); await refreshList(); } async function loadFile(file?: File) { if (!file) return; setFilename(file.name); setContent(await file.text()); } return <><small>P2.4 · MATERIAL TO WORLD</small><h2>上传材料生成候选世界</h2><input type="file" accept=".txt,.md,.json,.csv" onChange={(e) => void loadFile(e.target.files?.[0])} /><input value={filename} onChange={(e) => setFilename(e.target.value)} /><textarea rows={8} value={content} onChange={(e) => setContent(e.target.value)} placeholder="上传文本文件或粘贴政策、招商、产业材料。没有证据的参数会标记为 Demo 假设。" /><button className="wide-button accent" onClick={() => void api.createCandidate(filename, content).then(setCandidate)}>提取实体、关系、证据与候选参数</button>{candidate && <div className="modal-list"><article><strong>实体与关系</strong><p>{candidate.entities.join("、") || "未识别命名实体"}</p>{candidate.relations.map((item, index) => <small key={index}>{item.source} → {item.relation} → {item.target}：{item.evidence}</small>)}</article>{candidate.parameters.map((item, index) => <article key={item.id}><strong>{item.target}</strong><p>原文证据：{item.evidence}</p><label>最终确认值<input type="number" value={item.final_value ?? item.suggested_value} onChange={(e) => setCandidate({ ...candidate, parameters: candidate.parameters.map((row, i) => i === index ? { ...row, final_value: Number(e.target.value) } : row) })} /></label><label>参数来源<select value={item.provenance} onChange={(e) => setCandidate({ ...candidate, parameters: candidate.parameters.map((row, i) => i === index ? { ...row, provenance: e.target.value } : row) })}><option value="public_source">公开资料</option><option value="expert_judgment">专家判断</option><option value="user_input">用户设定</option><option value="demo_assumption">Demo 假设</option></select></label><small>置信度 {(item.confidence * 100).toFixed(0)}%</small></article>)}<button className="wide-button accent" onClick={() => void confirm()}>确认全部参数并创建世界</button></div>}</>; }
function money(value?: number) { return value == null ? "—" : `${value.toFixed(2)} 亿`; }
function toolName(item: string) { return ({ subsidy: "现金", equity: "本级股权", external_equity: "联合基金股权", credit_support: "信贷成本", credit_support_cost: "信贷成本" } as Record<string, string>)[item] ?? item; }
