# KAM V3 Dockerfile（内置前端静态构建）
FROM node:20-alpine AS frontend-build

WORKDIR /workspace/app
COPY app/package*.json ./
RUN npm ci
COPY app/ ./
ARG VITE_API_URL=/api
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM python:3.11-slim

WORKDIR /workspace

RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r ./backend/requirements.txt

COPY backend/ ./backend/

COPY --from=frontend-build /workspace/app/dist/ ./app/dist/

EXPOSE 8000

WORKDIR /workspace/backend

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
