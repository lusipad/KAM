#!/bin/bash

# AI工作助手 - 启动脚本
set -e

echo "=================================="
echo "  AI工作助手 - 启动脚本"
echo "=================================="
echo ""

# 检查Docker是否安装
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

# 加载.env文件
if [ -f ".env" ]; then
    set -a
    source ./.env
    set +a
fi

# 检查环境变量
if [ -z "$OPENAI_API_KEY" ]; then
    echo "警告: OPENAI_API_KEY环境变量未设置"
    echo "请在 .env 中设置您的OpenAI API密钥，或先执行:"
    echo "  export OPENAI_API_KEY=your-api-key"
    echo ""
    read -p "是否继续启动? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "正在启动AI工作助手..."
echo ""

# 启动服务
"${COMPOSE_CMD[@]}" up -d --build

# 等待服务启动
echo ""
echo "等待服务启动..."
sleep 5

# 检查服务状态
echo ""
echo "服务状态:"
"${COMPOSE_CMD[@]}" ps

echo ""
echo "=================================="
echo "  AI工作助手已启动!"
echo "=================================="
echo ""
echo "访问地址:"
echo "  应用界面: http://localhost:8000"
echo "  API文档:  http://localhost:8000/docs"
echo ""
echo "数据库:"
echo "  PostgreSQL: localhost:5432"
echo "  Redis:      localhost:6379"
echo ""
echo "查看日志:"
echo "  ${COMPOSE_CMD[*]} logs -f"
echo ""
echo "停止服务:"
echo "  ${COMPOSE_CMD[*]} down"
echo ""
