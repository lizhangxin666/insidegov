# InsideGov Console

InsideGov 的交互式推演控制台。页面数据全部来自 Python API，支持推进、干预、分支、恢复与导出。

```bash
npm install
npm run dev
```

启动前需在仓库根目录运行 `uv run uvicorn insidegov.api:app --reload`。如 API 不在 `http://localhost:8000`，设置 `NEXT_PUBLIC_INSIDEGOV_API_URL`。

需要 Node.js 22.13 或更高版本。
