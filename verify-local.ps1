param(
    [switch]$SkipSmoke
)

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $RootDir ".venv\\Scripts\\python.exe"

if (-not (Test-Path $Python)) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        throw "未找到可用的 Python 解释器。"
    }
    $Python = $pythonCommand.Source
}

Write-Host "==================================" -ForegroundColor Cyan
Write-Host "  KAM V3 - 本地验证脚本" -ForegroundColor Cyan
Write-Host "==================================" -ForegroundColor Cyan
Write-Host ""

Push-Location $RootDir
try {
    & $Python -m unittest backend.tests.test_v3_api -v

    Push-Location (Join-Path $RootDir "app")
    try {
        npm run build
        npm run lint
        if (-not $SkipSmoke) {
            npm run test:smoke:local
        }
    }
    finally {
        Pop-Location
    }
}
finally {
    Pop-Location
}
