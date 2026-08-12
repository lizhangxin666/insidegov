# 真实案例参数卡：2020合肥—蔚来

## 案例定位

本案例用于校准现有“政府内部协商—企业回应—条件承诺—履约—供应链扩散”世界，
不是对历史交易的机械复刻。公开事实只提供初始条件和历史核验基准，Agent仍通过
正常策略实时提出政策包，财政规则仍独立计算硬上限。

## 公开事实

| 事实 | 数值/时间 | 来源 |
|---|---:|---|
| 战略投资者现金投资 | 70亿元，取得24.1%股权 | [蔚来投资者关系公告](https://ir.nio.com/news-events/news-releases/news-release-details/nio-announces-entry-definitive-agreements/) |
| 企业现金投入 | 42.6亿元 | [蔚来投资者关系公告](https://ir.nio.com/news-events/news-releases/news-release-details/nio-announces-entry-definitive-agreements/) |
| 注入核心资产估值 | 177.7亿元 | [蔚来投资者关系公告](https://ir.nio.com/news-events/news-releases/news-release-details/nio-announces-entry-definitive-agreements/) |
| 战略投资五期付款 | 35、15、10、5、5亿元 | [蔚来投资者关系公告](https://ir.nio.com/news-events/news-releases/news-release-details/nio-announces-entry-definitive-agreements/) |
| 2020年6月实际到账 | 首两期50亿元中到账48亿元，余2亿元约定9月底前支付 | [蔚来实际到账公告](https://ir.nio.com/news-events/news-releases/news-release-details/nio-announces-substantial-completion-cash-injections/) |
| 最终现金出资履行 | 2020年年报确认双方现金出资义务均已履行 | [NIO 2020 Form 20-F](https://www.sec.gov/Archives/edgar/data/1736541/000110465921046834/nio-20201231x20f.htm) |
| 制造基地年产能 | 12万辆 | [NIO 2020 Form 20-F](https://www.sec.gov/Archives/edgar/data/1736541/000110465921046834/nio-20201231x20f.htm) |
| 2020年合肥一般公共预算收入 | 762.90亿元 | [合肥市2020年统计公报转载](http://www.tjcn.org/tjgb/12ah/36644.html) |
| 2022年合肥新能源汽车产业链 | 新签约145个项目；上下游企业300余家 | [新华社调研](https://www.news.cn/fortune/2023-06/01/c_1129663466.htm) |

## 参数来源分层

| 模拟参数 | 最终值 | 类型 | 说明 |
|---|---:|---|---|
| `city_lin.fiscal_budget` | 762.9亿元 | 公开资料 | 财政规模，不等于项目可动用资金 |
| `city_lin.available_budget` | 190.725亿元 | 专家判断 | 暂取公共预算收入25%，需做15%—35%敏感性分析 |
| `city_lin.objective_credibility` | 0.92 | 专家判断 | 将快速到账及最终履行映射为初始信用指数 |
| `city_lin.supply_chain` | 68/100 | 专家判断 | 将既有制造能力和后续产业链事实映射为指数 |
| `city_lin.administrative_capacity` | 92/100 | 专家判断 | 将交易交割与到账速度映射为执行能力 |
| `city_lin.talent_pool` | 78/100 | 模型假设 | 公开协议没有足够人才数据 |
| `firm_nova.investment_capacity` | 220.3亿元 | 公开资料 | 177.7亿元资产＋42.6亿元现金 |
| `firm_nova.cash` | 42.6亿元 | 公开资料 | 企业现金投入 |
| `firm_nova.production_capacity` | 12万辆/年 | 公开资料 | 年报披露的江淮合作工厂产能 |
| `firm_nova.jobs_capacity` | 2500人 | 模型假设 | 年报仅披露全球员工7763人，不能直接作为合肥新增就业 |
| `supplier.entry_window` | Q10—Q16 | 模型假设 | 145个新项目不能识别蔚来单独贡献，暂不作为企业级进入速度 |

当前版本没有把任何参数伪标成“用户手动设定”。用户在前端修改并确认后，才应使用
`user_input` 标签。

## 实际运行结果

运行条件：确定性认知层、seed 42、16季度。

### 基线

- 蔚来中国选择合肥市；
- Q1企业还价，Q2和Q3接受；
- 合肥招商局Q3提出：现金18.47亿元、股权17.28亿元；
- 财政规则压回：现金上限9.54亿元、股权上限16.48亿元；
- 最终可执行政策包：现金9.54亿元＋股权16.48亿元＋信贷支持23.04亿元，财政成本27.86亿元；
- 五项承诺全部履行，规则结算支付27.86亿元；
- Q9投产，Q16共有12家供应商进入，集群规模13，就业5416。

历史的70亿元股权投资与模拟的16.48亿元股权工具存在明显差距。这是模型校准结果，
不是错误隐藏：当前财政硬约束与招商提案函数不能解释历史联合投资者的出资规模。
后续应增加“多层级政府投资主体/产业基金联合出资”，而不应简单放宽财政上限。

### 反事实：Q4可用财力下降50%

选址已经在Q3完成，因此企业仍落户合肥，但履约与产业扩散发生变化：

| 指标 | 基线 | 财力下降50% | 差值 |
|---|---:|---:|---:|
| 已履行承诺 | 5 | 3 | -2 |
| 已支付政策金额 | 27.86亿元 | 22.12亿元 | -5.74亿元 |
| 合肥客观信用 | 0.955 | 0.250 | -0.705 |
| 进入供应商 | 12 | 2 | -10 |
| 集群规模 | 13 | 3 | -10 |
| 就业 | 5416 | 3008 | -2408 |

因果链为：

```text
Q4可用财力下降
→ 部分股权/补贴承诺延期
→ 客观信用与企业感知信用下降
→ 边缘供应商未达到进入门槛
→ Q16集群与就业低于基线
```

这组差值是当前规则与参数下的模拟结果，不能直接表述为现实政策效应大小。

## 运行

```bash
uv run insidegov case-hefei-nio --seed 42 --quarters 16

# Q4可用财力降至原来的50%
uv run insidegov case-hefei-nio --seed 42 --quarters 16 --fiscal-shock 0.5
```
