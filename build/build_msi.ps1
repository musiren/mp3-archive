# build/build_msi.ps1
#
# Build the Windows MSI installer for mp3-archive.
# Reads the version from NEWS and converts vYYYYMMDD -> YYYY.M.D.0 for WiX.
#
# Usage (run from project root):
#   powershell -ExecutionPolicy Bypass -File build\build_msi.ps1
#
# Requirements:
#   - pyinstaller  (pip install pyinstaller)
#   - WiX Toolset v3  https://github.com/wixtoolset/wix3/releases
#
# Output:
#   dist\mp3-archive.msi

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot

# ---------------------------------------------------------------------------
# Locate WiX Toolset v3 (candle.exe / light.exe)
# ---------------------------------------------------------------------------
function Find-WixBin {
    # 1. Already on PATH
    if (Get-Command candle.exe -ErrorAction SilentlyContinue) {
        return $null   # use PATH as-is
    }
    # 2. Refresh PATH from registry (picks up installs done in this session)
    $machinePath = [System.Environment]::GetEnvironmentVariable("PATH", "Machine")
    $userPath    = [System.Environment]::GetEnvironmentVariable("PATH", "User")
    $env:PATH    = "$machinePath;$userPath"
    if (Get-Command candle.exe -ErrorAction SilentlyContinue) {
        return $null
    }
    # 3. Scan common install roots for any WiX v3 directory
    $searchRoots = @(
        "${env:ProgramFiles(x86)}",
        "${env:ProgramFiles}",
        "${env:LocalAppData}\Programs",
        "${env:ProgramData}"
    )
    foreach ($base in $searchRoots) {
        if (-not $base -or -not (Test-Path $base)) { continue }
        # Use foreach loop (not ForEach-Object) so return exits the function
        $dirs = Get-ChildItem -Path $base -Filter "WiX*" -Directory -ErrorAction SilentlyContinue |
                    Where-Object { $_.Name -match "v?3\." -or $_.Name -match "Toolset" } |
                    Sort-Object Name -Descending
        foreach ($dir in $dirs) {
            $bin = Join-Path $dir.FullName "bin"
            if (Test-Path (Join-Path $bin "candle.exe")) {
                return $bin
            }
            if (Test-Path (Join-Path $dir.FullName "candle.exe")) {
                return $dir.FullName
            }
        }
    }
    return $null
}

$wixBin = Find-WixBin
if ($wixBin -eq $null -and -not (Get-Command candle.exe -ErrorAction SilentlyContinue)) {
    Write-Error @"
WiX Toolset v3 not found.
Install it from: https://github.com/wixtoolset/wix3/releases
Then re-run this script.
"@
    exit 1
}
if ($wixBin) {
    Write-Host "==> WiX found: $wixBin"
    $candle = Join-Path $wixBin "candle.exe"
    $light  = Join-Path $wixBin "light.exe"
} else {
    $candle = "candle"
    $light  = "light"
}

# ---------------------------------------------------------------------------
# Parse version from NEWS
# ---------------------------------------------------------------------------
$newsPath = Join-Path $Root "NEWS"
$match = Select-String -Path $newsPath -Pattern "^v(\d{8})" | Select-Object -First 1
if (-not $match) {
    Write-Error "Could not parse version from NEWS"
    exit 1
}
$raw = $match.Matches[0].Groups[1].Value   # e.g. "20260407"
$yy    = [int]$raw.Substring(2, 2)        # 26  (WiX major must be < 256)
$month = [int]$raw.Substring(4, 2)        # 4
$day   = [int]$raw.Substring(6, 2)        # 7
$WixVersion = "$yy.$month.$day.0"         # "26.4.7.0"

Write-Host "==> Version from NEWS: $raw  ->  WiX: $WixVersion"

# ---------------------------------------------------------------------------
# Step 1: Build EXE with PyInstaller
# ---------------------------------------------------------------------------
Write-Host "==> Building EXE with PyInstaller..."
Push-Location $Root
python.exe -m PyInstaller build\windows.spec
Pop-Location

# ---------------------------------------------------------------------------
# Step 2: Compile WiX source
# ---------------------------------------------------------------------------
Write-Host "==> Running candle..."
$wxsFile  = Join-Path $Root "build\installer.wxs"
$wixObj   = Join-Path $Root "build\installer.wixobj"
& $candle $wxsFile "-dVersion=$WixVersion" -o $wixObj

# ---------------------------------------------------------------------------
# Step 3: Link into MSI
# ---------------------------------------------------------------------------
Write-Host "==> Running light..."
$msiOut = Join-Path $Root "dist\mp3-archive.msi"
New-Item -ItemType Directory -Force -Path (Join-Path $Root "dist") | Out-Null
& $light $wixObj -ext WixUIExtension -o $msiOut

Write-Host ""
Write-Host "Done: $msiOut"
