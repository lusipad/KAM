param(
    [string]$BindHost = "0.0.0.0",
    [int]$Port = 8000,
    [string]$PythonBin = "",
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Npm = $null

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

function Resolve-Npm {
    $npmCommand = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $npmCommand) {
        throw "未找到可用的 npm 命令。"
    }

    $source = $npmCommand.Source
    if ($IsWindows -and $source.EndsWith(".ps1")) {
        $npmCmd = Join-Path (Split-Path $source -Parent) "npm.cmd"
        if (Test-Path $npmCmd) {
            return $npmCmd
        }
    }

    return $source
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

$Python = Resolve-Python -ExplicitPath $PythonBin
$Npm = Resolve-Npm

Write-Host "==================================" -ForegroundColor Cyan
Write-Host "  KAM V3 - 本地启动脚本" -ForegroundColor Cyan
Write-Host "==================================" -ForegroundColor Cyan
Write-Host ""

if (-not $SkipBuild) {
    Push-Location (Join-Path $RootDir "app")
    try {
        Invoke-CheckedProcess "前端构建" $Npm @("run", "build") (Get-Location).Path
    }
    finally {
        Pop-Location
    }
}

Write-Host "启动地址: http://127.0.0.1:$Port" -ForegroundColor Green
Write-Host "如需演示数据，可另开一个终端执行: pwsh -File .\\seed-demo.ps1" -ForegroundColor DarkGray
Write-Host ""

Push-Location (Join-Path $RootDir "backend")
try {
    & $Python -m uvicorn main:app --host $BindHost --port $Port
}
finally {
    Pop-Location
}
