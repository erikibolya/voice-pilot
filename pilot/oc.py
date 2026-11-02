"""Klient pro lokální OpenCode službu (127.0.0.1:28894).

Používá stejné přihlášení jako desktopová aplikace: HTTP Basic s uživatelem
"opencode" a heslem z ~/.config/opencode/service.json. Klíč k modelu tak
nemusí být nikde v projektu.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx


class OpenCodeError(RuntimeError):
    pass


class OpenCode:
    def __init__(self, url: str, password_file: str, provider_id: str, model_id: str):
        self.url = url.rstrip("/")
        self.password_file = Path(password_file)
        self.provider_id = provider_id
        self.model_id = model_id
        self._client = httpx.Client(timeout=120.0)

    def _password(self) -> str:
        if not self.password_file.exists():
            raise OpenCodeError(
                f"Nenacházím přihlášení k OpenCode ({self.password_file}). "
                "Běží desktopová aplikace OpenCode?"
            )
        return json.loads(self.password_file.read_text(encoding="utf-8"))["password"]

    def auth(self) -> tuple[str, str]:
        return ("opencode", self._password())

    def info(self) -> dict:
        r = self._client.get(f"{self.url}/api/info", auth=self.auth())
        r.raise_for_status()
        return r.json()

    def generate(self, prompt: str) -> str:
        """Jednořázové volání modelu bez historie. Vrací prostý text."""
        r = self._client.post(
            f"{self.url}/api/experimental/generate/text",
            json={
                "prompt": prompt,
                "model": {"providerID": self.provider_id, "id": self.model_id},
            },
            auth=self.auth(),
        )

        if r.status_code != 200:
            raise OpenCodeError(_explain(r))

        payload = r.json()
        return payload.get("data", {}).get("text", "").strip()


def _explain(response: httpx.Response) -> str:
    try:
        body = response.json()
    except Exception:
        return f"HTTP {response.status_code}: {response.text[:200]}"

    tag = body.get("_tag", "")
    msg = body.get("message") or body.get("reason") or ""
    if tag == "ProviderRequestError":
        pid = body.get("providerID", "?")
        return f"Model {pid} odmítl požadavek ({body.get('reason', '?')}): {msg}"
    return f"{tag or 'chyba'}: {msg or response.text[:200]}"
