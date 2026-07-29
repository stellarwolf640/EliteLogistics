param(
    [switch]$SmokeTest
)

$ErrorActionPreference = "Stop"
trap {
    if ($SmokeTest) {
        Write-Error $_.Exception.Message
        exit 1
    }

    try {
        Add-Type -AssemblyName PresentationFramework
        [System.Windows.MessageBox]::Show(
            $_.Exception.Message,
            "Elite Logistics - Startup Error",
            [System.Windows.MessageBoxButton]::OK,
            [System.Windows.MessageBoxImage]::Error
        ) | Out-Null
    } catch {
        # If the native dialog itself is unavailable, PowerShell retains the
        # original error for anyone launching this script interactively.
    }
    exit 1
}

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$dependencyStamp = Join-Path $projectRoot ".venv\.elite-logistics-dependencies"
$backendProject = Join-Path $projectRoot "backend\pyproject.toml"
$frontendDist = Join-Path $projectRoot "frontend\dist\index.html"

Set-Location -LiteralPath $projectRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python 3.12 or newer is required."
}
$dependencyInstallRequired = $false
if (-not (Test-Path -LiteralPath $venvPython)) {
    python -m venv (Join-Path $projectRoot ".venv")
    $dependencyInstallRequired = $true
}

if (-not (Test-Path -LiteralPath $dependencyStamp)) {
    $dependencyInstallRequired = $true
} elseif ((Get-Item -LiteralPath $backendProject).LastWriteTimeUtc -gt (Get-Item -LiteralPath $dependencyStamp).LastWriteTimeUtc) {
    $dependencyInstallRequired = $true
}

if ($dependencyInstallRequired) {
    & $venvPython -m pip install --disable-pip-version-check -e "$projectRoot\backend"
    Set-Content -LiteralPath $dependencyStamp -Value (Get-Date).ToUniversalTime().ToString("O")
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
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "Node.js 22 or newer is required to rebuild the interface."
    }
    if (-not (Test-Path -LiteralPath "$projectRoot\frontend\node_modules")) {
        npm --prefix "$projectRoot\frontend" install
    }
    npm --prefix "$projectRoot\frontend" run build
}

$env:ELITE_LOGISTICS_DATA_DIR = Join-Path $projectRoot "data"
$env:ELITE_LOGISTICS_OPEN_BROWSER = "0"
$env:ELITE_LOGISTICS_DESKTOP = "1"
& $venvPython -m alembic -c "$projectRoot\backend\alembic.ini" upgrade head
$desktopArguments = @("-m", "elite_logistics.desktop")
if ($SmokeTest) {
    $desktopArguments += "--window-smoke-test"
}
if ($SmokeTest) {
    $desktopProcess = Start-Process `
        -FilePath $venvPython `
        -ArgumentList $desktopArguments `
        -WorkingDirectory $projectRoot `
        -PassThru `
        -Wait

    if ($desktopProcess.ExitCode -ne 0) {
        throw "The native Elite Logistics window smoke test failed with exit code $($desktopProcess.ExitCode)."
    }
} else {
    Start-Process `
        -FilePath $venvPython `
        -ArgumentList $desktopArguments `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden | Out-Null
}
