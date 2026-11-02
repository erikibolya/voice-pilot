"""Mozek: poskládá prompt z toho, co vidíme, a pošle ho OpenCode."""

from __future__ import annotations

from dataclasses import dataclass, field

from . import eyes
from .oc import OpenCode

SYSTEM = """\
Jsi Pilot, hlasový asistent běžící na českém Windows. Uživatel na tebe mluví a ty mu odpovídáš nahlas.

Jak mluvit:
- Česky, přirozeně, jako schopný kolega sedící vedle.
- Maximálně 2 krátké věty. Žádné odrážky, žádný markdown, žádné emoji, žádné závorky s poznámkami.
- Čísla piš slovy, když jde o krátký údaj (řekni "dvanáct", ne "12"), ale u názvů souborů a cest nech přesný tvar.
- Když si nejsi jistý, řekni to. Nevymýšlej si, co na obrazovce není.

Co umíš právě teď:
- Podívat se na obrazovku a popsat, co tam je.
- Přečíst názvy oken, tlačítek a textů v aktivním okně.

Co zatím NEumíš:
- Klikat, psát a ovládat myš. To přijde později.
- Když tě o to uživatel požádá, řekni to jednou krátkou větou a navrhni, na který prvek bys klikl.
"""


@dataclass
class Reply:
    say: str
    actions: list[dict] = field(default_factory=list)


class Brain:
    def __init__(self, cfg, client: OpenCode | None = None):
        self.cfg = cfg
        self.client = client or OpenCode(
            cfg.service_url, cfg.service_password_file, cfg.provider_id, cfg.model_id
        )
        self.history: list[tuple[str, str]] = []

    def look_and_answer(self, utterance: str, snap: eyes.Snapshot | None = None) -> Reply:
        snap = snap or eyes.snapshot(self.cfg)
        prompt = self._build_prompt(utterance, snap)
        answer = self.client.generate(prompt)

        self.history.append((utterance, answer))
        self.history = self.history[-6:]

        # Zatím jen řeč. Struktura je připravená na akce (milník 2).
        return Reply(say=answer)

    def describe_screen(self) -> Reply:
        return self.look_and_answer("Co teď vidíš na obrazovce? Popiš to jednou větou.")

    # ---------- vnitřní ----------

    def _build_prompt(self, utterance: str, snap: eyes.Snapshot) -> str:
        parts = [SYSTEM, "", "--- CO JE PRÁVĚ TEĎ NA OBRAZOVCE ---", snap.render()]

        if self.history:
            parts.append("")
            parts.append("--- PŘEDCHOZÍ ROZHOVOR ---")
            for said, answered in self.history:
                parts.append(f"Uživatel: {said}")
                parts.append(f"Ty: {answered}")

        parts.append("")
        parts.append(f'--- NOVÝ VSTUP ---')
        parts.append(f'Uživatel řekl: "{utterance}"')
        parts.append("")
        parts.append("Odpověz jednou nebo dvěma krátkými věty, česky, bez formátování.")
        return "\n".join(parts)
