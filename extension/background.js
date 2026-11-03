// Service worker: drží spojení s voice-pilotem a zprostředkovává příkazy.
//
// Prohlížeč se připojuje k Python aplikaci na 127.0.0.1, ne naopak — rozšíření
// nemůže naslouchat na portu. Když spojení spadne, zkouší to znovu.

const PORT = 8791;
const TOKEN = "voice-pilot"; // musí odpovídat pilot/bridge.py

let socket = null;
let zkouska = null;

function pripoj() {
  if (socket && socket.readyState <= 1) return;

  try {
    socket = new WebSocket(`ws://127.0.0.1:${PORT}`);
  } catch (e) {
    naplanuj();
    return;
  }

  socket.onopen = () => {
    socket.send(JSON.stringify({ type: "hello", token: TOKEN }));
  };

  socket.onmessage = async (event) => {
    let prikaz;
    try {
      prikaz = JSON.parse(event.data);
    } catch (e) {
      return;
    }
    const odpoved = await vyrid(prikaz);
    try {
      socket.send(JSON.stringify(odpoved));
    } catch (e) {
      /* spojení mezitím spadlo */
    }
  };

  socket.onclose = () => {
    socket = null;
    naplanuj();
  };

  socket.onerror = () => {
    try {
      socket.close();
    } catch (e) {
      /* už je zavřené */
    }
  };
}

function naplanuj() {
  if (zkouska) return;
  zkouska = setTimeout(() => {
    zkouska = null;
    pripoj();
  }, 3000);
}

// ---------------------------------------------------------------- příkazy

async function vyrid(prikaz) {
  const { id, cmd } = prikaz;
  try {
    switch (cmd) {
      case "ping":
        return { id, ok: true, data: "pong" };

      case "tabs":
        return { id, ok: true, data: await seznamKaret() };

      case "snapshot":
        return { id, ok: true, data: await vKarte(prikaz.tab, { cmd: "snapshot" }) };

      case "click":
        return {
          id,
          ok: true,
          data: await vKarte(prikaz.tab, {
            cmd: "click",
            index: prikaz.index,
            text: prikaz.text || "",
          }),
        };

      case "type":
        return {
          id,
          ok: true,
          data: await vKarte(prikaz.tab, {
            cmd: "type",
            index: prikaz.index,
            text: prikaz.text,
          }),
        };

      case "key":
        return { id, ok: true, data: await vKarte(prikaz.tab, { cmd: "key", keys: prikaz.keys }) };

      case "navigate":
        return {
          id,
          ok: true,
          data: await vKarte(prikaz.tab, { cmd: "navigate", url: prikaz.url }),
        };

      default:
        return { id, ok: false, error: `neznámý příkaz ${cmd}` };
    }
  } catch (e) {
    return { id, ok: false, error: String(e && e.message ? e.message : e) };
  }
}

async function seznamKaret() {
  const karty = await chrome.tabs.query({});
  return karty
    .filter((k) => k.url && !k.url.startsWith("chrome://") && !k.url.startsWith("devtools://"))
    .map((k) => ({ id: k.id, title: k.title || "", url: k.url || "", active: !!k.active }));
}

/** Vybere kartu: podle id, jinak aktivní, jinak první. */
async function vyberKartu(preferovane) {
  if (preferovane) {
    try {
      return await chrome.tabs.get(preferovane);
    } catch (e) {
      /* karta zmizela */
    }
  }
  const aktivni = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (aktivni.length) return aktivni[0];
  const vsechny = await chrome.tabs.query({});
  return vsechny[0];
}

/** Pošle příkaz do content scriptu; když tam není, vloží ho a zkusí znovu. */
async function vKarte(preferovane, zprava) {
  const karta = await vyberKartu(preferovane);
  if (!karta) throw new Error("žádná karta");

  try {
    return await chrome.tabs.sendMessage(karta.id, zprava);
  } catch (e) {
    await chrome.scripting.executeScript({ target: { tabId: karta.id }, files: ["content.js"] });
    // content script se po vložení ještě chvíli registruje
    await new Promise((r) => setTimeout(r, 120));
    return await chrome.tabs.sendMessage(karta.id, zprava);
  }
}

pripoj();
setInterval(pripoj, 10000);
