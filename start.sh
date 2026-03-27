#!/bin/bash

set -e
APP_PORT=${APP_PORT:-8000}

echo "=================================="
echo "  KAM V3 - Docker 启动脚本"
echo "=================================="
echo ""

if ! command -v docker &> /dev/null; then
    echo "错误: Docker未安装，请先安装Docker"
    exit 1
fi

if ! docker info &> /dev/null; then
    echo "错误: Docker守护进程未运行，请先启动Docker Desktop"
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

echo "正在启动 KAM V3..."
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
echo "  KAM V3 已启动"
echo "=================================="
echo ""
echo "访问地址:"
echo "  应用界面: http://localhost:${APP_PORT}"
echo "  API文档:  http://localhost:${APP_PORT}/docs"
echo ""
echo "查看日志:"
echo "  ${COMPOSE_CMD[*]} logs -f"
echo ""
echo "停止服务:"
echo "  ${COMPOSE_CMD[*]} down"
echo ""
