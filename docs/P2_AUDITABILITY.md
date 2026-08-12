# P2.1 实验可审计性

P2.1 将分散的事件、谈判、记忆和 LLM 诊断串成统一证据链：

```text
局部观察 → 私有信息（默认脱敏）→ 认知建议 → 规则修正 → 最终执行 → 复盘
```

## 已实现

- `WorldState.action_audits` 保存每次招商提案、财政审核、领导协调和企业选址；
- 明确区分认知层建议、确定性规则调整与最终执行状态；
- 每条记录包含调用模型、结构化诊断、是否降级、检索记忆与行动复盘；
- API 每推进一个季度都保存不可变快照；
- 实验矩阵为每个策略、消融和 seed 保存完整世界与逐季度快照；
- 前端“Agent 行动审计”按季度和 Agent 筛选证据链；
- 默认 API 和导出均脱敏私有信息，仅展示使用过的字段名。

## 数据位置

- 交互世界：`.insidegov/worlds/<world-id>.json`
- 交互世界快照：`.insidegov/worlds/snapshots/<world-id>/qNN.json`
- 矩阵世界：`.insidegov/matrix-worlds/<world-id>.json`
- 矩阵快照：`.insidegov/matrix-worlds/snapshots/<world-id>/qNN.json`

重新运行矩阵后，新报告的 `strategy_runs` 和 `ablation_runs` 会包含
`world_id` 与 `world_archive`，可以从汇总结果下钻到完整世界。

## 查询接口

```text
GET /worlds/{world_id}/audits?quarter=1&agent_id=city_lin_finance
GET /worlds/{world_id}/snapshots
GET /worlds/{world_id}/snapshots/1
```

设置 `INSIDEGOV_ALLOW_PRIVATE_AUDIT=1` 后，受控调用可使用
`/audits?include_private=true` 或 `/export?include_private=true`。公开演示与默认导出不会泄露底线。

## 验收标准

选择任意已归档世界、季度和 Agent，应能回答：

1. 它当时看到了什么；
2. 使用了哪些私有信息字段；
3. 认知层建议了什么；
4. 规则引擎修改了什么；
5. 最终执行了什么；
6. 它如何复盘；
7. 是否发生修复、重试或降级。

## 下一阶段

P2.2—P2.4 已实现，验收说明见 [P2_PRODUCT_LOOP.md](P2_PRODUCT_LOOP.md)。
