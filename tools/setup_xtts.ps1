<#
  One-shot setup for XTTS-v2 voice cloning.

    powershell -ExecutionPolicy Bypass -File tools\setup_xtts.ps1          # CUDA
    powershell -ExecutionPolicy Bypass -File tools\setup_xtts.ps1 -Cpu     # CPU only
    powershell -ExecutionPolicy Bypass -File tools\setup_xtts.ps1 -SkipModel
#>
param([switch]$Cpu, [switch]$SkipModel)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"
$index = "https://pypi.tuna.tsinghua.edu.cn/simple"

if (-not (Test-Path $py)) {
    Write-Host "please run install.bat first (.venv missing)" -ForegroundColor Red
    exit 1
}

Write-Host "== 1/4 PyTorch" -ForegroundColor Cyan
if ($Cpu) {
    # 2.5.1 is the version coqui-tts is tested against: torch >= 2.6 flips
    # torch.load to weights_only=True and XTTS checkpoints stop loading.
    & $py -m pip install --disable-pip-version-check -i $index torch==2.5.1 torchaudio==2.5.1
}
else {
    $base = "https://mirror.sjtu.edu.cn/pytorch-wheels/cu121/"
    $dir = Join-Path $root "data\wheels"
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $names = @("torch-2.5.1+cu121-cp311-cp311-win_amd64.whl", "torchaudio-2.5.1+cu121-cp311-cp311-win_amd64.whl")
    $minMB = @{ "torch-2.5.1+cu121-cp311-cp311-win_amd64.whl" = 2300; "torchaudio-2.5.1+cu121-cp311-cp311-win_amd64.whl" = 2 }
    foreach ($name in $names) {
        $out = Join-Path $dir $name
        $have = Test-Path $out
        $sizeMB = 0
        if ($have) { $sizeMB = (Get-Item $out).Length / 1MB }
        if ($have -and ($sizeMB -gt $minMB[$name])) {
            Write-Host "  already complete: $name"
            continue
        }
        Write-Host "  downloading $name (2.3 GB, resumable)"
        $url = $base + $name.Replace("+", "%2B")
        curl.exe -L -C - --retry 30 --retry-delay 3 --retry-all-errors --max-time 14400 -o "$out" "$url"
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  download interrupted - rerun this script to resume" -ForegroundColor Red
            exit 1
        }
    }
    & $py -m pip install --disable-pip-version-check (Join-Path $dir $names[0]) (Join-Path $dir $names[1])
}
if ($LASTEXITCODE -ne 0) { Write-Host "PyTorch install failed" -ForegroundColor Red; exit 1 }

$torchVer = (& $py -c "import torch;print(torch.__version__)") 2>$null
Write-Host "  torch = $torchVer"
if ($torchVer -match "^2\.(9|[1-9][0-9])") {
    Write-Host "  warning: torch >= 2.9 also needs torchcodec for TTS audio IO" -ForegroundColor Yellow
}

Write-Host "== 2/4 coqui-tts" -ForegroundColor Cyan
& $py -m pip install --disable-pip-version-check -i $index coqui-tts
if ($LASTEXITCODE -ne 0) { Write-Host "coqui-tts install failed" -ForegroundColor Red; exit 1 }

# transformers 5 needs symbols that torch 2.5 does not have
& $py -m pip install --disable-pip-version-check -i $index "transformers>=4.43,<5"
if ($LASTEXITCODE -ne 0) { Write-Host "transformers pin failed" -ForegroundColor Red; exit 1 }

if (-not $SkipModel) {
    Write-Host "== 3/4 XTTS-v2 weights (~1.95 GB via hf-mirror, resumable)" -ForegroundColor Cyan
    $dest = Join-Path $root "data\models\xtts_v2"
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    $baseUrl = "https://hf-mirror.com/coqui/XTTS-v2/resolve/main/"
    $names = @("config.json", "vocab.json", "speakers_xtts.pth", "mel_stats.pth", "dvae.pth", "model.pth")
    $minMB = @{ "config.json" = 0.001; "vocab.json" = 0.2; "speakers_xtts.pth" = 7; "mel_stats.pth" = 0.5; "dvae.pth" = 190; "model.pth" = 1700 }
    foreach ($name in $names) {
        $out = Join-Path $dest $name
        if ((Test-Path $out) -and ($minMB[$name] -lt 1)) { Remove-Item $out -Force }
        $have = Test-Path $out
        $sizeMB = 0
        if ($have) { $sizeMB = (Get-Item $out).Length / 1MB }
        if ($have -and ($sizeMB -gt $minMB[$name])) {
            Write-Host "  already complete: $name"
            continue
        }
        Write-Host "  downloading $name"
        curl.exe -L -C - --retry 40 --retry-delay 3 --retry-all-errors --max-time 14400 -o "$out" "$baseUrl$name"
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  $name interrupted - rerun this script to resume" -ForegroundColor Yellow
        }
    }
}

Write-Host "== 4/4 verify" -ForegroundColor Cyan
$env:HF_ENDPOINT = "https://hf-mirror.com"
$env:HF_HUB_DISABLE_XET = "1"
$env:COQUI_TOS_AGREED = "1"
& $py (Join-Path $root "tools\check_xtts.py")
exit $LASTEXITCODE
