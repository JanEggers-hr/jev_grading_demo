"""Schlüssel aus einer .env-Datei in die Umgebung laden, ohne vorhandene zu überschreiben."""

import os
from collections.abc import MutableMapping
from pathlib import Path


def lade_env(pfad: Path, umgebung: MutableMapping[str, str] = os.environ) -> None:
    pfad = Path(pfad)
    if not pfad.is_file():
        return
    for zeile in pfad.read_text(encoding="utf-8").splitlines():
        zeile = zeile.strip().removeprefix("export ").strip()
        if not zeile or zeile.startswith("#") or "=" not in zeile:
            continue
        name, wert = zeile.split("=", 1)
        name, wert = name.strip(), wert.strip()
        if len(wert) >= 2 and wert[0] == wert[-1] and wert[0] in "\"'":
            wert = wert[1:-1]
        umgebung.setdefault(name, wert)
