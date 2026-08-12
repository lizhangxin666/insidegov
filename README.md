# InsideGov / 置身事内

> 让 Agent 在政府与企业真正面对的约束中做选择。

InsideGov 是一个面向政企互动研究与政策演示的多智能体实验场。它把地方政府组织、财政土地约束、企业异质性、政策承诺、产业网络和市场周期放入同一个可重复运行的世界，使三个典型场景成为连续的生命周期：

1. 多城市招商竞争；
2. 政策兑现与承诺可信度；
3. 产业补贴、企业进入与产能演化。

## 设计原则

- **LLM 负责想，模拟器负责算**：认知策略可替换，财政、土地、合同、项目、产能等状态由确定性规则更新。
- **客观世界与主观认知分离**：每个主体只有局部信息，并形成独立的可信度判断。
- **决策必须可追溯**：每次行动记录观察、目标、证据、约束、预期和实际结果。
- **实验必须可复现**：种子、配置、干预和事件日志构成完整实验记录。
- **三个场景共用一个世界**：招商、履约和产业演化不是三套脚本，而是一条因果链。

## 快速开始

核心引擎只使用 Python 标准库，可直接运行：

```bash
PYTHONPATH=src python3 -m insidegov.cli run --quarters 16
PYTHONPATH=src python3 -m insidegov.cli compare
```

启动 API：

```bash
python3 -m pip install -e '.[dev]'
uvicorn insidegov.api:app --reload --port 8000
```

启动推演控制台：

```bash
cd apps/web
npm install
npm run dev
```

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

- 三座异质城市、政府内部角色、龙头企业和供应商网络；
- 多维招商政策包和企业异质偏好；
- 有条件承诺、财政支付、延期与信誉更新；
- 龙头落地、供应商进入、集聚效应、需求冲击与产能利用率；
- 单步推进、连续运行、用户干预、状态快照和反事实分支；
- 无 API Key 的确定性策略；未来可接入 LLM 策略适配器。

## 研究边界

这是政策实验与机制探索工具，不是现实政策预测器。默认参数用于展示机制，不代表真实城市；任何经验结论都应经过数据校准、敏感性分析和外部验证。详细说明见 [docs/MODEL.md](docs/MODEL.md)。

## 开源

代码采用 MIT License。提交贡献前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 和 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。书籍 PDF 等受版权保护材料不会纳入公开仓库。

