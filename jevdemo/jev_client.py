"""Jev (TypeSafe System One) über OpenRouter: POST /api/alpha/decisions.

Der Body ist das native TypeSafe-Format {model, state, questions}; die Antwort
ebenfalls, plus usage.cost in USD. chat/completions lehnt Jev ab (geprüft 2026-09-22).
Nur Standardbibliothek, wie im Referenzprojekt.
"""

import json
import os
import time
import urllib.error
import urllib.request

ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
MODEL = "typesafe/jev-1.13"
PREIS_JE_M_INPUT = 0.042  # USD je 1 Mio. Input-Token; Output kostenlos (Stand 2026-09)
RETRY_STATUS = {429, 500, 502, 503, 529}


class JevFehler(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(f"HTTP {status}: {detail[:300]}")
        self.status = status
        self.detail = detail


class ZuLang(JevFehler):
    """HTTP 400 mit max_tokens_exceeded: der State passt nicht ins Kontextfenster."""


class JevClient:
    def __init__(self, api_key: str, model: str = MODEL, endpoint: str | None = None,
                 timeout: int = 120, retries: int = 4, schlaf=time.sleep):
        self.api_key = api_key
        self.model = model
        self.endpoint = endpoint or os.environ.get("JEV_ENDPOINT", ENDPOINT)
        self.timeout = timeout
        self.retries = retries
        self.schlaf = schlaf

    def decide(self, state, questions: dict) -> dict:
        """Ein Aufruf mit allen Fragen -> Antwort-dict (answers, usage, model, ...) plus 'sekunden'."""
        body = json.dumps({"model": self.model, "state": state, "questions": questions}).encode()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://woistderbus.interaktive-projekte.de/jev_grading_demo/",
            "X-Title": "jev_grading_demo",
        }
        for versuch in range(self.retries + 1):
            request = urllib.request.Request(self.endpoint, data=body, headers=headers, method="POST")
            start = time.perf_counter()
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as antwort:
                    daten = json.loads(antwort.read())
                    daten["sekunden"] = round(time.perf_counter() - start, 3)
                    return daten
            except urllib.error.HTTPError as e:
                detail = e.read().decode(errors="replace")
                if e.code in RETRY_STATUS and versuch < self.retries:
                    self.schlaf(2**versuch)
                    continue
                if e.code == 400 and "max_tokens_exceeded" in detail:
                    raise ZuLang(e.code, detail) from e
                raise JevFehler(e.code, detail) from e
            except (urllib.error.URLError, TimeoutError) as e:
                if versuch < self.retries:
                    self.schlaf(2**versuch)
                    continue
                raise JevFehler(0, str(e)) from e
        raise AssertionError("unreachable")


def cost_usd(usage: dict) -> float:
    if usage.get("cost") is not None:
        return float(usage["cost"])
    return usage.get("input_tokens", 0) / 1e6 * PREIS_JE_M_INPUT
