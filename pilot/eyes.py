"""Oči: co je na obrazovce, přečtené přes Windows UI Automation.

Proč zrovna takhle a ne jen ze screenshotu:
  * model dostane přesné názvy tlačítek a souřadnice, nemusí hádat z pixelů,
  * čeština projde bez OCR,
  * a hlavně - každý prvek má číslo, takže později stačí říct "klikni na [7]"
    a nemůže kliknout na něco, co jsme mu neukázali.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import uiautomation as auto

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "shots"

# ControlTypeName -> krátký a srozumitelný název pro model
FRIENDLY = {
    "ButtonControl": "tlačítko",
    "EditControl": "pole",
    "TextControl": "text",
    "MenuItemControl": "položka menu",
    "ListItemControl": "položka seznamu",
    "TreeItemControl": "položka stromu",
    "TabItemControl": "karta",
    "DocumentControl": "dokument",
    "HyperlinkControl": "odkaz",
    "ComboBoxControl": "výběrový seznam",
    "CheckBoxControl": "zaškrtávátko",
    "RadioButtonControl": "přepínač",
    "SliderControl": "posuvník",
    "PaneControl": "panel",
    "WindowControl": "okno",
    "GroupControl": "skupina",
    "DataItemControl": "položka",
    "ImageControl": "obrázek",
}


@dataclass
class Element:
    index: int
    kind: str
    name: str
    x: int
    y: int
    w: int
    h: int
    # živý ovládací prvek pro UI Automation; do textu pro model nepatří
    control: object | None = field(default=None, repr=False, compare=False)
    # "uia" pro Windows, "cdp" pro DevTools, "web" pro rozšíření v prohlížeči
    source: str = "uia"
    cdp_index: int | None = None
    tab: int | None = None

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.w // 2, self.y + self.h // 2)


@dataclass
class Snapshot:
    active_title: str = ""
    active_class: str = ""
    windows: list[dict] = field(default_factory=list)
    elements: list[Element] = field(default_factory=list)
    # index prvního prvku panelu úloh; None když se nepřečetl
    taskbar_from: int | None = None
    # index prvního prvku webové stránky (přes CDP); None když není
    web_from: int | None = None

    def render(self) -> str:
        lines: list[str] = []
        lines.append(f'AKTIVNÍ OKNO: "{self.active_title}" ({self.active_class})')

        if self.windows:
            others = [w for w in self.windows if w["title"] != self.active_title]
            if others:
                lines.append("DALŠÍ OTEVŘENÁ OKNA:")
                for w in others[:14]:
                    lines.append(f'  - "{_short(w["title"], 60)}"')

        okno = [e for e in self.elements if self.taskbar_from is None or e.index < self.taskbar_from]
        panel = [e for e in self.elements if self.taskbar_from is not None and e.index >= self.taskbar_from]
        if self.web_from is not None:
            okno = [e for e in okno if e.index < self.web_from]
            panel = [e for e in panel if e.index < self.web_from]

        if okno:
            lines.append("PRVKY V AKTIVNÍM OKNĚ (klikat lze jen na tato čísla):")
            for e in okno:
                lines.append(
                    f'  [{e.index}] {e.kind} "{_short(e.name, 70)}" @ ({e.x}, {e.y}) {e.w}x{e.h}'
                )
        else:
            lines.append("PRVKY: nepodařilo se přečíst (okno možná nepodporuje přístupnost)")

        if panel:
            lines.append("PRVKY V PANELU ÚLOH (ikony aplikací dole):")
            for e in panel:
                lines.append(
                    f'  [{e.index}] {e.kind} "{_short(e.name, 70)}" @ ({e.x}, {e.y}) {e.w}x{e.h}'
                )

        if self.web_from is not None:
            web = [e for e in self.elements if e.index >= self.web_from]
            if web:
                lines.append("PRVKY NA WEBOVÉ STRÁNCE (v prohlížeči):")
                for e in web:
                    lines.append(
                        f'  [{e.index}] {e.kind} "{_short(e.name, 70)}" @ ({e.x}, {e.y}) {e.w}x{e.h}'
                    )

        return "\n".join(lines)

    def by_index(self, index: int) -> Element | None:
        for e in self.elements:
            if e.index == index:
                return e
        return None

    def find_by_name(self, name: str, source: str = "uia") -> Element | None:
        for element in self.elements:
            if element.source == source and element.name == name:
                return element
        return None

    def find_like(self, element: Element, tolerance: int = 8) -> Element | None:
        """Najde stejný prvek v novém snímku — podle názvu a místa.

        Indexy se mezi snímky posunou, ale jméno a poloha zůstávají.
        """
        for kandidat in self.elements:
            if kandidat.kind != element.kind or kandidat.name != element.name:
                continue
            if (
                abs(kandidat.x - element.x) <= tolerance
                and abs(kandidat.y - element.y) <= tolerance
                and abs(kandidat.w - element.w) <= tolerance
                and abs(kandidat.h - element.h) <= tolerance
            ):
                return kandidat
        return None


def release(snap: "Snapshot") -> None:
    """Zahodí COM odkazy na prvky — a to ve vlákně, které je vytvořilo.

    UI Automation objekty patří do apartmentu svého vlákna. Když je uvolní
    jiné vlákno (nebo garbage collector), Windows vrátí RPC_E_DISCONNECTED
    a aplikace spadne. Data (jméno, poloha) zůstávají, jen se pustí COM.
    """
    for element in snap.elements:
        element.control = None


def _short(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _visible(ctrl) -> bool:
    try:
        r = ctrl.BoundingRectangle
        return (r.right - r.left) > 2 and (r.bottom - r.top) > 2
    except Exception:
        return False


def list_windows() -> list[dict]:
    result: list[dict] = []
    try:
        root = auto.GetRootControl()
        for w in root.GetChildren():
            try:
                title = w.Name
                if not title:
                    continue
                r = w.BoundingRectangle
                result.append(
                    {
                        "title": title,
                        "class": w.ClassName,
                        "hwnd": getattr(w, "NativeWindowHandle", 0),
                        "x": r.left,
                        "y": r.top,
                        "w": r.right - r.left,
                        "h": r.bottom - r.top,
                    }
                )
            except Exception:
                continue
    except Exception:
        pass
    return result


def _renderer_roots(hwnd: int) -> list:
    """Chrome drží obsah stránky ve zvláštním podřízeném HWND.

    Běžné GetChildren() se přes něj nedostane, takže ho musíme přidat zvlášť -
    jinak z prohlížeče vidíme jen panel nástrojů a stránku ne.
    """
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    roots: list = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(child, _lparam):  # noqa: ANN001
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(child, cls, 256)
        if "RenderWidgetHost" in cls.value:
            try:
                roots.append(auto.ControlFromHandle(child))
            except Exception:
                pass
        return True

    try:
        user32.EnumChildWindows(hwnd, callback, 0)
    except Exception:
        pass
    return roots


def _collect(
    roots: list, cfg, deadline: float, start_index: int = 1, limit: int | None = None
) -> list[Element]:
    """Projde stromy oken do šířky, aby se stihla vrchní úroveň."""
    maximum = limit if limit is not None else cfg.max_elements
    out: list[Element] = []
    seen: set[tuple] = set()
    queue: list[tuple[object, int]] = [(root, 0) for root in roots]
    cursor = 0

    while cursor < len(queue) and len(out) < maximum:
        if time.monotonic() > deadline:
            break
        node, depth = queue[cursor]
        cursor += 1

        try:
            children = node.GetChildren()
        except Exception:
            children = []

        for child in children:
            if depth < cfg.max_depth:
                queue.append((child, depth + 1))

            try:
                raw_name = child.Name
            except Exception:
                continue
            name = " ".join(raw_name.split()) if raw_name else ""
            if not name or not _visible(child):
                continue

            r = child.BoundingRectangle
            kind = FRIENDLY.get(child.ControlTypeName, child.ControlTypeName)
            key = (kind, name, r.left, r.top, r.right - r.left, r.bottom - r.top)
            if key in seen:
                continue
            seen.add(key)

            out.append(
                Element(
                    index=start_index + len(out),
                    kind=kind,
                    name=name,
                    x=r.left,
                    y=r.top,
                    w=r.right - r.left,
                    h=r.bottom - r.top,
                    control=child,
                )
            )
            if len(out) >= maximum:
                break

    return out


def snapshot(cfg) -> Snapshot:
    """Přečte obrazovku. Bezpečné i z vedlejšího vlákna.

    UI Automation je COM a COM musí být inicializováno v každém vlákně
    zvlášť. Bez toho `uiautomation` tiše vrátí prázdný strom — a model
    pak nevidí nic, což vypadá jako „asistent nic neumí“.
    """
    import threading

    import uiautomation as auto

    init = getattr(auto, "UIAutomationInitializerInThread", None)
    if init is not None and threading.current_thread() is not threading.main_thread():
        with init():
            return _snapshot(cfg)

    return _snapshot(cfg)


def _snapshot(cfg) -> Snapshot:
    snap = Snapshot()

    active = None
    hwnd = 0
    try:
        import ctypes

        hwnd = ctypes.windll.user32.GetForegroundWindow()
        active = auto.ControlFromHandle(hwnd)
    except Exception:
        active = None

    if active is not None:
        try:
            snap.active_title = active.Name or ""
            snap.active_class = active.ClassName or ""
        except Exception:
            pass

        roots: list = [active]
        try:
            roots.extend(_renderer_roots(hwnd))
        except Exception:
            pass

        deadline = time.monotonic() + cfg.ui_budget_seconds
        snap.elements = _collect(roots, cfg, deadline)

    if cfg.include_all_windows:
        snap.windows = list_windows()

    # Panel úloh je samostatné okno, takže v aktivním okně nikdy není.
    # Bez tohohle nejde kliknout na ikonu aplikace v liště.
    try:
        panel = _taskbar_control(snap.windows)
        if panel is not None:
            snap.taskbar_from = len(snap.elements) + 1
            deadline = time.monotonic() + cfg.ui_budget_seconds
            snap.elements.extend(
                _collect(
                    [panel],
                    cfg,
                    deadline,
                    start_index=snap.taskbar_from,
                    limit=cfg.max_taskbar_elements,
                )
            )
    except Exception:
        pass

    # Web: UI Automation z Chrome obsah nevydá. Nejdřív zkusíme rozšíření
    # v prohlížeči (funguje s normálním profilem), pak DevTools port.
    try:
        if "Chrome_WidgetWin_1" in snap.active_class or "MozillaWindowClass" in snap.active_class:
            _pripoj_web(snap, cfg)
    except Exception:
        pass

    return snap


def _pripoj_web(snap: Snapshot, cfg) -> None:
    from . import bridge

    if bridge.dostupne():
        karta = bridge.karta_pro_okno(snap.active_title)
        prvky = bridge.prvky(karta)[: cfg.max_web_elements]
        if prvky:
            snap.web_from = len(snap.elements) + 1
            for p in prvky:
                snap.elements.append(
                    Element(
                        index=len(snap.elements) + 1,
                        kind=str(p.get("tag", "prvek")),
                        name=str(p.get("text", "")),
                        x=int(p.get("x", 0)),
                        y=int(p.get("y", 0)),
                        w=int(p.get("w", 0)),
                        h=int(p.get("h", 0)),
                        source="web",
                        cdp_index=int(p.get("i", 0)),
                        tab=karta,
                    )
                )
        return

    from . import cdp

    if not cdp.available():
        return

    tab = cdp.tab_for_window(snap.active_title)
    if tab is None:
        return
    try:
        prvky = tab.elements()[: cfg.max_web_elements]
    finally:
        tab.close()

    if not prvky:
        return

    snap.web_from = len(snap.elements) + 1
    for p in prvky:
        snap.elements.append(
            Element(
                index=len(snap.elements) + 1,
                kind=str(p.get("tag", "prvek")),
                name=str(p.get("text", "")),
                x=int(p.get("x", 0)),
                y=int(p.get("y", 0)),
                w=int(p.get("w", 0)),
                h=int(p.get("h", 0)),
                source="cdp",
                cdp_index=int(p.get("i", 0)),
            )
        )


def _taskbar_control(okna: list[dict]):
    """Najde okno panelu úloh mezi otevřenými okny."""
    import ctypes

    for okno in okna:
        if okno.get("class") in ("Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
            hwnd = okno.get("hwnd") or 0
            if not hwnd:
                hwnd = ctypes.windll.user32.FindWindowW("Shell_TrayWnd", None)
            if hwnd:
                try:
                    return auto.ControlFromHandle(hwnd)
                except Exception:
                    continue

    hwnd = ctypes.windll.user32.FindWindowW("Shell_TrayWnd", None)
    if hwnd:
        try:
            return auto.ControlFromHandle(hwnd)
        except Exception:
            return None
    return None


def screenshot(name: str = "screen") -> Path:
    import mss

    SHOTS.mkdir(parents=True, exist_ok=True)
    path = SHOTS / f"{name}.png"
    factory = getattr(mss, "MSS", None) or mss.mss
    with factory() as sct:
        shot = sct.grab(sct.monitors[0])
        mss.tools.to_png(shot.rgb, shot.size, output=str(path))
    return path


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    from .config import load

    s = snapshot(load())
    print(s.render())
    print("\nscreenshot:", screenshot())
