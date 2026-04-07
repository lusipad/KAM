param(
    [string]$Version = "",
    [string]$OutputDir = "",
    [string]$PythonBin = ""
)

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $PSScriptRoot
$SpecPath = Join-Path $RootDir "packaging\\windows\\kam-release.spec"
$BuildRequirements = Join-Path $RootDir "packaging\\windows\\requirements-build.txt"
$FrontendIndex = Join-Path $RootDir "app\\dist\\index.html"

function Get-DefaultVersion {
    try {
        $shortSha = (git -C $RootDir rev-parse --short HEAD 2>$null).Trim()
        if ($shortSha) {
            return "dev-$shortSha"
        }
    }
    catch {
    }

    return "dev-local"
}

function Ensure-Directory {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Remove-DirectorySafe {
    param([string]$Path, [string]$ExpectedRoot)

    if (-not (Test-Path $Path)) {
        return
    }

    $resolvedPath = [System.IO.Path]::GetFullPath($Path)
    $resolvedRoot = [System.IO.Path]::GetFullPath($ExpectedRoot)
    if (-not $resolvedPath.StartsWith($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "拒绝删除预期目录之外的路径：$resolvedPath"
    }

    Remove-Item -LiteralPath $resolvedPath -Recurse -Force
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
            return @{
                FilePath = $candidate
                PrefixArgs = @()
            }
        }
    }

    foreach ($commandName in @("python", "python3", "py")) {
        $command = Get-Command $commandName -ErrorAction SilentlyContinue
        if ($command) {
            if ($commandName -eq "py") {
                return @{
                    FilePath = $command.Source
                    PrefixArgs = @("-3")
                }
            }
            return @{
                FilePath = $command.Source
                PrefixArgs = @()
            }
        }
    }

    throw "未找到可用的 Python 解释器。"
}

function Invoke-Python {
    param(
        [hashtable]$PythonCommand,
        [string[]]$Arguments,
        [string]$WorkingDirectory
    )

    $process = Start-Process -FilePath $PythonCommand.FilePath -ArgumentList ($PythonCommand.PrefixArgs + $Arguments) -WorkingDirectory $WorkingDirectory -NoNewWindow -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        throw "Python 命令失败，退出码 $($process.ExitCode)。"
    }
}

if (-not $Version) {
    $Version = Get-DefaultVersion
}

if (-not $OutputDir) {
    $OutputDir = Join-Path $RootDir "output\\windows-release"
}

if (-not (Test-Path $FrontendIndex)) {
    throw "未找到 app/dist/index.html。请先在 app/ 下执行 npm run build。"
}

$Python = Resolve-Python -ExplicitPath $PythonBin

$BuildRoot = Join-Path $OutputDir "build"
$DistRoot = Join-Path $OutputDir "dist"
$PackageRoot = Join-Path $OutputDir "package"
$PackageDirName = "kam-windows-exe-$Version"
$ReleaseRoot = Join-Path $PackageRoot $PackageDirName
$ZipPath = Join-Path $OutputDir "$PackageDirName.zip"

Ensure-Directory -Path $OutputDir
Ensure-Directory -Path $BuildRoot
Ensure-Directory -Path $DistRoot
Ensure-Directory -Path $PackageRoot

Remove-DirectorySafe -Path (Join-Path $BuildRoot "pyinstaller") -ExpectedRoot $BuildRoot
Remove-DirectorySafe -Path (Join-Path $DistRoot "KAM") -ExpectedRoot $DistRoot
Remove-DirectorySafe -Path $ReleaseRoot -ExpectedRoot $PackageRoot
if (Test-Path $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}

Invoke-Python -PythonCommand $Python -Arguments @("-m", "pip", "install", "-r", (Join-Path $RootDir "backend\\requirements.txt")) -WorkingDirectory $RootDir
Invoke-Python -PythonCommand $Python -Arguments @("-m", "pip", "install", "-r", $BuildRequirements) -WorkingDirectory $RootDir
Invoke-Python -PythonCommand $Python -Arguments @(
    "-m",
    "PyInstaller",
    "--noconfirm",
    "--clean",
    "--distpath",
    $DistRoot,
    "--workpath",
    (Join-Path $BuildRoot "pyinstaller"),
    $SpecPath
) -WorkingDirectory $RootDir

Copy-Item -Path (Join-Path $DistRoot "KAM") -Destination $ReleaseRoot -Recurse -Force
Compress-Archive -Path $ReleaseRoot -DestinationPath $ZipPath -CompressionLevel Optimal
Write-Host "Windows 可执行 release 已生成：$ZipPath"
