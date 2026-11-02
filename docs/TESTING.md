# Testovací inventář

Každá funkce, kterou uživatel pozná, má tady řádek a test, který ji projde
skutečnou cestou — ne jen zavoláním vnitřní funkce.

Puštění: `.venv\Scripts\python.exe -m pytest -q`
Rychlé (bez modelu a sítě): `.venv\Scripts\python.exe -m pytest -q -m "not slow"`

## Funkce → test

| Funkce (co uživatel pozná) | Test | Poznámka |
|---|---|---|
| Nastavení se uloží a přečte | `test_config_se_ulozi_a_nacte` | `config.json` |
| Neznámý klíč v configu neshodí start | `test_neznamy_klic_v_configu_neshodi_nacteni` | dopředná kompatibilita |
| Asistent pozná aktivní okno | `test_snapshot_precte_aktivni_okno` | UI Automation |
| Prvky mají použitelnou geometrii | `test_prvky_maji_rozumnou_geometrii` | regrese: prázdné názvy |
| Popis obrazovky obsahuje název okna | `test_render_obsahuje_nazev_okna` | to, co jde do modelu |
| Prvek jde najít podle čísla | `test_by_index_najde_prvek` | základ pro klikání |
| Screenshot se uloží | `test_screenshot_se_ulozi` | PNG > 10 kB |
| Hlas vyrobí zvuk | `test_edge_vyrobi_zvuk` | edge-tts |
| **Přehrání zvládne cestu s diakritikou** | `test_prehravac_zvlada_cestu_s_diakritikou` | regrese: `Výchozí projekt` v cestě |
| Whisper přepíše češtinu | `test_whisper_prepise_cestinu` | TTS→STT, shoda ≥ 80 % |
| Ticho se zahodí | `test_ticho_se_zahodi` | prázdná nahrávka |
| Ořez ticha na okrajích | `test_trim_silence_orizne_okraje` | jednotka |
| Srovnání hlasitosti z tichého mikrofonu | `test_normalize_srovna_tichy_mikrofon` | jednotka |
| Srovnání hlasitosti nerozbije ticho | `test_normalize_nedela_nic_s_tisem` | jednotka |
| Model odpoví česky | `test_model_odpovi_cesky` | OpenCode API |
| Kontrola mozku při startu | `test_preflight_najde_bezici_opencode` | `/api/info` |
| Srozumitelná hláška, když služba neběží | `test_preflight_hlasi_kdyz_sluzba_nebezi` | distribuce |
| Srozumitelná hláška, když chybí přihlášení | `test_preflight_hlasi_chybejici_prihlaseni` | distribuce |
| **Celé kolo: otázka → odpověď** | `test_cely_kolo_od_otazky_k_odpovedi` | `Pilot.handle` se skutečným modelem |
| Paměť předchozí věty | `test_pilot_si_pamatuje_predchozi_vetu` | historie v promptu |

## Co testy záměrně nepokrývají

- **Stisk F9.** Nedá se zautomatizovat: pynput v `GlobalHotKeys` ignoruje
  syntetické klávesy (`if not injected`), aby cizí aplikace nemohly spustit
  tvůj hotkey. To je správně, ale znamená to, že klávesu musí zmáčknout
  člověk. Zbytek řetězu pokrývá `live_check.py`.
- **Skutečný mikrofon.** `live_check.py` ho nahraje a přepíše, ale potřebuje,
  aby někdo mluvil.
- **Kvalita české výslovnosti.** Subjektivní, ověřuje se poslechem
  (`run.py --say "..."`).

## Živá kontrola

```bash
.venv\Scripts\python.exe live_check.py --seconds 5
```

Projde mikrofon → Whisper → UI Automation → model → reproduktory a vypíše
čas každého kroku. Můžeš mluvit, nebo poslat ticho přes `--ticho`.

## Ruční kontrolní seznam před používáním

1. `run.py --devices` — mikrofon je v seznamu a je označený `*`.
2. `run.py --mic` — přepis odpovídá tomu, co jsi řekl.
3. `run.py --say "test"` — ozve se český hlas.
4. `run.py --look` — popis sedí na to, co máš na obrazovce.
5. `run.py` — F9 nahraje, F9 odešle, odpověď se ozve.
