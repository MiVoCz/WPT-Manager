$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$distPath = Join-Path $projectRoot "dist\WPT-Manager"

if (-not (Test-Path -LiteralPath $distPath -PathType Container)) {
    throw "Distribution directory does not exist: $distPath"
}

$files = @(Get-ChildItem -LiteralPath $distPath -Recurse -File)
$distPrefixLength = $distPath.TrimEnd("\").Length + 1
$relativeFiles = @(
    $files | ForEach-Object {
        $_.FullName.Substring($distPrefixLength).Replace("\", "/")
    }
)

$requiredPatterns = @{
    "WPT-Manager.exe" = '^WPT-Manager\.exe$'
    "LICENSE" = '(^|/)LICENSE$'
    "README.md" = '(^|/)README\.md$'
    "config.example.json" = '(^|/)data/config\.example\.json$'
    "QtWebEngineProcess.exe" = '(^|/)QtWebEngineProcess\.exe$'
    "Qt platform plugin" = '(^|/)platforms/qwindows\.dll$'
    "Qt image format plugin" = '(^|/)imageformats/.+\.dll$'
    "Qt icon engine plugin" = '(^|/)iconengines/.+\.dll$'
    "Qt WebEngine resources" = '(^|/)resources/qtwebengine_resources.*\.pak$'
    "Qt WebEngine locales" = '(^|/)translations/qtwebengine_locales/.+\.pak$'
    "QWebChannel module" = '(^|/)PySide6/QtWebChannel\.pyd$'
}

foreach ($required in $requiredPatterns.GetEnumerator()) {
    if (-not ($relativeFiles | Where-Object { $_ -match $required.Value })) {
        throw "Required component is missing: $($required.Key)"
    }
}

$forbidden = @(
    $relativeFiles | Where-Object {
        $_ -match '(^|/)config\.json$' -or
        $_ -match '\.db$' -or
        $_ -match '(^|/)data/icons/' -or
        $_ -match '(^|/)tests(/|$)' -or
        $_ -match '(^|/)\.pytest' -or
        $_ -match '(^|/)\.test-'
    }
)
if ($forbidden) {
    throw "Forbidden files found in distribution:`n$($forbidden -join "`n")"
}

$sizeBytes = ($files | Measure-Object -Property Length -Sum).Sum
$sizeMiB = [math]::Round($sizeBytes / 1MB, 2)
Write-Host "Artifact audit passed."
Write-Host "Distribution: $distPath"
Write-Host "Size: $sizeMiB MiB"
