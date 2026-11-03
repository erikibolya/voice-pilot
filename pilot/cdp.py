"""Ovládání prohlížeče přes DevTools Protocol.

UI Automation z Chrome vydá jen panel nástrojů — obsah stránky ne. Proto
se pro weby připojujeme k Chrome přímo: dostaneme DOM, najdeme prvky podle
textu a klikneme přes prohlížeč.

Chrome musí běžet s `--remote-debugging-port=<port>`. Když ne, `available()`
vrátí False a aplikace funguje dál bez webů.
"""

from __future__ import annotations

import json
import urllib.request

PORT = 9223

SELEKTOR = (
    'a,button,input,textarea,select,[role="button"],[role="link"],'
    '[contenteditable="true"],video'
)

_JS_PRVKY = """
(() => {
  const selektor = %s;
  const out = [];
  let poradi = 0;
  for (const el of document.querySelectorAll(selektor)) {
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) continue;
    const s = getComputedStyle(el);
    if (s.visibility === 'hidden' || s.display === 'none' || s.opacity === '0') continue;
    const text = (el.innerText || el.value || el.getAttribute('aria-label')
                  || el.placeholder || el.title || el.tagName).trim()
                 .replace(/\\s+/g, ' ').slice(0, 70);
    const tag = el.tagName.toLowerCase();
    out.push({ i: poradi, tag: tag, text: text,
               x: Math.round(r.left), y: Math.round(r.top),
               w: Math.round(r.width), h: Math.round(r.height) });
    poradi += 1;
    if (out.length >= 150) break;
  }
  return JSON.stringify(out);
})()
""" % json.dumps(SELEKTOR)


class CdpError(RuntimeError):
    pass


def _http(path: str, timeout: float = 1.5):
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def available() -> bool:
    try:
        _http("/json/version")
        return True
    except Exception:
        return False


def pages() -> list[dict]:
    try:
        targets = _http("/json")
    except Exception:
        return []
    return [
        {"id": t.get("id"), "title": t.get("title", ""), "url": t.get("url", "")}
        for t in targets
        if t.get("type") == "page" and not t.get("url", "").startswith("devtools://")
    ]


class Tab:
    """Jedna karta prohlížeče."""

    def __init__(self, target_id: str):
        import websocket

        zaklad = _http("/json/version")["webSocketDebuggerUrl"].split("/devtools/")[0]
        try:
            self._ws = websocket.create_connection(
                f"{zaklad}/devtools/page/{target_id}",
                timeout=5,
                suppress_origin=True,  # Chrome 111+ jinak spojení odmítne
            )
        except Exception as exc:
            raise CdpError(f"ke kartě se nepodařilo připojit: {exc}") from exc
        self._id = 0

    def close(self) -> None:
        try:
            self._ws.close()
        except Exception:
            pass

    def _call(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        prikaz = {"id": self._id, "method": method}
        if params:
            prikaz["params"] = params
        self._ws.send(json.dumps(prikaz))
        while True:
            data = json.loads(self._ws.recv())
            if data.get("id") != self._id:
                continue
            if "error" in data:
                raise CdpError(data["error"].get("message", "chyba CDP"))
            return data.get("result", {})

    def evaluate(self, vyraz: str):
        vysledek = self._call(
            "Runtime.evaluate",
            {"expression": vyraz, "returnByValue": True, "awaitPromise": True},
        )
        return vysledek.get("result", {}).get("value")

    def elements(self) -> list[dict]:
        hodnota = self.evaluate(_JS_PRVKY)
        try:
            return json.loads(hodnota) if hodnota else []
        except Exception:
            return []

    def click(self, index: int, ocekavany: str = "") -> str:
        """Klikne na index-tý prvek. Ověří text, aby to netrefilo jinam."""
        js = """
        (() => {
          const selektor = %s;
          const prvky = Array.from(document.querySelectorAll(selektor));
          const el = prvky[%d];
          if (!el) return 'CHYBI';
          const r = el.getBoundingClientRect();
          if (r.width < 4 || r.height < 4) return 'CHYBI';
          const text = (el.innerText || el.value || el.getAttribute('aria-label')
                        || el.placeholder || el.title || el.tagName).trim()
                       .replace(/\\s+/g, ' ').slice(0, 70);
          const cekany = %s;
          if (cekany && text.indexOf(cekany) === -1) return 'JINY:' + text;
          el.scrollIntoView({block: 'center'});
          el.focus();
          el.click();
          return 'OK';
        })()
        """ % (json.dumps(SELEKTOR), int(index), json.dumps(ocekavany))

        vysledek = self.evaluate(js)
        if vysledek == "OK":
            return "ok"
        if vysledek == "CHYBI":
            raise CdpError("prvek na stránce už není")
        if isinstance(vysledek, str) and vysledek.startswith("JINY:"):
            raise CdpError(f"na místě je jiný prvek: {vysledek[5:]}")
        return "ok"

    def napis(self, index: int, text: str) -> str:
        """Píše do prvku na stejném indexu, jaký viděl model."""
        js = """
        (() => {
          const el = document.querySelectorAll(%s)[%d];
          if (!el) return 'CHYBI';
          const tag = el.tagName.toLowerCase();
          if (tag !== 'input' && tag !== 'textarea' && !el.isContentEditable) {
            return 'NENI_POLE';
          }
          el.focus();
          if (el.isContentEditable) { el.innerText = %s; }
          else { el.value = %s; }
          el.dispatchEvent(new Event('input', {bubbles: true}));
          el.dispatchEvent(new Event('change', {bubbles: true}));
          return 'OK';
        })()
        """ % (json.dumps(SELEKTOR), int(index), json.dumps(text), json.dumps(text))

        vysledek = self.evaluate(js)
        if vysledek == "CHYBI":
            raise CdpError("prvek na stránce už není")
        if vysledek == "NENI_POLE":
            raise CdpError("do tohohle prvku se psát nedá")
        return "ok"

    def navigate(self, url: str) -> str:
        self._call("Page.navigate", {"url": url})
        return "ok"

    def enter(self) -> str:
        for typ in ("keyDown", "keyUp"):
            self._call(
                "Input.dispatchKeyEvent",
                {"type": typ, "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13},
            )
        return "ok"


def first_page() -> Tab | None:
    vsechny = pages()
    if not vsechny:
        return None
    try:
        return Tab(vsechny[0]["id"])
    except CdpError:
        return None


def tab_for_window(okno_title: str) -> Tab | None:
    """Karta, která patří k aktivnímu oknu prohlížeče.

    Název okna ve Windows je „<titulek stránky> - Google Chrome". Porovnáním
    zabráníme tomu, abychom vzali prvky z jiné karty nebo jiné instance.
    """
    cisty = okno_title.replace(" - Google Chrome", "").replace(" - Chromium", "").strip()
    if not cisty:
        return first_page()

    for stranka in pages():
        titulek = (stranka.get("title") or "").strip()
        if not titulek:
            continue
        if titulek == cisty or cisty.startswith(titulek) or titulek.startswith(cisty):
            try:
                return Tab(stranka["id"])
            except CdpError:
                continue

    return None
