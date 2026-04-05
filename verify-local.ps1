param(
    [switch]$SkipSmoke,
    [switch]$SkipRealAgentSmoke,
    [switch]$RunRealAgentSmoke,
    [ValidateSet("codex", "claude-code")]
    [string]$RealSmokeAgent = "codex"
)

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $RootDir ".venv\\Scripts\\python.exe"
$Npm = $null
$Pwsh = $null

if (-not (Test-Path $Python)) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        throw "未找到可用的 Python 解释器。"
    }
    $Python = $pythonCommand.Source
}

try {
    $npmCommand = Get-Command npm -ErrorAction Stop
    $Npm = $npmCommand.Source
    if ($IsWindows -and $Npm.EndsWith(".ps1")) {
        $npmCmd = Join-Path (Split-Path $Npm -Parent) "npm.cmd"
        if (Test-Path $npmCmd) {
            $Npm = $npmCmd
        }
    }
}
catch {
    throw "未找到可用的 npm 命令。"
}

try {
    $Pwsh = (Get-Command pwsh -ErrorAction Stop).Source
}
catch {
    $Pwsh = (Get-Command powershell -ErrorAction Stop).Source
}

function Invoke-CheckedProcess {
    param(
        [string]$Label,
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$WorkingDirectory
    )

    $process = Start-Process -FilePath $FilePath -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory -NoNewWindow -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        throw "$Label 失败，退出码 $($process.ExitCode)。"
    }
}

function Assert-RealAgentSmokeReady {
    param(
        [string]$Agent
    )

    $helperPath = Join-Path $RootDir "backend\\scripts\\agent_readiness.py"
    $output = & $Python $helperPath --agent $Agent 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw (($output | Out-String).Trim())
    }
}

Write-Host "==================================" -ForegroundColor Cyan
Write-Host "  KAM Harness - 本地验证脚本" -ForegroundColor Cyan
Write-Host "==================================" -ForegroundColor Cyan
Write-Host ""

$shouldRunRealAgentSmoke = -not $SkipRealAgentSmoke -or $RunRealAgentSmoke

if ($shouldRunRealAgentSmoke) {
    Assert-RealAgentSmokeReady -Agent $RealSmokeAgent
}

Push-Location $RootDir
try {
    Invoke-CheckedProcess "数据库启动迁移测试" $Pwsh @(
        "-NoProfile",
        "-Command",
        "& '$Python' -m unittest backend.tests.test_db_init -v"
    ) $RootDir
    Invoke-CheckedProcess "Harness 后端单测" $Pwsh @(
        "-NoProfile",
        "-Command",
        "& '$Python' -m unittest backend.tests.test_harness_api -v"
    ) $RootDir
    Invoke-CheckedProcess "Task Planner 回归" $Pwsh @(
        "-NoProfile",
        "-Command",
        "& '$Python' -m unittest backend.tests.test_task_planner_api -v"
    ) $RootDir
    Invoke-CheckedProcess "Agent readiness 回归" $Pwsh @(
        "-NoProfile",
        "-Command",
        "& '$Python' -m unittest backend.tests.test_agent_readiness -v"
    ) $RootDir
    Invoke-CheckedProcess "Run Engine Lore 回归" $Pwsh @(
        "-NoProfile",
        "-Command",
        "& '$Python' -m unittest backend.tests.test_run_engine_lore -v"
    ) $RootDir
    Invoke-CheckedProcess "GitHub PR 适配器回归" $Pwsh @(
        "-NoProfile",
        "-Command",
        "& '$Python' -m unittest backend.tests.test_github_adapter -v"
    ) $RootDir
    Invoke-CheckedProcess "PR review monitor 回归" $Pwsh @(
        "-NoProfile",
        "-Command",
        "& '$Python' -m unittest backend.tests.test_pr_review_monitor -v"
    ) $RootDir

    Push-Location (Join-Path $RootDir "app")
    try {
        Invoke-CheckedProcess "前端构建" $Npm @("run", "build") (Get-Location).Path
        Invoke-CheckedProcess "前端 lint" $Npm @("run", "lint") (Get-Location).Path
        if (-not $SkipSmoke) {
            Invoke-CheckedProcess "本地 smoke" $Npm @("run", "test:smoke:local") (Get-Location).Path
        }
        if ($shouldRunRealAgentSmoke) {
            Invoke-CheckedProcess "真实 agent smoke" $Pwsh @(
                "-NoProfile",
                "-Command",
                "`$env:KAM_SMOKE_AGENT='$RealSmokeAgent'; & '$Npm' run test:smoke:agent"
            ) (Get-Location).Path
        }
    }
    finally {
        Pop-Location
    }
}
finally {
    Pop-Location
}
