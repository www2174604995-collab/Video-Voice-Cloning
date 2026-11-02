# 打包项目代码（不含 .venv / data / 模型 / 含 key 的 config.yaml），用于上传到云 GPU
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$stamp = Get-Date -Format "MMdd-HHmm"
$out = Join-Path $root ("bilisimul-code-" + $stamp + ".zip")
$tmp = Join-Path $env:TEMP ("bilisimul-pack-" + $stamp)
if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
New-Item -ItemType Directory -Path $tmp | Out-Null

$items = @("server","extension","web","tests","tools","scripts","docs","README.md","install.bat","start.bat","install-xtts.bat")
foreach ($i in $items) {
    $p = Join-Path $root $i
    if (Test-Path $p) { Copy-Item $p (Join-Path $tmp $i) -Recurse -Force }
}
Remove-Item (Join-Path $tmp "server\config.yaml") -Force -ErrorAction SilentlyContinue
Get-ChildItem $tmp -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Get-ChildItem $tmp -Recurse -Include "*.pyc" -File | Remove-Item -Force -ErrorAction SilentlyContinue
Compress-Archive -Path (Join-Path $tmp "*") -DestinationPath $out -Force
Remove-Item $tmp -Recurse -Force
Write-Host "打包完成: $out" -ForegroundColor Green
Write-Host "上传示例: scp -P <端口> <zip> root@<主机>:/root/" -ForegroundColor Cyan