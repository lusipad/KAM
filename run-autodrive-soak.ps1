param(
    [ValidateRange(1, 1440)]
    [int]$Minutes = 480,
    [ValidateRange(5, 3600)]
    [int]$TaskIntervalSeconds = 30,
    [ValidateRange(1, 300)]
    [int]$PollSeconds = 2,
    [ValidateRange(1, 300)]
    [int]$SettleSeconds = 5,
    [ValidateRange(1024, 65535)]
    [int]$Port = 8011,
    [string]$ArtifactRoot,
    [string]$ArtifactDir,
    [switch]$Detached
)

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppDir = Join-Path $RootDir "app"
$SoakScript = Join-Path $AppDir "scripts\\soak-autodrive.mjs"
$OutputDir = Join-Path $RootDir "output"

if (-not $ArtifactRoot) {
    $ArtifactRoot = Join-Path $OutputDir "soak-runs"
}

if (-not (Test-Path $SoakScript)) {
    throw "未找到 soak 脚本：$SoakScript"
}

try {
    $Node = (Get-Command node -ErrorAction Stop).Source
}
catch {
    throw "未找到可用的 node 命令。"
}

try {
    $Pwsh = (Get-Command pwsh -ErrorAction Stop).Source
}
catch {
    $Pwsh = (Get-Command powershell -ErrorAction Stop).Source
}

function ConvertTo-StableJson {
    param(
        [Parameter(Mandatory = $true)]
        [object]$Value
    )

    return ($Value | ConvertTo-Json -Depth 8)
}

function Get-GitRevision {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RootDir,
        [switch]$Short
    )

    $arguments = @("rev-parse")
    if ($Short) {
        $arguments += "--short"
    }
    $arguments += "HEAD"

    try {
        $value = (& git -C $RootDir @arguments 2>$null).Trim()
        if ($value) {
            return $value
        }
    }
    catch {
    }

    return "unknown"
}

function Get-ArtifactDirectory {
    param(
        [string]$ArtifactRoot,
        [string]$ArtifactDir,
        [string]$RootDir
    )

    if ($ArtifactDir) {
        $resolved = [System.IO.Path]::GetFullPath($ArtifactDir)
        New-Item -ItemType Directory -Force -Path $resolved | Out-Null
        return $resolved
    }

    New-Item -ItemType Directory -Force -Path $ArtifactRoot | Out-Null
    $stamp = Get-Date -AsUTC -Format "yyyyMMddTHHmmssZ"
    $commit = Get-GitRevision -RootDir $RootDir -Short
    $dir = Join-Path $ArtifactRoot "$stamp-$commit"
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    return [System.IO.Path]::GetFullPath($dir)
}

function Write-JsonFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [object]$Value
    )

    Set-Content -Path $Path -Value (ConvertTo-StableJson -Value $Value) -Encoding utf8
}

function Copy-IfExists {
    param(
        [string]$Source,
        [string]$Destination
    )

    if (Test-Path $Source) {
        Copy-Item -Force -Path $Source -Destination $Destination
    }
}

$artifactDirPath = Get-ArtifactDirectory -ArtifactRoot $ArtifactRoot -ArtifactDir $ArtifactDir -RootDir $RootDir
$commitHash = Get-GitRevision -RootDir $RootDir
$machineName = if ($env:COMPUTERNAME) { $env:COMPUTERNAME } else { [System.Net.Dns]::GetHostName() }
$commandSummary = "node scripts/soak-autodrive.mjs"

if ($Detached) {
    $launchFile = Join-Path $artifactDirPath "launch.json"
    $argumentList = @(
        "-NoProfile",
        "-File",
        $PSCommandPath,
        "-Minutes",
        $Minutes,
        "-TaskIntervalSeconds",
        $TaskIntervalSeconds,
        "-PollSeconds",
        $PollSeconds,
        "-SettleSeconds",
        $SettleSeconds,
        "-Port",
        $Port,
        "-ArtifactDir",
        $artifactDirPath
    )
    $process = Start-Process -FilePath $Pwsh -ArgumentList $argumentList -WorkingDirectory $RootDir -WindowStyle Hidden -PassThru
    $launchPayload = [ordered]@{
        launchedAt = (Get-Date).ToString("o")
        artifactDir = $artifactDirPath
        pid = $process.Id
        machine = $machineName
        commit = $commitHash
        minutes = $Minutes
        taskIntervalSeconds = $TaskIntervalSeconds
        pollSeconds = $PollSeconds
        settleSeconds = $SettleSeconds
        port = $Port
        command = "pwsh -NoProfile -File .\\run-autodrive-soak.ps1 ..."
        status = "launched"
    }
    Write-JsonFile -Path $launchFile -Value $launchPayload
    Write-Output (ConvertTo-StableJson -Value $launchPayload)
    exit 0
}

$startedAt = Get-Date
$artifactName = Split-Path -Leaf $artifactDirPath
$logPrefix = "soak-backend-$artifactName"
$metadataFile = Join-Path $artifactDirPath "metadata.json"
$stdoutFile = Join-Path $artifactDirPath "runner-stdout.log"
$stderrFile = Join-Path $artifactDirPath "runner-stderr.log"
$resultFile = Join-Path $artifactDirPath "soak-result.json"
$backendOutFile = Join-Path $OutputDir "$logPrefix.out.log"
$backendErrFile = Join-Path $OutputDir "$logPrefix.err.log"

$metadata = [ordered]@{
    startedAt = $startedAt.ToString("o")
    completedAt = $null
    status = "running"
    machine = $machineName
    commit = $commitHash
    artifactDir = $artifactDirPath
    command = $commandSummary
    minutes = $Minutes
    taskIntervalSeconds = $TaskIntervalSeconds
    pollSeconds = $PollSeconds
    settleSeconds = $SettleSeconds
    port = $Port
    logPrefix = $logPrefix
    resultFile = $resultFile
}
Write-JsonFile -Path $metadataFile -Value $metadata

$previousEnv = @{
    KAM_SOAK_DURATION_MS = $env:KAM_SOAK_DURATION_MS
    KAM_SOAK_TASK_INTERVAL_MS = $env:KAM_SOAK_TASK_INTERVAL_MS
    KAM_SOAK_POLL_MS = $env:KAM_SOAK_POLL_MS
    KAM_SOAK_SETTLE_MS = $env:KAM_SOAK_SETTLE_MS
    KAM_SOAK_PORT = $env:KAM_SOAK_PORT
    KAM_SOAK_LOG_PREFIX = $env:KAM_SOAK_LOG_PREFIX
    KAM_SOAK_RESULT_FILE = $env:KAM_SOAK_RESULT_FILE
}

Remove-Item -Force -ErrorAction SilentlyContinue $stdoutFile, $stderrFile, $resultFile, $backendOutFile, $backendErrFile

try {
    $env:KAM_SOAK_DURATION_MS = [string]($Minutes * 60 * 1000)
    $env:KAM_SOAK_TASK_INTERVAL_MS = [string]($TaskIntervalSeconds * 1000)
    $env:KAM_SOAK_POLL_MS = [string]($PollSeconds * 1000)
    $env:KAM_SOAK_SETTLE_MS = [string]($SettleSeconds * 1000)
    $env:KAM_SOAK_PORT = [string]$Port
    $env:KAM_SOAK_LOG_PREFIX = $logPrefix
    $env:KAM_SOAK_RESULT_FILE = $resultFile

    $process = Start-Process -FilePath $Node -ArgumentList @("scripts/soak-autodrive.mjs") -WorkingDirectory $AppDir -RedirectStandardOutput $stdoutFile -RedirectStandardError $stderrFile -PassThru -Wait
    $exitCode = $process.ExitCode
}
finally {
    foreach ($name in $previousEnv.Keys) {
        if ($null -eq $previousEnv[$name]) {
            Remove-Item "Env:$name" -ErrorAction SilentlyContinue
        }
        else {
            Set-Item "Env:$name" -Value $previousEnv[$name]
        }
    }
}

$completedAt = Get-Date
Copy-IfExists -Source $backendOutFile -Destination (Join-Path $artifactDirPath "backend.out.log")
Copy-IfExists -Source $backendErrFile -Destination (Join-Path $artifactDirPath "backend.err.log")

$resultPayload = $null
if (Test-Path $resultFile) {
    $resultPayload = Get-Content -Raw -Path $resultFile | ConvertFrom-Json
}

$metadata.status = if ($exitCode -eq 0) { "passed" } else { "failed" }
$metadata.completedAt = $completedAt.ToString("o")
$metadata.exitCode = $exitCode
$metadata.durationSeconds = [int][Math]::Round(($completedAt - $startedAt).TotalSeconds)
$metadata.result = $resultPayload
Write-JsonFile -Path $metadataFile -Value $metadata

Write-Output (ConvertTo-StableJson -Value $metadata)

if ($exitCode -ne 0) {
    throw "Autodrive soak 执行失败，退出码 $exitCode。"
}
