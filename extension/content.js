// Content script: čte a ovládá stránku.
//
// Běží uvnitř stránky, takže vidí skutečné DOM — to, co UI Automation u Chrome
// nikdy nedá. Indexy jsou stejné jako v seznamu, který dostane model.

const SELEKTOR = [
  "a",
  "button",
  "input",
  "textarea",
  "select",
  "video",
  '[role="button"]',
  '[role="link"]',
  '[role="checkbox"]',
  '[contenteditable="true"]',
].join(",");

const LIMIT = 150;

function prvky() {
  const out = [];
  for (const el of document.querySelectorAll(SELEKTOR)) {
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) continue;

    const s = getComputedStyle(el);
    if (s.visibility === "hidden" || s.display === "none" || s.opacity === "0") continue;

    const text = (el.innerText || el.value || el.getAttribute("aria-label") || el.placeholder || el.title || "")
      .trim()
      .replace(/\s+/g, " ")
      .slice(0, 70);

    out.push({
      tag: el.tagName.toLowerCase(),
      text: text || el.tagName.toLowerCase(),
      x: Math.round(r.left + window.scrollX),
      y: Math.round(r.top + window.scrollY),
      w: Math.round(r.width),
      h: Math.round(r.height),
      _el: el,
    });

    if (out.length >= LIMIT) break;
  }
  return out;
}

function najdi(index, ocekavany) {
  const vsechny = prvky();
  const cil = vsechny[index];
  if (!cil) throw new Error("prvek na stránce už není");

  if (ocekavany && cil.text.indexOf(ocekavany) === -1) {
    throw new Error(`na místě je jiný prvek: ${cil.text}`);
  }
  return cil;
}

const akce = {
  snapshot() {
    return prvky().map((p, i) => ({
      i,
      tag: p.tag,
      text: p.text,
      x: p.x,
      y: p.y,
      w: p.w,
      h: p.h,
    }));
  },

  click({ index, text }) {
    const cil = najdi(index, text);
    cil._el.scrollIntoView({ block: "center" });
    cil._el.focus();
    cil._el.click();
    return "ok";
  },

  type({ index, text }) {
    const cil = najdi(index, "");
    const el = cil._el;
    const tag = el.tagName.toLowerCase();

    if (tag !== "input" && tag !== "textarea" && !el.isContentEditable) {
      throw new Error("do tohohle prvku se psát nedá");
    }

    el.focus();
    if (el.isContentEditable) {
      el.innerText = text;
    } else {
      el.value = text;
    }
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return "ok";
  },

  key({ keys }) {
    const mapa = {
      enter: { key: "Enter", code: "Enter", keyCode: 13 },
      escape: { key: "Escape", code: "Escape", keyCode: 27 },
      tab: { key: "Tab", code: "Tab", keyCode: 9 },
    };
    const k = mapa[String(keys).trim().toLowerCase()];
    if (!k) throw new Error(`klávesu ${keys} na stránce neumím`);

    const cil = document.activeElement || document.body;
    for (const typ of ["keydown", "keypress", "keyup"]) {
      cil.dispatchEvent(
        new KeyboardEvent(typ, {
          key: k.key,
          code: k.code,
          keyCode: k.keyCode,
          which: k.keyCode,
          bubbles: true,
        })
      );
    }
    return "ok";
  },

  navigate({ url }) {
    window.location.href = url;
    return "ok";
  },
};

chrome.runtime.onMessage.addListener((zprava, odesilatel, odpoved) => {
  try {
    const f = akce[zprava.cmd];
    if (!f) throw new Error(`neznámý příkaz ${zprava.cmd}`);
    odpoved({ ok: true, data: f(zprava) });
  } catch (e) {
    odpoved({ ok: false, error: String(e && e.message ? e.message : e) });
  }
  return true;
});
