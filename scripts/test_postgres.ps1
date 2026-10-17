# Runs the full suite against a disposable pgvector/PostgreSQL container.
# Requires Docker Desktop; never connects to a configured persistent database.

$ErrorActionPreference = 'Stop'
$containerName = 'sus-explorer-test-' + [guid]::NewGuid().ToString('N').Substring(0, 12)
$dbPassword = [Convert]::ToHexString(
    [System.Security.Cryptography.RandomNumberGenerator]::GetBytes(24)
)
$containerStarted = $false
$workspace = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$pythonPath = Join-Path $workspace '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Create .venv and install requirements-dev.txt before running this script'
}

Push-Location $workspace
try {
    docker run -d --rm --name $containerName `
        -e "POSTGRES_PASSWORD=$dbPassword" -e 'POSTGRES_DB=sus_explorer_test' `
        -p '127.0.0.1::5432' `
        --tmpfs '/var/lib/postgresql/data:rw,size=512m' `
        'pgvector/pgvector:0.8.6-pg17' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Disposable PostgreSQL container did not start' }
    $containerStarted = $true

    $ready = $false
    for ($attempt = 0; $attempt -lt 45; $attempt++) {
        docker exec $containerName pg_isready -U postgres -d sus_explorer_test *> $null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        Start-Sleep -Seconds 1
    }
    if (-not $ready) { throw 'Disposable PostgreSQL did not become ready' }

    $portLine = docker port $containerName 5432/tcp
    $env:POSTGRES_HOST = '127.0.0.1'
    $env:POSTGRES_PORT = ($portLine -split ':')[-1]
    $env:POSTGRES_DB = 'sus_explorer_test'
    $env:POSTGRES_USER = 'postgres'
    $env:POSTGRES_PASSWORD = $dbPassword
    $env:POSTGRES_SSLMODE = 'disable'
    $env:POSTGRES_SCHEMA = 'sus_explorer'
    $env:SUS_EXPLORER_TEST_DB = '1'

    Write-Output 'Checking PostgreSQL with SELECT 1'
    & $pythonPath -m sus_explorer.data.persistence.healthcheck
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL health check failed' }
    Write-Output 'Applying versioned migrations'
    & $pythonPath -m sus_explorer.data.persistence.migrate
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL migration failed' }
    Write-Output 'Running full test suite against disposable PostgreSQL'
    & $pythonPath -m pytest tests -q -rs --tb=short
    if ($LASTEXITCODE -ne 0) { throw 'Test suite failed' }
}
finally {
    if ($containerStarted) {
        docker stop $containerName *> $null
        Write-Output 'Disposable PostgreSQL container stopped and removed'
    }
    Pop-Location
}
