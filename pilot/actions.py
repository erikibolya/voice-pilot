"""Akce, které smí model navrhnout — a jejich provedení.

Bezpečnostní pravidlo celého milníku 2: model **nesmí** říct „klikni na
souřadnice“. Smí jen odkázat na číslo prvku, který jsme mu ukázali ve
snímku obrazovky. Prvek, který v seznamu není, se nikdy neprovede.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field

from .eyes import Element, Snapshot

MAX_ACTIONS = 8

ALLOWED = {
    "click",
    "double_click",
    "right_click",
    "invoke",
    "focus",
    "type",
    "key",
    "scroll",
}

# slova, u kterých se před provedením varuje dvakrát
DESTRUCTIVE = (
    "smazat", "smaž", "odstranit", "vymazat", "zničit", "přesunout do koše",
    "delete", "remove", "format",
    "odeslat", "odešli", "poslat", "send", "zveřejnit", "publish",
    "zaplatit", "koupit", "objednat", "pay", "buy", "checkout",
    "odinstalovat", "uninstall",
    "přepsat", "overwrite",
    "vypnout", "restartovat",
    # volání a hovory: omylem vytořený hovor nejde vzít zpět
    "zavolat", "zavolej", "volat", "hovor", "call",
)


class ActionError(ValueError):
    pass


@dataclass
class Action:
    type: str
    target: int | None = None
    text: str = ""
    keys: str = ""
    direction: str = ""
    amount: int = 0

    @classmethod
    def from_dict(cls, data: object) -> "Action":
        if not isinstance(data, dict):
            raise ActionError("akce musí být objekt")

        kind = str(data.get("type") or "").strip().lower()
        if kind not in ALLOWED:
            raise ActionError(f"neznámý typ akce {kind!r}")

        target = data.get("target")
        if target is not None:
            try:
                target = int(target)
            except (TypeError, ValueError):
                raise ActionError("target musí být číslo")

        if kind in ("click", "double_click", "right_click", "invoke", "focus"):
            if target is None:
                raise ActionError(f"{kind} potřebuje target")

        text = str(data.get("text") or "")
        if kind == "type" and not text:
            raise ActionError("type potřebuje text")

        keys = str(data.get("keys") or "")
        if kind == "key" and not keys:
            raise ActionError("key potřebuje keys")

        return cls(
            type=kind,
            target=target,
            text=text,
            keys=keys,
            direction=str(data.get("direction") or "down"),
            amount=int(data.get("amount") or 3),
        )

    def je_nebezpecna(self, element: Element | None = None) -> bool:
        slova = f"{self.text} {self.keys} {element.name if element else ''}".lower()
        return any(slovo in slova for slovo in DESTRUCTIVE)


@dataclass
class Plan:
    say: str = ""
    actions: list[Action] = field(default_factory=list)
    error: str = ""
    done: bool = False
    @property
    def needs_confirmation(self) -> bool:
        return bool(self.actions)

    @property
    def is_destructive(self) -> bool:
        return any(a.je_nebezpecna() for a in self.actions)


def _extract_json(text: str) -> dict | None:
    """Najde první JSON objekt v odpovědi, i když je v markdown bloku."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        return None

    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None

    return data if isinstance(data, dict) else None


def parse(text: str) -> Plan:
    """Přečte odpověď modelu. Když není JSON, bereme to jako čistou řeč."""
    data = _extract_json(text)
    if data is None:
        return Plan(say=text.strip())

    say = str(data.get("say") or "").strip()
    raw = data.get("actions") or []

    if not isinstance(raw, list):
        return Plan(say=say or text.strip(), error="akce musí být seznam")

    if len(raw) > MAX_ACTIONS:
        return Plan(say=say, error=f"příliš mnoho akcí ({len(raw)}), limit je {MAX_ACTIONS}")

    actions: list[Action] = []
    for item in raw:
        try:
            actions.append(Action.from_dict(item))
        except ActionError as exc:
            # jedna vadná akce zruší celý plán - částečné provedení je horší
            return Plan(say=say or text.strip(), error=str(exc))

    return Plan(say=say or text.strip(), actions=actions, done=bool(data.get("done")))


# --------------------------------------------------------------- popis


def je_nebezpecny(plan: Plan, snap: Snapshot) -> bool:
    """Posuzuje i název prvku — „Smazat“ je nebezpečné tlačítko, ne text."""
    for action in plan.actions:
        element = snap.by_index(action.target) if action.target is not None else None
        if action.je_nebezpecna(element):
            return True
    return False


def describe(plan: Plan, snap: Snapshot) -> str:
    """Co se chystá, lidsky a česky — jde do hlasu i do potvrzovací lišty."""
    if not plan.actions:
        return ""

    casti: list[str] = []
    for action in plan.actions:
        element = snap.by_index(action.target) if action.target else None

        if action.type == "type":
            casti.append(f'napsat „{_short(action.text, 40)}“')
        elif action.type == "key":
            casti.append(f'stisknout {action.keys}')
        elif action.type == "scroll":
            smer = "dolů" if action.direction == "down" else "nahoru"
            casti.append(f"rolovat {smer}")
        elif action.type == "focus":
            casti.append(f'přepnout na „{_short(element.name, 28)}“' if element else "přepnout prvek")
        elif element is None:
            casti.append(f"{action.type} prvek [{action.target}]")
        else:
            sloveso = {
                "click": "kliknout na",
                "double_click": "dvakrát kliknout na",
                "right_click": "kliknout pravým na",
                "invoke": "stisknout",
            }.get(action.type, action.type)
            casti.append(f'{sloveso} „{_short(element.name, 28)}“')

    return ", potom ".join(casti)


def _short(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


# ------------------------------------------------------------- provedení


def execute(action: Action, snap: Snapshot) -> str:
    """Provede jednu akci. Vrací krátký popis, co se stalo."""
    element = snap.by_index(action.target) if action.target is not None else None

    if action.target is not None and element is None:
        raise ActionError(f"prvek [{action.target}] už na obrazovce není")

    if action.type in ("click", "double_click", "right_click"):
        _klikni(element, action.type)
        return f"kliknuto na „{element.name}“"

    if action.type == "invoke":
        _invoke(element)
        return f"stisknuto „{element.name}“"

    if action.type == "focus":
        _focus(element)
        return f"přepnuto na „{element.name}“"

    if action.type == "type":
        if element is not None:
            _focus(element)
        _napis(action.text)
        return f"napsáno {len(action.text)} znaků"

    if action.type == "key":
        _stiskni(action.keys)
        return f"stisknuto {action.keys}"

    if action.type == "scroll":
        _roluj(action.direction, action.amount)
        return f"rolováno {action.direction}"

    raise ActionError(f"akci {action.type} neumím provést")


def _klikni(element: Element, kind: str) -> None:
    control = element.control
    if control is not None:
        try:
            if kind == "click":
                control.Click()
            elif kind == "double_click":
                control.DoubleClick()
            else:
                control.RightClick()
            return
        except Exception:
            pass  # některé prvky UIA neumí, zkusíme souřadnice

        # Než klikneme naslepo, ověříme, že prvek je pořád tam, kde byl.
        if not _porad_na_miste(element):
            raise ActionError(
                f"„{element.name}“ se mezitím posunul nebo zmizel, neklikám naslepo"
            )

    x, y = element.center
    _klik_mysi(x, y, kind)


def _porad_na_miste(element: Element, tolerance: int = 6) -> bool:
    control = element.control
    if control is None:
        return True
    try:
        r = control.BoundingRectangle
        return (
            abs(r.left - element.x) <= tolerance
            and abs(r.top - element.y) <= tolerance
            and abs((r.right - r.left) - element.w) <= tolerance
            and abs((r.bottom - r.top) - element.h) <= tolerance
        )
    except Exception:
        return False


def _invoke(element: Element) -> None:
    control = element.control
    if control is not None:
        try:
            control.Invoke()
            return
        except Exception:
            pass
    x, y = element.center
    _klik_mysi(x, y, "click")


def _focus(element: Element) -> None:
    control = element.control
    if control is not None:
        try:
            control.SetFocus()
        except Exception:
            pass


def _klik_mysi(x: int, y: int, kind: str) -> None:
    """Klik přes Windows API — bez další závislosti."""
    import ctypes
    import ctypes.wintypes as wintypes

    user32 = ctypes.windll.user32
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.05)

    if kind == "right_click":
        down, up = 0x0008, 0x0010
    else:
        down, up = 0x0002, 0x0004

    kliki = 2 if kind == "double_click" else 1
    for _ in range(kliki):
        user32.mouse_event(down, 0, 0, 0, 0)
        user32.mouse_event(up, 0, 0, 0, 0)
        time.sleep(0.08)


def _napis(text: str) -> None:
    from pynput.keyboard import Controller

    Controller().type(text)


def _stiskni(combo: str) -> None:
    from pynput.keyboard import Controller, Key

    aliasy = {
        "ctrl": Key.ctrl, "control": Key.ctrl,
        "alt": Key.alt, "shift": Key.shift,
        "win": Key.cmd, "cmd": Key.cmd,
        "enter": Key.enter, "return": Key.enter,
        "esc": Key.esc, "escape": Key.esc,
        "tab": Key.tab, "space": Key.space,
        "backspace": Key.backspace, "delete": Key.delete, "del": Key.delete,
        "up": Key.up, "down": Key.down, "left": Key.left, "right": Key.right,
        "home": Key.home, "end": Key.end,
        "pageup": Key.page_up, "pagedown": Key.page_down,
    }

    klavesy = []
    for cast in combo.replace(" ", "").split("+"):
        if not cast:
            continue
        klavesy.append(aliasy.get(cast.lower(), cast))

    if not klavesy:
        raise ActionError("prázdná kombinace kláves")

    keyboard = Controller()
    for klavesa in klavesy:
        keyboard.press(klavesa)
    for klavesa in reversed(klavesy):
        keyboard.release(klavesa)


def _roluj(direction: str, amount: int) -> None:
    import ctypes

    krok = 120 * max(1, min(amount, 10))
    ctypes.windll.user32.mouse_event(0x0800, 0, 0, krok if direction == "up" else -krok, 0)
