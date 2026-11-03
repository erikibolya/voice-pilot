"""Mozek: z toho, co vidíme, udělá odpověď a případně plán akcí."""

from __future__ import annotations

from dataclasses import dataclass, field

from . import actions, eyes
from .actions import Plan
from .oc import OpenCode

SYSTEM = """\
Jsi Pilot, hlasový asistent běžící na českém Windows. Uživatel na tebe mluví a ty mu odpovídáš nahlas. Umíš se podívat na obrazovku a ovládat myš a klávesnici.

Odpovídej VŽDY jen jedním JSON objektem, bez markdownu a bez textu okolo:
{"say": "co řekneš nahlas", "actions": [], "done": false}

"done" je true, když je úkol hotový (nebo když už nemáš co dělat).

"say" je to, co se přečte nahlas. Drž se krátce:
- když se uživatel na něco ptá, odpověz jednou větou,
- když něco děláš, nech "say" PRÁZDNÉ. Neohlížej se, nekomentuj, nepopisuj
  kroky (žádné „klikl jsem“, „přesunul jsem se“, „hotovo“),
- mluv jen na konci, když je "done": true — a i tam jen tehdy, když máš
  co sdělit (výsledek, číslo, chybu). Když je výsledkem jen přepnuté okno
  nebo kliknutí, nech "say" prázdné — uživatel to vidí na obrazovce,
- když není co říct, nech prázdný řetězec "".

Povolené akce — "target" je VŽDY číslo prvku ze seznamu PRVKY:
  {"type": "click",        "target": 7}
  {"type": "double_click", "target": 7}
  {"type": "right_click",  "target": 7}
  {"type": "invoke",       "target": 7}          // tlačítko; spolehlivější než click
  {"type": "focus",        "target": 7}
  {"type": "type",         "target": 7, "text": "co napsat"}
  {"type": "key",          "keys": "ctrl+s"}
  {"type": "scroll",       "direction": "down", "amount": 3}
  {"type": "activate",     "title": "Discord"}   // přepne okno dopředu
  {"type": "close",        "title": "Discord"}   // zavře okno (jako křížek)

U oken používej "activate" a "close" s částí názvu okna. Je to spolehlivější
než klikat na ikonu v panelu úloh — a na zavření okna to je jediná cesta.

Pravidla, která se nesmí porušit:
- Používej pouze čísla z posledního seznamu PRVKY. Jiné prvky neexistují.
- Když uživatel chce něco, co v seznamu není, řekni to v "say" a žádnou akci nedělej.
- Maximálně 8 akcí. Méně a jistě je lepší než hodně a naslepo.
- Nevymýšlej si názvy souborů, texty ani obsah, který jsi v seznamu neviděl.

Seznam může mít dvě části: PRVKY V AKTIVNÍM OKNĚ a PRVKY V PANELU ÚLOH.
Panel úloh jsou ikony aplikací dole na obrazovce — kliknutím na ně se aplikace
přenese dopředu. Když chce uživatel přepnout do jiné aplikace, hledej ji tam.

Pracuješ po krocích: dostaneš úkol a aktuální obrazovku, provedeš jeden krok,
a pak se podíváš znovu. Nikdy neplánuj víc kroků dopředu naslepo — obrazovka
se mezi kroky změní. Když je cíl splněný, dej "done": true.
"""


JAZYK_NAZEV = {"cs": "čeština", "en": "angličtina"}


@dataclass
class Reply:
    say: str
    plan: Plan = field(default_factory=Plan)


class Brain:
    def __init__(self, cfg, client: OpenCode | None = None):
        self.cfg = cfg
        self.client = client or OpenCode(
            cfg.service_url, cfg.service_password_file, cfg.provider_id, cfg.model_id
        )
        self.history: list[tuple[str, str]] = []
        # nastaví engine podle jazyka, který rozpoznal Whisper
        self.override_language: str | None = None

    def _jazyk(self) -> str:
        jazyk = self.override_language or getattr(self.cfg, "language", "auto")
        if jazyk in ("auto", "", None):
            jazyk = "cs"
        return JAZYK_NAZEV.get(jazyk, "čeština")

    def look_and_answer(self, utterance: str, snap: eyes.Snapshot | None = None) -> Reply:
        snap = snap or eyes.snapshot(self.cfg)
        prompt = self._build_prompt(utterance, snap)

        raw = self.client.generate(prompt)
        plan = actions.parse(raw)

        self.history.append((utterance, plan.say))
        self.history = self.history[-6:]

        return Reply(say=plan.say, plan=plan)

    # ---------------------------------------------------------- vision

    def vision_prompt(self, cil: str, provedeno: list[str], obraz) -> str:
        """Výzva k modelu, který se dívá na screenshot."""
        radky = [
            "Jsi Pilot, hlasový asistent, který ovládá český Windows. Díváš se na screenshot obrazovky.",
            "",
            f"Obrázek má {obraz.sirka}x{obraz.vyska} pixelů. Souřadnice vracej v TĚCHTO pixelech,"
            " počátek 0,0 je levý horní roh obrázku.",
            "",
            'Odpověz POUZE jedním JSON objektem, bez textu okolo:',
            '{"say": "", "actions": [], "done": false}',
            "",
            "Akce (u kliknutí vždy x a y):",
            '  {"type": "click",        "x": 400, "y": 300}',
            '  {"type": "double_click", "x": 400, "y": 300}',
            '  {"type": "right_click",  "x": 400, "y": 300}',
            '  {"type": "type",         "x": 400, "y": 300, "text": "co napsat"}',
            '  {"type": "key",          "keys": "alt+f4"}',
            '  {"type": "close",        "title": "Discord"}',
            "",
            "Pravidla:",
            '  - "say" nech prázdné, dokud není úkol hotový. Nepopisuj kroky.',
            '  - Když je hotovo, dej "done": true.',
            "  - Klíčová slova a tlačítka poznáš z obrázku; trefuj jejich středy.",
            "  - Když si nejsi jistý, radši neklikej a napiš to do say.",
            "",
            "--- ÚKOL ---",
            cil,
        ]
        if provedeno:
            radky += ["", "--- UŽ PROVEDENO ---"] + [f"  - {k}" for k in provedeno[-10:]]
        return "\n".join(radky)

    def describe_screen(self) -> Reply:
        return self.look_and_answer("Co teď vidíš na obrazovce? Popiš to jednou větou.")

    def next_step(self, goal: str, provedeno: list[str], snap: eyes.Snapshot) -> Plan:
        """Další krok k cíli — po provedení předchozího a novém snímku."""
        parts = [
            SYSTEM,
            "",
            f"Jazyk odpovědi: {self._jazyk()}. V tom jazyce piš i 'say'.",
            "",
            "--- ÚKOL ---",
            goal,
            "",
            "--- UŽ PROVEDENO ---",
        ]
        if provedeno:
            parts.extend(f"  - {krok}" for krok in provedeno[-12:])
        else:
            parts.append("  (nic)")
        parts += [
            "",
            "--- CO JE PRÁVĚ TEĎ NA OBRAZOVCE ---",
            snap.render(),
            "",
            'Pokud je úkol hotový, dej "done": true a "actions": [].',
            "Jinak proveď jen další krok a nech \"done\": false.",
        ]
        raw = self.client.generate("\n".join(parts))
        return actions.parse(raw)

    # ---------- vnitřní ----------

    def _build_prompt(self, utterance: str, snap: eyes.Snapshot) -> str:
        parts = [
            SYSTEM,
            "",
            f"Jazyk odpovědi: {self._jazyk()}. V tom jazyce piš i 'say'.",
            "",
            "--- CO JE PRÁVĚ TEĎ NA OBRAZOVCE ---",
            snap.render(),
        ]

        if self.history:
            parts.append("")
            parts.append("--- PŘEDCHOZÍ ROZHOVOR ---")
            for said, answered in self.history:
                parts.append(f"Uživatel: {said}")
                parts.append(f"Ty: {answered}")

        parts.append("")
        parts.append("--- NOVÝ VSTUP ---")
        parts.append(f'Uživatel řekl: "{utterance}"')
        parts.append("")
        parts.append('Odpověz JSON objektem {"say": ..., "actions": [...]}.')
        return "\n".join(parts)
