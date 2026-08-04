#!/bin/bash
set -euo pipefail
# OneWeblog 更新脚本 — 安装依赖 + 构建 + 重启 Node

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

npm install
npx astro build

# pm2 可能不在 root PATH 中，用 npx 找到它
if npx pm2 list 2>/dev/null | grep -q oneweblog; then
    npx pm2 restart oneweblog
else
    npx pm2 start npm --name oneweblog -- run start
    npx pm2 save
fi

echo "更新完成: https://oneweblog.cn"
echo "新增内容即刻生效，无需重启。"
