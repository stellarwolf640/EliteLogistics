$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"

Set-Location -LiteralPath $projectRoot
if (-not (Test-Path -LiteralPath $venvPython)) {
    python -m venv (Join-Path $projectRoot ".venv")
}
& $venvPython -m pip install --disable-pip-version-check -e "$projectRoot\backend[dev]"
if (-not (Test-Path -LiteralPath "$projectRoot\frontend\node_modules")) {
    npm --prefix "$projectRoot\frontend" install
}
$env:ELITE_LOGISTICS_DATA_DIR = Join-Path $projectRoot "data"
$env:ELITE_LOGISTICS_OPEN_BROWSER = "0"
& $venvPython -m alembic -c "$projectRoot\backend\alembic.ini" upgrade head
Start-Process -FilePath $venvPython -ArgumentList "-m", "elite_logistics.main" -WorkingDirectory $projectRoot -WindowStyle Hidden
npm --prefix "$projectRoot\frontend" run dev
