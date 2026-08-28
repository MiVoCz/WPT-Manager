$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$specPath = Join-Path $projectRoot "packaging\WPT-Manager.spec"
$python = (Get-Command python -ErrorAction Stop).Source

foreach ($directoryName in @("build", "dist")) {
    $directory = Join-Path $projectRoot $directoryName
    $resolvedParent = (Resolve-Path (Split-Path $directory -Parent)).Path
    if ($resolvedParent -ne $projectRoot) {
        throw "Refusing to clean path outside project root: $directory"
    }
    if (Test-Path -LiteralPath $directory) {
        Remove-Item -LiteralPath $directory -Recurse -Force
    }
}

Write-Host "Python: $python"
& $python -m PyInstaller --noconfirm --clean $specPath
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

& (Join-Path $PSScriptRoot "audit_windows_dist.ps1")
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
