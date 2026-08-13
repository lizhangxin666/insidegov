"use client";

import { useEffect, useMemo, useState } from "react";
import {
  api,
  type ConversationExperience,
  type ConversationMechanism,
  type DueDiligenceCase,
  type DueDiligenceReport,
  type DynamicCompetitionReport,
  type StoryManifest,
  type StoryView,
  type World,
} from "../lib/api";
import { PublicJobRoom, PublicTaskDock } from "./PublicJobExperience";

type SceneId = "coordination" | "diligence" | "rescue" | "conversation" | "story";
type Audience = "government" | "enterprise" | "public";
type Outcome = {
  headline: string;
  conclusion: string;
  metrics: Array<{ label: string; value: string }>;
  process: Array<{ actor: string; action: string; feedback: string; tone?: string }>;
  findings: string[];
  governmentActions: string[];
  enterpriseActions: string[];
  publicSummary: string;
  story: string[];
  boundary: string;
  runtime: {
    modelName: string;
    decisions: number;
    fallbacks: number;
  };
};

const scenes = [
  {
    id: "coordination" as const,
    index: "01",
    eyebrow: "会商前预演",
    title: "怎样让部门冲突更早暴露？",
    description: "让招商、财政、市领导和企业在会前先走一遍，查看分歧在哪里出现、怎样重组政策包。",
    users: "招商干部 · 财政部门 · 项目企业",
    time: "真实 Agent · 数分钟",
    accent: "mint",
  },
  {
    id: "diligence" as const,
    index: "02",
    eyebrow: "项目真实性",
    title: "一家新企业到底靠不靠谱？",
    description: "不预先告诉 Agent 答案，让它选择查资金、技术、客户还是信用，并比较不同尽调程序。",
    users: "招商部门 · 基金团队 · 企业",
    time: "真实 Agent · 数分钟",
    accent: "amber",
  },
  {
    id: "rescue" as const,
    index: "03",
    eyebrow: "产业压力测试",
    title: "需求下滑时，应该救还是退？",
    description: "在完全相同的冲击下，对比市场退出、无条件救助和附条件救助的就业与财政后果。",
    users: "政府决策者 · 企业 · 社会公众",
    time: "真实 Agent · 长时推演",
    accent: "blue",
  },
  {
    id: "conversation" as const,
    index: "04",
    eyebrow: "协商机制压力测试",
    title: "同一句诉求，怎样问才不容易误签？",
    description: "输入一条项目异动，切换确认、会商和条件承诺机制，看信息如何暴露、承诺如何形成。",
    users: "政府部门 · 项目企业 · 研究教学",
    time: "真实 Agent · 数分钟",
    accent: "rose",
  },
  {
    id: "story" as const,
    index: "05",
    eyebrow: "第一人称组织博弈",
    title: "如果你坐进会场，会先做什么？",
    description: "选择招商、财政、市领导或园区角色。你发起一项行动，其他组织自主回应，规则结算真实后果。",
    users: "干部培训 · 普通公众 · 比赛展示",
    time: "每回合由 Agent 实时生成",
    accent: "violet",
  },
];

const strategies: Record<SceneId, Array<{ id: string; name: string; note: string }>> = {
  coordination: [
    { id: "formal", name: "正式程序", note: "按送审、审核、集体决策依次推进" },
    { id: "informal", name: "非正式协调", note: "先通过会前沟通和联盟降低阻力" },
    { id: "hybrid", name: "混合模式", note: "非正式探测边界，再进入正式审查" },
  ],
  diligence: [
    { id: "light_screen", name: "轻量筛查", note: "主要依赖企业提交材料，快且便宜" },
    { id: "independent_verification", name: "独立核验", note: "逐项验证资金、技术、市场和信用" },
    { id: "adaptive_staged", name: "自适应＋试点", note: "按信息价值调查，风险项目先做可逆试点" },
  ],
  rescue: [
    { id: "market_exit", name: "允许市场退出", note: "不提供救助，接受短期就业冲击" },
    { id: "unconditional", name: "无条件救助", note: "优先稳就业，但财政承担全部风险" },
    { id: "conditional", name: "附条件救助", note: "救助换整改，并压缩低效产能" },
  ],
  conversation: [],
  story: [],
};

export function ExperienceHome({ onOpenResearch }: { onOpenResearch: () => void }) {
  const [scene, setScene] = useState<SceneId | null>(null);
  const [strategy, setStrategy] = useState("");
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [audience, setAudience] = useState<Audience>("government");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [conversationResult, setConversationResult] = useState<ConversationExperience | null>(null);
  const [storyResult, setStoryResult] = useState<StoryView | null>(null);
  const selectedScene = useMemo(() => scenes.find((item) => item.id === scene), [scene]);

  function enter(id: SceneId) {
    setScene(id);
    setStrategy(id === "coordination" ? "hybrid" : id === "diligence" ? "adaptive_staged" : id === "rescue" ? "conditional" : "");
    setOutcome(null);
    setConversationResult(null);
    setStoryResult(null);
    setAudience("government");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function run() {
    if (!scene || !strategy) return;
    setBusy(true);
    setError("");
    setOutcome(null);
    try {
      if (scene === "coordination") {
        const job = await api.createPublicJob("coordination", { process_mode: strategy, seed: 42 });
        setActiveJobId(job.id);
      } else if (scene === "diligence") {
        const job = await api.createPublicJob("diligence", { program: strategy, seed: 42 });
        setActiveJobId(job.id);
      } else if (scene === "rescue") {
        const job = await api.createPublicJob("dynamic_competition", { policy: strategy, seed: 42, quarters: 16 });
        setActiveJobId(job.id);
      }
    } catch (caught) {
      setError(String(caught));
    } finally {
      setBusy(false);
    }
  }

  async function openJobResult(job: import("../lib/api").PublicJob) {
    if (job.scene === "coordination") {
      const result = await api.getPublicJobResult<World>(job.id);
      const mode = String(job.config.process_mode ?? "hybrid");
      setScene("coordination"); setStrategy(mode); setOutcome(coordinationOutcome(result, mode));
    } else if (job.scene === "diligence") {
      const result = await api.getPublicJobResult<DueDiligenceReport>(job.id);
      const program = String(job.config.program ?? "adaptive_staged");
      setScene("diligence"); setStrategy(program); setOutcome(diligenceOutcome(result, program));
    } else if (job.scene === "dynamic_competition") {
      const result = await api.getPublicJobResult<DynamicCompetitionReport>(job.id);
      const policy = String(job.config.policy ?? "conditional");
      setScene("rescue"); setStrategy(policy); setOutcome(rescueOutcome(result, policy));
    } else if (job.scene === "conversation") {
      setConversationResult(await api.getPublicJobResult<ConversationExperience>(job.id));
      setScene("conversation");
    } else {
      setStoryResult(await api.getPublicJobResult<StoryView>(job.id));
      setScene("story");
    }
    setActiveJobId(null);
  }

  if (activeJobId) {
    return <><PublicJobRoom jobId={activeJobId} onLeave={() => setActiveJobId(null)} onResult={openJobResult} onJobChanged={setActiveJobId} /><PublicTaskDock onOpen={setActiveJobId} /></>;
  }

  if (!scene) {
    return (
      <><main className="experience-home">
        <header className="experience-nav">
          <div className="experience-brand"><i>内</i><span><b>InsideGov</b><small>把政策过程放到桌面上</small></span></div>
          <nav><a href="#scenes">选择场景</a><button onClick={onOpenResearch}>进入研究工作台</button></nav>
        </header>
        <section className="experience-hero">
          <div>
            <small>AGENT-BASED POLICY SIMULATION</small>
            <h1>先把问题<br />在现实发生前跑一遍。</h1>
            <p>InsideGov 让政府部门、企业和规则在同一个世界里真实互动。你不需要先理解模型，只需要选择一个正在面对的问题。</p>
            <a href="#scenes">选择我要解决的问题 <span>↓</span></a>
          </div>
          <div className="hero-proof">
            <span>01</span><p><b>Agent 自主决策</b>不是预写剧情</p>
            <span>02</span><p><b>规则确定结算</b>财政、合同和产能可复核</p>
            <span>03</span><p><b>结果面向不同人</b>政府、企业和公众各看各的</p>
          </div>
        </section>
        <section className="scene-section" id="scenes">
          <header><small>CHOOSE A QUESTION</small><h2>你今天想先解决哪个问题？</h2><p>每个入口都是一条完整体验，复杂参数留在过程背后。</p></header>
          <div className="scene-entry-grid">
            {scenes.map((item) => (
              <button key={item.id} className={item.accent} onClick={() => enter(item.id)}>
                <span>{item.index}</span><small>{item.eyebrow}</small><h3>{item.title}</h3><p>{item.description}</p>
                <footer><em>{item.users}</em><b>{item.time} →</b></footer>
              </button>
            ))}
          </div>
        </section>
        <section className="experience-how">
          <small>ONE ENGINE · DIFFERENT EXPERIENCES</small><h2>底层是一套世界，用户只看与问题有关的那条线。</h2>
          <div><span><b>1</b>选择问题</span><i>→</i><span><b>2</b>选择策略</span><i>→</i><span><b>3</b>观察过程</span><i>→</i><span><b>4</b>获得自己的结果</span></div>
        </section>
        <footer className="experience-footer"><b>InsideGov</b><span>政策实验与组织行为研究工具，不构成现实政策预测。</span><button onClick={onOpenResearch}>研究者入口 →</button></footer>
      </main><PublicTaskDock onOpen={setActiveJobId} /></>
    );
  }

  if (scene === "conversation") {
    return <><ConversationExperiencePanel selectedScene={selectedScene} initialResult={conversationResult} onStartJob={setActiveJobId} onBack={() => setScene(null)} onOpenResearch={onOpenResearch} /><PublicTaskDock onOpen={setActiveJobId} /></>;
  }

  if (scene === "story") {
    return <><StoryExperiencePanel selectedScene={selectedScene} initialStory={storyResult} onStartJob={setActiveJobId} onBack={() => setScene(null)} onOpenResearch={onOpenResearch} /><PublicTaskDock onOpen={setActiveJobId} /></>;
  }

  return (
    <><main className="scenario-shell">
      <header className="scenario-nav"><button onClick={() => setScene(null)}>← 返回问题首页</button><div><i>内</i><b>InsideGov</b></div><button onClick={onOpenResearch}>研究工作台</button></header>
      <section className="scenario-heading">
        <small>{selectedScene?.eyebrow} · {selectedScene?.index}</small><h1>{selectedScene?.title}</h1><p>{selectedScene?.description}</p>
        <ol><li className="active">选择策略</li><li className={outcome || busy ? "active" : ""}>运行过程</li><li className={outcome ? "active" : ""}>查看结果</li></ol>
      </section>

      {!outcome && !busy && (
        <section className="strategy-step">
          <header><small>STEP 1 / 3</small><h2>这次想采用哪种处理方式？</h2><p>我们只改变这一项，其他城市、企业和随机条件保持一致。</p></header>
          <div>{strategies[scene].map((item) => <button className={strategy === item.id ? "active" : ""} key={item.id} onClick={() => setStrategy(item.id)}><i>{strategy === item.id ? "✓" : ""}</i><b>{item.name}</b><span>{item.note}</span></button>)}</div>
          <button className="run-scenario" onClick={() => void run()}>开始推演 <span>→</span></button>
          {error && <p className="scenario-error">{error}</p>}
        </section>
      )}

      {busy && <section className="scenario-running"><div className="running-orbit"><i /><i /><b>内</b></div><small>DEEPSEEK AGENTS ARE RUNNING</small><h2>各组织正在观察、行动和回应…</h2><p>所有公众场景固定调用 LLM Agent；世界状态仍由 InsideGov 规则引擎逐步结算。</p></section>}

      {outcome && (
        <>
          <section className="process-step">
            <header><div><small>STEP 2 / 3 · GENERATED PROCESS</small><h2>这次推演实际发生了什么？</h2><AgentRuntimeBadge modelName={outcome.runtime.modelName} decisions={outcome.runtime.decisions} fallbacks={outcome.runtime.fallbacks} /></div><button onClick={() => setOutcome(null)}>更换策略</button></header>
            <div className="simple-process">{outcome.process.map((item, index) => <article key={`${item.actor}-${index}`} className={item.tone ?? ""}><i>{index + 1}</i><div><small>{item.actor}</small><b>{item.action}</b><p>{item.feedback}</p></div></article>)}</div>
          </section>
          <section className="result-step">
            <header><small>STEP 3 / 3</small><h2>这份结果要给谁看？</h2><div className="audience-tabs"><button className={audience === "government" ? "active" : ""} onClick={() => setAudience("government")}>政府决策者</button><button className={audience === "enterprise" ? "active" : ""} onClick={() => setAudience("enterprise")}>项目企业</button><button className={audience === "public" ? "active" : ""} onClick={() => setAudience("public")}>普通公众</button></div></header>
            <AudienceResult audience={audience} outcome={outcome} scene={scene} strategy={strategies[scene].find((item) => item.id === strategy)?.name ?? strategy} />
          </section>
        </>
      )}
    </main><PublicTaskDock onOpen={setActiveJobId} /></>
  );
}

type SceneHeading = (typeof scenes)[number] | undefined;

function ExperienceNav({ onBack, onOpenResearch }: { onBack: () => void; onOpenResearch: () => void }) {
  return <header className="scenario-nav"><button onClick={onBack}>← 返回问题首页</button><div><i>内</i><b>InsideGov</b></div><button onClick={onOpenResearch}>研究工作台</button></header>;
}

function ConversationExperiencePanel({ selectedScene, initialResult, onStartJob, onBack, onOpenResearch }: { selectedScene: SceneHeading; initialResult: ConversationExperience | null; onStartJob: (jobId: string) => void; onBack: () => void; onOpenResearch: () => void }) {
  const [mechanisms, setMechanisms] = useState<ConversationMechanism[]>([]);
  const [selected, setSelected] = useState("M8");
  const [eventText, setEventText] = useState("企业融资计划反复调整，但尚未公开说明自筹资金缺口。");
  const [result, setResult] = useState<ConversationExperience | null>(initialResult);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    void api.conversationMechanisms().then(setMechanisms).catch((caught) => setError(String(caught)));
  }, []);

  async function run() {
    setBusy(true); setError(""); setResult(null);
    try {
      const job = await api.createPublicJob("conversation", { mechanism_id: selected, event_text: eventText, seed: 42 });
      onStartJob(job.id);
    }
    catch (caught) { setError(String(caught)); }
    finally { setBusy(false); }
  }

  return <main className="scenario-shell conversation-experience">
    <ExperienceNav onBack={onBack} onOpenResearch={onOpenResearch} />
    <section className="scenario-heading"><small>{selectedScene?.eyebrow} · {selectedScene?.index}</small><h1>{selectedScene?.title}</h1><p>{selectedScene?.description}</p><ol><li className="active">输入条件</li><li className={busy || result ? "active" : ""}>机制运行</li><li className={result ? "active" : ""}>查看证据链</li></ol></section>
    {!result && !busy ? <section className="experience-config conversation-config">
      <header><small>STEP 1 / 3</small><h2>这次项目出现了什么新情况？</h2><p>系统先把自然语言编译为知情方、可观察信号和透明的世界参数变化，不会直接让模型改数字。</p></header>
      <textarea aria-label="压力事件" value={eventText} onChange={(event) => setEventText(event.target.value)} />
      <div className="quick-events"><button onClick={() => setEventText("企业融资计划反复调整，自筹资金证明仍待补充。")}>融资疑点</button><button onClick={() => setEventText("核心客户名单与订单口径发生变化。")}>客户疑点</button><button onClick={() => setEventText("企业实控人出现新的诉讼和信用信息。")}>治理疑点</button><button onClick={() => setEventText("地方财政预算收紧，大额支持需重新测算。")}>财政收紧</button></div>
      <header><small>MECHANISM</small><h2>选择协商机制</h2><p>三个开关组成八种机制。Agent 仍自主判断谈什么，协议只约束必要的信息和承诺程序。</p></header>
      <div className="mechanism-grid">{mechanisms.map((item) => <button key={item.id} className={selected === item.id ? "active" : ""} onClick={() => setSelected(item.id)}><small>{item.id}</small><b>{item.name}</b><span>{item.description}</span><em>{Object.entries(item.dimensions).map(([key, value]) => <i key={key} className={value ? "on" : ""}>{dimensionLabel(key)}</i>)}</em></button>)}</div>
      <button className="run-scenario" onClick={() => void run()}>开始协商压力测试 <span>→</span></button>{error ? <p className="scenario-error">{error}</p> : null}
    </section> : null}
    {busy ? <section className="scenario-running"><div className="running-orbit"><i /><i /><b>商</b></div><small>DEEPSEEK · ONE AUTHORITATIVE WORLD</small><h2>各主体正在基于局部信息行动…</h2><p>协商动作由 LLM Agent 实时生成，证据、承诺和财政后果由 InsideGov 结算。</p></section> : null}
    {result ? <ConversationResult result={result} onReset={() => setResult(null)} /> : null}
  </main>;
}

function ConversationResult({ result, onReset }: { result: ConversationExperience; onReset: () => void }) {
  const verdict = result.result.decision === "reject" ? "本轮不进入签约" : result.result.decision === "conditional_pilot" ? "先做附条件试点" : result.result.decision === "defer" ? "证据不足，暂缓" : "进入后续协商";
  return <>
    <section className="process-step conversation-process"><header><div><small>STEP 2 / 3 · LIVE TRAJECTORY</small><h2>风险是怎样被看见的？</h2><AgentRuntimeBadge modelName={result.agent_runtime.model_name} decisions={result.agent_runtime.audited_agent_decisions} fallbacks={result.agent_runtime.fallback_count} /></div><button onClick={onReset}>更换机制</button></header><div className="event-compiler"><small>事件编译结果</small><b>{result.compiled_event.title}</b><p>最初知情：{result.compiled_event.initially_informed_agent_ids.map(actorName).join("、")}</p><p>最初未知：{result.compiled_event.initially_uninformed_agent_ids.map(actorName).join("、")}</p><p>可观察信号：{result.compiled_event.observable_signals.join("；")}</p><code>{JSON.stringify(result.compiled_event.authoritative_change)}</code></div><div className="simple-process">{result.timeline.map((item, index) => <article key={`${item.kind}-${index}`}><i>{item.round ?? index + 1}</i><div><small>{actorName(item.actor_id)}</small><b>{conversationActionName(item.action)}</b><p>{humanizeDetail(item.detail)}</p></div></article>)}</div></section>
    <section className="result-step"><header><small>STEP 3 / 3 · EVIDENCE-GATED RESULT</small><h2>决定不是标签，而是一条可检查的程序结果。</h2></header><div className="conversation-verdict"><header><small>本轮建议</small><h3>{verdict}</h3><p>{result.result.fail_reason || `经过 ${result.result.elapsed_days} 天、${result.result.evidence_count} 项证据，形成当前判断。`}</p></header><div className="brief-metrics"><span>事前失败风险<b>{pct(result.result.estimated_failure_probability)}</b></span><span>剩余不确定性<b>{pct(result.result.uncertainty)}</b></span><span>理解差距<b>{result.result.understanding_gap_before.toFixed(2)} → {result.result.understanding_gap_after.toFixed(2)}</b></span><span>权威世界审计<b>{result.audit_count} 条</b></span></div><section className="evidence-strip">{result.evidence.map((item) => <article key={item.id}><small>{dimensionName(item.dimension)} · {item.source_type}</small><b>观察 {pct(item.observed_quality)}</b><span>主张 {pct(item.claim_value)} · 冲突 {pct(item.conflict)}</span><p>{item.summary}</p></article>)}</section><footer><b>{result.authority_engine}</b><span>{result.boundary}</span></footer></div></section>
  </>;
}

function StoryExperiencePanel({ selectedScene, initialStory, onStartJob, onBack, onOpenResearch }: { selectedScene: SceneHeading; initialStory: StoryView | null; onStartJob: (jobId: string) => void; onBack: () => void; onOpenResearch: () => void }) {
  const [manifest, setManifest] = useState<StoryManifest | null>(null);
  const [role, setRole] = useState("city_lin_investment");
  const [story, setStory] = useState<StoryView | null>(initialStory);
  const [action, setAction] = useState("");
  const [statement, setStatement] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    void api.storyManifest().then((next) => { setManifest(next); setRole(next.roles[0]?.id ?? "city_lin_investment"); }).catch((caught) => setError(String(caught)));
  }, []);

  async function start() {
    setBusy(true); setError("");
    try { const next = await api.startStory(role); setStory(next); setAction(next.available_actions[0]?.id ?? ""); }
    catch (caught) { setError(String(caught)); }
    finally { setBusy(false); }
  }

  async function play() {
    if (!story || !action) return;
    setBusy(true); setError("");
    try {
      const job = await api.createPublicJob("story_turn", { session_id: story.session_id, action_id: action, statement });
      onStartJob(job.id);
      setStatement("");
    }
    catch (caught) { setError(String(caught)); }
    finally { setBusy(false); }
  }

  return <main className="scenario-shell story-experience"><ExperienceNav onBack={onBack} onOpenResearch={onOpenResearch} /><section className="scenario-heading"><small>{selectedScene?.eyebrow} · {selectedScene?.index}</small><h1>{selectedScene?.title}</h1><p>{selectedScene?.description}</p><ol><li className="active">选择角色</li><li className={story || busy ? "active" : ""}>采取行动</li><li className={story?.receipt ? "active" : ""}>观察回应</li></ol></section>
    {!story && !busy ? <section className="experience-config story-role-step"><header><small>STEP 1 / 3</small><h2>今天，你代表哪个组织？</h2><p>你可以改变角色的行动，但不能突破它的法定权限；其他组织不会配合你“通关”。</p></header><div>{manifest?.roles.map((item) => <button key={item.id} className={role === item.id ? "active" : ""} onClick={() => setRole(item.id)}><i>{role === item.id ? "✓" : ""}</i><b>{item.name}</b><span>{item.motive}</span></button>)}</div><aside>{manifest?.rules.map((item, index) => <p key={item}><b>{index + 1}</b>{item}</p>)}</aside><button className="run-scenario" onClick={() => void start()}>坐进会场 <span>→</span></button>{error ? <p className="scenario-error">{error}</p> : null}</section> : null}
    {busy && !story ? <section className="scenario-running"><div className="running-orbit"><i /><i /><b>局</b></div><small>DEEPSEEK · BRANCHING THE WORLD</small><h2>正在复制一条 LLM Agent 世界线…</h2><p>这局不会改写基线世界，其他组织将自主回应。</p></section> : null}
    {story ? <section className="story-board"><header><div><small>Q{story.quarter} · TURN {story.turn} · {story.authority_engine}</small><h2>{story.scene_title}</h2><AgentRuntimeBadge modelName={story.agent_runtime.model_name} decisions={story.agent_runtime.audited_agent_decisions} fallbacks={story.agent_runtime.fallback_count} /><p>你是<b>{story.player.name}</b>。{story.boundary}</p></div><button onClick={() => setStory(null)}>重新选角色</button></header><div className="story-layout"><aside className="role-dossier"><small>我的任务</small>{story.player.goals.map((item) => <p key={item}>— {item}</p>)}<small>只有我知道</small>{story.player.private_facts.map((item) => <p key={item.key}><b>{privateFactLabel(item.key)}</b>{String(item.value)}</p>)}<small>局势信号</small><div>{story.signals.map((item) => <span key={item.label}>{item.label}<b>{item.level}</b></span>)}</div></aside><article className="story-stage"><small>这一回合发生了什么</small>{story.narrative.map((item, index) => <p key={`${item}-${index}`}>{humanizeDetail(item)}</p>)}{story.receipt ? <div className={`action-receipt ${story.receipt.status}`}><small>规则执行回执</small><b>{story.receipt.executed_action?.action_name || story.receipt.requested_action} · {story.receipt.status === "executed" ? "已执行" : "被拦截"}</b><p>{story.receipt.executed_action?.blocked_reason || story.receipt.executed_action?.selection_rationale || story.receipt.rule_statement}</p><span>新增 Agent 审计 {story.receipt.new_agent_audits} 条 · 新增世界事件 {story.receipt.new_events.length} 条</span></div> : null}</article><aside className="story-action-panel"><small>我这一轮准备</small><div>{story.available_actions.map((item) => <button key={item.id} className={action === item.id ? "active" : ""} onClick={() => setAction(item.id)}><b>{item.name}</b><span>{item.rationale}</span></button>)}</div><textarea aria-label="角色公开表态" value={statement} onChange={(event) => setStatement(event.target.value)} placeholder="补充你准备如何表达、向谁施压或说明什么依据（可选）" /><button className="story-submit" disabled={busy || !action} onClick={() => void play()}>{busy ? "其他组织正在回应…" : "发起行动 →"}</button>{error ? <p className="scenario-error">{error}</p> : null}</aside></div><footer><span>世界分支 {story.world_id}</span><span>组织行动 {story.world_summary.organization_actions}</span><span>Agent 审计 {story.world_summary.agent_audits}</span><span>状态 {story.world_summary.recruitment_status === "active" ? "协商中" : story.world_summary.recruitment_status}</span></footer></section> : null}
  </main>;
}

function dimensionLabel(key: string) { return ({ mutual_confirmation: "确认需求", pre_commitment_consultation: "承诺前会商", conditional_commitment: "条件承诺" } as Record<string, string>)[key] ?? key; }
function conversationActionName(id: string) { return ({ verify_funding_sources: "核验资金来源", technical_expert_review: "技术专家评审", customer_contract_check: "核验客户合同", credit_and_litigation_check: "信用与诉讼核查", team_delivery_reference: "团队交付背调", red_team_challenge: "红队质询", conditional_pilot: "附条件试点", approve: "进入后续协商", reject: "本轮否决", defer: "暂缓并补证", disclose: "策略性披露", disclose_under_constraint_first: "约束披露后回应", accept: "接受方案", counter: "提出还价", terminate: "退出谈判" } as Record<string, string>)[id] ?? id; }
function privateFactLabel(key: string) { return ({ reserve_floor: "财政底线", stress_limit: "压力容忍度", signing_target: "签约目标", cash_preference: "现金偏好", competitive_intensity: "竞争压力", land_pressure: "土地压力", leadership_attention: "领导注意力", political_priority: "政策优先度" } as Record<string, string>)[key] ?? key; }
function humanizeDetail(text: string) { return text.replaceAll("credit_and_litigation_check", "信用与诉讼核查").replaceAll("verify_funding_sources", "资金来源核验").replaceAll("customer_contract_check", "客户合同核验").replaceAll("team_delivery_reference", "团队交付背调").replaceAll("conditional_pilot", "附条件试点").replaceAll("start_formal_process", "启动正式程序").replaceAll("dormant", "尚未启动").replaceAll("active", "进行中"); }

function AudienceResult({ audience, outcome, scene, strategy }: { audience: Audience; outcome: Outcome; scene: SceneId; strategy: string }) {
  if (audience === "public") return <div className="public-result"><div className="plain-report"><small>给公众的三分钟说明</small><h3>{outcome.headline}</h3><p>{outcome.publicSummary}</p><div>{outcome.metrics.map((item) => <span key={item.label}>{item.label}<b>{item.value}</b></span>)}</div></div><article className="story-result"><small>根据本次推演自动改写 · 纪实短篇</small><h3>《会前的那盏灯》</h3>{outcome.story.map((item, index) => <p key={index}>{item}</p>)}<footer>故事中的数值与转折来自本次模拟，不代表现实事件预测。</footer></article></div>;
  const actions = audience === "government" ? outcome.governmentActions : outcome.enterpriseActions;
  return <div className={`brief-result ${audience}`}><header><small>{audience === "government" ? "DECISION BRIEF / 决策简报" : "PROJECT RESPONSE / 企业响应报告"}</small><h3>{outcome.headline}</h3><p>{outcome.conclusion}</p></header><div className="brief-metrics">{outcome.metrics.map((item) => <span key={item.label}>{item.label}<b>{item.value}</b></span>)}</div><section><div><h4>本次发现</h4>{outcome.findings.map((item) => <p key={item}>— {item}</p>)}</div><div><h4>{audience === "government" ? "建议动作" : "企业下一步"}</h4>{actions.map((item, index) => <p key={item}><b>{index + 1}</b>{item}</p>)}</div></section><footer><span>场景：{scene}</span><span>策略：{strategy}</span><p>{outcome.boundary}</p></footer></div>;
}

function AgentRuntimeBadge({ modelName, decisions, fallbacks }: { modelName: string; decisions: number; fallbacks: number }) {
  return <div className="agent-runtime-badge"><i>AI</i><span><b>{modelName}</b><small>公众入口固定 LLM Agent · 已审计 {decisions} 次决策{fallbacks ? ` · 降级 ${fallbacks} 次` : " · 无降级"}</small></span></div>;
}

function coordinationOutcome(world: World, mode: string): Outcome {
  const selected = world.selected_city_id ? world.cities[world.selected_city_id] : null;
  const negotiation = [...world.negotiations].reverse().find((item) => item.city_id === world.selected_city_id) ?? world.negotiations.at(-1);
  const actions = world.organization_actions.filter((item) => item.city_id === (world.selected_city_id ?? "city_lin"));
  const process = actions.slice(-4).map((item) => ({ actor: actorName(item.actor_role), action: actionName(item.action_id), feedback: item.blocked_reason ? `程序未通过：${item.blocked_reason}` : item.selection_rationale || item.rationale, tone: item.authorized ? "" : "warning" }));
  if (negotiation) process.push({ actor: "财政规则引擎", action: negotiation.finance_approved ? "财政审核通过" : "工具级核减", feedback: `提案成本 ${negotiation.proposal_cost.toFixed(1)} 亿，最终可执行成本 ${negotiation.final_cost.toFixed(1)} 亿。`, tone: negotiation.finance_approved ? "success" : "warning" });
  const response = world.external_negotiations.at(-1);
  if (response) process.push({ actor: "企业董事会", action: response.enterprise_response === "accept" ? "接受方案" : response.enterprise_response === "counter" ? "提出还价" : "退出谈判", feedback: response.enterprise_rationale, tone: response.enterprise_response === "accept" ? "success" : "" });
  return {
    headline: selected ? `${selected.name}进入企业最终选择范围` : "部门完成会前政策包重组",
    conclusion: negotiation ? `内部冲突没有被隐藏：招商提案经财政审核后从 ${negotiation.proposal_cost.toFixed(1)} 亿调整为 ${negotiation.final_cost.toFixed(1)} 亿，并形成可执行的分期安排。` : "组织已完成本轮程序，但尚未形成最终报价。",
    metrics: [{ label: "组织行动", value: `${actions.length} 次` }, { label: "内部会商", value: `${world.negotiations.length} 轮` }, { label: "最终政策成本", value: `${negotiation?.final_cost.toFixed(1) ?? "—"} 亿` }, { label: "企业状态", value: response?.enterprise_response === "accept" ? "接受" : response?.enterprise_response === "counter" ? "还价" : "等待" }],
    process,
    findings: [`${modeName(mode)}决定了冲突暴露的时点和行动顺序。`, negotiation && negotiation.proposal_cost > negotiation.final_cost ? `财政约束真实核减了 ${(negotiation.proposal_cost - negotiation.final_cost).toFixed(1)} 亿，而非只生成反对文本。` : "本轮政策包处于财政承受范围内。", "企业回应发生在政府内部协调之后，并可以接受、还价或退出。"],
    governmentActions: ["把本次财政核减项带入正式会商议程。", "将企业还价拆成可核验的分期条件。", "保存本次行动链，作为下一轮部门协调依据。"],
    enterpriseActions: ["确认最终政策包而不是招商初始口径。", "重点核对每期兑现条件和资金来源。", "若关键条件未写入合同，保留继续还价或退出选项。"],
    publicSummary: `几个部门并没有一开始就意见一致。招商部门希望项目更有吸引力，财政部门关心能不能付得起，市领导再把两边意见重组为可执行方案。${negotiation ? `最终方案比最初提案减少了 ${(negotiation.proposal_cost - negotiation.final_cost).toFixed(1)} 亿元。` : ""}`,
    story: ["晚上九点，会议室里只剩下三盏灯。招商干部把厚厚的项目册推到桌子中央：如果今天不能形成报价，企业明天就要去另一座城市。", negotiation ? `财政局没有接那句话，只在纸上圈出两个数字：最初方案要 ${negotiation.proposal_cost.toFixed(1)} 亿元，而账上能执行的只有 ${negotiation.final_cost.toFixed(1)} 亿元。空气安静了几秒。` : "财政局翻开预算表，一项一项核对承诺。", "市领导没有要求任何一方简单让步。他把现金、股权和分期节点重新排开，让每笔钱都对应一个项目进度。方案终于可以送到企业面前，但企业仍保留了说“不”的权利。"],
    boundary: "该结果来自模拟世界中的组织目标、私有信息与财政规则，用于会商预演，不等同于现实项目结论。",
    runtime: {
      modelName: world.model_name ?? "DeepSeek Agent",
      decisions: world.action_audits.length,
      fallbacks: world.action_audits.filter((item) => item.fallback).length,
    },
  };
}

function diligenceOutcome(report: DueDiligenceReport, program: string): Outcome {
  const run = report.program_runs.find((item) => item.program === program && item.seed === report.configuration.seeds[0]) ?? report.program_runs.find((item) => item.program === program)!;
  const item = run.cases.find((row) => row.firm_id === "firm_risky") ?? run.cases[0];
  const summary = report.program_summary.find((row) => row.id === program)!;
  const evaluatedCases = report.program_runs.filter((candidate) => candidate.program === program).flatMap((candidate) => candidate.cases);
  const hasEvaluationSet = report.configuration.seeds.length > 1 && evaluatedCases.length > 2;
  const process = item.evidence.map((evidence) => ({ actor: reviewerName(evidence.requested_by), action: `${dimensionName(evidence.dimension)}核验`, feedback: `${evidenceSourceName(evidence.source_type)}显示，这项能力${evidenceLevel(evidence.observed_quality)}；${evidence.conflict > 0.3 ? "与企业材料存在明显差异" : evidence.conflict > 0.15 ? "与企业材料有一定出入" : "与企业材料基本一致"}。`, tone: evidence.conflict > 0.2 ? "warning" : "" }));
  process.push({ actor: "市级项目决策组", action: decisionName(item.decision), feedback: `事前失败风险估计 ${(item.estimated_failure_probability * 100).toFixed(0)}%，剩余不确定性 ${(item.uncertainty * 100).toFixed(0)}%。`, tone: item.decision === "reject" ? "warning" : item.decision === "conditional_pilot" ? "success" : "" });
  const metrics = hasEvaluationSet
    ? [{ label: "失败项目召回", value: pct(summary.metrics.recall.mean) }, { label: "不误伤好项目", value: pct(summary.metrics.specificity.mean) }, { label: "本案证据", value: `${item.evidence.length} 项` }, { label: "耗时", value: `${item.elapsed_days} 天` }]
    : [{ label: "当前处置", value: decisionName(item.decision) }, { label: "事前风险", value: pct(item.estimated_failure_probability) }, { label: "本案证据", value: `${item.evidence.length} 项` }, { label: "耗时", value: `${item.elapsed_days} 天` }];
  const evaluationFinding = hasEvaluationSet
    ? `在本组多案例实验中，该程序识别出约 ${pct(summary.metrics.recall.mean)} 的失败项目，同时保留 ${pct(summary.metrics.specificity.mean)} 的好项目。`
    : "这是一家企业的一次程序演示，尚不能据此计算识别率或误伤率；这两个指标需要一组有后续结果的历史项目。";
  return {
    headline: `对“${item.firm_name}”建议：${decisionName(item.decision)}`,
    conclusion: `程序没有读取企业的真实质量答案，而是通过 ${item.evidence.length} 项证据形成 ${(item.estimated_failure_probability * 100).toFixed(0)}% 的事前风险判断。`,
    metrics,
    process,
    findings: [item.evidence.some((row) => row.conflict > 0.2) ? "企业材料与独立观察存在明显差异，单靠多问几轮不足以解决。" : "企业材料与核验观察暂未出现重大冲突。", evaluationFinding, `最终处置是“${decisionName(item.decision)}”，不是简单的好/坏二元标签。`],
    governmentActions: ["将高冲突证据提交跨部门复核，而不是直接根据行业热度签约。", item.decision === "conditional_pilot" ? "把资金拨付与中试、客户验证和自筹到位绑定。" : "在签约前完成结论复核并留下审计链。", "用历史成功/失败项目重新校准阈值，持续报告误伤率。"],
    enterpriseActions: ["补充能够被第三方验证的资金来源和客户合同。", "对材料主张与核验观察之间的差异作出解释。", "接受可逆试点，用阶段结果换取后续完整支持。"],
    publicSummary: `政府并不是让人工智能直接给企业贴“好”或“坏”的标签，而是让不同部门逐项查证。这个程序用了 ${item.elapsed_days} 天，最后决定“${decisionName(item.decision)}”。它仍然可能判断错误；只有加入一组有后续结果的历史项目后，才能进一步报告识别率和误伤率。`,
    story: ["企业代表带来了一份漂亮的演示文稿。市场规模、融资计划、量产时间，每一页都指向同一个结论：机会稍纵即逝。", item.evidence[0] ? `第一份外部证据回来时，会议室里的语气变了。材料里的说法接近 ${(item.evidence[0].claim_value * 100).toFixed(0)} 分，核验结果却只有 ${(item.evidence[0].observed_quality * 100).toFixed(0)} 分。没有人立即宣布企业“不可靠”，他们决定继续查下一项。` : "项目组决定不只听材料里的说法。", item.decision === "conditional_pilot" ? "最后，市领导没有给出“好企业”或“坏企业”的判词。他写下的是“可逆试点”：让项目用真实进展证明自己，也让财政保留退路。" : item.decision === "reject" ? "最后，市领导仍然没有给企业贴上“坏”的标签。他写下的是“本轮不进入签约”，并把五项证据和复核路径一同附在决定后面。否决的是当前方案，不是用一句话给企业盖棺定论。" : `最后，市领导写下“${decisionName(item.decision)}”。这不是对企业的永久判决，而是对当前证据状态的程序回应。`],
    boundary: report.interpretation_boundary,
    runtime: {
      modelName: report.agent_runtime.model_name ?? "DeepSeek Agent",
      decisions: report.agent_runtime.audited_agent_decisions,
      fallbacks: report.agent_runtime.fallback_count,
    },
  };
}

function evidenceSourceName(source: string) { return ({ industry_expert: "行业专家评审", independent_verification: "独立资金核验", public_registry: "公开信用记录", third_party_reference: "第三方履历核查", cross_department_red_team: "跨部门反方质询", counterparty_check: "客户与交易对手核验", enterprise_material: "企业提交材料" } as Record<string, string>)[source] ?? "核验材料"; }
function evidenceLevel(value: number) { return value < 0.4 ? "证据偏弱" : value < 0.65 ? "仍需观察" : "已有较强支撑"; }

function rescueOutcome(report: DynamicCompetitionReport, policy: string): Outcome {
  const variant = report.variants.find((item) => item.id === policy) ?? report.variants[0];
  const rescue = variant.rescue_decisions.find((item) => item.decision !== "reject_rescue") ?? variant.rescue_decisions[0];
  const process = [
    ...variant.imitation_decisions.slice(0, 2).map((item) => ({ actor: cityName(item.city_id), action: item.strategy === "blocked" ? "模仿被拦截" : "跟进同类产业", feedback: item.strategy === "blocked" ? item.rationale : `观察到先发城市信号后，选择${imitationName(item.strategy)}，形成新增产能 ${item.added_capacity.toFixed(1)}。`, tone: item.strategy === "blocked" ? "warning" : "" })),
    { actor: "市场环境", action: `需求在 Q${report.common_conditions.demand_shock_quarter} 下滑`, feedback: `共同冲击 ${(report.common_conditions.demand_shock * 100).toFixed(0)}%，所有制度世界完全相同。`, tone: "warning" },
  ];
  if (rescue) process.push({ actor: cityName(rescue.city_id), action: rescueDecisionName(rescue.decision), feedback: `企业申请 ${rescue.requested_amount.toFixed(1)} 亿，财政上限 ${rescue.finance_limit.toFixed(1)} 亿，最终执行 ${rescue.approved_amount.toFixed(1)} 亿。`, tone: rescue.decision === "reject_rescue" ? "warning" : "success" });
  process.push({ actor: "规则引擎", action: "结算就业、产能与财政", feedback: `期末退出 ${variant.final.exited_firms} 家，僵尸企业 ${variant.final.zombie_firms} 家，救助支出 ${variant.final.rescue_spending.toFixed(1)} 亿。`, tone: "" });
  return {
    headline: `${variant.name}：就业 ${variant.final.total_employment.toLocaleString()}，财政救助 ${variant.final.rescue_spending.toFixed(1)} 亿`,
    conclusion: `同样的需求冲击下，该制度形成 ${variant.final.exited_firms} 家退出、${variant.final.zombie_firms} 家僵尸企业，期末产能利用率 ${(variant.final.utilization * 100).toFixed(0)}%。`,
    metrics: [{ label: "就业", value: variant.final.total_employment.toLocaleString() }, { label: "企业退出", value: `${variant.final.exited_firms} 家` }, { label: "僵尸企业", value: `${variant.final.zombie_firms} 家` }, { label: "救助支出", value: `${variant.final.rescue_spending.toFixed(1)} 亿` }],
    process,
    findings: ["城市模仿会把单个成功项目放大为重复产能。", "短期稳就业和长期财政效率并不总是一致。", `${variant.name}下，期末产能利用率为 ${(variant.final.utilization * 100).toFixed(1)}%。`],
    governmentActions: [policy === "unconditional" ? "为救助设置整改、产能压减和退出节点，避免永久续命。" : "为失业冲击预留转岗和社会保障安排。", "把城市模仿形成的新增产能纳入政策评估。", "同步报告短期就业和长期财政成本，不用单一指标下结论。"],
    enterpriseActions: ["在扩产前压力测试需求下降和政策退出情景。", "把救助条件转化为可完成的经营整改计划。", "若长期利用率不足，提前制定并购、转产或有序退出方案。"],
    publicSummary: `市场变差以后，政府面临两难：不救，岗位可能马上减少；一直救，财政压力和低效企业可能越来越多。本次“${variant.name}”世界最终有 ${variant.final.exited_firms} 家企业退出，政府支出 ${variant.final.rescue_spending.toFixed(1)} 亿元用于救助。`,
    story: ["产业园最热闹的时候，隔壁两座城市也立起了相似的厂房。每个人都相信需求还会继续增长，新的产能一条接一条上马。", `第 ${report.common_conditions.demand_shock_quarter} 个季度，订单突然少了。工厂的灯仍然亮着，但生产线开始空转。企业带着救助申请来到政府会议室，申请金额和财政底线第一次被摆在同一张纸上。`, `会议最后选择了“${variant.name}”。它保住了一些岗位，也付出了相应代价：期末救助支出 ${variant.final.rescue_spending.toFixed(1)} 亿元，退出 ${variant.final.exited_firms} 家，僵尸企业 ${variant.final.zombie_firms} 家。没有完美答案，只有被完整记录的取舍。`],
    boundary: report.interpretation_boundary,
    runtime: {
      modelName: report.agent_runtime.model_name ?? "DeepSeek Agent",
      decisions: report.agent_runtime.audited_agent_decisions,
      fallbacks: report.agent_runtime.fallback_count,
    },
  };
}

function actorName(role: string) {
  const exact = ({
    investment: "招商部门",
    finance: "财政部门",
    city_leader: "市领导",
    park: "产业园区",
    legal: "法务与信用组",
    technical: "技术评审组",
  } as Record<string, string>)[role];
  if (exact) return exact;
  if (role.startsWith("firm_")) return "项目企业";
  if (role.includes("finance")) return "财政部门";
  if (role.includes("legal")) return "法务与信用组";
  if (role.includes("technical")) return "技术评审组";
  if (role.includes("investment")) return "招商项目组";
  if (role.includes("leader")) return "市领导";
  if (role.includes("park")) return "产业园区";
  return role;
}
function reviewerName(id: string) { return id.includes("finance") ? "财政尽调组" : id.includes("legal") ? "法务与信用组" : id.includes("technical") ? "技术评审组" : "招商项目组"; }
function actionName(id: string) { return ({ preconsult_finance: "提前探测财政边界", disclose_fiscal_boundary: "公开财政边界", authorize_pilot: "授权分阶段试点", collective_deliberation: "进入集体会商", risk_assessment: "开展风险评估", legality_review: "完成合法性审查", mobilize_park_coalition: "组织园区协作", re_agenda: "重新列入议程", start_formal_process: "启动正式程序", resume_formal_process: "恢复正式程序", proceed_formal_review: "继续正式审查", pause_formal_process: "暂停并补充材料", return_for_revision: "退回修改" } as Record<string, string>)[id] ?? id; }
function modeName(id: string) { return ({ formal: "正式程序", informal: "非正式协调", hybrid: "混合模式" } as Record<string, string>)[id] ?? id; }
function dimensionName(id: string) { return ({ financing: "资金闭合", technology: "技术成熟", market: "市场验证", governance: "治理信用", execution: "交付能力" } as Record<string, string>)[id] ?? id; }
function decisionName(id: DueDiligenceCase["decision"]) { return ({ approve: "正式推进", conditional_pilot: "可逆试点", defer: "补证后再议", reject: "签约前否决" } as Record<string, string>)[id] ?? id; }
function rescueDecisionName(id: string) { return ({ unconditional: "无条件救助", unconditional_rescue: "无条件救助", conditional: "附条件救助", conditional_rescue: "附条件救助", reject_rescue: "拒绝救助" } as Record<string, string>)[id] ?? id; }
function imitationName(id: string) { return ({ aggressive_imitation: "激进模仿", targeted_imitation: "定向模仿", cautious_wait: "谨慎观望" } as Record<string, string>)[id] ?? "产业跟进"; }
function cityName(id: string) { return ({ city_lin: "临江市", city_hai: "海州市", city_yun: "云麓市" } as Record<string, string>)[id] ?? id; }
function pct(value: number) { return `${(value * 100).toFixed(0)}%`; }
