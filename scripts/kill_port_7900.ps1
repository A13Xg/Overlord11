param(
    [int]$Port = 7900
)

$conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1

if ($null -eq $conn) {
    Write-Output "No process is listening on port $Port."
    exit 0
}

$procId = $conn.OwningProcess

try {
    Stop-Process -Id $procId -Force -ErrorAction Stop
    Write-Output "Stopped process $procId on port $Port."
    exit 0
}
catch {
    Write-Error "Failed to stop process $procId on port $Port. $($_.Exception.Message)"
    exit 1
}
