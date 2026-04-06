param(
    [string]$Version = "",
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $PSScriptRoot
$DistDir = Join-Path $RootDir "app\\dist"
$PortableAssetsDir = Join-Path $RootDir "packaging\\portable"

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

function Copy-Tree {
    param(
        [string]$SourceRoot,
        [string]$DestinationRoot
    )

    $resolvedSource = [System.IO.Path]::GetFullPath($SourceRoot)
    Ensure-Directory -Path $DestinationRoot

    Get-ChildItem -Path $resolvedSource -Recurse -File | Where-Object {
        $_.FullName -notmatch '[\\/]+__pycache__([\\/]|$)' -and
        $_.Name -notlike '*.pyc' -and
        $_.Name -notlike '*.pyo' -and
        $_.Name -notlike '*.log'
    } | ForEach-Object {
        $relativePath = [System.IO.Path]::GetRelativePath($resolvedSource, $_.FullName)
        $destinationPath = Join-Path $DestinationRoot $relativePath
        $destinationDir = Split-Path -Parent $destinationPath
        Ensure-Directory -Path $destinationDir
        Copy-Item -Path $_.FullName -Destination $destinationPath -Force
    }
}

if (-not $Version) {
    $Version = Get-DefaultVersion
}

if (-not $OutputDir) {
    $OutputDir = Join-Path $RootDir "output\\packages"
}

if (-not (Test-Path (Join-Path $DistDir "index.html"))) {
    throw "未找到 app/dist/index.html。请先在 app/ 下执行 npm run build。"
}

Ensure-Directory -Path $OutputDir

$StageDir = Join-Path $OutputDir "stage"
$PackageDirName = "kam-portable-$Version"
$PackageRoot = Join-Path $StageDir $PackageDirName
$ZipPath = Join-Path $OutputDir "$PackageDirName.zip"

Ensure-Directory -Path $StageDir
Remove-DirectorySafe -Path $PackageRoot -ExpectedRoot $StageDir
if (Test-Path $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}

Ensure-Directory -Path $PackageRoot
Ensure-Directory -Path (Join-Path $PackageRoot "app")
Ensure-Directory -Path (Join-Path $PackageRoot "backend")

Copy-Tree -SourceRoot $DistDir -DestinationRoot (Join-Path $PackageRoot "app\\dist")

$backendRoot = Join-Path $RootDir "backend"
foreach ($directory in @("api", "adapters", "alembic", "scripts", "services")) {
    Copy-Tree -SourceRoot (Join-Path $backendRoot $directory) -DestinationRoot (Join-Path $PackageRoot "backend\\$directory")
}

foreach ($file in @(
    ".env.example",
    "kam-operator.ps1",
    "seed-harness.ps1",
    "start-local.ps1",
    "start-local.sh"
)) {
    Copy-Item -Path (Join-Path $RootDir $file) -Destination (Join-Path $PackageRoot $file) -Force
}

foreach ($file in @(
    "main.py",
    "config.py",
    "db.py",
    "models.py",
    "requirements.txt",
    "alembic.ini"
)) {
    Copy-Item -Path (Join-Path $backendRoot $file) -Destination (Join-Path $PackageRoot "backend\\$file") -Force
}

foreach ($file in @("install.ps1", "install.sh", "run.ps1", "run.sh")) {
    Copy-Item -Path (Join-Path $PortableAssetsDir $file) -Destination (Join-Path $PackageRoot $file) -Force
}

Copy-Item -Path (Join-Path $PortableAssetsDir "README.md") -Destination (Join-Path $PackageRoot "README.md") -Force

Compress-Archive -Path $PackageRoot -DestinationPath $ZipPath -CompressionLevel Optimal
Write-Host "便携包已生成：$ZipPath"
