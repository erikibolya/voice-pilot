# voice-pilot bridge (rozšíření do Chrome)

Nechá voice-pilot číst a ovládat stránky v prohlížeči. Bez něj vidí
UI Automation z Chrome jen panel nástrojů, ne obsah stránky.

## Instalace (vývoj)

1. Otevři `chrome://extensions`
2. Zapni **Developer mode** (vpravo nahoře)
3. **Load unpacked** → vyber tuto složku (`extension/`)
4. Zkontroluj, že voice-pilot běží — rozšíření se k němu připojí samo

Stav poznáš podle service workeru: v `chrome://extensions` klikni na
„service worker" a v konzoli by mělo být vidět připojení.

## Jak to funguje

```
Chrome (rozšíření)  ──WebSocket──▶  127.0.0.1:8791  (voice-pilot)
```

Prohlížeč nemůže naslouchat na portu, takže spojení vždy iniciuje on.
Když spadne, zkusí to znovu za 3 sekundy.

Token v `hello` brání tomu, aby se připojil jiný program na stroji
a ovládal prohlížeč jménem uživatele.

## Oprávnění

| Oprávnění | Proč |
|---|---|
| `tabs` | seznam karet a jejich názvy |
| `scripting` | vložení content scriptu do karty |
| `<all_urls>` | ovládání jakékoli stránky, kterou uživatel otevře |

## Co to neumí

Nativní aplikace. Tlačítka Windows, Průzkumník, Office nebo panel úloh
řeší UI Automation v Python aplikaci.
