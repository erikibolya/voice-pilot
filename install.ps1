<#
    voice-pilot - instalace na Windows.

    Spusteni: dvojklik na install.bat
    Moznosti:
        -InstallDir "D:\Apps\VoicePilot"   jinam
        -SkipModel                         nestahovat Whisper model (3 GB)
        -SkipCuda                          neinstalovat CUDA knihovny
        -NoShortcut                        nedelat ikonu na plochu

    Instalace nepotrebuje spravce a nic nemeni v systemu - vsechno
    skonci v jednom adresari, ktery se da smazat.
#>

param(
    [string]$InstallDir = "$env:LOCALAPPDATA\VoicePilot",
    [switch]$SkipModel,
    [switch]$SkipCuda,
    [switch]$NoShortcut
)

$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

function Krok($cislo, $text) {
    Write-Host ""
    Write-Host "[$cislo] $text" -ForegroundColor Cyan
}
function Dobry($text) { Write-Host "      $text" -ForegroundColor Green }
function Pozor($text) { Write-Host "      $text" -ForegroundColor Yellow }
function Selhalo($text) {
    Write-Host ""
    Write-Host "  CHYBA: $text" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "  voice-pilot - instalace" -ForegroundColor White
Write-Host "  -----------------------" -ForegroundColor DarkGray

# ---------------------------------------------------------------- 1. Python

Krok 1 "Hledam Python 3.10 nebo novejsi"

function Najdi-Python {
    $kandidati = @(
        @{ Exe = "py";      Args = @("-3") },
        @{ Exe = "python";  Args = @() },
        @{ Exe = "python3"; Args = @() }
    )
    foreach ($k in $kandidati) {
        if (-not (Get-Command $k.Exe -ErrorAction SilentlyContinue)) { continue }
        try {
            $v = & $k.Exe @($k.Args + @("-c", "import sys;print(sys.version_info[0]*100+sys.version_info[1])")) 2>$null
            if ($LASTEXITCODE -ne 0 -or -not $v) { continue }
            $cislo = [int]("$v".Trim())
            if ($cislo -ge 310) {
                return @{ Exe = $k.Exe; Args = $k.Args; Verze = "$([math]::Floor($cislo/100)).$($cislo % 100)" }
            }
        } catch { continue }
    }
    return $null
}

$py = Najdi-Python
if (-not $py) {
    Selhalo @"
Nenasel jsem Python 3.10+.
      Stahni ho z https://www.python.org/downloads/windows/
      Pri instalaci zaskrtni "Add python.exe to PATH" a spust instalaci znovu.
"@
}
Dobry "Python $($py.Verze) nalezen"

# ------------------------------------------------------------ 2. kopirovani

Krok 2 "Kopiruji aplikaci do $InstallDir"

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
foreach ($polozka in @("pilot", "run.py", "requirements.txt", "README.md", "launch.cmd")) {
    $zdroj = Join-Path $PSScriptRoot $polozka
    if (Test-Path $zdroj) {
        Copy-Item -Path $zdroj -Destination $InstallDir -Recurse -Force
    }
}
Dobry "zkopirovano"

if (Test-Path (Join-Path $InstallDir "config.json")) {
    Dobry "tvuj config.json zustava nedotceny"
}

# ----------------------------------------------------------------- 3. venv

Krok 3 "Vytvarim virtualni prostredi"

$venv = Join-Path $InstallDir ".venv"
$pythonV = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path $pythonV)) {
    & $py.Exe @($py.Args + @("-m", "venv", $venv))
    if ($LASTEXITCODE -ne 0) { Selhalo "virtualni prostredi se nepodarilo vytvorit" }
    Dobry "vytvoreno"
} else {
    Dobry "uz existuje, pouziji ho"
}

# -------------------------------------------------------------- 4. balicky

Krok 4 "Instaluji zavislosti (muze trvat nekolik minut)"

& $pythonV -m pip install --upgrade pip --quiet --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { Selhalo "pip se nepodarilo aktualizovat" }

$pozadavky = Join-Path $InstallDir "requirements.txt"
& $pythonV -m pip install -r $pozadavky --quiet --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { Selhalo "balicky se nepodarilo nainstalovat" }
Dobry "hotovo"

# ---------------------------------------------------------------- 5. CUDA

Krok 5 "CUDA knihovny pro beh na grafice"

$maNvidia = $false
try {
    if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
        & nvidia-smi --query-gpu=name --format=csv,noheader 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { $maNvidia = $true }
    }
} catch { }

if ($SkipCuda) {
    Pozor "preskoceno (-SkipCuda)"
} elseif ($maNvidia) {
    & $pythonV -m pip install nvidia-cublas-cu12 nvidia-cudnn-cu12 --quiet --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) {
        Pozor "CUDA knihovny se nepodarilo nainstalovat - pojede se na CPU"
    } else {
        Dobry "GPU detekovana, CUDA nainstalovana"
    }
} else {
    Pozor "NVIDIA GPU nenalezena - prepis pobezi na CPU (pomaleji)"
}

# --------------------------------------------------------------- 6. model

Krok 6 "Model pro prepis reci"

if ($SkipModel) {
    Pozor "preskoceno (-SkipModel) - stahne se pri prvnim spusteni"
} else {
    Pozor "stahuji Whisper large-v3, asi 3 GB. Muze to trvat i deset minut."
    & $pythonV -c "from faster_whisper.utils import download_model; print('   ->', download_model('large-v3'))"
    if ($LASTEXITCODE -ne 0) {
        Pozor "model se nestahl - zkusi to znovu pri prvnim spusteni"
    } else {
        Dobry "model pripraven"
    }
}

# ----------------------------------------------------------- 7. zastupci

Krok 7 "Zastupci"

$shell = New-Object -ComObject WScript.Shell
$cil = Join-Path $InstallDir "launch.cmd"

function Udelej-Zastupce($cesta, $popis) {
    $zkratka = $shell.CreateShortcut($cesta)
    $zkratka.TargetPath = $cil
    $zkratka.WorkingDirectory = $InstallDir
    $zkratka.IconLocation = "$env:SystemRoot\System32\shell32.dll,138"
    $zkratka.Description = $popis
    $zkratka.Save()
}

try {
    if ($NoShortcut) {
        Pozor "preskoceno (-NoShortcut)"
    } else {
        $startMenu = Join-Path ([Environment]::GetFolderPath("Programs")) "voice-pilot.lnk"
        Udelej-Zastupce $startMenu "Hlasovy asistent pro Windows"
        Dobry "v nabidce Start"
    }
} catch {
    Pozor "zastupce v nabidce Start se nepovedl: $($_.Exception.Message)"
}

if (-not $NoShortcut) {
    try {
        $plocha = Join-Path ([Environment]::GetFolderPath("Desktop")) "voice-pilot.lnk"
        Udelej-Zastupce $plocha "Hlasovy asistent pro Windows"
        Dobry "na plose"
    } catch {
        Pozor "zastupce na plose se nepovedl: $($_.Exception.Message)"
    }
}

# ------------------------------------------------------------- 8. kontrola

Krok 8 "Kontrolni spusteni"

& $pythonV -c "import faster_whisper, edge_tts, sounddevice, mss, uiautomation, pynput, httpx; print('      vsechny balicky nacteny')"
if ($LASTEXITCODE -ne 0) { Selhalo "neco se nainstalovalo spatne" }

Write-Host ""
Write-Host "  Instalace dokoncena." -ForegroundColor Green
Write-Host ""
Write-Host "  Spusteni:  ikona 'voice-pilot' na plose nebo v nabidce Start"
Write-Host "  Ovladani:  F9 zacne nahravat, druha F9 ukonci a odpovi"
Write-Host ""
Write-Host "  Dulezite: aplikace potrebuje bezici OpenCode." -ForegroundColor Yellow
Write-Host "            Bez nej nema cim myslet a hned to rekne."
Write-Host ""
Write-Host "  Odinstalace: smaz slozku $InstallDir" -ForegroundColor DarkGray
Write-Host "               a oba zastupce." -ForegroundColor DarkGray
