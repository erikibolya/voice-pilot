"""Most mezi rozšířením do Chrome a aplikací.

Rozšíření se připojuje k nám na `127.0.0.1:8791` — prohlížeč nemůže
naslouchat na portu, takže iniciátor je vždycky on. My mu posíláme příkazy
a čekáme na odpověď.

Token v `hello` není bezpečnostní divadlo: bez něj by se mohl připojit
jakýkoli jiný program na stroji a ovládat prohlížeč jménem uživatele.
"""

from __future__ import annotations

import itertools
import json
import threading

PORT = 8791
TOKEN = "voice-pilot"


class BridgeError(RuntimeError):
    pass


class Bridge:
    def __init__(self, port: int = PORT, token: str = TOKEN):
        self.port = port
        self.token = token

        self._ws = None
        self._zamek = threading.RLock()
        self._cekajici: dict[int, dict] = {}
        self._cisla = itertools.count(1)
        self._pripraveno = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------ život

    @property
    def connected(self) -> bool:
        return self._ws is not None

    def start(self) -> bool:
        if self._thread is not None:
            return True
        self._thread = threading.Thread(target=self._bez, daemon=True)
        self._thread.start()
        self._pripraveno.wait(3.0)
        return True

    def _bez(self) -> None:
        from websockets.sync.server import serve

        try:
            server = serve(self._obsluha, "127.0.0.1", self.port)
        except Exception:
            self._pripraveno.set()
            return

        self._pripraveno.set()
        try:
            server.serve_forever()
        except Exception:
            pass

    def _obsluha(self, ws) -> None:
        """Jedno připojení prohlížeče. Čte odpovědi a budí čekající."""
        try:
            pozdrav = json.loads(ws.recv(timeout=5))
        except Exception:
            return

        if not isinstance(pozdrav, dict) or pozdrav.get("token") != self.token:
            try:
                ws.close()
            except Exception:
                pass
            return

        self._ws = ws
        try:
            for sprava in ws:
                try:
                    data = json.loads(sprava)
                except Exception:
                    continue
                cekajici = self._cekajici.get(data.get("id"))
                if cekajici is not None:
                    cekajici["data"] = data
                    cekajici["hotovo"].set()
        except Exception:
            pass
        finally:
            if self._ws is ws:
                self._ws = None

    # --------------------------------------------------------- příkazy

    def request(self, cmd: str, timeout: float = 6.0, **kwargs):
        ws = self._ws
        if ws is None:
            raise BridgeError("prohlížeč není připojený (chybí rozšíření?)")

        with self._zamek:
            cislo = next(self._cisla)
            cekajici = {"hotovo": threading.Event(), "data": None}
            self._cekajici[cislo] = cekajici
            try:
                ws.send(json.dumps({"id": cislo, "cmd": cmd, **kwargs}))
                if not cekajici["hotovo"].wait(timeout):
                    raise BridgeError("prohlížeč neodpověděl včas")
            finally:
                self._cekajici.pop(cislo, None)

        data = cekajici["data"] or {}
        if not data.get("ok"):
            raise BridgeError(str(data.get("error") or "neznámá chyba"))
        return data.get("data")

    # ------------------------------------------------------ zkratky

    def karty(self) -> list[dict]:
        return self.request("tabs") or []

    def prvky(self, tab: int | None = None) -> list[dict]:
        return self.request("snapshot", tab=tab) or []

    def klik(self, index: int, text: str = "", tab: int | None = None) -> str:
        return self.request("click", tab=tab, index=index, text=text)

    def napis(self, index: int, text: str, tab: int | None = None) -> str:
        return self.request("type", tab=tab, index=index, text=text)

    def stiskni(self, keys: str, tab: int | None = None) -> str:
        return self.request("key", tab=tab, keys=keys)

    def jdi_na(self, url: str, tab: int | None = None) -> str:
        return self.request("navigate", tab=tab, url=url)


_most: Bridge | None = None


def most() -> Bridge:
    global _most
    if _most is None:
        _most = Bridge()
        _most.start()
    return _most


def dostupne() -> bool:
    try:
        return most().connected
    except Exception:
        return False


def karta_pro_okno(titulek: str) -> int | None:
    """Najde kartu, která patří k aktivnímu oknu prohlížeče."""
    cisty = (
        titulek.replace(" - Google Chrome", "")
        .replace(" - Chromium", "")
        .replace(" - Microsoft Edge", "")
        .strip()
    )
    karty = most().karty()
    if not karty:
        return None

    for karta in karty:
        nazev = (karta.get("title") or "").strip()
        if not nazev:
            continue
        if nazev == cisty or cisty.startswith(nazev) or nazev.startswith(cisty):
            return karta["id"]

    for karta in karty:
        if karta.get("active"):
            return karta["id"]
    return None
