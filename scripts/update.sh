#!/bin/bash
set -euo pipefail
# OneWeblog 更新脚本 — 安装依赖 + 构建 + 重启 Node

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

npm install
npx astro build
pm2 restart oneweblog

echo "更新完成: https://oneweblog.cn"
echo "新增内容即刻生效，无需重启。"
