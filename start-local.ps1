param(
    [string]$BindHost = "0.0.0.0",
    [int]$Port = 8000,
    [string]$PythonBin = "",
    [switch]$SkipBuild
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

    throw "未找到可用的 Python 解释器。"
}

$Python = Resolve-Python -ExplicitPath $PythonBin

Write-Host "==================================" -ForegroundColor Cyan
Write-Host "  KAM V3 - 本地启动脚本" -ForegroundColor Cyan
Write-Host "==================================" -ForegroundColor Cyan
Write-Host ""

if (-not $SkipBuild) {
    Push-Location (Join-Path $RootDir "app")
    try {
        npm run build
    }
    finally {
        Pop-Location
    }
}

Push-Location (Join-Path $RootDir "backend")
try {
    & $Python -m uvicorn main:app --host $BindHost --port $Port
}
finally {
    Pop-Location
}
