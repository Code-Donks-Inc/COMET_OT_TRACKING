
$ErrorActionPreference = "Stop"

# Store backups in a folder beside this script.
$backupDir = Join-Path $PSScriptRoot "backups"
New-Item -ItemType Directory -Path $backupDir -Force |
    Out-Null

# Generate unique names for the backup.
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$containerDump = "/tmp/otintel_$timestamp.dump"
$backupPath = Join-Path $backupDir "otintel_$timestamp.dump"

$containerId = $null
$backupVerified = $false

try {
    # Find the database container.
    $containerId = (& docker compose ps -q db).Trim()

    if ($LASTEXITCODE -ne 0 -or
        [string]::IsNullOrWhiteSpace($containerId)) {
        throw "Database container not found. Is Docker Compose running?"
    }

    # Create a PostgreSQL custom-format backup.
    & docker compose exec -T db pg_dump `
        -U otintel -d otintel -Fc -f $containerDump

    if ($LASTEXITCODE -ne 0) {
        throw "Backup creation failed."
    }

    # Copy the backup to the Windows host.
    & docker cp "${containerId}:$containerDump" $backupPath

    if ($LASTEXITCODE -ne 0) {
        throw "Could not copy the backup to the project."
    }

    # Check that the local backup exists and is not empty.
    if (-not (Test-Path $backupPath) -or
        (Get-Item $backupPath).Length -eq 0) {
        throw "Backup file is missing or empty."
    }

    # Verify that PostgreSQL can read the backup archive.
    & docker compose exec -T db pg_restore --list $containerDump |
        Out-Null

    if ($LASTEXITCODE -ne 0) {
        throw "Backup archive verification failed."
    }

    $backupVerified = $true

    Write-Host "Backup created and archive verified."
    Write-Host "File: $backupPath"
    Write-Host "Size: $((Get-Item $backupPath).Length) bytes"
}
finally {
    # Remove the temporary copy from the container.
    if (-not [string]::IsNullOrWhiteSpace($containerId)) {
        & docker compose exec -T db rm -f $containerDump |
            Out-Null
    }

    # Remove the local file if verification did not finish.
    if (-not $backupVerified -and (Test-Path $backupPath)) {
        Remove-Item $backupPath -Force
    }
}
