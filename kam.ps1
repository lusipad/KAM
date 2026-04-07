param(
    [ValidateSet("menu", "ui", "operator", "demo", "status", "watch", "verify")]
    [string]$Command = "menu",
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [int]$Port = 8000,
    [string]$PythonBin = ""
)

$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$StartScript = Join-Path $RootDir "start-local.ps1"
$OperatorScript = Join-Path $RootDir "kam-operator.ps1"
$SeedScript = Join-Path $RootDir "seed-harness.ps1"
$VerifyScript = Join-Path $RootDir "verify-local.ps1"
$FrontendIndex = Join-Path $RootDir "app\\dist\\index.html"
$ApiBaseUrl = "$($BaseUrl.TrimEnd('/'))/api"

function Resolve-Pwsh {
    foreach ($commandName in @("pwsh", "powershell")) {
        $command = Get-Command $commandName -ErrorAction SilentlyContinue
        if ($command) {
            return $command.Source
        }
    }

    throw "未找到可用的 PowerShell。"
}

function Test-BackendHealth {
    try {
        $response = Invoke-RestMethod -Method Get -Uri "$($BaseUrl.TrimEnd('/'))/health" -TimeoutSec 2
        return $response.status -eq "ok"
    }
    catch {
        return $false
    }
}

function Wait-BackendHealthy {
    param(
        [int]$TimeoutSeconds = 60
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-BackendHealth) {
            return $true
        }
        Start-Sleep -Seconds 1
    }

    return $false
}

function Start-BackendWindow {
    if (Test-BackendHealth) {
        return
    }

    $pwsh = Resolve-Pwsh
    $arguments = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $StartScript, "-Port", "$Port")
    if ($PythonBin) {
        $arguments += @("-PythonBin", $PythonBin)
    }
    if (Test-Path $FrontendIndex) {
        $arguments += "-SkipBuild"
    }

    Start-Process -FilePath $pwsh -ArgumentList $arguments -WorkingDirectory $RootDir | Out-Null
    if (-not (Wait-BackendHealthy)) {
        throw "KAM 服务启动超时。请检查新打开的服务窗口日志。"
    }
}

function Ensure-Backend {
    if (-not (Test-BackendHealth)) {
        Write-Host "KAM 服务未运行，正在自动拉起..." -ForegroundColor DarkGray
        Start-BackendWindow
    }
}

function Open-Workbench {
    Ensure-Backend
    Start-Process "$($BaseUrl.TrimEnd('/'))/" | Out-Null
    Write-Host "已打开 KAM 工作台：$($BaseUrl.TrimEnd('/'))/" -ForegroundColor Green
}

function Open-OperatorMenu {
    Ensure-Backend
    & $OperatorScript -OperatorArgs @("menu", "--kam-url", $ApiBaseUrl)
}

function Seed-DemoHarness {
    Ensure-Backend
    & $SeedScript -BaseUrl $BaseUrl -OpenBrowser
}

function Show-Status {
    Ensure-Backend
    & $OperatorScript -OperatorArgs @("status", "--kam-url", $ApiBaseUrl)
}

function Watch-Status {
    Ensure-Backend
    & $OperatorScript -OperatorArgs @("watch", "--kam-url", $ApiBaseUrl, "--interval-seconds", "5")
}

function Run-Verify {
    & $VerifyScript
}

function Show-Menu {
    while ($true) {
        $backendState = if (Test-BackendHealth) { "在线" } else { "离线" }
        Write-Host ""
        Write-Host "==================================" -ForegroundColor Cyan
        Write-Host "  KAM Launcher" -ForegroundColor Cyan
        Write-Host "==================================" -ForegroundColor Cyan
        Write-Host "服务状态: $backendState" -ForegroundColor Gray
        Write-Host "1. 打开 KAM 工作台"
        Write-Host "2. 进入 operator 菜单"
        Write-Host "3. 播种 demo 数据并打开浏览器"
        Write-Host "4. 查看当前状态"
        Write-Host "5. 持续 watch 状态"
        Write-Host "6. 跑本地验证"
        Write-Host "Q. 退出"
        $choice = (Read-Host "请选择入口").Trim().ToLowerInvariant()

        switch ($choice) {
            "1" { Open-Workbench }
            "2" { Open-OperatorMenu }
            "3" { Seed-DemoHarness }
            "4" { Show-Status }
            "5" { Watch-Status }
            "6" { Run-Verify }
            "q" { return }
            "quit" { return }
            "exit" { return }
            default {
                Write-Host "无效输入，请重新选择。" -ForegroundColor Yellow
            }
        }
    }
}

switch ($Command) {
    "menu" { Show-Menu }
    "ui" { Open-Workbench }
    "operator" { Open-OperatorMenu }
    "demo" { Seed-DemoHarness }
    "status" { Show-Status }
    "watch" { Watch-Status }
    "verify" { Run-Verify }
}
