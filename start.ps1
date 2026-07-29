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

$frontendBuildRequired = -not (Test-Path -LiteralPath $frontendDist)
if (-not $frontendBuildRequired) {
    $compiledAt = (Get-Item -LiteralPath $frontendDist).LastWriteTimeUtc
    $frontendInputs = @(
        Get-ChildItem -LiteralPath "$projectRoot\frontend\src" -Recurse -File
        Get-Item -LiteralPath "$projectRoot\frontend\package.json"
        Get-Item -LiteralPath "$projectRoot\frontend\package-lock.json" -ErrorAction SilentlyContinue
        Get-Item -LiteralPath "$projectRoot\frontend\vite.config.ts" -ErrorAction SilentlyContinue
        Get-Item -LiteralPath "$projectRoot\frontend\tsconfig.app.json" -ErrorAction SilentlyContinue
    ) | Where-Object { $_ }
    $frontendBuildRequired = $null -ne ($frontendInputs | Where-Object { $_.LastWriteTimeUtc -gt $compiledAt } | Select-Object -First 1)
}

if ($frontendBuildRequired) {
    npm --prefix "$projectRoot\frontend" run build
}

$env:ELITE_LOGISTICS_DATA_DIR = Join-Path $projectRoot "data"
$env:ELITE_LOGISTICS_OPEN_BROWSER = "1"
& $venvPython -m alembic -c "$projectRoot\backend\alembic.ini" upgrade head
& $venvPython -m elite_logistics.main
