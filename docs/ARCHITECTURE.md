# 系统架构

InsideGov 采用“认知层提出行动、规则层验证并执行、事件层记录证据”的分层结构。

```mermaid
flowchart TB
  UI[推演控制台] --> API[实验 API]
  API --> Orchestrator[时间与行动调度]
  Orchestrator --> Policy[可插拔认知策略]
  Policy --> Validator[权限与资源校验]
  Validator --> Rules[确定性规则引擎]
  Rules --> State[(World State)]
  State --> Memory[局部记忆与主观信念]
  Memory --> Policy
  Rules --> Trace[(事件与决策证据)]
  Trace --> UI
```

## 模块边界

- `models.py`：世界状态与结构化动作的数据契约；
- `policies.py`：Agent 认知与选择策略，默认实现完全确定；
- `engine.py`：财政、土地、合同、项目、市场和产业网络规则；
- `scenarios.py`：初始世界工厂，不包含预设结局；
- `experiments.py`：相同初始条件下的反事实分支；
- `api.py`：创建、推进、干预、复制和审计世界；
- `apps/web`：面向演示和研究的可视化控制台。

## 接入 LLM 的原则

未来的 `LLMPolicy` 只能返回符合动作 Schema 的提案。引擎仍然负责权限、预算、合同和状态变更。外部模型不可直接修改 `WorldState`，失败的行动会附原因返回认知层重新规划。

