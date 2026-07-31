param(
    [Parameter(Mandatory = $true)]
    [string]$Executable,
    [string]$ProfilePath = (Join-Path $env:TEMP ("ion-window-smoke-" + [guid]::NewGuid().ToString("N"))),
    [int]$TimeoutSeconds = 30
)

$ErrorActionPreference = "Stop"
$resolvedExecutable = (Resolve-Path -LiteralPath $Executable).Path
New-Item -ItemType Directory -Path $ProfilePath -Force | Out-Null

$previousDataDir = $env:ELITE_LOGISTICS_DATA_DIR
try {
    $env:ELITE_LOGISTICS_DATA_DIR = $ProfilePath
    $process = Start-Process -FilePath $resolvedExecutable -ArgumentList "--window-smoke-test" -PassThru
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        Stop-Process -Id $process.Id -Force
        throw "Native window smoke test timed out after $TimeoutSeconds seconds."
    }
    if ($process.ExitCode -ne 0) {
        throw "Native window smoke test failed with exit code $($process.ExitCode)."
    }

    $logPath = Join-Path $ProfilePath "logs\ion.log"
    if (-not (Test-Path -LiteralPath $logPath)) {
        throw "Native window smoke test did not create an application log."
    }

    $bridgeErrors = Select-String -LiteralPath $logPath -Pattern (
        "maximum recursion depth",
        "Error while processing .*\.native",
        "\sERROR\s"
    )
    if ($bridgeErrors) {
        $details = ($bridgeErrors | ForEach-Object { $_.Line }) -join [Environment]::NewLine
        throw "Native window smoke test logged an error:$([Environment]::NewLine)$details"
    }
} finally {
    $env:ELITE_LOGISTICS_DATA_DIR = $previousDataDir
}

Write-Host "Native window smoke test passed."
