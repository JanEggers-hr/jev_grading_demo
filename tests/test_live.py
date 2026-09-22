"""Echter Aufruf gegen OpenRouter. Läuft nur mit `uv run --env-file .env pytest -m live`."""

import os

import pytest

from jevdemo.jev_client import JevClient

pytestmark = pytest.mark.live


@pytest.mark.skipif(not os.environ.get("OPENROUTER_API_KEY"), reason="kein OPENROUTER_API_KEY in der Umgebung")
def test_drei_fragetypen_live():
    client = JevClient(os.environ["OPENROUTER_API_KEY"])
    antwort = client.decide(
        {"text_type": "Meinungsbeitrag",
         "text": "Diese Regierung versagt auf ganzer Linie. Wir brauchen endlich mehr Geld für die Bundeswehr."},
        {
            "polemisch": {"type": "noul", "instructions": "Ist der Text polemisch?"},
            "domain": {"type": "choice", "instructions": "Which policy domain is the text about?",
                       "criteria": {"Military": "defence and armed forces", "Welfare": "social policy"}},
            "meinung": {"type": "score", "instructions": "Wie meinungsstark ist der Text?",
                        "criteria": ["neutral", "wertend", "polemisch"]},
        },
    )
    a = antwort["answers"]
    assert 0 <= a["polemisch"]["noul"] <= 1
    assert a["domain"]["choice"] in ("Military", "Welfare")
    assert set(a["domain"]["probabilities"]) == {"Military", "Welfare"}
    assert 0 <= a["meinung"]["score"] <= 2
    assert set(a["meinung"]["probabilities"]) == {"0", "1", "2"}
    assert antwort["usage"]["input_tokens"] > 0
    assert antwort["model"].startswith("typesafe/jev-1.13")
