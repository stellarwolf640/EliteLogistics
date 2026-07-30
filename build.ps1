$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Version = & "$Root\.venv\Scripts\python.exe" "$Root\scripts\check_versions.py"

Push-Location "$Root\frontend"
try {
    npm ci
    npm run build
} finally {
    Pop-Location
}

& "$Root\.venv\Scripts\python.exe" "$Root\scripts\create_icon.py"
& "$Root\.venv\Scripts\pyinstaller.exe" --clean --noconfirm --distpath "$Root\dist" --workpath "$Root\build\pyinstaller" "$Root\backend\ion.spec"
& "$Root\scripts\window_smoke.ps1" -Executable "$Root\dist\ION\ION.exe"

$env:ION_VERSION = $Version
$Inno = if ($env:INNO_SETUP_COMPILER) {
    $env:INNO_SETUP_COMPILER
} elseif (Test-Path "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") {
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
} else {
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
}
if (-not (Test-Path $Inno)) {
    throw "Inno Setup 6 was not found. Set INNO_SETUP_COMPILER or install Inno Setup."
}
& $Inno "$Root\installer\ION.iss"
Write-Host "ION $Version installer created in $Root\dist\installer"
