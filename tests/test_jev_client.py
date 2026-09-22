import io
import json
import urllib.error
import urllib.request

import pytest

from jevdemo.jev_client import JevClient, JevFehler, ZuLang, cost_usd

OK = {
    "model": "typesafe/jev-1.13-20260917",
    "answers": {"q": {"type": "noul", "noul": 0.8}},
    "usage": {"input_tokens": 284, "output_tokens": 22, "cost": 0.000011928},
    "id": "gen-dec-1", "provider": "TypeSafe",
}


class _Antwort:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _http_error(code: int, body: str) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://x", code, "msg", {}, io.BytesIO(body.encode()))


def _folge(monkeypatch, ergebnisse: list):
    """urlopen-Ersatz, der die Ergebnisse der Reihe nach liefert oder wirft; gibt die Requests zurück."""
    aufrufe = []

    def urlopen(request, timeout=None):
        aufrufe.append(request)
        ergebnis = ergebnisse.pop(0)
        if isinstance(ergebnis, Exception):
            raise ergebnis
        return _Antwort(ergebnis)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    return aufrufe


def _client(**kw) -> tuple[JevClient, list]:
    schlaf = []
    return JevClient("k", schlaf=schlaf.append, **kw), schlaf


def test_body_header_und_antwort(monkeypatch):
    aufrufe = _folge(monkeypatch, [OK])
    client, _ = _client()
    antwort = client.decide({"text_type": "t", "text": "x"}, {"q": {"type": "noul", "instructions": "?"}})
    req = aufrufe[0]
    assert req.full_url == "https://openrouter.ai/api/alpha/decisions"
    assert json.loads(req.data) == {
        "model": "typesafe/jev-1.13",
        "state": {"text_type": "t", "text": "x"},
        "questions": {"q": {"type": "noul", "instructions": "?"}},
    }
    assert req.get_header("Authorization") == "Bearer k"
    assert req.get_header("Content-type") == "application/json"
    assert antwort["answers"]["q"]["noul"] == 0.8
    assert antwort["sekunden"] >= 0


def test_endpoint_aus_umgebung(monkeypatch):
    monkeypatch.setenv("JEV_ENDPOINT", "https://example.test/dec")
    client, _ = _client()
    assert client.endpoint == "https://example.test/dec"


def test_retry_bei_429_dann_erfolg(monkeypatch):
    aufrufe = _folge(monkeypatch, [_http_error(429, "zu viel"), OK])
    client, schlaf = _client()
    assert client.decide("s", {})["answers"]["q"]["noul"] == 0.8
    assert len(aufrufe) == 2
    assert schlaf == [1]


def test_retry_bei_netzfehler(monkeypatch):
    aufrufe = _folge(monkeypatch, [urllib.error.URLError("dns"), OK])
    client, schlaf = _client()
    client.decide("s", {})
    assert len(aufrufe) == 2 and schlaf == [1]


def test_zu_lang(monkeypatch):
    _folge(monkeypatch, [_http_error(400, '{"error":{"message":"HTTP 400: {\\"detail\\":{\\"error_type\\":\\"max_tokens_exceeded\\"}}"}')])
    client, schlaf = _client()
    with pytest.raises(ZuLang) as e:
        client.decide("s", {})
    assert e.value.status == 400
    assert schlaf == []


def test_anderer_400_ist_jevfehler(monkeypatch):
    _folge(monkeypatch, [_http_error(400, "kaputt")])
    client, _ = _client()
    with pytest.raises(JevFehler) as e:
        client.decide("s", {})
    assert not isinstance(e.value, ZuLang)
    assert e.value.status == 400 and "kaputt" in str(e.value)


def test_500_erschoepft_wiederholungen(monkeypatch):
    aufrufe = _folge(monkeypatch, [_http_error(500, "a"), _http_error(500, "b")])
    client, schlaf = _client(retries=1)
    with pytest.raises(JevFehler) as e:
        client.decide("s", {})
    assert e.value.status == 500 and len(aufrufe) == 2 and schlaf == [1]


def test_cost_usd():
    assert cost_usd({"cost": 0.5, "input_tokens": 1}) == 0.5
    assert cost_usd({"input_tokens": 1_000_000}) == pytest.approx(0.042)
    assert cost_usd({}) == 0.0
