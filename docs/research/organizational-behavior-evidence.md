# 组织行动内核：行为依据与编码边界

本模块模拟的是组织行动，而不是把部门拟人化为拥有无限行为能力的个人。组织 Agent 只能从与其职责、权限和所处程序相匹配的动作集中选择；确定性规则仍负责财政扣减、合同生效、项目进度、生产和违约后果。

## 1. 正式科层程序

司法部对《重大行政决策程序暂行条例》的官方说明将公众参与、专家论证、风险评估、合法性审查和集体讨论列为法定程序，其中合法性审查和集体讨论是刚性程序；行政首长最后发表意见，意见与多数不一致时需说明理由，讨论过程应记录并追责。

- 来源：[司法部负责人就《重大行政决策程序暂行条例》答记者问](https://www.moj.gov.cn/pub/sfbgw/zcjd/201905/t20190516_390231.html)
- 编码：`risk_assessment`、`legality_review`、`collective_deliberation`。
- 边界：正式模式不得跳过合法性审查和集体讨论；风险评估影响财政局选择的风险政策，但不直接创造财政资金。

## 2. 政府投资基金的独立决策

国务院办公厅的指导意见要求政府投资基金市场化、法治化、专业化运作，建立独立投资决策和尽职调查机制；政府部门可以监督投向和进度，但不得以行政手段干预日常管理和具体项目投资决策。

- 来源：[国务院办公厅关于促进政府投资基金高质量发展的指导意见](https://www.mee.gov.cn/zcwj/gwywj/202501/t20250108_1100235.shtml)
- 编码：`fund_due_diligence`，基金根据自身资本余额、尽调阈值和项目质量独立批准或拒绝。
- 边界：市领导不能把被财政否决的现金自动转换为基金出资；基金批准额不占本级财政现金上限，但进入基金自身资本和履约账本。

## 3. 非正式政治动力学

Chen 与 Bian 对中国城市政策试验的研究把政策推动中的困难概括为对上议程设置、同级协调和对下执行。当正式权力网络不足时，政策企业家会作为对上的“主动顾问”、对同级的“修辞盟友”和对下的“支持型导师”建立非正式网络。

- 来源：[Policy Experimentation within Bureaucratic Power Networks](https://www.cambridge.org/core/journals/china-quarterly/article/policy-experimentation-within-bureaucratic-power-networks-the-policebusiness-cooperation-scheme-in-urban-china/6E7E2E1536065118E626082F0CFF58E8)
- 编码：`frame_strategic_project`、`mobilize_park_coalition`、`preconsult_finance`、`broker_compromise`、`authorize_pilot`。
- 边界：非正式不等于违规。它可以改变议程优先级、信任、联盟、行动顺序和政策工具组合，但最终报价仍必须通过财政硬约束。

## 4. 有限注意力

科层组织中的政策议题竞争受到有限注意力约束，项目进入领导议程不是固定事件。

- 来源：[Competition for attention in the Chinese bureaucracy](https://link.springer.com/article/10.1186/s40711-018-0071-z)
- 编码：每座城市拥有可变化的 `agenda_priority`；招商局可尝试上推议题，但是否成为优先事项受季度、竞争压力和既有联盟共同影响。

## 三种模式的实验含义

| 模式 | 允许的自主行动 | 必须保留的硬边界 |
|---|---|---|
| 正式 | 材料补充、需求澄清、风险政策选择 | 合法性审查、集体讨论、财政结算 |
| 非正式 | 会前沟通、议程上推、同级联盟、领导调解、试点 | 财政硬约束、合同和生产规则 |
| 混合 | 先由非正式网络组织注意力和方案，再进入正式审查 | 正式审查链与全部状态结算 |

三模式共享同一个初始世界和随机种子。比较结果用于识别“程序如何改变行动路径与结果”，不代表某一现实制度的真实因果效应大小。

## 行动发起与程序状态机

v0.6 不再由季度脚本指定“谁先行动”。每个招商局、财政局、园区和市领导都会独立输出：

```text
act / wait
+ 本角色权限内的 action_id
+ urgency
+ target_actor_id
+ rationale
```

同一城市每轮只有有限的 `attention_budget`。主动发起者按紧迫度竞争注意力，未入选行动会被记录为 `deferred`，主动等待则记录为 `wait`；两者都保留当时可选动作、理由和复盘，因而不会在展示层被误写成“什么都没有发生”。

随后市领导从与当前状态相容的转换中决策：

```text
dormant → start / pause / return
paused 或 returned → resume / re-agenda / abandon
completed → re-agenda / keep closed
active → proceed / pause / return
```

只有 `start`、`resume`、`re-agenda`、`proceed` 或非正式模式下的授权动作会放行对外报价。正式或混合模式一旦放行，风险评估、合法性审查和集体讨论仍是不可跳过的规则门；Agent 决定程序是否与何时进入，规则引擎决定进入后必须满足什么。

## 企业的时点自主性

企业董事会不再在 Q3 被固定选址。它对每座城市逐轮输出 `accept / counter / terminate`，并在全局层面输出 `select_now / continue_negotiating / exit_all`。认知层可比较效用差距、信息充分度、其他城市状态和等待成本；规则层只保留两条边界：低于私有最低效用门槛的接受不会执行，达到实验最大谈判轮次时必须选址或退出。

因此，同一世界中可能出现 Q1 提前接受、程序退回后 Q2 恢复、连续还价、暂停等待或全部退出，而不是统一沿用 Q1—Q3 的预写节奏。
