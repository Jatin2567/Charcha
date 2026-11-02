# Prepare local tools only: no login, deployment, GPU or provider call.
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$uvCommand = Get-Command uv -ErrorAction Stop
$pythonStore = Join-Path $taskRoot 'work/python-runtime'
$cliEnvironment = Join-Path $taskRoot 'work/modal-cli-py312/.venv'
$cache = Join-Path $taskRoot 'work/uv-cache'
$previousStore = $env:UV_PYTHON_INSTALL_DIR
try {
    $env:UV_PYTHON_INSTALL_DIR = $pythonStore
    & $uvCommand.Source python install 3.12 --no-bin --no-registry --cache-dir $cache
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 preparation failed.' }
    $interpreter = & $uvCommand.Source python find 3.12 --managed-python --no-project --no-python-downloads
    if ($LASTEXITCODE -ne 0) { throw 'Prepared Python 3.12 was not found.' }
    if (-not (Test-Path -LiteralPath (Join-Path $cliEnvironment 'Scripts/python.exe'))) {
        & $uvCommand.Source venv --python $interpreter $cliEnvironment
        if ($LASTEXITCODE -ne 0) { throw 'Isolated CLI preparation failed.' }
    }
    & $uvCommand.Source pip install --python (Join-Path $cliEnvironment 'Scripts/python.exe') --cache-dir $cache --requirement (Join-Path $taskRoot 'deploy/modal/requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Pinned Modal CLI installation failed.' }
    Write-Output 'Local Modal tools are ready with Python 3.12. No cloud resources started.'
    Write-Output 'Use work/modal-cli-py312/.venv/Scripts/modal.exe with your existing artha-mesh profile.'
} finally {
    $env:UV_PYTHON_INSTALL_DIR = $previousStore
}
