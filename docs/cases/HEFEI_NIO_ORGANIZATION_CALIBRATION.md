# 2020合肥—蔚来：组织行为校准与质量评估设计

## 为什么需要单独做组织行为校准

现有真实案例参数卡已经校准了财政规模、70亿元战略投资、企业资产与现金投入、
产能和分期结构，但“数值接近历史结果”不等于“组织行为接近真实过程”。本评估把
参数校准与行为校准分开，回答五个不同问题：

1. 模拟是否复现了公开可观察的关键组织行为；
2. 行动主体、权限和工具是否匹配；
3. 框架协议、正式协议、分期出资和执行是否保持正确顺序；
4. 未用于模式选择的后续历史节点能否被模拟命中；
5. 系统是否把不可观察的内部过程错误包装成历史事实。

## 证据编码规则

每条证据被标记为以下类型之一：

| 类型 | 含义 | 是否评分 |
|---|---|:---:|
| `direct_public_record` | 协议、年报或公告直接披露 | 是 |
| `triangulated_inference` | 多份材料共同支持机制类别，但不支持逐轮细节 | 低权重 |
| `triangulated_public_record` | 多来源支持后续方向性结果 | 是 |
| `not_publicly_observable` | 内部会商、否决措辞、游说对象没有公开记录 | 否 |

因此，“财政局具体说了什么”“市领导是否在某次会前单独协调”不会被编码为历史金标准。
这些行为可以在模拟世界中出现，但必须标为模型生成的机制路径。

## 校准集与留出集

### 校准集：截至2020年4月29日

- 2月先形成总部落户框架协议，4月再签正式投资和股东协议；
- 疫情期间招商推动与最终正式治理结构并存；
- 国投招商、安徽省高新投、合肥市建投等多主体联合参与；
- 核心工具为股权投资，不是单一财政局无条件现金补贴；
- 70亿元采用五期出资；
- 部分后续支持与产能、采购额、车辆销售等绩效条件挂钩。

### 留出验证集

- 2020年6月：首两期50亿元中48亿元到账；
- 2020年10月：蔚来中国总部正式启用；
- 此后：政企继续推进智能电动汽车产业链合作。

模式选择只能看到校准集。留出节点不能参与选择，否则只是把历史结局重新写进模型。

## 评分结构

| 指标 | 权重 | 说明 |
|---|---:|---|
| 校准事件拟合 | 35% | 公开行为、组织结构和合同工具 |
| 留出节点 | 35% | 早期到账、运营里程碑和产业扩散 |
| 角色边界 | 12% | 基金、财政、司法和领导是否越权 |
| 证据纪律 | 10% | 行动是否有机制依据，是否区分事实与模拟 |
| 行动顺序 | 8% | 动员、审查、基金尽调和合同执行的相对顺序 |

高“校准得分”本身不代表预测能力，因为70亿元等结构已经用于建模。真正更重要的是
留出得分、失败节点和跨案例外部验证。

## 数据源

- [NIO 2020 Form 20-F](https://www.sec.gov/Archives/edgar/data/1736541/000110465921046834/nio-20201231x20f.htm)
- [NIO China Shareholders Agreement](https://www.sec.gov/Archives/edgar/data/1736541/000110465920061585/nio-20191231xex4d36.htm)
- [蔚来正式投资协议公告](https://ir.nio.com/news-events/news-releases/news-release-details/nio-announces-entry-definitive-agreements/)
- [蔚来早期到账公告](https://ir.nio.com/news-events/news-releases/news-release-details/nio-announces-substantial-completion-cash-injections/)
- [商务部转载：2020年2月框架协议](https://tradeinservices.mofcom.gov.cn/article/news/gnxw/202002/99256.html)
- [商务部：蔚来中国总部启用](https://tradeinservices.mofcom.gov.cn/article/shidian/jyjliu/202201/125856.html)
- [国务院国资委：多投资主体协同](https://wap.sasac.gov.cn/n2588025/n2588129/c18459830/content.html)

## 运行

```bash
uv run insidegov case-hefei-nio-org-calibration \
  --seeds 11,23,42,57,89 \
  --modes formal,informal,hybrid \
  --quarters 16
```

报告写入：

```text
docs/reports/hefei-nio-organization-calibration/report.json
docs/reports/hefei-nio-organization-calibration/report.md
```

## 当前评估边界

- 单案例主要提供内部效度，不能证明适用于其他产业和城市；
- 真实自然月被映射为政策阶段季度，不能逐日比较；
- 全市产业链发展无法识别为单一项目的净因果效应；
- 确定性策略在强案例参数下可能跨seed差异过小；
- 下一步需要加入第二个失败或退出案例，并让专家对事件编码进行双人复核。
