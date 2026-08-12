# InsideGov Console

InsideGov 的交互式推演控制台。页面数据全部来自 Python API，支持推进、干预、分支、恢复与导出。v0.5 首页提供“进入五分钟演示”和“实验结果”两个主入口：前者实时生成典型博弈与反事实，后者支持矩阵均值、seed、消融和失败案例下钻。

```bash
npm install
npm run dev
```

启动前需在仓库根目录运行 `uv run uvicorn insidegov.api:app --reload`。如 API 不在 `http://localhost:8000`，设置 `NEXT_PUBLIC_INSIDEGOV_API_URL`。

也可在仓库根目录运行 `make demo-stack` 一键启动前后端。确定性演示不需要API Key。

需要 Node.js 22.13 或更高版本。
