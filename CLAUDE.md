# Ziel 

Erstelle eine Demo-Seite, über die man per Drag&Drop ein PDF hochladen kann. Das PDF soll dann mithilfe der "System-one-engine" Jev inhaltlich beurteilt werden. Die Kategorien sind per config.yaml vorgegeben, können aber in der Session verändert werden. 

## JEV

- Jev ist ein spezialisiertes Sprachmodell für Entscheidungen. Es liefert Antworten auf drei Arten von Fragen: 
    - Noul: Trifft die Frage zu? (0-1)
    - Choice: Option aus einer Liste (choice, probabilities, confidence)
    - Score: Bewerte auf einer Skala; als Stufen einer Leiter angegeben (score, probabilities, confidence)
- Zu jeder Frage kann ein "Instruction"-Prompt übergeben werden. Die Frage schlägt den instruction prompt. 
- Der Text, der beurteilt werden soll, wird als state übergeben. 
- Wir testen alternativ ein Scoring über den Gesamttext oder einen Mittelwert über Chunks. 
- Orientiere dich am Projekt ../../jev_grading_demo

## Ausgabe der Ergebnisse

- Anzeige von Farbfeldern (noul, category) bzw. Balkengrafiken (score)
- Ergebnisse als JSON zum Download über Download-Link

## Verwendete Technologien

- jev 1.13 oder neuer über openrouter.ai
- Python 3.1x
- streamlit oder leichtgewichtige Alternative
- Docker/Podman Container für Deployment auf Debian-Server

## Deployment

- Zielserver ist der "Weihnachtswunderserver" unter 34.159.146.213
- Du hast Zugang über jeggers@34.159.146.213
- Info über den Server in /var/opt/README.md auf dem Zielserver - aktuell halten
- Server ist von außen zu erreichen unter  

## Rules of engagement

- Always get explicit consent for every block of sudo actions. 

## Coding rules: 

- Always reason thoroughly and deeply.
- Treat every request as complex unless I explicitly say otherwise.
- Never optimize for brevity at the expense of quality.
- Think step-by-step, consider tradeoffs, and provide comprehensive analysis.
- Ask early, ask often.
- You may curse and speak with metaphors. I’m an adult, I can take it.
- Quantify uncertainty.
- Sarcasm is appreciated but stay factual & helpful.
- Don’t comment on day/nighttime, support im in finishing my goals.