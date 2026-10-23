param([switch]$Live)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location -LiteralPath $projectRoot
try {
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw 'Install Node.js 22 or newer from nodejs.org first.' }
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'Install uv from docs.astral.sh/uv/getting-started/installation first.' }
    if (-not (Test-Path -LiteralPath 'server/.env')) { Copy-Item -LiteralPath 'server/.env.example' -Destination 'server/.env' }
    npm install --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
    $syncArguments = @('sync', '--project', 'server', '--extra', 'dev')
    if ($Live) { $syncArguments += @('--extra', 'live') }
    & uv @syncArguments
    if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }
    Write-Host 'Ready. Start the application with: npm run dev'
    Write-Host 'Live setup values belong in server/.env; keep that file private.'
} finally {
    Pop-Location
}
