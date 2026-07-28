$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$frontendDist = Join-Path $projectRoot "frontend\dist\index.html"

Set-Location -LiteralPath $projectRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python 3.12 or newer is required."
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "Node.js 22 or newer is required."
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    python -m venv (Join-Path $projectRoot ".venv")
}

& $venvPython -m pip install --disable-pip-version-check -e "$projectRoot\backend"

if (-not (Test-Path -LiteralPath "$projectRoot\frontend\node_modules")) {
    npm --prefix "$projectRoot\frontend" install
}

if (-not (Test-Path -LiteralPath $frontendDist)) {
    npm --prefix "$projectRoot\frontend" run build
}

$env:ELITE_LOGISTICS_DATA_DIR = Join-Path $projectRoot "data"
$env:ELITE_LOGISTICS_OPEN_BROWSER = "1"
& $venvPython -m alembic -c "$projectRoot\backend\alembic.ini" upgrade head
& $venvPython -m elite_logistics.main
