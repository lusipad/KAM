param(
    [ValidateSet("menu", "register", "list", "run-once", "remove", "legacy-run")]
    [string]$Action = "",
    [string]$Repo = "",
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string]$RepoPath = "",
    [string]$PythonBin = "",
    [string]$OutputDir = "",
    [switch]$DryRun,
    [switch]$NoRunNow,
    [switch]$Json
)

$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$LegacyScriptPath = Join-Path $RootDir "backend\\scripts\\github_issue_monitor.py"

function Get-ApiBaseUrl {
    param([string]$Url)

    $trimmed = $Url.Trim().TrimEnd("/")
    if (-not $trimmed) {
        throw "必须提供 BaseUrl。"
    }
    if ($trimmed.ToLowerInvariant().EndsWith("/api")) {
        return $trimmed
    }
    return "$trimmed/api"
}

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

function Resolve-Repo {
    param([string]$Value)

    $normalized = $Value.Trim()
    if (-not $normalized) {
        throw "必须提供 GitHub repo。"
    }
    $parts = $normalized.Split("/", 2)
    if ($parts.Count -ne 2 -or -not $parts[0].Trim() -or -not $parts[1].Trim()) {
        throw "GitHub repo 必须是 owner/name 形式。"
    }
    return "$($parts[0].Trim())/$($parts[1].Trim())"
}

function Split-Repo {
    param([string]$Value)

    $normalized = Resolve-Repo $Value
    return $normalized.Split("/", 2)
}

function Invoke-KamApi {
    param(
        [string]$Method,
        [string]$Path,
        [object]$Body = $null
    )

    $uri = "$(Get-ApiBaseUrl $BaseUrl)$Path"
    if ($null -eq $Body) {
        return Invoke-RestMethod -Method $Method -Uri $uri
    }

    $payload = $Body | ConvertTo-Json -Depth 8
    return Invoke-RestMethod -Method $Method -Uri $uri -ContentType "application/json; charset=utf-8" -Body $payload
}

function Write-JsonResult {
    param([object]$Value)
    $Value | ConvertTo-Json -Depth 10
}

function Show-Monitor {
    param([object]$Monitor)

    $runningLabel = if ($Monitor.running) { "运行中" } else { "待机" }
    Write-Host ""
    Write-Host "仓库: $($Monitor.repo)" -ForegroundColor Cyan
    if ($Monitor.repoPath) {
        Write-Host "repoPath: $($Monitor.repoPath)"
    }
    Write-Host "状态: $($Monitor.status) / $runningLabel"
    if ($Monitor.lastCheckedAt) {
        Write-Host "上次检查: $($Monitor.lastCheckedAt)"
    }
    if ($null -ne $Monitor.issueCount) {
        Write-Host "Issue 总数: $($Monitor.issueCount)"
    }
    if ($null -ne $Monitor.changedIssueCount) {
        Write-Host "本轮变化: $($Monitor.changedIssueCount)"
    }
    if ($Monitor.taskIds -and $Monitor.taskIds.Count -gt 0) {
        Write-Host "最近任务: $($Monitor.taskIds -join ', ')"
    }
    Write-Host "摘要: $($Monitor.summary)" -ForegroundColor DarkGray
}

function Show-MonitorList {
    param([object[]]$Monitors)

    if (-not $Monitors -or $Monitors.Count -eq 0) {
        Write-Host "当前还没有注册任何 GitHub Issue 自动监控。" -ForegroundColor Yellow
        return
    }

    $rows = foreach ($item in $Monitors) {
        [pscustomobject]@{
            Repo          = $item.repo
            Status        = $item.status
            Running       = [bool]$item.running
            LastCheckedAt = $item.lastCheckedAt
            RepoPath      = $item.repoPath
            Summary       = $item.summary
        }
    }
    $rows | Format-Table -AutoSize | Out-Host
}

function Show-RunSummary {
    param([object]$Summary)

    Write-Host ""
    Write-Host "仓库: $($Summary.repo)" -ForegroundColor Cyan
    Write-Host "状态: $($Summary.status)"
    if ($Summary.checkedAt) {
        Write-Host "检查时间: $($Summary.checkedAt)"
    }
    if ($Summary.workspace) {
        Write-Host "工作区: $($Summary.workspace)"
    }
    if ($null -ne $Summary.issueCount) {
        Write-Host "Issue 总数: $($Summary.issueCount)"
    }
    if ($null -ne $Summary.changedIssueCount) {
        Write-Host "本轮变化: $($Summary.changedIssueCount)"
    }
    if ($Summary.issueNumbers -and $Summary.issueNumbers.Count -gt 0) {
        Write-Host "变化 Issue: $($Summary.issueNumbers -join ', ')"
    }
    if ($Summary.taskIds -and $Summary.taskIds.Count -gt 0) {
        Write-Host "写入任务: $($Summary.taskIds -join ', ')"
    }
    Write-Host "摘要: $($Summary.message)" -ForegroundColor DarkGray
}

function Invoke-LegacyRun {
    $repo = $Repo
    if (-not $repo.Trim()) {
        $repo = (Read-Host "GitHub repo (owner/name)").Trim()
    }
    $repo = Resolve-Repo $repo

    if (-not (Test-Path $LegacyScriptPath)) {
        throw "未找到 legacy issue monitor 脚本：$LegacyScriptPath"
    }

    $python = Resolve-Python -ExplicitPath $PythonBin
    $scriptArgs = @($LegacyScriptPath, "--repo", $repo, "--kam-url", (Get-ApiBaseUrl $BaseUrl))
    if ($RepoPath) {
        $scriptArgs += @("--repo-path", $RepoPath)
    }
    if ($OutputDir) {
        $scriptArgs += @("--output-dir", $OutputDir)
    }
    if ($DryRun) {
        $scriptArgs += "--dry-run"
    }

    & $python @scriptArgs
    if ($LASTEXITCODE -ne 0) {
        throw "legacy GitHub Issue monitor 执行失败，退出码 $LASTEXITCODE。"
    }
}

function Register-IssueMonitor {
    $repo = $Repo
    if (-not $repo.Trim()) {
        $repo = (Read-Host "GitHub repo (owner/name)").Trim()
    }
    $repo = Resolve-Repo $repo

    $repoPath = $RepoPath
    if (-not $repoPath.Trim()) {
        $repoPath = (Read-Host "本地 repoPath（可留空）").Trim()
    }

    $result = Invoke-KamApi -Method Post -Path "/issue-monitors" -Body @{
        repo     = $repo
        repoPath = if ($repoPath) { $repoPath } else { $null }
        runNow   = (-not $NoRunNow)
    }

    if ($Json) {
        Write-JsonResult $result
        return
    }

    Write-Host "已注册 GitHub Issue 自动监控；KAM 后续重启会自动恢复。" -ForegroundColor Green
    Show-Monitor $result
}

function List-IssueMonitors {
    $result = Invoke-KamApi -Method Get -Path "/issue-monitors"
    if ($Json) {
        Write-JsonResult $result
        return
    }
    Show-MonitorList $result.monitors
}

function Run-IssueMonitorOnce {
    $repo = $Repo
    if (-not $repo.Trim()) {
        $repo = (Read-Host "GitHub repo (owner/name)").Trim()
    }
    $parts = Split-Repo $repo
    $owner = [uri]::EscapeDataString($parts[0])
    $name = [uri]::EscapeDataString($parts[1])
    $result = Invoke-KamApi -Method Post -Path "/issue-monitors/$owner/$name/run-once"

    if ($Json) {
        Write-JsonResult $result
        return
    }
    Show-RunSummary $result
}

function Remove-IssueMonitor {
    $repo = $Repo
    if (-not $repo.Trim()) {
        $repo = (Read-Host "GitHub repo (owner/name)").Trim()
    }
    $parts = Split-Repo $repo
    $owner = [uri]::EscapeDataString($parts[0])
    $name = [uri]::EscapeDataString($parts[1])
    $null = Invoke-KamApi -Method Delete -Path "/issue-monitors/$owner/$name"

    if ($Json) {
        Write-JsonResult @{ ok = $true; repo = "$($parts[0])/$($parts[1])" }
        return
    }
    Write-Host "已移除 GitHub Issue 自动监控：$($parts[0])/$($parts[1])" -ForegroundColor Green
}

function Show-Menu {
    while ($true) {
        Write-Host ""
        Write-Host "==================================" -ForegroundColor Cyan
        Write-Host "  GitHub Issue 自动入池" -ForegroundColor Cyan
        Write-Host "==================================" -ForegroundColor Cyan
        Write-Host "1. 查看已注册监控"
        Write-Host "2. 注册/更新仓库监控"
        Write-Host "3. 手动立即扫一轮"
        Write-Host "4. 删除仓库监控"
        Write-Host "5. legacy 单轮运行（兼容 dry-run）"
        Write-Host "Q. 返回"
        $choice = (Read-Host "请选择操作").Trim().ToLowerInvariant()

        switch ($choice) {
            "1" { List-IssueMonitors }
            "2" { Register-IssueMonitor }
            "3" { Run-IssueMonitorOnce }
            "4" { Remove-IssueMonitor }
            "5" { Invoke-LegacyRun }
            "q" { return }
            "quit" { return }
            "exit" { return }
            default {
                Write-Host "无效输入，请重新选择。" -ForegroundColor Yellow
            }
        }
    }
}

if ($DryRun -or $OutputDir) {
    $Action = "legacy-run"
}
elseif (-not $Action) {
    if ($Repo.Trim()) {
        $Action = "register"
    }
    else {
        $Action = "menu"
    }
}

switch ($Action) {
    "menu" { Show-Menu }
    "register" { Register-IssueMonitor }
    "list" { List-IssueMonitors }
    "run-once" { Run-IssueMonitorOnce }
    "remove" { Remove-IssueMonitor }
    "legacy-run" { Invoke-LegacyRun }
}
