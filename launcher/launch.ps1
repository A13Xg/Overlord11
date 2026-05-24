#!/usr/bin/env pwsh

param(
    [Alias('p')]
    [int]$Port = $(if ($env:OVERLORD_PORT) { [int]$env:OVERLORD_PORT } elseif ($env:PORT) { [int]$env:PORT } else { 7900 }),
    [switch]$stop,
    [switch]$kill,
    [switch]$help
)

$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Resolve-Path (Join-Path $ScriptDir '..')).Path

function Show-Usage {
    @"
Overlord11 PowerShell Launcher

Usage:
  ./launcher/launch.ps1 [-Port <port>] [-stop] [-kill] [-help]

Options:
  -Port <port>  Port to run/stop (default: OVERLORD_PORT, PORT, or 7900)
  -stop         Stop process listening on the selected port (Stop-Process)
  -kill         Force kill process on the selected port (Stop-Process -Force)
  -help         Show help

Examples:
  ./launcher/launch.ps1
  ./launcher/launch.ps1 -Port 8000
  ./launcher/launch.ps1 -stop -Port 7900
  ./launcher/launch.ps1 -kill -Port 7900
"@
}

function Write-Log {
    param([string]$Message)
    Write-Host "[launcher] $Message"
}

function Test-Command {
    param([string]$Name)
    return [bool](Get-Command -Name $Name -ErrorAction SilentlyContinue)
}

function Install-Python {
    Write-Log 'Python 3 not found. Attempting install...'

    if (Test-Command 'winget') {
        & winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
        return
    }

    if (Test-Command 'choco') {
        & choco install -y python
        return
    }

    if (Test-Command 'scoop') {
        & scoop install python
        return
    }

    throw 'Could not auto-install Python. Install Python 3 manually and re-run.'
}

function Install-Node {
    Write-Log 'Node.js/npm not found. Attempting install...'

    if (Test-Command 'winget') {
        & winget install -e --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
        return
    }

    if (Test-Command 'choco') {
        & choco install -y nodejs-lts
        return
    }

    if (Test-Command 'scoop') {
        & scoop install nodejs-lts
        return
    }

    throw 'Could not auto-install Node.js/npm. Install Node.js manually and re-run.'
}

function Resolve-PythonCommand {
    if (Test-Command 'python') {
        return 'python'
    }

    if (Test-Command 'py') {
        return 'py -3'
    }

    Install-Python

    if (Test-Command 'python') {
        return 'python'
    }

    if (Test-Command 'py') {
        return 'py -3'
    }

    throw 'Python install completed but executable is still unavailable.'
}

function Invoke-Python {
    param(
        [Parameter(Mandatory = $true)][string]$PythonCommand,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    if ($PythonCommand -eq 'python') {
        & python @Arguments
        return
    }

    if ($PythonCommand -eq 'py -3') {
        & py -3 @Arguments
        return
    }

    throw "Unsupported Python command: $PythonCommand"
}

function Ensure-Pip {
    param([Parameter(Mandatory = $true)][string]$PythonCommand)

    try {
        Invoke-Python -PythonCommand $PythonCommand -Arguments @('-m', 'pip', '--version') | Out-Null
    } catch {
        Write-Log 'pip missing. Attempting bootstrap via ensurepip...'
        try {
            Invoke-Python -PythonCommand $PythonCommand -Arguments @('-m', 'ensurepip', '--upgrade') | Out-Null
        } catch {
            throw 'pip is unavailable and ensurepip failed. Install pip manually and re-run.'
        }
    }
}

function Ensure-NodeNpm {
    if (-not (Test-Command 'node') -or -not (Test-Command 'npm')) {
        Install-Node
    }

    if (-not (Test-Command 'node') -or -not (Test-Command 'npm')) {
        throw 'Node.js/npm install completed but executable is still unavailable.'
    }
}

function Install-PythonDependencies {
    param([Parameter(Mandatory = $true)][string]$PythonCommand)

    $requirements = Join-Path $ProjectRoot 'requirements.txt'
    if (Test-Path $requirements) {
        Write-Log 'Installing Python dependencies from requirements.txt'
        Invoke-Python -PythonCommand $PythonCommand -Arguments @('-m', 'pip', 'install', '--upgrade', 'pip')
        Invoke-Python -PythonCommand $PythonCommand -Arguments @('-m', 'pip', 'install', '-r', $requirements)
    } else {
        Write-Log 'No requirements.txt found. Skipping Python dependency install.'
    }
}

function Install-NpmDependencies {
    $packageJson = Join-Path $ProjectRoot 'package.json'
    if (Test-Path $packageJson) {
        $lockFile = Join-Path $ProjectRoot 'package-lock.json'
        Push-Location $ProjectRoot
        try {
            if (Test-Path $lockFile) {
                Write-Log 'Installing npm dependencies with package-lock.json (npm ci)'
                & npm ci
            } else {
                Write-Log 'Installing npm dependencies (npm install)'
                & npm install
            }
        } finally {
            Pop-Location
        }
    } else {
        Write-Log 'No package.json found. Skipping npm dependency install.'
    }
}

function Get-PidsByPort {
    param([Parameter(Mandatory = $true)][int]$TargetPort)

    $pids = @()

    try {
        $connections = Get-NetTCPConnection -LocalPort $TargetPort -ErrorAction Stop
        $pids += $connections | Select-Object -ExpandProperty OwningProcess -Unique
    } catch {
        if (Test-Command 'lsof') {
            $lsofPids = & lsof -ti tcp:$TargetPort -sTCP:LISTEN 2>$null
            if ($lsofPids) {
                $pids += $lsofPids
            }
        }
    }

    $clean = $pids | ForEach-Object { $_.ToString().Trim() } | Where-Object { $_ -match '^[0-9]+$' } | Sort-Object -Unique
    return $clean
}

function Stop-PortProcess {
    param(
        [Parameter(Mandatory = $true)][int]$TargetPort,
        [Parameter(Mandatory = $true)][bool]$ForceKill
    )

    $pids = Get-PidsByPort -TargetPort $TargetPort

    if (-not $pids -or $pids.Count -eq 0) {
        Write-Log "No listening process found on port $TargetPort"
        return
    }

    $label = if ($ForceKill) { 'force kill' } else { 'stop' }
    Write-Log "$label process(es) on port $TargetPort: $($pids -join ',')"

    foreach ($pid in $pids) {
        if ($ForceKill) {
            Stop-Process -Id ([int]$pid) -Force -ErrorAction SilentlyContinue
        } else {
            Stop-Process -Id ([int]$pid) -ErrorAction SilentlyContinue
        }
    }
}

if ($help) {
    Show-Usage
    exit 0
}

if ($Port -lt 1 -or $Port -gt 65535) {
    throw "Invalid port: $Port"
}

if ($stop -and $kill) {
    throw 'Use either -stop or -kill, not both.'
}

if ($stop -or $kill) {
    Stop-PortProcess -TargetPort $Port -ForceKill ([bool]$kill)
    exit 0
}

$pythonCommand = Resolve-PythonCommand
Ensure-Pip -PythonCommand $pythonCommand
Ensure-NodeNpm
Install-PythonDependencies -PythonCommand $pythonCommand
Install-NpmDependencies

Write-Log "Starting Overlord11 on port $Port"
Push-Location $ProjectRoot
try {
    $env:PORT = [string]$Port
    Invoke-Python -PythonCommand $pythonCommand -Arguments @('scripts/run_webui.py')
} finally {
    Pop-Location
}
