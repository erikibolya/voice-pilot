<#
    Příprava prostředí po instalaci.

    Volá ji instalátor po zkopírování souborů. Vytvoří virtuální prostředí
    a doinstaluje závislosti. Vše se loguje do install.log vedle aplikace.

    Pozor na `$ErrorActionPreference`: v PowerShellu 5.1 shodí "Stop"
    celý skript, jakmile nativní příkaz (pip) napíše cokoli na stderr.
    Proto "Continue" a explicitní kontrola $LASTEXITCODE.
#>

param(
    [string]$InstallDir = $PSScriptRoot
)

$ErrorActionPreference = "Continue"
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

# --- 1. Python ---------------------------------------------------------------
$python = $null
foreach ($k in @(@{Exe = "py"; Args = @("-3")}, @{Exe = "python"; Args = @()})) {
    if (-not (Get-Command $k.Exe -ErrorAction SilentlyContinue)) { continue }
    $v = & $k.Exe @($k.Args + @("-c", "import sys;print(sys.version_info[0]*100+sys.version_info[1])")) 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $v) { continue }
    if ([int]("$v".Trim()) -ge 310) {
        $python = $k
        Zapis "Python nalezen: $($k.Exe)"
        break
    }
}

if (-not $python) {
    Selhalo "Python 3.10+ nebyl nalezen. Nainstaluj ho z https://www.python.org/downloads/windows/ a spust instalaci znovu."
}

# --- 2. virtuální prostředí --------------------------------------------------
$venv = Join-Path $InstallDir ".venv"
$venvPython = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Zapis "Vytvářím virtuální prostředí…"
    $kod = Spust $python.Exe ($python.Args + @("-m", "venv", $venv))
    if ($kod -ne 0) { Selhalo "venv se nepodařilo vytvořit (kód $kod)" }
}
Zapis "Virtuální prostředí připraveno."

# --- 3. balíčky --------------------------------------------------------------
Zapis "Instaluji závislosti…"
$kod = Spust $venvPython @("-m", "pip", "install", "--upgrade", "pip", "--quiet", "--disable-pip-version-check")
if ($kod -ne 0) { Selhalo "pip se nepodařilo aktualizovat (kód $kod)" }

$requirements = Join-Path $InstallDir "requirements.txt"
$kod = Spust $venvPython @("-m", "pip", "install", "-r", $requirements, "--quiet", "--disable-pip-version-check")
if ($kod -ne 0) { Selhalo "balíčky se nepodařilo nainstalovat (kód $kod)" }
Zapis "Závislosti nainstalovány."

# --- 4. CUDA (nepovinné) -----------------------------------------------------
$maNvidia = $false
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
    & nvidia-smi --query-gpu=name --format=csv,noheader 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $maNvidia = $true }
}

if ($maNvidia) {
    Zapis "NVIDIA GPU nalezena, instaluji CUDA knihovny…"
    $kod = Spust $venvPython @("-m", "pip", "install", "nvidia-cublas-cu12", "nvidia-cudnn-cu12", "--quiet", "--disable-pip-version-check")
    if ($kod -ne 0) {
        Zapis "CUDA knihovny se nepodařilo nainstalovat (kód $kod) - přepis poběží na CPU."
    } else {
        Zapis "CUDA knihovny nainstalovány."
    }
} else {
    Zapis "NVIDIA GPU nenalezena - přepis poběží na CPU."
}

# --- 5. kontrola -------------------------------------------------------------
Zapis "Kontroluji instalaci…"
$kod = Spust $venvPython @("-c", "import faster_whisper, edge_tts, sounddevice, mss, uiautomation, pynput, httpx, PySide6")
if ($kod -ne 0) { Selhalo "kontrolní import selhal (kód $kod)" }

Zapis "Hotovo."
exit 0
