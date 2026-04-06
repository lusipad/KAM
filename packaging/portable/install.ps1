param(
    [string]$PythonBin = ""
)

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir = Join-Path $RootDir ".venv"
$EnvExample = Join-Path $RootDir ".env.example"
$EnvFile = Join-Path $RootDir ".env"

function Resolve-PythonCommand {
    param([string]$ExplicitPath)

    if ($ExplicitPath) {
        if (-not (Test-Path $ExplicitPath)) {
            throw "指定的 Python 不存在：$ExplicitPath"
        }

        return @{
            FilePath = $ExplicitPath
            PrefixArgs = @()
        }
    }

    foreach ($commandName in @("python", "python3")) {
        $command = Get-Command $commandName -ErrorAction SilentlyContinue
        if ($command) {
            return @{
                FilePath = $command.Source
                PrefixArgs = @()
            }
        }
    }

    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        return @{
            FilePath = $pyLauncher.Source
            PrefixArgs = @("-3")
        }
    }

    throw "未找到可用的 Python 解释器。请先安装 Python 3。"
}

function Invoke-CheckedCommand {
    param(
        [string]$Label,
        [string]$FilePath,
        [string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Label 失败，退出码 $LASTEXITCODE。"
    }
}

function Resolve-VenvPython {
    $candidates = @(
        (Join-Path $VenvDir "Scripts\\python.exe"),
        (Join-Path $VenvDir "bin\\python")
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    throw "虚拟环境创建失败，未找到解释器。"
}

$PythonCommand = Resolve-PythonCommand -ExplicitPath $PythonBin

if (-not (Test-Path $VenvDir)) {
    Invoke-CheckedCommand "创建虚拟环境" $PythonCommand.FilePath ($PythonCommand.PrefixArgs + @("-m", "venv", $VenvDir))
}

$VenvPython = Resolve-VenvPython
Invoke-CheckedCommand "升级 pip" $VenvPython @("-m", "pip", "install", "--upgrade", "pip")
Invoke-CheckedCommand "安装后端依赖" $VenvPython @("-m", "pip", "install", "-r", (Join-Path $RootDir "backend\\requirements.txt"))

if ((Test-Path $EnvExample) -and -not (Test-Path $EnvFile)) {
    Copy-Item -Path $EnvExample -Destination $EnvFile -Force
}

Write-Host "安装完成。" -ForegroundColor Green
Write-Host "启动服务: pwsh -File .\\run.ps1" -ForegroundColor DarkGray
Write-Host "值守入口: pwsh -File .\\kam-operator.ps1 menu" -ForegroundColor DarkGray
