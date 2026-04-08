param(
    [string]$Repo = "",
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string]$RepoPath = "",
    [string]$PythonBin = "",
    [string]$OutputDir = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ScriptPath = Join-Path $RootDir "backend\\scripts\\github_issue_monitor.py"
$ApiBaseUrl = "$($BaseUrl.TrimEnd('/'))/api"

function Resolve-Python {
    param([string]$ExplicitPath)

    $candidates = @()
    if ($ExplicitPath) {
        $candidates += $ExplicitPath
    }
    if ($env:PYTHON_BIN) {
        $candidates += $env:PYTHON_BIN
    }

    $candidates += @(
        (Join-Path $RootDir ".venv\\Scripts\\python.exe"),
        (Join-Path $RootDir ".venv\\bin\\python")
    )

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            return $candidate
        }
    }

    foreach ($commandName in @("python", "python3")) {
        $command = Get-Command $commandName -ErrorAction SilentlyContinue
        if ($command) {
            return $command.Source
        }
    }

    throw "未找到可用的 Python 解释器。"
}

if (-not $Repo.Trim()) {
    $Repo = (Read-Host "GitHub repo (owner/name)").Trim()
}

if (-not $Repo) {
    throw "必须提供 GitHub repo。"
}

$Python = Resolve-Python -ExplicitPath $PythonBin
$ScriptArgs = @($ScriptPath, "--repo", $Repo, "--kam-url", $ApiBaseUrl)

if ($RepoPath) {
    $ScriptArgs += @("--repo-path", $RepoPath)
}
if ($OutputDir) {
    $ScriptArgs += @("--output-dir", $OutputDir)
}
if ($DryRun) {
    $ScriptArgs += "--dry-run"
}

& $Python @ScriptArgs
if ($LASTEXITCODE -ne 0) {
    throw "GitHub Issue monitor 执行失败，退出码 $LASTEXITCODE。"
}
