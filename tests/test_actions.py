"""Testy milníku 2 — akce a jejich potvrzování."""

from __future__ import annotations

import pytest

from pilot import actions
from pilot.actions import Action, ActionError, Plan
from pilot.eyes import Element, Snapshot


def _snap() -> Snapshot:
    return Snapshot(
        active_title="Faktury – Průzkumník souborů",
        active_class="CabinetWClass",
        elements=[
            Element(index=1, kind="tlačítko", name="Přejmenovat", x=10, y=10, w=40, h=20),
            Element(index=2, kind="tlačítko", name="Smazat", x=60, y=10, w=40, h=20),
            Element(index=3, kind="pole", name="Název", x=10, y=40, w=200, h=20),
        ],
    )


# ------------------------------------------------------------------ parsing


def test_odpoved_bez_jsonu_je_cista_rec():
    plan = actions.parse("Máš otevřený průzkumník.")

    assert plan.say == "Máš otevřený průzkumník."
    assert plan.actions == []
    assert plan.error == ""


def test_json_se_rozpozna_i_v_markdown_bloku():
    plan = actions.parse(
        '```json\n{"say": "Kliknu.", "actions": [{"type": "click", "target": 1}]}\n```'
    )

    assert plan.say == "Kliknu."
    assert len(plan.actions) == 1
    assert plan.actions[0].target == 1


def test_neznama_akce_zrusi_cely_plan():
    plan = actions.parse(
        '{"say": "x", "actions": [{"type": "click", "target": 1}, {"type": "rm -rf"}]}'
    )

    assert plan.actions == []
    assert plan.error


def test_kliknuti_bez_cile_zrusi_plan():
    plan = actions.parse('{"say": "x", "actions": [{"type": "click"}]}')

    assert plan.actions == []
    assert "target" in plan.error


def test_prilis_mnoho_akci_se_odmitne():
    akce = ", ".join('{"type": "click", "target": 1}' for _ in range(20))
    plan = actions.parse('{"say": "x", "actions": [' + akce + "]}")

    assert plan.actions == []
    assert "limit" in plan.error


def test_psani_potrebuje_text():
    plan = actions.parse('{"say": "x", "actions": [{"type": "type"}]}')

    assert plan.actions == []
    assert "text" in plan.error


# ------------------------------------------------------------------ popis


def test_popis_je_cesky_a_obsahuje_nazev_prvku():
    plan = Plan(
        say="Jdu na to.",
        actions=[Action(type="click", target=1), Action(type="type", text="nove.pdf")],
    )

    popis = actions.describe(plan, _snap())

    assert "Přejmenovat" in popis
    assert "nove.pdf" in popis


def test_popis_oznaci_akci_ktera_neni_na_obrazovce():
    plan = Plan(say="x", actions=[Action(type="click", target=99)])
    assert "99" in actions.describe(plan, _snap())


# ------------------------------------------------------------ nebezpecnost


@pytest.mark.parametrize(
    "text",
    ["smazat soubor", "Smazat", "odeslat formulář", "zaplatit", "uninstall"],
)
def test_nebezpecna_slova_se_poznaji(text):
    plan = Plan(say="x", actions=[Action(type="type", text=text)])
    assert plan.is_destructive


def test_bezna_akce_neni_nebezpecna():
    plan = Plan(say="x", actions=[Action(type="click", target=1)])
    assert not plan.is_destructive


def test_nebezpecny_nazev_prvku_se_pozna():
    action = Action(type="click", target=2)
    element = _snap().by_index(2)
    assert action.je_nebezpecna(element)


# ------------------------------------------------------------- provedení


def test_klik_na_neexistujici_prvek_selze():
    with pytest.raises(ActionError):
        actions.execute(Action(type="click", target=99), _snap())


def test_klik_se_provede_na_spravnem_prvku(monkeypatch):
    provedeno = []
    monkeypatch.setattr(actions, "_klik_mysi", lambda x, y, k: provedeno.append((x, y, k)))

    vysledek = actions.execute(Action(type="click", target=1), _snap())

    assert provedeno == [(30, 20, "click")]
    assert "Přejmenovat" in vysledek


def test_psani_se_provede(monkeypatch):
    napsano = []
    monkeypatch.setattr(actions, "_napis", lambda text: napsano.append(text))

    actions.execute(Action(type="type", target=3, text="nove.pdf"), _snap())

    assert napsano == ["nove.pdf"]


def test_posunuty_prvek_se_neklikne_naslepo():
    """Když UIA prvek neumí kliknout a mezitím se posunul, radši nic."""
    snap = _snap()

    class Posunuty:
        def Click(self):
            raise RuntimeError("neumím")

        @property
        def BoundingRectangle(self):
            class R:
                left, top, right, bottom = 900, 900, 940, 920

            return R()

    snap.elements[0].control = Posunuty()

    with pytest.raises(ActionError):
        actions.execute(Action(type="click", target=1), snap)
