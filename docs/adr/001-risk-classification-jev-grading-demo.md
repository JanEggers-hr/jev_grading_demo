# 001. Risk Classification — jev_grading_demo

Datum: 2026-09-23

## Status

Proposed

## Kontext

Die Jev Grading Demo ist eine Streamlit-App: PDF hochladen, Text extrahieren (PyMuPDF), mit Jev 1.13 über
OpenRouter bewerten, Ergebnisse als Farbfelder, Balken und JSON-Download. Sie läuft als Container auf dem
Weihnachtswunderserver unter https://woistderbus.interaktive-projekte.de/jev_grading_demo/, geschützt durch ein
geteiltes Passwort. Der Code ist vollständig KI-generiert: alle 32 Commits tragen einen `Co-Authored-By: Claude`-Trailer.

Die Bewertung lief mit `/risk-assess` (Vibe-Coding Risk Radar). Das Repo ist ein einziges Modul. Der Tier ist das
Maximum der fünf Dimensionen, jede auf einer Skala von 0 bis 4.

| Dimension | Score | Begründung |
|---|---|---|
| Code Type | 4 | `_gate()` in `app.py` (Zeilen 22–38) ist Zugriffskontrolle: geteiltes Passwort, Vergleich per `hmac.compare_digest`, Flag in `st.session_state`. Es schützt einen bezahlten OpenRouter-Key auf einer öffentlich erreichbaren URL. Der Regex-Scan fand nichts, weil die Bezeichner deutsch sind (`passwort`, `authed`); der Befund ist manuell. Der Rest des Codes läge bei 3 (OpenRouter-Client mit Bearer-Token, Streamlit als Webserver) bzw. 2 (Chunking, Scoring, Manifesto-Logik). |
| Language | 2 | 27 Python-Dateien, keine anderen bewerteten Sprachen. Type Hints vorhanden, aber kein Type Checker. |
| Deployment | 1 | Entscheidung des Owners: faktisch ein internes Team-Tool. Die URL ist öffentlich erreichbar (Auto-Vorschlag war deshalb 2), davor steht aber das Passwort. Keine Regulierungs-Keywords im Code. |
| Data Sensitivity | 1 | Regex-Scan ohne Treffer. Vorgesehen sind öffentliche Parteiprogramme (0), hochladen lässt sich aber jedes PDF, auch unveröffentlichte Entwürfe. Der Text geht an OpenRouter als Drittanbieter. Auf dem Server wird nichts persistiert. Randfall: Texte identifizierbarer Privatpersonen ergäben eine Einordnung politischer Meinungen (Art. 9 DSGVO); das ist nicht Zweck der App. |
| Blast Radius | 1 | Entscheidung des Owners. Keine Persistenz, also kein Datenverlust. Worst Case: verbranntes API-Guthaben, Key-Rotation, RAM-Erschöpfung auf dem Host neben dem Produktions-Tracker. |

### Befunde aus dem Scan

Risiken:

1. **Gate ohne Brute-Force-Schutz.** Beliebig viele Versuche, weder Zähler noch Verzögerung.
2. **Gate ohne Tests.** Kein Test berührt `_gate`, `APP_PASSWORD` oder `authed`. Der einzige Tier-4-Code ist
   ungetestet, während die 70 übrigen Tests offline grün sind.
3. **Unbegrenzte Caches.** Die drei `st.cache_data`-Funktionen in `app.py` (Zeilen 41, 51, 56) haben weder `ttl` noch
   `max_entries`; extrahierte PDF-Texte sammeln sich sessionübergreifend im RAM. `compose.yaml` setzt kein
   Speicherlimit. Der Host hat 7,7 GiB RAM, keinen Swap und betreibt nebenan die Produktions-App.
4. **Geteiltes Docker-Netz.** Der Container hängt im Netz `weihnachtswunder-gps-tracker_default`, zusammen mit Caddy
   und der Tracker-App. Ungeprüft ist, ob die Tracker-App ihren Admin-Bereich selbst schützt oder sich allein auf die
   Basic Auth in Caddy verlässt. Im zweiten Fall käme ein kompromittierter Demo-Container direkt an `app:3000` heran,
   an der Auth vorbei.
5. **C-Parser auf fremden Uploads.** PyMuPDF 1.28.2 bringt MuPDF (C) mit und parst jede hochgeladene Datei. Der Upload
   liegt hinter dem Gate, was die Angriffsfläche verkleinert.
6. **Keine automatischen Gates.** Kein Linter, kein Type Checker, kein CI, kein Pre-Commit, kein Dependency-Audit;
   `main` ist ungeschützt, es wird direkt gepusht.

Was schon stimmt:

- Keine Secrets in der Git-Historie. Die `APP_PASSWORD=`-Treffer in `docs/` sind Platzhalter; das lokale
  Dev-Passwort steht in keinem Commit.
- `.env` ist per `.gitignore` und `.dockerignore` ausgeschlossen; das Image enthält nur explizit kopierte Dateien.
- Der Container läuft als Nicht-Root (uid 1000); Abhängigkeiten sind per `uv.lock` gepinnt und werden mit
  `--frozen` installiert.
- Der Passwortvergleich läuft in konstanter Zeit; Streamlits XSRF-Schutz ist nicht abgeschaltet.

## Entscheidung

Das Modul `jev_grading_demo` wird als **Tier 4** eingestuft, bestimmt durch **Code Type = 4**. Alle anderen
Dimensionen liegen bei 2 oder darunter. Der Owner hat die strenge Lesart des Modells gewählt. Die verworfene
Alternative war, das Gate als Beiwerk zu werten (Code Type 3, damit Tier 3).

**Vorschlag zur verhältnismäßigen Umsetzung** (Teil des Status *Proposed*, braucht Bestätigung): Die
Tier-4-Maßnahmen gelten für den Tier-4-Code, also `_gate()`. Für den Rest der App gelten die Maßnahmen der Tiers 1
bis 3. Begründung: Durch die Max-Aggregation bestimmen 17 Zeilen den Tier der ganzen App. Formale Verifikation einer
Streamlit-Oberfläche kostet viel und bringt nichts.

Konkret für das Gate:

- **Contract statt Beweis:** Vor- und Nachbedingungen im Docstring festhalten und mit Tests absichern, MC/DC-artig
  über die vier Bedingungen (Env-Variable fehlt, schon angemeldet, Eingabe leer, Vergleich wahr oder falsch).
  Streamlits `AppTest` reicht dafür.
- **Brute-Force-Bremse:** Fehlversuche pro Session zählen und verzögern oder sperren.
- **KI nur als Entwurfshilfe:** Änderungen an `_gate()` nur mit menschlichem Review.
- **Option:** Das Gate nach `jevdemo/auth.py` auslagern. Dann ist es ein eigenes, separat bewertbares Modul, und
  der Rest der App fällt auf Tier 3.

## Konsequenzen

Positiv:

- Das Gate, bisher ungetestet und ohne Brute-Force-Schutz, bekommt die Aufmerksamkeit, die es als einzige Tür vor
  dem API-Key verdient.
- Die Tier-1-Grundausstattung (Ruff, pip-audit, pytest in GitHub Actions) ist billig und fängt typische Fehler früh.
- Die Herkunft des Codes ist dokumentiert: Spec und Plan in `docs/superpowers/`, Co-Authored-By-Trailer in jedem
  Commit.

Negativ:

- Tier 4 verlangt formal Maßnahmen wie unabhängige Re-Verifikation und Zertifizierung, die für eine Demo
  unverhältnismäßig sind. Ohne die Beschränkung auf `_gate()` wird die Einstufung zum Theater.
- „KI nur als Entwurfshilfe“ widerspricht dem Entstehungsweg der App. Für das Gate heißt das künftig Handarbeit
  oder Review.
- CI, SAST und Dependency-Audit erzeugen Pflegeaufwand für ein Projekt mit begrenzter Lebensdauer.
- Härtung auf dem Server (Speicherlimit, eigenes Netz) braucht `sudo` auf einer Maschine mit Produktions-App; jeder
  Block braucht laut CLAUDE.md eine ausdrückliche Freigabe.

Reihenfolge nach Aufwand und Nutzen:

1. Tests für `_gate()` und eine Brute-Force-Bremse.
2. `max_entries` bzw. `ttl` an den Caches, `mem_limit` in `compose.yaml`.
3. Ruff, pip-audit und pytest in GitHub Actions; Branch-Protection mit Pflicht-CI auf `main`.
4. Prüfen, ob `app:3000` der Tracker-App ohne Caddy-Auth erreichbar ist; falls ja, die Demo in ein eigenes Netz
   legen, das sie nur mit Caddy teilt.
5. Semgrep im CI; Fuzzing des PDF-Pfads nur, wenn die Demo länger lebt.

## Nachtrag 2026-09-23: Umsetzung

Erledigt, Status des ADR bleibt *Proposed*:

- Gate nach `jevdemo/auth.py` ausgelagert, mit Contract im Docstring. Damit ist die Option aus der Entscheidung
  umgesetzt; eine getrennte Bewertung des Moduls steht noch aus.
- Brute-Force-Bremse: 10 Fehlversuche in 10 Minuten sperren prozessweit, jeder Fehlversuch kostet 1 s. Ein Rerun mit
  derselben Eingabe zählt nicht doppelt; in der Session liegt nur ein Hash der letzten Fehleingabe.
- Tests: `tests/test_auth.py` (Bremse, Vergleich) und `tests/test_gate.py` (AppTest gegen die echte App).
- Caches: `max_entries` und `ttl=3600` an allen drei `st.cache_data`-Funktionen.
- `compose.yaml`: `mem_limit: 2g`, `pids_limit: 256`, `cap_drop: ALL`, `no-new-privileges`. Lokal mit Podman
  geprüft; auf dem Server noch nicht ausgerollt.
- Ruff-Lint, pytest und pip-audit in GitHub Actions. pip-audit fand keine bekannten Schwachstellen.

Offen: Ausrollen auf den Server, eigenes Docker-Netz, Type Checker, Pre-Commit, SAST, menschliches Review von
`jevdemo/auth.py`.
