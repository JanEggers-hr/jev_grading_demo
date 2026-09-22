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
