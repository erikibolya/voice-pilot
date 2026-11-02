# voice-pilot

Hlasový asistent pro Windows, který se dívá na obrazovku a mluví česky.

Zatím umí **koukat a mluvit** — přečte, co máš na obrazovce, a odpoví nahlas.
Klikání myší je připravené na další krok (viz [Co dál](#co-dál)).

```
  ty: "Co mám na obrazovce?"
  pilot: "Máš aktivní Facebook v Chromu a na stránce je vidět potvrzení
          Zpráva je odeslaná. Mezi dalšími okny máš Messenger a Spotify."
```

## Jak to funguje

```
mikrofon → Whisper (GPU) → text
                             ↓
                   UI Automation → popis obrazovky
                             ↓
                        OpenCode → odpověď
                             ↓
                     edge-tts → reproduktory
```

**Mozek není v projektu.** Volá se lokálně běžící OpenCode služba
(`127.0.0.1:28894`), takže se používají tvoje stávající přihlášení k modelům.
Žádný API klíč se v projektu neukládá.

**Oči nejsou screenshot.** Windows UI Automation dá přesné názvy tlačítek,
polí a textů i s jejich souřadnicemi — v češtině a bez OCR. Každý prvek
dostane číslo, takže v dalším kroku půjde říct „klikni na `[7]`“ a asistent
nemůže kliknout na něco, co mu neukážeme.

## Požadavky

- Windows 10/11, Python 3.11+
- Běžící OpenCode (desktopová aplikace) — dodává model
- Mikrofon a reproduktory
- Internet pro hlas (edge-tts); přepis řeči jde celý lokálně

## Instalace

### Pro běžné použití (jeden dvojklik)

Stačí `install.bat`. Vytvoří si vlastní Python prostředí, nainstaluje
závislosti a udělá ikonu na ploše a v nabídce Start.

```
install.bat
```

Volitelné přepínače (přes `powershell -File install.ps1 ...`):

| Přepínač | Význam |
|---|---|
| `-InstallDir "D:\Apps\VoicePilot"` | jinam než do `%LOCALAPPDATA%\VoicePilot` |
| `-SkipModel` | nestahovat model (3 GB) při instalaci |
| `-SkipCuda` | neinstalovat CUDA knihovny (pojede na CPU) |
| `-NoShortcut` | nedělat ikonu na ploše |

Instalace **nepotřebuje správce** a nic nemění v systému — všechno skončí
v jednom adresáři. Odinstalace = smazat ten adresář a dvě zástupce.

**Co instalace neumí zařídit:** OpenCode. Aplikace ho potřebuje jako mozek;
bez něj se spustí, ale hned řekne, že nemá čím myslet.

### Pro vývoj

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
```

CUDA balíčky jsou potřeba, aby Whisper běžel na grafice. Bez nich se
aplikace přepne na CPU a bude ~6× pomalejší (ale funguje).

První spuštění si stáhne model Whisperu `large-v3` (~3 GB).

## Použití

```bash
.venv\Scripts\python.exe run.py
```

Zmáčkni **F9**, mluv, znovu **F9**. Ukončení `Ctrl+C`.

Další režimy:

| Příkaz | Co dělá |
|---|---|
| `run.py` | hlavní smyčka na klávesu F9 |
| `run.py --text` | bez mikrofonu, piš otázky do terminálu |
| `run.py --look` | jednorázově popíše obrazovku |
| `run.py --say "text"` | vyzkouší hlas |
| `run.py --mic` | nahraje jednu větu a vypíše přepis |
| `run.py --devices` | seznam mikrofonů |
| `run.py --setup-piper` | stáhne offline hlas pro případ výpadku netu |
| `run.py --model deepseek-v4-pro` | přepne model |

## Nastavení

`config.json` se vytvoří při prvním spuštění:

| Klíč | Význam |
|---|---|
| `model_id`, `provider_id` | který model odpovídá |
| `whisper_model` | `large-v3` (nejlepší čeština), `medium`, `small` |
| `whisper_device` | `cuda` nebo `cpu` |
| `tts_engine` | `auto` (edge → piper), `edge`, `piper` |
| `voice` | `cs-CZ-VlastaNeural` (žena), `cs-CZ-AntoninNeural` (muž) |
| `hotkey` | klávesa pro nahrávání, výchozí `f9` |
| `max_elements` | kolik prvků okna se posílá modelu |

## Testy

```bash
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m pytest -q -m "not slow"   # bez modelu a sítě
```

Přehled toho, co je čím pokryté, je v [docs/TESTING.md](docs/TESTING.md).
Samostatná kontrola audio řetězu (vyrobí nahrávku a nechá ji přepsat):

```bash
.venv\Scripts\python.exe check_audio.py
```

## Známá omezení

- **Prohlížeče** vydají jen dokument a hlavní odkazy, ne celou stránku.
  Chrome má strom přístupnosti líný; plnohodnotné čtení stránek přijde
  přes DevTools Protocol v dalším kroku.
- **Offline hlas** (Piper) není nainstalovaný, dokud nespustíš `--setup-piper`.
  Bez něj je potřeba internet.
- Cesta k projektu **má českou diakritiku**. Kód si s tím poradí (soubory
  se čtou po bajtech), ale kdyby přibyla další knihovna v C, může to bolet.
- Výchozí `deepseek-flash` je rychlý, ale občas si vymyslí detail. Na
  přesnější popis přepni `--model deepseek-v4-pro`.

## Co dál

**Milník 2 — klikání s potvrzením.** Model dostane seznam prvků s čísly
a vrací strukturované akce (`klikni [7]`, `napiš "text"`). Platí tři pravidla:

1. Klikat jde **jen na prvky, které jsme ukázali** — ne na souřadnice.
2. Každý klik se **ohlásí nahlas** a čeká na potvrzení (Enter = ano, Esc = ne).
3. Nevratné akce (smazat, odeslat, zaplatit) mají varování navíc.

## Bezpečnost

Aplikace zatím **nic nemění** — jen čte obrazovku a mluví. Až přibude
klikání, bude každá akce potvrzená. Agent, který ovládá myš, je nejrizikovější
věc na stroji: text na obrazovce může obsahovat pokyn, který model poslechne
místo tebe. Proto se akce omezují na očíslované prvky a potvrzují se.
