# AI工作助手后端 Dockerfile（内置前端静态构建）
FROM node:20-alpine AS frontend-build

WORKDIR /frontend
COPY app/package*.json ./
RUN npm ci
COPY app/ ./
ARG VITE_API_URL=/api
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM python:3.11-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 复制后端代码
COPY backend/app/ ./app/

# 复制前端构建产物，供 FastAPI 直接服务
COPY --from=frontend-build /frontend/dist/ ./dist/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
