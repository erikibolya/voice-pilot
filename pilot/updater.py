"""Kontrola aktualizací přes GitHub Releases.

Stejný princip jako má RedLine: aplikace se podívá na nejnovější vydání
a nabídne stažení instalátoru. Na rozdíl od Tauri updateru neděláme
podpisové klíče - instalátor stahujeme z GitHubu po HTTPS a spouštíme
ho s vědomím uživatele.
"""

from __future__ import annotations

import json
import re
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import __version__

REPO = "erikibolya/voice-pilot"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
DOWNLOAD_PAGE = f"https://github.com/{REPO}/releases/latest"


@dataclass
class Update:
    version: str
    url: str
    notes: str
    published: str
    size: int = 0


def parse_version(text: str) -> tuple[int, ...]:
    """`v0.2.1` -> (0, 2, 1). Nečíselné části (dev, beta) se ignorují."""
    numbers = re.findall(r"\d+", text.split("-")[0].split("+")[0])
    return tuple(int(n) for n in numbers) if numbers else (0,)


def is_newer(candidate: str, current: str) -> bool:
    a, b = parse_version(candidate), parse_version(current)
    length = max(len(a), len(b))
    return a + (0,) * (length - len(a)) > b + (0,) * (length - len(b))


def check(timeout: float = 10.0) -> tuple[Update | None, str]:
    """Vrací (aktualizace_nebo_None, zpráva_pro_člověka)."""
    request = urllib.request.Request(
        API_LATEST,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"voice-pilot/{__version__}",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None, "Zatím žádné vydání — není co aktualizovat."
        if exc.code == 403:
            return None, "GitHub dočasně odmítá požadavky (limit). Zkus to za chvíli."
        return None, f"GitHub vrátil chybu {exc.code}."
    except Exception as exc:
        return None, f"Nepodařilo se spojit s GitHubem: {exc}"

    tag = payload.get("tag_name") or payload.get("name") or ""
    if not tag:
        return None, "Vydání nemá verzi."

    if not is_newer(tag, __version__):
        return None, f"Máš nejnovější verzi ({__version__})."

    installer = _pick_installer(payload.get("assets", []))
    if installer is None:
        return None, f"Verze {tag} vyšla, ale nemá instalátor."

    return (
        Update(
            version=tag.lstrip("v"),
            url=installer["browser_download_url"],
            notes=(payload.get("body") or "").strip(),
            published=payload.get("published_at", ""),
            size=installer.get("size", 0),
        ),
        f"K dispozici je verze {tag.lstrip('v')}.",
    )


def _pick_installer(assets: list[dict]) -> dict | None:
    for asset in assets:
        name = asset.get("name", "").lower()
        if name.endswith(".exe") and "setup" in name:
            return asset
    for asset in assets:
        if asset.get("name", "").lower().endswith(".exe"):
            return asset
    return None


def download(update: Update, progress=None) -> Path:
    """Stáhne instalátor do dočasného adresáře. `progress(0..1)` je volitelný."""
    target = Path(tempfile.gettempdir()) / f"voice-pilot-{update.version}-setup.exe"
    request = urllib.request.Request(
        update.url, headers={"User-Agent": f"voice-pilot/{__version__}"}
    )

    with urllib.request.urlopen(request, timeout=60) as response, open(target, "wb") as fh:
        total = int(response.headers.get("Content-Length") or update.size or 0)
        done = 0
        while chunk := response.read(65536):
            fh.write(chunk)
            done += len(chunk)
            if progress and total:
                progress(min(1.0, done / total))

    return target
