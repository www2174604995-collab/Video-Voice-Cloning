# Pack the project as tar.gz for Linux/cloud (no venv, no data, no secrets).
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
$name = "bilisimul-code.tar.gz"
Remove-Item $name -Force -ErrorAction SilentlyContinue
tar -czf $name --exclude=server/config.yaml --exclude=__pycache__ --exclude=*.pyc --exclude=.venv --exclude=data README.md install.bat start.bat install-xtts.bat extension server web tests tools scripts docs
Write-Host "packed $name ($([math]::Round((Get-Item $name).Length/1KB,0)) KB)"
$has = (tar -tzf $name) -match "server/config.yaml"
if ($has) { Write-Host "FAILED: config.yaml included" } else { Write-Host "verify config excluded: ok" }