"""Passwort-Gate mit Brute-Force-Bremse.

Risikoklasse: Tier 4 (siehe docs/adr/001-risk-classification-jev-grading-demo.md).
Änderungen an diesem Modul nur mit menschlichem Review.
"""

import hashlib
import hmac
import math
import os
import threading
import time
from collections import deque


def passwort_ok(eingabe: str, passwort: str) -> bool:
    """Vergleich in konstanter Zeit. Ein leeres Soll-Passwort lässt nie durch."""
    if not passwort:
        return False
    return hmac.compare_digest(eingabe.encode(), passwort.encode())


class Drossel:
    """Zählt Fehlversuche prozessweit in einem gleitenden Fenster.

    Prozessweit, weil eine Sperre pro Session sich durch Neuladen der Seite umgehen ließe.
    Nebenwirkung: Während einer Sperre kommen auch Berechtigte nicht rein.
    """

    def __init__(self, max_fehler: int = 10, fenster: float = 600, uhr=time.monotonic):
        self.max_fehler = max_fehler
        self.fenster = fenster
        self.uhr = uhr
        self._fehler: deque[float] = deque()
        self._lock = threading.Lock()

    def _aufraeumen(self, jetzt: float) -> None:
        while self._fehler and self._fehler[0] <= jetzt - self.fenster:
            self._fehler.popleft()

    def fehler(self) -> None:
        with self._lock:
            jetzt = self.uhr()
            self._aufraeumen(jetzt)
            self._fehler.append(jetzt)

    def gesperrt(self) -> float:
        """Sekunden bis zum Ende der Sperre, 0 wenn offen."""
        with self._lock:
            jetzt = self.uhr()
            self._aufraeumen(jetzt)
            if len(self._fehler) < self.max_fehler:
                return 0
            return self._fehler[-self.max_fehler] + self.fenster - jetzt


PAUSE = 1.0  # Sekunden Wartezeit nach jedem Fehlversuch
DROSSEL = Drossel()  # eine für den ganzen Streamlit-Prozess


def gate() -> None:
    """Hält die Seite an, bis das Passwort stimmt.

    Vorbedingung: APP_PASSWORD und OPENROUTER_API_KEY sind gesetzt, sonst Fehler und Stopp.
    Nachbedingung beim Zurückkehren: st.session_state["authed"] ist True.
    Jede neue falsche Eingabe zählt einmal in DROSSEL und kostet PAUSE Sekunden.
    Solange DROSSEL sperrt, wird gar nicht verglichen.
    """
    import streamlit as st  # erst hier, damit die Bremse ohne Streamlit testbar bleibt

    passwort = os.environ.get("APP_PASSWORD", "")
    fehlend = [n for n in ("APP_PASSWORD", "OPENROUTER_API_KEY") if not os.environ.get(n)]
    if fehlend:
        st.error(f"Umgebungsvariable fehlt: {', '.join(fehlend)}. Siehe .env.example.")
        st.stop()
    if st.session_state.get("authed"):
        return
    st.title("Jev Grading Demo")
    eingabe = st.text_input("Passwort", type="password")
    if not eingabe:
        st.stop()
    rest = DROSSEL.gesperrt()
    if rest:
        st.error(f"Zu viele Fehlversuche. Bitte in {math.ceil(rest / 60)} Minuten erneut versuchen.")
        st.stop()
    if passwort_ok(eingabe, passwort):
        st.session_state["authed"] = True
        st.session_state.pop("letzter_fehlversuch", None)
        st.rerun()
    fingerabdruck = hashlib.sha256(eingabe.encode()).hexdigest()  # kein Klartext in der Session
    if st.session_state.get("letzter_fehlversuch") != fingerabdruck:
        st.session_state["letzter_fehlversuch"] = fingerabdruck
        DROSSEL.fehler()
        time.sleep(PAUSE)
    st.error("Falsches Passwort")
    st.stop()
