param(
    [string]$BindHost = "0.0.0.0",
    [int]$Port = 8000,
    [string]$PythonBin = ""
)

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$StartScript = Join-Path $RootDir "start-local.ps1"

if (-not (Test-Path $StartScript)) {
    throw "未找到启动脚本：$StartScript"
}

& $StartScript -BindHost $BindHost -Port $Port -PythonBin $PythonBin -SkipBuild
exit $LASTEXITCODE
