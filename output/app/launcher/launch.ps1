param(
  [switch]$Kill,
  [int]$Port = 4310
)

$ErrorActionPreference = "Stop"

function Stop-PortProcess {
  param([int]$TargetPort)

  $pids = @()
  try {
    $pids = (Get-NetTCPConnection -LocalPort $TargetPort -State Listen -ErrorAction Stop | Select-Object -ExpandProperty OwningProcess | Sort-Object -Unique)
  } catch {
    $pids = @()
  }

  if (-not $pids -or $pids.Count -eq 0) {
    Write-Host "[launcher] No process on port $TargetPort"
    return
  }

  Write-Host "[launcher] Stopping port $TargetPort: $($pids -join ', ')"
  foreach ($pid in $pids) {
    try { Stop-Process -Id $pid -ErrorAction SilentlyContinue } catch { }
  }
  Start-Sleep -Seconds 1
  foreach ($pid in $pids) {
    try { Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue } catch { }
  }
}

if ($Kill) {
  Stop-PortProcess -TargetPort $Port
  exit 0
}

if (Test-Path "requirements.txt") {
  Write-Host "[launcher] Installing Python dependencies"
  python -m pip install -r requirements.txt
}

if (Test-Path "package.json") {
  Write-Host "[launcher] Installing Node dependencies"
  if (Test-Path "package-lock.json") { npm ci } else { npm install }
}

$appCmd = "python3 app.py --port {port}".Replace("{port}", "$Port")
Write-Host "[launcher] Starting app on port $Port"
Invoke-Expression $appCmd
