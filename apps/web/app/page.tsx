"use client";

import { useMemo, useState } from "react";

type Branch = "基线世界" | "财政冲击" | "需求下行" | "履约保障";

const cities = [
  { name: "海州市", tone: "amber", fiscal: 82, land: 560, chain: 58, credibility: 82, offer: 31.4 },
  { name: "临江市", tone: "cyan", fiscal: 126, land: 430, chain: 76, credibility: 91, offer: 48.0 },
  { name: "云麓市", tone: "violet", fiscal: 64, land: 720, chain: 43, credibility: 74, offer: 24.2 },
];

const baseEvents = [
  { q: 1, kind: "报价", title: "三城提交首轮政策包", detail: "财政、土地、基金与人才工具被组合报价", tone: "neutral" },
  { q: 2, kind: "协商", title: "财政局否决现金加码", detail: "临江市改用产业基金与分期兑现结构", tone: "warning" },
  { q: 3, kind: "选址", title: "星澜显示选择临江市", detail: "供应链基础与履约可信度抵消了较低的土地折让", tone: "success" },
  { q: 4, kind: "履约", title: "首笔股权投资到账", detail: "合同触发条件满足，政府信用轻微上升", tone: "success" },
  { q: 6, kind: "建设", title: "项目完成设备进场", detail: "产线建设进度达到 58%，现金流保持安全", tone: "neutral" },
  { q: 8, kind: "投产", title: "龙头产线开始试生产", detail: "2,600 个岗位形成，供应链吸引力上升", tone: "success" },
  { q: 10, kind: "集聚", title: "第 10 家链企进入园区", detail: "本地采购和订单预期形成自增强循环", tone: "success" },
  { q: 13, kind: "预警", title: "产能利用率跌破 50%", detail: "新增产能快于市场需求，救助压力出现", tone: "danger" },
  { q: 16, kind: "演化", title: "集聚与过剩同时出现", detail: "产业链扩至 11 家，但利用率仅为 56%", tone: "warning" },
];

const traces = [
  { actor: "星澜显示", action: "选择临江市", evidence: "履约历史 · 供应链基础 · 政策包", score: "82.7", why: "长期运营效率权重高于一次性现金补贴" },
  { actor: "临江市财政局", action: "拒绝继续现金加码", evidence: "财政压力 · 债务付息 · 竞争报价", score: "风险 34%", why: "改用分期支付，降低当期预算挤压" },
  { actor: "链企 07", action: "跟随龙头落地", evidence: "订单预期 · 政府履约 · 运输成本", score: "71.4", why: "集聚收益已超过迁移成本和政策风险" },
];

function makeHistory(branch: Branch) {
  return Array.from({ length: 16 }, (_, index) => {
    const q = index + 1;
    const started = q >= 8;
    const cluster = started ? Math.min(11, 1 + Math.floor((q - 7) * 1.45)) : 0;
    let credibility = 83.7 + (q >= 4 ? Math.min(1.8, (q - 3) * 0.16) : 0);
    let demand = 100 + q * 3.4 + Math.sin((q + 1) / 2.4) * 11;
    if (branch === "财政冲击" && q >= 4) credibility -= Math.min(13, (q - 3) * 2.2);
    if (branch === "履约保障" && q >= 4) credibility += 7.5;
    if (branch === "需求下行" && q >= 10) demand *= 0.68;
    const capacity = started ? 120 + (cluster - 1) * 16.25 : 0;
    const utilization = capacity ? Math.min(100, demand / capacity * 100) : 0;
    return { q, cluster, credibility, demand, capacity, utilization, jobs: started ? 2600 + (cluster - 1) * 221 : 0 };
  });
}

export default function Home() {
  const [quarter, setQuarter] = useState(10);
  const [branch, setBranch] = useState<Branch>("基线世界");
  const [playing, setPlaying] = useState(false);
  const history = useMemo(() => makeHistory(branch), [branch]);
  const current = history[quarter - 1];
  const phase = quarter <= 3 ? "招商竞争" : quarter <= 7 ? "承诺履约" : "产业演化";
  const visibleEvents = baseEvents.filter((event) => event.q <= quarter).slice(-6).reverse();

  function advance() {
    setQuarter((value) => (value >= 16 ? 1 : value + 1));
  }

  function togglePlay() {
    if (playing) return setPlaying(false);
    setPlaying(true);
    let cursor = quarter;
    const timer = window.setInterval(() => {
      cursor += 1;
      if (cursor > 16) {
        window.clearInterval(timer);
        setPlaying(false);
        return;
      }
      setQuarter(cursor);
    }, 520);
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand-lockup">
          <span className="seal">内</span>
          <div><strong>InsideGov</strong><small>政企互动推演场</small></div>
        </div>
        <div className="world-title"><span className="live-dot" />地方产业发展全生命周期 <em>seed 42</em></div>
        <nav><button className="ghost">研究说明</button><button className="ghost">导出实验</button><button className="avatar">研</button></nav>
      </header>

      <section className="control-strip">
        <div className="time-block"><small>模拟时钟</small><strong>2030 Q{((quarter - 1) % 4) + 1}</strong><span>第 {quarter} / 16 季度</span></div>
        <div className="phase-track" aria-label="推演阶段">
          {["招商竞争", "承诺履约", "产业演化"].map((item, index) => <div key={item} className={(index <= (phase === "招商竞争" ? 0 : phase === "承诺履约" ? 1 : 2)) ? "done" : ""}><i>{index + 1}</i><span>{item}</span></div>)}
        </div>
        <div className="play-controls"><button onClick={() => setQuarter(1)} aria-label="重置">↺</button><button className="primary" onClick={togglePlay}>{playing ? "暂停" : "连续推演"}</button><button onClick={advance}>推进一季 →</button></div>
      </section>

      <section className="dashboard-grid">
        <aside className="left-rail panel">
          <div className="panel-heading"><div><small>OBJECTIVE WORLD</small><h2>城市与资源</h2></div><span>3 个政府</span></div>
          <div className="city-list">
            {cities.map((city, index) => <article className={`city-card ${index === 1 ? "selected" : ""}`} key={city.name}>
              <div className="city-head"><span className={`city-mark ${city.tone}`}>{city.name.slice(0, 1)}</span><div><h3>{city.name}</h3><p>{index === 1 ? "显示产业基础城市" : index === 0 ? "均衡型制造城市" : "土地资源型城市"}</p></div>{index === 1 && <b>中标</b>}</div>
              <div className="mini-metrics"><span>可用财力<strong>{city.fiscal} 亿</strong></span><span>工业用地<strong>{city.land} 亩</strong></span></div>
              <label>供应链基础 <em>{city.chain}</em><i><b style={{ width: `${city.chain}%` }} /></i></label>
              <label>客观可信度 <em>{city.credibility}%</em><i><b style={{ width: `${city.credibility}%` }} /></i></label>
              <div className="offer">最终政策成本 <strong>{city.offer.toFixed(1)} 亿</strong></div>
            </article>)}
          </div>
          <button className="wide-button">＋ 查看政府内部部门</button>
        </aside>

        <section className="center-stage">
          <div className="metric-row">
            <Metric label="产业链企业" value={`${current.cluster} 家`} delta={current.cluster ? "+10 较签约时" : "等待龙头落地"} tone="cyan" />
            <Metric label="带动就业" value={current.jobs.toLocaleString()} delta="直接与链企岗位" tone="amber" />
            <Metric label="平均制度信誉" value={`${current.credibility.toFixed(1)}%`} delta={branch === "财政冲击" ? "财政冲击后下降" : "履约记录持续更新"} tone="green" />
            <Metric label="产能利用率" value={`${current.utilization.toFixed(0)}%`} delta={current.utilization && current.utilization < 68 ? "低于安全阈值" : "供需基本匹配"} tone={current.utilization && current.utilization < 68 ? "red" : "violet"} />
          </div>

          <div className="world-map panel">
            <div className="panel-heading"><div><small>WORLD STATE</small><h2>产业世界态势</h2></div><div className="legend"><span>● 政府</span><span>◆ 龙头</span><span>· 链企</span></div></div>
            <div className="map-canvas">
              <div className="grid-lines" />
              <div className="flow flow-a" /><div className="flow flow-b" />
              <div className="map-city map-hai"><span>海</span><b>海州市</b><small>报价落选</small></div>
              <div className="map-city map-yun"><span>云</span><b>云麓市</b><small>土地优势</small></div>
              <div className="cluster-core">
                <div className="rings"><i /><i /><i /></div>
                <span className="anchor">◆</span><b>星澜显示</b><small>临江市 · 项目已投产</small>
                {Array.from({ length: Math.min(10, current.cluster - 1) }, (_, i) => <i key={i} className={`supplier s${i + 1}`} />)}
              </div>
              <div className="map-caption"><strong>{phase}</strong><span>{phase === "招商竞争" ? "三座城市正在形成差异化政策包" : phase === "承诺履约" ? "合同节点和财政状态共同决定实际支付" : "供应链集聚正在推高产能，市场约束开始显现"}</span></div>
            </div>
          </div>

          <div className="chart-panel panel">
            <div className="panel-heading"><div><small>EVOLUTION</small><h2>产能与需求演化</h2></div><span className="alert">安全阈值 68%</span></div>
            <div className="chart-area">
              {history.map((point) => <button key={point.q} onClick={() => setQuarter(point.q)} className={point.q === quarter ? "active" : ""} title={`Q${point.q} 利用率 ${point.utilization.toFixed(0)}%`}><i className="demand" style={{ height: `${Math.min(92, point.demand / 2.1)}%` }} /><i className="capacity" style={{ height: `${Math.min(96, point.capacity / 3.1)}%` }} /><span>{point.q}</span></button>)}
            </div>
            <div className="chart-legend"><span><i className="cyan-box" />市场需求</span><span><i className="amber-box" />形成产能</span><strong>点击柱体回看任一季度</strong></div>
          </div>
        </section>

        <aside className="right-rail">
          <div className="panel experiment-panel">
            <div className="panel-heading"><div><small>COUNTERFACTUAL</small><h2>分支实验台</h2></div><span>同源种子</span></div>
            <p>只改变一个条件，观察同一世界如何走向不同结果。</p>
            <div className="branch-list">
              {(["基线世界", "财政冲击", "需求下行", "履约保障"] as Branch[]).map((item, index) => <button key={item} className={branch === item ? "active" : ""} onClick={() => setBranch(item)}><i>{String.fromCharCode(65 + index)}</i><span><strong>{item}</strong><small>{index === 0 ? "无外部干预" : index === 1 ? "Q4 可用财力 -92%" : index === 2 ? "Q10 市场需求 -32%" : "Q4 建立专项资金"}</small></span><b>›</b></button>)}
            </div>
            <button className="wide-button accent">复制当前世界创建分支</button>
          </div>

          <div className="panel event-panel">
            <div className="panel-heading"><div><small>EVENT STREAM</small><h2>世界事件流</h2></div><span>实时</span></div>
            <div className="events">{visibleEvents.map((event) => <article key={`${event.q}-${event.title}`} className={event.tone}><time>Q{event.q}</time><div><small>{event.kind}</small><h3>{event.title}</h3><p>{event.detail}</p></div></article>)}</div>
          </div>
        </aside>
      </section>

      <section className="trace-drawer panel">
        <div className="panel-heading"><div><small>DECISION TRACE</small><h2>可追溯决策链</h2></div><span>观察 → 证据 → 权衡 → 行动 → 结果</span></div>
        <div className="trace-grid">{traces.map((trace, index) => <article key={trace.actor}><span className="trace-no">0{index + 1}</span><div className="trace-who"><small>{trace.actor}</small><h3>{trace.action}</h3></div><div><small>调用证据</small><p>{trace.evidence}</p></div><div><small>内部权衡</small><p>{trace.why}</p></div><strong>{trace.score}</strong><button>查看完整链条 →</button></article>)}</div>
      </section>

      <footer><span>InsideGov v0.1 · 合成世界，不构成现实政策预测</span><span>确定性策略 · 完整事件日志 · Seed 42</span></footer>
    </main>
  );
}

function Metric({ label, value, delta, tone }: { label: string; value: string; delta: string; tone: string }) {
  return <article className={`metric-card ${tone}`}><small>{label}</small><strong>{value}</strong><span>{delta}</span></article>;
}
