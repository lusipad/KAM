param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [switch]$OpenBrowser
)

$ErrorActionPreference = "Stop"

$uri = "$($BaseUrl.TrimEnd('/'))/api/dev/seed-demo"
$payload = @{ reset = $true } | ConvertTo-Json

try {
    $result = Invoke-RestMethod -Method Post -Uri $uri -ContentType "application/json" -Body $payload
}
catch {
    throw "无法访问 $uri。请先启动本地服务，例如执行：pwsh -File .\\start-local.ps1"
}

Write-Host "Demo 数据已写入：" -ForegroundColor Green
Write-Host "  Project: $($result.projectId)"
Write-Host "  Thread:  $($result.threadId)"
Write-Host "  Watcher: $($result.watcherId)"

if ($OpenBrowser) {
    Start-Process "$($BaseUrl.TrimEnd('/'))/"
}
