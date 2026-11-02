<#
    Sestaví instalátor do dist\voice-pilot-<verze>-setup.exe.

    Použití:
        powershell -ExecutionPolicy Bypass -File tools\build_installer.ps1
        powershell ... -Version 0.3.0        # přebít verzi
#>

param(
    [string]$Version = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root

function Krok($text) { Write-Host "`n== $text" -ForegroundColor Cyan }
function Hotovo($text) { Write-Host "   $text" -ForegroundColor Green }

try {
    # --- verze z jednoho místa -------------------------------------------
    if (-not $Version) {
        $init = Get-Content "pilot\__init__.py" -Raw
        if ($init -match '__version__\s*=\s*"([^"]+)"') {
            $Version = $Matches[1]
        } else {
            throw "v pilot\__init__.py chybí __version__"
        }
    }
    $Version = $Version.TrimStart("v")
    Krok "Verze: $Version"

    # --- ikona ------------------------------------------------------------
    Krok "Generuji ikonu"
    $python = ".venv\Scripts\python.exe"
    if (-not (Test-Path $python)) { $python = "python" }
    & $python "tools\make_icon.py"
    if ($LASTEXITCODE -ne 0) { throw "ikona se nevygenerovala" }

    # --- Inno Setup -------------------------------------------------------
    Krok "Hledám Inno Setup"
    $iscc = $null
    foreach ($candidate in @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )) {
        if (Test-Path $candidate) { $iscc = $candidate; break }
    }
    if (-not $iscc) {
        throw "Inno Setup nenalezen. Nainstaluj ho: winget install JRSoftware.InnoSetup"
    }
    Hotovo $iscc

    # --- sestavení --------------------------------------------------------
    Krok "Sestavuji instalátor"
    New-Item -ItemType Directory -Force -Path "dist" | Out-Null

    & $iscc "/DVersion=$Version" "installer\voice-pilot.iss"
    if ($LASTEXITCODE -ne 0) { throw "ISCC selhal (kód $LASTEXITCODE)" }

    $setup = Get-ChildItem "dist\voice-pilot-*-setup.exe" |
             Sort-Object LastWriteTime -Descending | Select-Object -First 1

    if (-not $setup) { throw "instalátor se nevytvořil" }

    $mb = [math]::Round($setup.Length / 1MB, 1)
    Write-Host ""
    Write-Host "  Hotovo: $($setup.FullName) ($mb MB)" -ForegroundColor Green
}
finally {
    Pop-Location
}
