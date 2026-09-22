# Demo: Textbewertung mit Jev

Können wir Texte in einem vorgegebenen Schema politisch klassifizieren, mithilfe von KI? Also zum Beispiel sagen: "In diesem Parteiprogramm werden diese und diese"

## Das Bewertungsschema...

...haben wir für den Start vom [MANIFESTO-Projekt](https://manifesto-project.wzb.eu) geklaut: Es wurde für Parteiprogramme entwickelt und misst positive und negative Positionierungen auf einzelnen Themenfeldern, z.B.: Militär: pro oder contra? Das Codebuch und eine JSON-Datei mit dem Coding-Schema liegen im Ordner ``manifesto``.

Das Schema ist eher für nationalen und internationalen Vergleich da, nicht für Regionalwahlen - aber man kann es benutzen, um durch Aufsummieren der Dimensionen ein paar einfache Einstufungen zu treffen: 

Ist der Text programmatisch eher...
- links oder rechts? (Variable: rile)
- planwirtwschaftlich, also in Richtung: Regulierung und Planung? (planeco)
- marktwirtschaftlich, also in Richtung: Deregulierung und Anreizsteuerung? (markeco)
- welfare
- intpeace

## Welche KI kommt zum Einsatz?

- Jev ist ein sehr neues, spezialisiertes Sprachmodell für Entscheidungen (veröffentlicht 09/2026). Es liefert Antworten auf drei Arten von Fragen: 
    - Noul: Trifft die Frage zu? (0-1)
    - Choice: Option aus einer Liste (choice, probabilities, confidence)
    - Score: Bewerte auf einer Skala; als Stufen einer Leiter angegeben (score, probabilities, confidence)

## Was ich machen kann: 

- Voreingestellt sind die Bewertungsfragen aus dem MANIFESTO-Schema. 
- Ich kann Kategorien im User-Interface neu anlegen, löschen, oder verändern. 

## Die Demo benutzen

1. Link öffnen, gemeinsames Passwort eingeben.
2. PDF in die Upload-Zone ziehen. Die App zeigt Seiten, Zeichen und geschätzte Token.
3. Modus wählen:
   - **Gesamttext**: ein Aufruf über den ganzen Text. Jev nimmt maximal rund 26.000 Token je Aufruf;
     längere Texte werden abgeschnitten, die App sagt, wie viel Prozent bewertet wurden.
   - **Chunks**: der Text wird in Stücke geteilt (Slider), jedes Stück einzeln bewertet, die Ergebnisse
     werden token-gewichtet gemittelt. Deckt den ganzen Text ab und ist beim Manifesto-Schema näher am
     Original-Verfahren (Kodierung kleiner Einheiten, dann Anteile).
   - **Beide**: nebeneinander.
4. "Bewerten". Ergebnisse: Manifesto-Anteile und Kennzahlen als Balken, Score-Leitern als Balken je Stufe,
   Choice und Noul als Farbfelder. Download als JSON (mit allen Rohantworten je Einheit) und der
   extrahierte Text als TXT.

## Fragen anpassen

Die Fragen stehen in `config.yaml` und lassen sich in der Seitenleiste je Block ändern, löschen oder
ergänzen; "Zurücksetzen" holt die Datei zurück, "Config als YAML herunterladen" sichert den Stand.
Die Datei auf dem Server wird nie verändert.

| Typ | Felder | Jev antwortet mit |
| --- | --- | --- |
| `noul` | `instructions` | Wert 0 bis 1: trifft die Aussage zu? |
| `choice` | `instructions`, `criteria` als Mapping Option → Beschreibung | Wahl, Wahrscheinlichkeiten, Confidence |
| `score` | `instructions`, `criteria` als geordnete Liste (Leiter), `skala: [min, max]` | Erwartete Stufe, Verteilung, Confidence; die App rechnet auf die Skala um |
| `manifesto` | `instructions`, `domains`, `kennzahlen` | Choice über die 57 Manifesto-Hauptkategorien; daraus Anteile, Domänen, rile, planeco, markeco, welfare, intpeace |

Die Frage schlägt den Instruction-Prompt: Jev bekommt jede Frage einzeln mit ihrer Instruction, der
Text geht als `state` mit dem `text_typ` aus der Config.

## Entwicklung

```bash
uv sync
cp .env.example .env        # OPENROUTER_API_KEY und APP_PASSWORD eintragen
uv run pytest               # ohne Netz
uv run --env-file .env pytest -m live   # ein echter Aufruf gegen OpenRouter
uv run --env-file .env streamlit run app.py --server.baseUrlPath jev_grading_demo
```

Deployment: siehe `docs/superpowers/specs/2026-09-22-jev-grading-demo-design.md`, Abschnitt 11.
