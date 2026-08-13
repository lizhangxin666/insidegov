# Agent 行为边界：开放生成、权力约束与确定性执行

## 核心原则

```text
行为可以开放生成，权力不能开放生成；
策略由 Agent 提出，后果由规则引擎结算。
```

`ACTION_CATALOG` 与 `ROLE_AFFORDANCES` 是常见、可复现的标准行为模板，不是穷尽式
白名单。Agent 仍可选择 `propose_open_action`，提交一个新的组织行动：

```python
class NovelOrganizationAction(BaseModel):
    title: str
    intent: str
    mechanism: str
    domain: str
    arena: Literal["formal", "informal", "public", "market"]
    target_actor_ids: list[str]
    requested_information: list[str]
    authority_claims: list[str]
    requested_effects: dict[str, float]
    resource_request: dict[str, float]
    timing: str
    reversibility: float
    rationale: str
```

`mechanism` 可以是 Agent 新提出的 snake_case 名称，不需要预先出现在机制目录。

## 能力与禁止事项

`RoleCapability` 保存：

```python
domains
information_scopes
resource_authorities
approval_authorities
prohibitions
arenas
```

全局禁止事项包括：

- 凭空创造财政、土地或产能；
- 伪造证据；
- 读取未授权私有信息；
- 改写历史事件或随机状态；
- 跳过必须的法律程序；
- 直接指定项目成功、失败或生产结果。

“提出资源申请”和“创造资源”不同。例如招商局可以提出 20 亿元产业支持申请，但申请
只会形成待财政局和市领导处理的审批事项，不会使 `available_budget` 自动增加。

## 五级权限结果

| 状态 | 含义 | 是否立即产生世界效果 |
|---|---|---:|
| `execute` | 在本组织职责内直接执行 | 是，限于安全效果维度 |
| `execute_with_limits` | 可以执行，但申请幅度被压至上限 | 是，执行限幅后的效果 |
| `requires_coordination` | 行动有效，但需要其他主体参与或同意 | 否，先形成协调事项 |
| `requires_approval` | 涉及资源或正式授权 | 否，先形成审批事项 |
| `blocked` | 违反禁止事项、信息权限或程序模式 | 否 |

## 执行原语

自由行动不会直接转换为任意 Python 代码，而是编译为有限原语：

```text
send_message
request_information
schedule_meeting
open_agenda
create_proposal
request_resource
request_approval
wait
bounded_state_effect
block
```

例如：

```text
招商局提出“请行业协会组织闭门订单核验”
→ send_message
→ request_information
→ schedule_meeting
→ requires_coordination
```

```text
招商局提出“增加 20 亿元专项支持”
→ create_proposal
→ request_resource
→ request_approval
→ requires_approval
```

```text
招商局提出“直接把可用预算增加 20 亿元”
→ block
→ direct_state_mutation:available_budget_delta
```

## 查询接口

```text
GET /organization/actions
GET /organization/capabilities
```

前者返回标准行为模板，并标记
`catalog_semantics=standard_affordance_not_exhaustive_whitelist`；后者返回角色能力、
全局禁止事项和五级权限状态。
