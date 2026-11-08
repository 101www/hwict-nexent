#!/bin/bash
# ============================================================
# Nexent 启动脚本
#   用途：虚拟机重启后，一键把 Nexent 全栈拉起来
#   用法：bash start-nexent.sh
# ============================================================
set -e

NEXENT_DIR="/data/nexent"
WEB_URL="http://192.168.100.150:3000"

cd "$NEXENT_DIR"

echo "▶ 读取配置..."
set -a
source deploy/env/.env
[ -f deploy/env/image-source.mainland.env ] && source deploy/env/image-source.mainland.env
[ -f deploy/docker/.env.generated ] && source deploy/docker/.env.generated
set +a

echo "▶ 启动容器（已在运行的会跳过，不会重建）..."
docker compose --env-file deploy/env/.env -p nexent \
  -f deploy/docker/compose/docker-compose.yml up -d

echo ""
echo "▶ 等待服务就绪（60 秒）..."
sleep 60

echo ""
echo "════════ 容器状态 ════════"
docker ps --format 'table {{.Names}}\t{{.Status}}'

echo ""
echo "════════ 异常容器（应该为空）════════"
docker ps -a --filter 'status=exited' --filter 'status=restarting' \
  --format '{{.Names}}  {{.Status}}' || true

echo ""
echo "════════ 内存 ════════"
free -h

echo ""
echo "════════════════════════════════════"
echo "  访问地址：$WEB_URL"
echo "  账号：3122274020@qq.com"
echo "  提示：浏览器记得 Ctrl+Shift+R 强制刷新"
echo "════════════════════════════════════"
