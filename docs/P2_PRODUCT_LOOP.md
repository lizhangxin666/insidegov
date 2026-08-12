# P2.2—P2.4 产品闭环验收

> 核心招商与双边协商已进一步合并，见 [UNIFIED_NEGOTIATION_WORLD.md](UNIFIED_NEGOTIATION_WORLD.md)。

## P2.2：严格反事实闭环

- 每季度世界快照保存 Python PRNG 的完整内部状态；
- 可从任意已保存季度创建一对“基线副本 / 干预副本”；
- 两个副本从相同世界状态和相同随机状态开始；
- 成对世界在同一服务进程内共享认知响应缓存；相同观察下的 LLM 动作保持一致，
  只有干预改变上下文后才重新请求并分叉；
- 无干预时同步推进，历史、事件和指标保持一致；
- 自然语言先解析为白名单 `InterventionPlan`，必须人工确认；
- 确认后才由规则引擎执行财政乘数、专项资金、信用或需求变化；
- 两个世界可同步推进并返回就业、集群、信用和财政承诺差异。

## P2.3：解释闭环

- 采访固定到指定世界、季度和 Agent；
- 回答只使用该季度快照中的观察、记忆、行动和规则执行证据；
- 自动区分当时已知、私有字段、当时未知、事后信息与假设性判断；
- 没有历史行动时明确拒绝补写理由；
- 自动报告包含世界卡、关键事件链、基线/分支差异、Agent 审计、LLM
  修复/重试/降级和现实外推边界；
- 报告输出为自包含 HTML。

## P2.4：材料闭环

- 材料以文件名和原文内容上传；
- 从原文抽取城市、机构及带证据的候选参数；
- 每个参数保存原文证据、建议值、置信度、来源类型和最终确认值；
- 无原文证据的值明确标为 `demo_assumption`；
- 所有参数都必须由用户确认，才能创建世界；
- 确认后的参数溯源写入 `WorldState.parameter_provenance`，随世界永久保存。

## 前端路径

```text
分支实验台
├── 历史分支＋自然语言干预
├── 采访 Agent
├── 材料建世界
└── 自动报告
```

首页另提供两条面向评委的证据入口：

- **五分钟典型博弈回放**：从案例参数、企业表达和内部会商，一直下钻到条件承诺、
  规则结算和共同随机数反事实；
- **实验结果**：浏览矩阵报告，从策略/消融均值下钻到单个seed、归档世界、失败和
  降级原因，并导出JSON。

## 核心接口

```text
POST /worlds/{id}/counterfactual-pairs
POST /worlds/{id}/intervention-plans
POST /worlds/{id}/intervention-plans/confirm
POST /experiments/sync-worlds
POST /worlds/{id}/interviews
POST /worlds/{id}/reports
POST /materials/candidates
POST /materials/candidates/{id}/confirm
POST /demos/hefei-nio
GET  /cases/hefei-nio/sensitivity
GET  /experiment-reports
GET  /experiment-reports/{id}
GET  /experiment-reports/{id}/worlds/{world_id}
```

## 当前边界

- 自然语言干预采用受限解析器，只允许经过白名单的数据路径；
- 模拟 PRNG 状态可跨进程恢复；LLM 的成对响应一致性依赖同一服务进程中的共享缓存，
  若要跨机器严格重放，还需把认知缓存一并持久化；
- Agent 采访当前采用证据模板生成，不调用 LLM 扩写，优先保证不越权和可复现；
- 材料抽取当前支持文本内容。PDF/Word 可先提取文本再提交；
- 自动报告解释的是模拟内部机制，不是对现实政策效果的统计因果识别。
