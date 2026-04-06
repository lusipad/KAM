param(
    [string]$PythonBin = "",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$OperatorArgs
)

$ErrorActionPreference = "Stop"
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ScriptPath = Join-Path $RootDir "backend\\scripts\\operator_cli.py"

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

if (-not (Test-Path $ScriptPath)) {
    throw "未找到 operator CLI 脚本：$ScriptPath"
}

$Python = Resolve-Python -ExplicitPath $PythonBin
& $Python $ScriptPath @OperatorArgs
exit $LASTEXITCODE
