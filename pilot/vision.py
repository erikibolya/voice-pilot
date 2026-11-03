"""Oči přes obrázek: screenshot → model s vision → souřadnice.

UI Automation dá jména prvků, ale jen tam, kde je aplikace ochotná je vydat.
Screenshot ukáže cokoli — plátna, hry, weby bez rozšíření. Model dostane
zmenšený snímek a vrací souřadnice v prostoru toho snímku; my je přepočítáme
zpátky na skutečnou obrazovku.
"""

from __future__ import annotations

import io
import json
import pathlib
import time
from dataclasses import dataclass

import httpx

MAX_SIRKA = 1920
KVALITA = 70


@dataclass
class Snimek:
    """Zmenšený snímek monitoru a přepočet zpátky do skutečných souřadnic."""

    data: bytes
    sirka: int          # rozměry obrázku, který vidí model
    vyska: int
    offset_x: int       # levý horní roh monitoru na ploše
    offset_y: int
    scale: float        # skutečný / zmenšený

    def na_obrazovku(self, x: float, y: float) -> tuple[int, int]:
        return (int(self.offset_x + x * self.scale), int(self.offset_y + y * self.scale))

    @property
    def popis(self) -> str:
        return f"{self.sirka}x{self.vyska} px"


def _monitor_okna(hwnd: int) -> dict:
    """Monitor, na kterém leží aktivní okno."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    stred_x = (rect.left + rect.right) // 2
    stred_y = (rect.top + rect.bottom) // 2

    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    MONITOR_DEFAULTTONEAREST = 2
    hmon = user32.MonitorFromPoint(
        wintypes.POINT(stred_x, stred_y), MONITOR_DEFAULTTONEAREST
    )
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    user32.GetMonitorInfoW(hmon, ctypes.byref(info))
    r = info.rcMonitor
    return {"left": r.left, "top": r.top, "width": r.right - r.left, "height": r.bottom - r.top}


def snimek() -> Snimek:
    """Zachytí monitor s aktivním oknem a zmenší ho."""
    import ctypes

    import mss
    from PIL import Image

    hwnd = ctypes.windll.user32.GetForegroundWindow()
    oblast = _monitor_okna(hwnd)

    with mss.mss() as sct:
        raw = sct.grab(oblast)

    obrazek = Image.frombytes("RGB", raw.size, raw.rgb)

    scale = max(1.0, raw.width / MAX_SIRKA)
    if scale > 1.0:
        obrazek = obrazek.resize(
            (int(raw.width / scale), int(raw.height / scale)), Image.LANCZOS
        )

    buf = io.BytesIO()
    obrazek.save(buf, format="JPEG", quality=KVALITA)

    return Snimek(
        data=buf.getvalue(),
        sirka=obrazek.width,
        vyska=obrazek.height,
        offset_x=oblast["left"],
        offset_y=oblast["top"],
        scale=scale,
    )


class Citac:
    """Posílá snímky modelu a vrací text odpovědi."""

    def __init__(self, cfg):
        self.cfg = cfg
        self._http = httpx.Client(timeout=120)
        self._session: str | None = None
        self._soubor = pathlib.Path(
            pathlib.Path.home() / "AppData" / "Local" / "Temp" / "voice-pilot-vision.jpg"
        )

    # ------------------------------------------------------------ session

    def _auth(self) -> tuple[str, str]:
        import json as _json

        heslo = _json.loads(
            pathlib.Path(self.cfg.service_password_file).read_text(encoding="utf-8")
        )["password"]
        return ("opencode", heslo)

    def _vytvor_session(self) -> str:
        r = self._http.post(
            f"{self.cfg.service_url}/api/session",
            auth=self._auth(),
            json={
                "title": "voice-pilot vision",
                "model": {"providerID": self.cfg.provider_id, "id": self.cfg.model_id},
            },
        )
        r.raise_for_status()
        telo = r.json()
        return (telo.get("data") or telo)["id"]

    # ------------------------------------------------------------- dotaz

    def zeptej_se(self, vyzva: str, obraz: Snimek, timeout: float = 40.0) -> str:
        if self._session is None:
            self._session = self._vytvor_session()

        self._soubor.parent.mkdir(parents=True, exist_ok=True)
        self._soubor.write_bytes(obraz.data)
        uri = self._soubor.as_uri()

        r = self._http.post(
            f"{self.cfg.service_url}/api/session/{self._session}/prompt",
            auth=self._auth(),
            json={
                "text": vyzva,
                "files": [
                    {"uri": uri, "source": {"type": "uri", "uri": uri}, "name": "screen.jpg"}
                ],
            },
        )
        r.raise_for_status()

        zacatek = time.monotonic()
        while time.monotonic() - zacatek < timeout:
            time.sleep(0.15)
            r = self._http.get(
                f"{self.cfg.service_url}/api/session/{self._session}/message",
                auth=self._auth(),
            )
            telo = r.json().get("data")
            zpravy = telo if isinstance(telo, list) else (telo or {}).get("messages", [])

            for zprava in zpravy:
                if zprava.get("type") != "assistant":
                    continue
                if zprava.get("error"):
                    raise RuntimeError(zprava["error"].get("message", "model selhal"))
                text = " ".join(
                    cast.get("text", "")
                    for cast in (zprava.get("content") or [])
                    if isinstance(cast, dict)
                ).strip()
                if text:
                    return text

        raise RuntimeError("model neodpověděl včas")
