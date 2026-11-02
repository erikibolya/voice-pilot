<#
    Připraví vše, co instalátor přibalí: Python a balíčky jako kola (wheels).

    Díky tomu se instalace obejde bez internetu a bez Pythonu v systému.

    Použití:
        powershell -ExecutionPolicy Bypass -File tools\vendor_deps.ps1
        powershell ... -WithCuda      # přibalí i CUDA (~1,3 GB)
#>

param(
    [switch]$WithCuda,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root

$vendor = Join-Path $root "installer\vendor"
$pythonDir = Join-Path $vendor "python"
$wheelsDir = Join-Path $vendor "wheels"
$nupkg = Join-Path $vendor "python.nupkg"

function Krok($text) { Write-Host "`n== $text" -ForegroundColor Cyan }
function Hotovo($text) { Write-Host "   $text" -ForegroundColor Green }

try {
    New-Item -ItemType Directory -Force -Path $vendor | Out-Null

    # --- Python ---------------------------------------------------------
    Krok "Python pro přibalení"
    $pythonExe = Join-Path $pythonDir "python.exe"

    if ((Test-Path $pythonExe) -and -not $Force) {
        Hotovo "už je připravený"
    } else {
        if (-not (Test-Path $nupkg) -or $Force) {
            $url = "https://www.nuget.org/api/v2/package/python/3.11.9"
            Write-Host "   stahuji $url"
            Invoke-WebRequest -Uri $url -OutFile $nupkg -UseBasicParsing
        }

        Add-Type -AssemblyName System.IO.Compression.FileSystem
        if (Test-Path $pythonDir) { Remove-Item $pythonDir -Recurse -Force }
        New-Item -ItemType Directory -Force -Path $pythonDir | Out-Null

        $zip = [System.IO.Compression.ZipFile]::OpenRead($nupkg)
        try {
            foreach ($e in $zip.Entries) {
                if ($e.FullName -like "tools/*" -and $e.Name -ne "") {
                    $rel = $e.FullName.Substring(6)
                    $target = Join-Path $pythonDir $rel
                    New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null
                    [System.IO.Compression.ZipFileExtensions]::ExtractToFile($e, $target, $true)
                }
            }
        } finally {
            $zip.Dispose()
        }
        Hotovo "rozbaleno"
    }

    $verze = & $pythonExe --version 2>&1
    Hotovo $verze

    # --- kola -----------------------------------------------------------
    Krok "Balíčky jako kola"
    if ((Test-Path $wheelsDir) -and -not $Force) {
        Get-ChildItem $wheelsDir -Filter *.whl | Remove-Item -Force
    } else {
        New-Item -ItemType Directory -Force -Path $wheelsDir | Out-Null
    }

    & $pythonExe -m pip download -r requirements.txt -d $wheelsDir `
        --only-binary=:all: --quiet --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) { throw "balíčky se nepodařilo stáhnout" }

    if ($WithCuda) {
        Write-Host "   přibírám CUDA (1,3 GB)…"
        & $pythonExe -m pip download nvidia-cublas-cu12 nvidia-cudnn-cu12 -d $wheelsDir `
            --only-binary=:all: --quiet --disable-pip-version-check
        if ($LASTEXITCODE -ne 0) { throw "CUDA se nepodařilo stáhnout" }
    }

    $velikost = (Get-ChildItem $wheelsDir -Filter *.whl | Measure-Object -Property Length -Sum).Sum
    Hotovo ("{0} kol, {1:N0} MB" -f (Get-ChildItem $wheelsDir -Filter *.whl).Count, ($velikost / 1MB))

    Write-Host ""
    Write-Host "  Připraveno pro build_installer.ps1" -ForegroundColor Green
}
finally {
    Pop-Location
}
