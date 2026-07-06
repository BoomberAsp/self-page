#!/bin/bash
set -euo pipefail
# OneWeblog 更新脚本 — 安装依赖 + 构建 + 重载 Nginx

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

npm ci --omit=dev 2>/dev/null || npm install
npx astro build
sudo nginx -t && sudo systemctl reload nginx

echo "更新完成: https://oneweblog.cn"
