# voice-pilot

Hlasový asistent pro Windows. Mluvíš česky, on se podívá na obrazovku a odpoví nahlas.

![voice-pilot, tmavý režim](docs/screenshot-dark.png)

Zatím **kouká a mluví** — přečte okna, tlačítka a texty na obrazovce a řekne, co vidí.
Klikání myší je připravené na další krok (viz [Co dál](#co-dál)).

## Jak to funguje

```
mikrofon → Whisper na GPU → text
                             ↓
                UI Automation → popis obrazovky
                             ↓
                       OpenCode → odpověď
                             ↓
                     edge-tts → reproduktory
```

**Mozek není v projektu.** Volá se lokálně běžící OpenCode služba
(`127.0.0.1:28894`), takže se používají tvoje stávající přihlášení k modelům.
Žádný API klíč se neukládá.

**Oči nejsou screenshot.** Windows UI Automation dá přesné názvy tlačítek,
polí a textů i s jejich souřadnicemi — v češtině a bez OCR. Každý prvek
dostane číslo, takže v dalším kroku půjde říct „klikni na `[7]`“ a asistent
nemůže kliknout na něco, co mu neukážeme.

## Instalace

### Instalátor

Stáhni `voice-pilot-<verze>-setup.exe` z [Releases](../../releases) a spusť ho.
Nepotřebuje správce, instaluje se do `%LOCALAPPDATA%\VoicePilot`.

Instalátor po zkopírování souborů spustí přípravu prostředí: vytvoří virtuální
Python prostředí a nainstaluje závislosti. Trvá to asi minutu a půl a potřebuje
internet. Průběh se loguje do `install.log` v instalační složce.

**Vyžaduje Python 3.10+** nainstalovaný v systému ([python.org](https://www.python.org/downloads/windows/),
zaškrtni „Add python.exe to PATH“).

### Ze zdrojů

```bash
git clone https://github.com/erikibolya/voice-pilot.git
cd voice-pilot
install.bat
```

### Pro vývoj

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
```

CUDA balíčky jsou potřeba, aby Whisper běžel na grafice. Bez nich se aplikace
přepne na CPU a bude ~6× pomalejší (ale funguje). Model `large-v3` (~3 GB) se
stáhne při prvním použití.

## Ovládání

Aplikace běží v okně i v systémové liště.

| | |
|---|---|
| **F9** | začne nahrávat; druhá F9 nahrávku ukončí a odpoví |
| **klik na mikrofon** | totéž co F9 |
| **psaný dotaz** | napiš do pole dole a zmáčkni Enter |
| **zavření okna** | skryje do lišty, aplikace běží dál |
| **dvojklik na ikonu** | vrátí okno |
| **Ukončit v liště** | skutečné ukončení |

Pípnutí označuje začátek a konec nahrávání, takže se nemusíš dívat do okna.

## Nastavení

V okně přes ozubené kolo: klávesa, hlas, model a velikost modelu pro přepis.
Ukládá se do `config.json` vedle aplikace.

| Klíč | Význam |
|---|---|
| `hotkey` | klávesa pro nahrávání, výchozí `f9` |
| `voice` | `cs-CZ-VlastaNeural` (žena) nebo `cs-CZ-AntoninNeural` (muž) |
| `model_id` | `deepseek-flash` (rychlý) nebo `deepseek-v4-pro` (přesnější) |
| `whisper_model` | `large-v3`, `medium`, `small` |
| `tts_engine` | `auto` (edge → piper), `edge`, `piper` |

## Aktualizace

Aplikace se při startu zeptá GitHubu na nejnovější vydání. Když je novější,
v hlavičce se objeví odznak a v patičce tlačítko, které instalátor stáhne
a spustí. Stav se dá ověřit i z terminálu:

```bash
run.py --check-update
```

Vydání vzniká pushnutím tagu `v*.*.*` — GitHub Actions sestaví instalátor
a přiloží ho k vydání.

## Testy

```bash
.venv\Scripts\python.exe -m pytest -q                      # vše
.venv\Scripts\python.exe -m pytest -q -m "not slow"        # bez modelu
.venv\Scripts\python.exe -m pytest -q -m "not slow and not desktop"   # co běží v CI
```

Přehled, co je čím pokryté, je v [docs/TESTING.md](docs/TESTING.md).

## Sestavení instalátoru

```bash
powershell -ExecutionPolicy Bypass -File tools\build_installer.ps1
```

Výsledek je `dist\voice-pilot-<verze>-setup.exe`. Potřebuje
[Inno Setup 6](https://jrsoftware.org/isinfo.php) (`winget install JRSoftware.InnoSetup`).

## Známá omezení

- **Prohlížeče** vydají jen dokument a hlavní odkazy, ne celý obsah stránky.
  Chrome má strom přístupnosti líný; plnohodnotné čtení přijde přes DevTools
  Protocol v dalším kroku.
- **Offline hlas** (Piper) není nainstalovaný, dokud nespustíš `--setup-piper`.
  Bez něj je potřeba internet.
- **Python musí být v systému.** Instalátor ho nebalí; potřebuje 3.10+ na PATH.
- Výchozí `deepseek-flash` je rychlý, ale občas si vymyslí detail.

## Co dál

**Milník 2 — klikání s potvrzením.** Model dostane seznam prvků s čísly
a vrací strukturované akce (`klikni [7]`, `napiš "text"`). Tři pravidla:

1. Klikat jde **jen na prvky, které jsme ukázali** — ne na souřadnice.
2. Každý klik se **ohlásí nahlas** a čeká na potvrzení (Enter = ano, Esc = ne).
3. Nevratné akce (smazat, odeslat, zaplatit) mají varování navíc.

## Bezpečnost

Aplikace zatím **nic nemění** — jen čte obrazovku a mluví. Až přibude
klikání, bude každá akce potvrzená. Agent, který ovládá myš, je nejrizikovější
věc na stroji: text na obrazovce může obsahovat pokyn, který model poslechne
místo tebe.

Globální klávesa záměrně ignoruje syntetické stisky (`pynput` filtruje
injektované události), takže F9 nemůže spustit jiná aplikace.

## Poděkování

Vizuální styl vychází z [RedLine](https://github.com/erikibolya/redline) —
stejné barevné tokeny, rádiusy a typografie. Schopnosti dodávají
[faster-whisper](https://github.com/SYSTRAN/faster-whisper),
[edge-tts](https://github.com/rany2/edge-tts) a
[UI Automation](https://github.com/yinkaisheng/Python-UIAutomation-for-Windows).

## Licence

MIT — viz [LICENSE](LICENSE).
