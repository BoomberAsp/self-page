#!/bin/bash
set -euo pipefail
# OneWeblog 更新脚本 — 拉取代码 + 构建 + 重载 Nginx

PROJECT_DIR="/opt/oneweblog"

cd "$PROJECT_DIR"
git pull origin main
npm ci --omit=dev 2>/dev/null || npm install
npx astro build
sudo nginx -t && sudo systemctl reload nginx

echo "更新完成: https://oneweblog.cn"
