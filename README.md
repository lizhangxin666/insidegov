# InsideGov / 置身事内

> 让 Agent 在政府与企业真正面对的约束中做选择。

InsideGov 是一个面向政企互动研究与政策演示的多智能体实验场。它把地方政府组织、财政土地约束、企业异质性、政策承诺、产业网络和市场周期放入同一个可重复运行的世界，使三个典型场景成为连续的生命周期：

1. 多城市招商竞争；
2. 政策兑现与承诺可信度；
3. 产业补贴、企业进入与产能演化。

核心世界现已继续演化到**城市模仿、企业退出与政府救助**：竞争城市会观察成功项目并自主选择模仿策略，需求冲击后困难企业进入跨部门救助会商，可严格比较市场退出、无条件救助和附条件救助的就业—财政—效率权衡。见 [docs/DYNAMIC_COMPETITION.md](docs/DYNAMIC_COMPETITION.md)。

另有一个**独立的人才对接场景**（需求 ↔ 政策 ↔ 能力映射），把「沟通协商机制」建成可运行的 2x2 反事实实验：语言模式（官话/人话）× 中介平台（关/开）。见 [docs/TALENT_SCENARIO.md](docs/TALENT_SCENARIO.md)。

再有一个**政企协商机制实验室**（双边协商与共同问题建构）：企业带着私有信息（真实需求 ≠ 第一轮表达）、政府带着有限认知进入协商，七种协商机制（自由/政策匹配/澄清优先/复述确认/约束先行/多方案/分阶段承诺）在完全相同的初始世界上反事实对比，产出帕累托前沿与 H1-H7 假设检验。见 [docs/NEGOTIATION_LAB.md](docs/NEGOTIATION_LAB.md)。

低质项目识别已升级为**无答案标签的证据型尽调实验**：政府 Agent 自主选择调查顺序和最终处置，只能观察企业材料与独立核验证据；隐藏的多维项目状态仅用于生成证据和事后结算。前端可比较五种程序、多 seed、误签/误伤和阈值曲线。见 [docs/DUE_DILIGENCE_RESEARCH.md](docs/DUE_DILIGENCE_RESEARCH.md)。

## 设计原则

- **LLM 负责想，模拟器负责算**：认知策略可替换，财政、土地、合同、项目、产能等状态由确定性规则更新。
- **客观世界与主观认知分离**：每个主体只有局部信息，并形成独立的可信度判断。
- **决策必须可追溯**：每次行动记录观察、目标、证据、约束、预期和实际结果。
- **实验必须可复现**：种子、配置、干预和事件日志构成完整实验记录。
- **seed 生成世界，不是只生成噪声**：种子同时决定城市财政/产业禀赋、企业私有偏好、部门底线、信用先验和项目扰动。
- **三个场景共用一个世界**：招商、履约和产业演化不是三套脚本，而是一条因果链。
- **组织而非个人是行动者**：不同部门拥有不同标准行为模板、职责能力、信息权限和禁止事项；Agent 可提出目录外行动并自主决定行动或等待，财政、合同与生产边界仍保持刚性。

## 快速开始

推荐使用 `uv` 安装与运行：

```bash
# 五分钟评委演示：实时生成基线、反事实、审计链和敏感性结果
uv run insidegov demo --seed 42 --fiscal-multiplier 0.5
# 真实案例校准与敏感性
uv run insidegov case-hefei-nio --seed 42 --quarters 16
uv run insidegov case-hefei-nio-sensitivity --seed 42 --quarters 16
uv run insidegov run --quarters 16
# 同一 seed 比较正式科层、非正式动力学与混合过程
uv run insidegov organization-compare --seed 42 --quarters 16

# 真实案例的组织行为校准：校准集选模式，后续节点做留出验证
uv run insidegov case-hefei-nio-org-calibration \
  --seeds 11,23,42,57,89 \
  --modes formal,informal,hybrid \
  --quarters 16
uv run insidegov compare
uv run insidegov matrix --no-llm
# 只跑确定性 + Flash（检查点保存在 .insidegov）
uv run insidegov matrix --strategies deterministic,deepseek-v4-flash
# 人才对接场景
uv run insidegov talent --language plain --platform
uv run insidegov talent-compare --seed 42
uv run insidegov talent-matrix --seeds 11,23,42,57,89
# 政企协商机制实验室
uv run insidegov negotiate --protocol clarify_first --seed 42
uv run insidegov negotiate-compare --seed 42
uv run insidegov negotiate-matrix --seeds 11,23,42,57,89
```

启动 API：

```bash
uv run uvicorn insidegov.api:app --reload --port 8000
```

启动推演控制台：

```bash
cd apps/web
npm install
npm run dev
```

Web 端要求 Node.js 22 或更高版本。也可以运行 `make demo-stack` 同时启动 API 与前端，
然后在首页点击“进入五分钟演示”。演示使用确定性认知层，断网时也能完成，不消耗
模型 Token。详细讲解词和验收步骤见 [docs/DEMO.md](docs/DEMO.md)。

默认使用确定性认知层。需使用 DeepSeek 时，复制 `.env.example` 的变量到本地 `.env`，将凭据放在 `DEEPSEEK_API_KEY`，然后在控制台“研究说明”中创建 LLM 世界。密钥不应提交到 Git。

## 仓库结构

```text
src/insidegov/       世界模型、规则引擎、场景、API 与 CLI
apps/web/            React 推演控制台
configs/             可版本化实验配置
docs/                架构、机制、实验与开源说明
tests/               可复现性和关键约束测试
比赛信息/             原始赛题材料（参考文献 PDF 默认不进入 Git）
```

## 当前能力

- 三座异质城市、招商局—财政局—市领导—企业董事会可执行 Agent 与供应商网络；
- **组织行动内核**：招商、财政、司法审查、园区、市领导、企业与产业基金拥有角色专属标准行为模板，但模板不是行动上限；开放行动经能力、禁止事项和执行原语编译后进入世界。各部门自主争夺有限注意力，正式程序可启动、暂停、退回、恢复或重新议程化。
- **组织自主学习闭环**：组织保存跨季度计划树并比较候选策略；可提出目录外行动并接受职责和资源审查；上级政策、会议、竞争、财政、舆情和领导更替形成内生机会窗口；否决、协调和企业回应持续更新信任、策略偏好、组织惯例与可迁移教训。
- Agent 私有观察、记忆检索、结构化行动、事后复盘与财政否决协调；
- 多维招商政策包和企业异质偏好；
- 有条件承诺、财政支付、延期与信誉更新；
- 龙头落地、供应商进入、集聚效应、需求冲击与产能利用率；
- 单步/连续推进、用户干预、原子持久化、服务重启恢复、完整导出和反事实分支；
- DeepSeek OpenAI 兼容接口，支持 `deepseek-v4-flash` / `deepseek-v4-pro`，异常时单步自动降级；
- 四类 Agent 独立校准任务；确定性与两种 DeepSeek 的多种子矩阵；五组机制消融；均值、方差和失败案例报告；
- 私有信息、内部治理、信用扩散、供应链溢出均进入状态转移公式；消融会改变入园门槛、履约数和集群规模，不只是更改提示词。
- **五分钟典型博弈回放**：从公开事实与参数来源，到企业表达、政府内部审核、联合基金、分期合同、跨期履约和财政冲击反事实；所有 ID 和结果均由本次运行生成，不是前端预写结局。
- **实验报告中心**：策略与消融均值、单个 seed、失败/降级原因和归档世界下钻，支持 JSON 导出。
- **P2 产品闭环**：历史季度复制、自然语言干预人工确认、证据约束的 Agent 访谈、HTML/JSON 自动报告、文本材料参数抽取与溯源。
- **真实案例校准**：合肥—蔚来公开参数卡，本级财政与三类联合产业基金分账结算，以及15%—35%财政空间敏感性。
- **人才对接场景**：企业需求向量化表达、政策工具包与语言模式（官话/人话）设计、人才解读协商（理解度/信任/覆盖度）、可选平台翻译撮合、合同分期兑现与知识外溢，以及 2x2 反事实矩阵。
- **政企协商机制实验室**：企业双层需求与政府信念分离、七种协商机制反事实对比；低质项目模块不读取答案标签，由资金/技术/市场/治理/交付证据驱动多 Agent 自主尽调，并报告假阳性、假阴性、Brier、阈值敏感性和分阶段承诺结果。

## 产品文档

完整的产品定位、目标用户、端到端流程、世界与 Agent 设计、功能需求、验收标准和版本路线见 [docs/PRODUCT.md](docs/PRODUCT.md)。组织行动的现实依据与编码边界见 [docs/research/organizational-behavior-evidence.md](docs/research/organizational-behavior-evidence.md)，计划、开放行动、机会窗口和学习机制见 [docs/research/organization-autonomy-upgrade.md](docs/research/organization-autonomy-upgrade.md)。系统实现另见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)，研究机制与结论边界见 [docs/MODEL.md](docs/MODEL.md)。人才对接场景见 [docs/TALENT_SCENARIO.md](docs/TALENT_SCENARIO.md)；政企协商机制见 [docs/NEGOTIATION_LAB.md](docs/NEGOTIATION_LAB.md)；无答案标签尽调研究见 [docs/DUE_DILIGENCE_RESEARCH.md](docs/DUE_DILIGENCE_RESEARCH.md)。

## 研究边界

这是政策实验与机制探索工具，不是现实政策预测器。默认参数用于展示机制，不代表真实城市；任何经验结论都应经过数据校准、敏感性分析和外部验证。详细说明见 [docs/MODEL.md](docs/MODEL.md)。

## 开源

代码采用 MIT License。提交贡献前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 和 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。书籍 PDF 等受版权保护材料不会纳入公开仓库。

公开前可运行 `make verify`，一次检查 Python 测试/Ruff 与 Web lint/typecheck/test/build。
`.env`、`.insidegov/`、本地检查点、运行日志与参考文献 PDF 均已默认排除。如果密钥曾在聊天、终端或截图中暴露，应在开源前到服务商控制台轮换；仅从 Git 删除它不等于失效。
