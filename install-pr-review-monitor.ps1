param(
    [string]$Repo = "lusipad/KAM",
    [int]$PullRequest = 4518,
    [string]$PythonBin = "",
    [string]$CodexBin = "",
    [string]$KamApiUrl = "http://127.0.0.1:8000/api",
    [string]$TaskName = "",
    [switch]$DirectCodex,
    [switch]$SkipValidate,
    [switch]$RunNow
)

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path

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

    throw "No usable Python interpreter was found."
}

function Resolve-Codex {
    param([string]$ExplicitPath)

    $candidates = @()
    if ($ExplicitPath) {
        $candidates += $ExplicitPath
    }
    if ($env:CODEX_PATH) {
        $candidates += $env:CODEX_PATH
    }

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            return (Resolve-Path $candidate).Path
        }
    }

    foreach ($commandName in @("codex.cmd", "codex.exe", "codex.bat", "codex")) {
        $command = Get-Command $commandName -ErrorAction SilentlyContinue
        if ($command) {
            return $command.Source
        }
    }

    throw "No usable Codex executable was found."
}

$Python = Resolve-Python -ExplicitPath $PythonBin
$ScriptPath = Join-Path $RootDir "backend\\scripts\\pr_review_monitor.py"
if (-not (Test-Path $ScriptPath)) {
    throw "Monitor script not found: $ScriptPath"
}

$UseHarnessQueue = (-not $DirectCodex) -and [string]::IsNullOrWhiteSpace($KamApiUrl) -eq $false
$Codex = $null
if (-not $UseHarnessQueue) {
    $Codex = Resolve-Codex -ExplicitPath $CodexBin
}

if (-not $SkipValidate) {
    $ValidationDir = Join-Path ([System.IO.Path]::GetTempPath()) ("kam-pr-review-validate-" + [guid]::NewGuid().ToString("N"))
    try {
        $ValidationOutput = & $Python $ScriptPath --repo $Repo --pr $PullRequest --dry-run --output-dir $ValidationDir 2>&1
        $ValidationExitCode = $LASTEXITCODE

        $ValidationJson = ($ValidationOutput | Out-String).Trim()
        if (-not $ValidationJson) {
            throw "Preflight returned no output."
        }

        try {
            $Validation = $ValidationJson | ConvertFrom-Json
        } catch {
            throw "Preflight output was not valid JSON: $ValidationJson"
        }

        if ($Validation.status -in @("source-error", "failed")) {
            $ValidationMessage = if ($Validation.message) { $Validation.message } else { "unknown error" }
            throw "Preflight failed: $ValidationMessage"
        }
        if ($ValidationExitCode -ne 0) {
            throw "Preflight command failed: $ValidationJson"
        }
    } finally {
        if (Test-Path $ValidationDir) {
            Remove-Item -LiteralPath $ValidationDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

$EffectiveTaskName = if ($TaskName) { $TaskName } else { "KAM-PRReview-$($Repo.Replace('/','-'))-$PullRequest" }
$Argument = '"' + $ScriptPath + '" --repo "' + $Repo + '" --pr ' + $PullRequest
if ($UseHarnessQueue) {
    $Argument += ' --kam-url "' + $KamApiUrl + '"'
} else {
    $Argument += ' --codex-path "' + $Codex + '"'
}
$Action = New-ScheduledTaskAction -Execute $Python -Argument $Argument
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration (New-TimeSpan -Days 3650)
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 12)

Register-ScheduledTask `
    -TaskName $EffectiveTaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "Monitor $Repo PR #$PullRequest review comments every 30 minutes and feed them into KAM." `
    -Force | Out-Null

if ($RunNow) {
    Start-ScheduledTask -TaskName $EffectiveTaskName
}

Write-Host "Installed PR review monitor task: $EffectiveTaskName" -ForegroundColor Green
Write-Host ("Mode: " + ($(if ($UseHarnessQueue) { "KAM harness queue" } else { "Direct Codex fallback" }))) -ForegroundColor DarkGray
Write-Host "Command: $Python $Argument" -ForegroundColor DarkGray
