#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"

if ! command -v uv >/dev/null 2>&1; then
  echo "缺少 uv：请先安装 https://docs.astral.sh/uv/" >&2
  exit 1
fi

if ! command -v node >/dev/null 2>&1; then
  echo "缺少 Node.js 22+。" >&2
  exit 1
fi

node_major="$(node -p 'process.versions.node.split(`.`)[0]')"
if (( node_major < 22 )); then
  echo "当前 Node.js 为 $(node -v)，Web 演示需要 Node.js 22+。" >&2
  exit 1
fi

api_pid=""
web_pid=""
cleanup() {
  [[ -n "$api_pid" ]] && kill "$api_pid" 2>/dev/null || true
  [[ -n "$web_pid" ]] && kill "$web_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

uv run uvicorn insidegov.api:app --host 127.0.0.1 --port 8000 &
api_pid=$!
(
  cd apps/web
  npm run dev
) &
web_pid=$!

echo "InsideGov API: http://127.0.0.1:8000"
echo "InsideGov Web: http://localhost:3000"
echo "按 Ctrl+C 停止两个服务。"
wait "$api_pid" "$web_pid"
