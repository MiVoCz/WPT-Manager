param(
    [string]$Version = "0.1.0"
)

$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$distRoot = Join-Path $projectRoot "dist"
$sourcePath = Join-Path $distRoot "WPT-Manager"
$zipPath = Join-Path $distRoot "WPT-Manager-$Version-win64.zip"

function Get-ForbiddenPaths {
    param([string[]]$Paths)

    return @(
        $Paths | Where-Object {
            $_ -match '(^|/)config\.json$' -or
            $_ -match '\.db$' -or
            $_ -match '\.gpx$' -or
            $_ -match '(^|/)data/icons(/|$)' -or
            $_ -match '(^|/)tests(/|$)' -or
            $_ -match '(^|/)\.pytest' -or
            $_ -match '(^|/)\.test-' -or
            $_ -match '(^|/)__pycache__(/|$)' -or
            $_ -match '\.(py|pyc|pyo|spec|spec\.tmp|ps1|toml)$'
        }
    )
}

if (-not (Test-Path -LiteralPath $sourcePath -PathType Container)) {
    throw "Existing onedir distribution does not exist: $sourcePath"
}

& (Join-Path $PSScriptRoot "audit_windows_dist.ps1")

$sourceFiles = @(Get-ChildItem -LiteralPath $sourcePath -Recurse -File)
$sourcePrefixLength = $sourcePath.TrimEnd("\").Length + 1
$sourceRelativeFiles = @(
    $sourceFiles | ForEach-Object {
        $_.FullName.Substring($sourcePrefixLength).Replace("\", "/")
    }
)
$forbiddenSourceFiles = Get-ForbiddenPaths $sourceRelativeFiles
if ($forbiddenSourceFiles) {
    throw "Forbidden files found in onedir source:`n$($forbiddenSourceFiles -join "`n")"
}

$temporaryRoot = Join-Path (
    [System.IO.Path]::GetTempPath()
) ("WPT-Manager-package-" + [guid]::NewGuid().ToString("N"))
$stagedApplication = Join-Path $temporaryRoot "WPT-Manager"

try {
    New-Item -ItemType Directory -Path $temporaryRoot | Out-Null
    Copy-Item -LiteralPath $sourcePath -Destination $stagedApplication -Recurse

    foreach ($documentName in @("LICENSE", "README.md")) {
        $internalDocument = Join-Path $stagedApplication "_internal\$documentName"
        $rootDocument = Join-Path $stagedApplication $documentName
        if (-not (Test-Path -LiteralPath $internalDocument -PathType Leaf)) {
            throw "Required distribution document is missing: $documentName"
        }
        Move-Item -LiteralPath $internalDocument -Destination $rootDocument
    }

    if (Test-Path -LiteralPath $zipPath) {
        Remove-Item -LiteralPath $zipPath -Force
    }

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::CreateFromDirectory(
        $temporaryRoot,
        $zipPath,
        [System.IO.Compression.CompressionLevel]::Optimal,
        $false
    )
} finally {
    if (Test-Path -LiteralPath $temporaryRoot) {
        Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
    }
}

$archive = [System.IO.Compression.ZipFile]::OpenRead($zipPath)
try {
    $entries = @(
        $archive.Entries |
            Where-Object { -not $_.FullName.EndsWith("/") } |
            ForEach-Object { $_.FullName.Replace("\", "/") }
    )

    if (-not $entries -or ($entries | Where-Object { $_ -notmatch '^WPT-Manager/' })) {
        throw "ZIP root structure is invalid. Every file must be under WPT-Manager/."
    }

    $requiredPatterns = @{
        "WPT-Manager.exe" = '^WPT-Manager/WPT-Manager\.exe$'
        "LICENSE" = '^WPT-Manager/LICENSE$'
        "README.md" = '^WPT-Manager/README\.md$'
        "QtWebEngineProcess.exe" = '(^|/)QtWebEngineProcess\.exe$'
        "Qt platform plugin" = '(^|/)platforms/qwindows\.dll$'
        "Qt WebEngine resources" = '(^|/)resources/qtwebengine_resources.*\.pak$'
        "Qt WebEngine locales" = '(^|/)translations/qtwebengine_locales/.+\.pak$'
        "QWebChannel module" = '(^|/)PySide6/QtWebChannel\.pyd$'
    }
    foreach ($required in $requiredPatterns.GetEnumerator()) {
        if (-not ($entries | Where-Object { $_ -match $required.Value })) {
            throw "Required ZIP component is missing: $($required.Key)"
        }
    }

    $archiveRelativeFiles = @(
        $entries | ForEach-Object { $_.Substring("WPT-Manager/".Length) }
    )
    $forbiddenArchiveFiles = Get-ForbiddenPaths $archiveRelativeFiles
    if ($forbiddenArchiveFiles) {
        throw "Forbidden files found in ZIP:`n$($forbiddenArchiveFiles -join "`n")"
    }
} finally {
    $archive.Dispose()
}

$zip = Get-Item -LiteralPath $zipPath
$sizeMiB = [math]::Round($zip.Length / 1MB, 2)
$sha256 = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash
Write-Host "Package audit passed."
Write-Host "ZIP: $zipPath"
Write-Host "Size: $sizeMiB MiB"
Write-Host "SHA-256: $sha256"
