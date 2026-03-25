#!/bin/bash

set -e

echo "=================================="
echo "  KAM Lite - 启动脚本"
echo "=================================="
echo ""

if ! command -v docker &> /dev/null; then
    echo "错误: Docker未安装，请先安装Docker"
    exit 1
fi

if docker compose version &> /dev/null; then
    COMPOSE_CMD=(docker compose)
elif command -v docker-compose &> /dev/null; then
    COMPOSE_CMD=(docker-compose)
else
    echo "错误: Docker Compose未安装，请先安装Docker Compose"
    exit 1
fi

echo "正在启动 KAM Lite..."
echo ""

"${COMPOSE_CMD[@]}" up -d --build

echo ""
echo "等待服务启动..."
sleep 5

echo ""
echo "服务状态:"
"${COMPOSE_CMD[@]}" ps

echo ""
echo "=================================="
echo "  KAM Lite 已启动"
echo "=================================="
echo ""
echo "访问地址:"
echo "  应用界面: http://localhost:8000"
echo "  API文档:  http://localhost:8000/docs"
echo ""
echo "数据库:"
echo "  PostgreSQL: localhost:5432"
echo ""
echo "查看日志:"
echo "  ${COMPOSE_CMD[*]} logs -f"
echo ""
echo "停止服务:"
echo "  ${COMPOSE_CMD[*]} down"
echo ""
