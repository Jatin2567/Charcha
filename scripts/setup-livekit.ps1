# Installs only the pinned, official Windows local media server. No account/API call.
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$binaryFolder = Join-Path $projectRoot 'work/bin'
$binaryPath = Join-Path $binaryFolder 'livekit-server.exe'
$expectedHash = 'D1AC299A2F42D581E7044063C28355946808BDDDCBCC83E9801BEF147A6AB6FB'
if (Test-Path -LiteralPath $binaryPath) {
    if ((Get-FileHash -LiteralPath $binaryPath -Algorithm SHA256).Hash -ne $expectedHash) { throw 'Existing local LiveKit checksum mismatch. Do not run it.' }
    & $binaryPath --version
    if ($LASTEXITCODE -ne 0) { throw 'Existing local LiveKit executable failed.' }
    return
}
New-Item -ItemType Directory -Path $binaryFolder -Force | Out-Null
$archivePath = Join-Path $binaryFolder 'livekit-1.9.1.zip'
$releaseUrl = 'https://github.com/livekit/livekit/releases/download/v1.9.1/livekit_1.9.1_windows_amd64.zip'
Invoke-WebRequest -Uri $releaseUrl -OutFile $archivePath
# SHA-256 of the previously verified official v1.9.1 Windows executable.
Expand-Archive -LiteralPath $archivePath -DestinationPath $binaryFolder -Force
if (-not (Test-Path -LiteralPath $binaryPath)) { throw 'Official archive did not contain livekit-server.exe.' }
$actualHash = (Get-FileHash -LiteralPath $binaryPath -Algorithm SHA256).Hash
if ($actualHash -ne $expectedHash) { throw 'Local media server checksum mismatch. Do not run this executable.' }
& $binaryPath --version
if ($LASTEXITCODE -ne 0) { throw 'Local LiveKit verification failed.' }
Write-Host 'Local media server ready. Start with npm run dev:local.'
