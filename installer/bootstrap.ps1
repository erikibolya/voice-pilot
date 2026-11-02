<#
    Příprava prostředí po instalaci.

    Volá ji instalátor po zkopírování souborů. Python i balíčky už jsou
    přibalené, takže se nic nestahuje — jen se nainstalují z místních kol.
    CUDA knihovny (pro GPU) se stahují až tady a jen když je NVIDIA karta;
    bez nich aplikace funguje, jen pomaleji.

    Pozor na `$ErrorActionPreference`: v PowerShellu 5.1 shodí "Stop"
    celý skript, jakmile nativní příkaz (pip) napíše cokoli na stderr.
#>

param(
    [string]$InstallDir = $PSScriptRoot
)

$ErrorActionPreference = "Continue"
$env:PYTHONNOUSERSITE = "1"
$log = Join-Path $InstallDir "install.log"

function Zapis($text) {
    $line = "$(Get-Date -Format 'HH:mm:ss')  $text"
    Add-Content -Path $log -Value $line -Encoding UTF8
}

function Selhalo($text) {
    Zapis "CHYBA: $text"
    exit 1
}

function Spust($exe, [string[]]$argumenty) {
    & $exe @argumenty *>&1 | Add-Content -Path $log
    return $LASTEXITCODE
}

Set-Content -Path $log -Value "voice-pilot - instalace $(Get-Date)" -Encoding UTF8

# --- 1. přibalený Python ------------------------------------------------
$python = Join-Path $InstallDir "python\python.exe"
if (-not (Test-Path $python)) {
    Selhalo "Přibalený Python chybí ($python). Instalace je poškozená, spusť instalátor znovu."
}
Zapis ("Python: " + (& $python --version 2>&1))

# --- 2. balíčky z místních kol -----------------------------------------
$wheels = Join-Path $InstallDir "wheels"
$requirements = Join-Path $InstallDir "requirements.txt"

if (-not (Test-Path $wheels)) {
    Selhalo "Chybí balíčky ($wheels). Instalace je poškozená, spusť instalátor znovu."
}

Zapis "Instaluji balíčky z přibalených kol…"
$kod = Spust $python @(
    "-m", "pip", "install",
    "--no-index", "--find-links", $wheels,
    "-r", $requirements,
    "--quiet", "--disable-pip-version-check"
)
if ($kod -ne 0) { Selhalo "balíčky se nepodařilo nainstalovat (kód $kod)" }
Zapis "Balíčky nainstalovány."

# --- 3. CUDA (nepovinné, jen s NVIDIA kartou) ---------------------------
$maNvidia = $false
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    & nvidia-smi --query-gpu=name --format=csv,noheader 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $maNvidia = $true }
}

if (-not $maNvidia) {
    Zapis "NVIDIA GPU nenalezena - přepis poběží na CPU (pomaleji)."
} else {
    $cudaVeKolech = Get-ChildItem $wheels -Filter "nvidia_cublas*.whl" -ErrorAction SilentlyContinue
    if ($cudaVeKolech) {
        Zapis "Instaluji CUDA z přibalených kol…"
        $kod = Spust $python @(
            "-m", "pip", "install", "--no-index", "--find-links", $wheels,
            "nvidia-cublas-cu12", "nvidia-cudnn-cu12",
            "--quiet", "--disable-pip-version-check"
        )
    } else {
        Zapis "NVIDIA GPU nalezena, stahuji CUDA knihovny…"
        $kod = Spust $python @(
            "-m", "pip", "install", "nvidia-cublas-cu12", "nvidia-cudnn-cu12",
            "--quiet", "--disable-pip-version-check"
        )
    }

    if ($kod -ne 0) {
        Zapis "CUDA se nepodařilo nainstalovat (kód $kod) - přepis poběží na CPU."
    } else {
        Zapis "CUDA nainstalována, přepis poběží na GPU."
    }
}

# --- 4. kontrola --------------------------------------------------------
Zapis "Kontroluji instalaci…"
$kod = Spust $python @(
    "-c",
    "import faster_whisper, edge_tts, sounddevice, mss, uiautomation, pynput, httpx, PySide6"
)
if ($kod -ne 0) { Selhalo "kontrolní import selhal (kód $kod)" }

# --- 5. úklid -----------------------------------------------------------
# Kola už nejsou potřeba a zabírají 170 MB.
Remove-Item $wheels -Recurse -Force -ErrorAction SilentlyContinue
Zapis "Balíčky po instalaci uklizeny."

Zapis "Hotovo."
exit 0
