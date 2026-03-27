param(
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

Write-Host "==================================" -ForegroundColor Cyan
Write-Host "  KAM V3 - Docker 启动脚本" -ForegroundColor Cyan
Write-Host "==================================" -ForegroundColor Cyan
Write-Host ""

$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) {
    throw "Docker 未安装，请先安装 Docker。"
}

& docker compose version *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose 不可用。"
}

& docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker 守护进程未运行，请先启动 Docker Desktop。"
}

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Push-Location $RootDir
try {
    $env:APP_PORT = $Port.ToString()

    Write-Host "正在启动 KAM V3..." -ForegroundColor Yellow
    Write-Host ""

    & docker compose up -d --build
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose up 失败。"
    }

    Write-Host ""
    Write-Host "等待服务启动..." -ForegroundColor Yellow
    Start-Sleep -Seconds 5

    Write-Host ""
    Write-Host "服务状态:" -ForegroundColor Yellow
    & docker compose ps
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose ps 失败。"
    }

    Write-Host ""
    Write-Host "==================================" -ForegroundColor Green
    Write-Host "  KAM V3 已启动" -ForegroundColor Green
    Write-Host "==================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "访问地址:"
    Write-Host "  应用界面: http://localhost:$Port"
    Write-Host "  API文档:  http://localhost:$Port/docs"
    Write-Host ""
    Write-Host "查看日志:"
    Write-Host "  docker compose logs -f"
    Write-Host ""
    Write-Host "停止服务:"
    Write-Host "  docker compose down"
    Write-Host ""
}
finally {
    Pop-Location
}
