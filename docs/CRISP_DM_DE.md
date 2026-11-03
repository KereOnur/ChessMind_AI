# NeuroChess nach CRISP-DM

CRISP-DM gliedert das Projekt in sechs Phasen. Messergebnisse können eine Rückkehr zur Datenauswahl oder Modellierung begründen. [IBM CRISP-DM Guide](https://www.ibm.com/docs/en/SS3RA7_18.5.0/pdf/ModelerCRISPDM.pdf).

## 1. Business Understanding

Ein lokales Schachspiel macht nachvollziehbar, wie Zugberechnung, Stellungsbewertung und Lernen zusammenwirken. Spieler können auf drei Brettern gegen drei Gegner antreten. Die Adaptive-KI soll ihre Stellungsbewertung anhand beobachteter Partien verändern. NeuroChess implementiert Suche und Bewertung selbst und verwendet python-chess für die Schachregeln. Eine externe Engine, Eröffnungsdatenbank oder Elo-Vorgabe gehört nicht zum Ansatz.

Messbare Ziele sind legale Züge, reproduzierbare Tests, konsistente Spielstände und identische Paarbedingungen für 200 Testpartien je Version. Das 600-Partien-Training muss seine Farbverteilung einhalten und allein die Trainingskopie verändern. CPU, Speicher und Antwortzeit begrenzen die Suche. Mehr Punkte in einem Kurztest dienen als Entscheidungshilfe innerhalb dieses Protokolls.

## 2. Data Understanding

Ein Spiel erzeugt Ausgangsstellung, legale Züge, Uhren, Ereignisse und Ergebnis. SQLite enthält UCI-Züge zur Rekonstruktion und SAN für die Zugliste. Die Zugfolge bleibt erhalten, weil eine einzelne FEN Wiederholungen nicht abbildet. Das Lernmodell speichert fünf Gewichte, Revisions-IDs, Start- und Endmodelle je Partie, TD-Vorhersage, Zielwert und Fehler. Die Daten stammen aus lokalen menschlichen Partien sowie separaten automatisierten Läufen. Es gibt keinen importierten personenbezogenen Datensatz.

Spieltabellen sichern Zustand und Fortsetzslot. Lerntabellen speichern unveränderliche Modellrevisionen, Fortschritt und Kandidaten. Training und Vergleich haben getrennte Lauf- und Ergebnistabellen. Modellvergleiche speichern außerdem Suchmanifest, feste Seeds, Snapshots und Entscheidungen.

## 3. Data Preparation

python-chess verwaltet Brett, Zugrecht, Rochaderechte, En passant und die Wiederholungshistorie. Beim Laden wird die Zugfolge erneut geprüft. Für die adaptive Bewertung liefern die gemeinsamen Bewertungsbausteine Weiß minus Schwarz. Die fünf Rohwerte werden durch feste Skalen geteilt und auf −1 bis +1 begrenzt.

| Merkmal | Berechnung | Skala |
| --- | --- | ---: |
| Figurenaktivität | Entwicklung, Figurenstandorte, offene Turmlinien und Aktivitätsabzüge plus Mobilität | 160 |
| Zentrumskontrolle | Bauernbesetzung und Angriffe auf d4, e4, d5 und e5 | 80 |
| Königssicherheit | Bauernschutz, gegnerische Angriffe, Königsposition | 100 |
| Bauernstruktur | Verbundene, isolierte, doppelte und freie Bauern | 160 |
| Endspielstrategie | Königszentralität und Königsdistanzen vor Freibauern, nach Phase gewichtet | 120 |

Material bleibt ein fester Summand. Lernen arbeitet unabhängig vom Zugrecht aus Sicht von Weiß. Die Suche dreht den Wert bei Schwarz am Zug um. Ein legaler, gespeicherter Zug erzeugt höchstens ein Übergangsereignis. Ein reguläres Partieende erzeugt zusätzlich ein Ergebnissignal. Eine nur gespeicherte Partie zählt erst nach Beendigung zur Zahl abgeschlossener Lernpartien. In automatischen Trainingsläufen werden vollständige Partien atomar bestätigt. Das Trainingsprotokoll wertet beim 48-Halbzuglimit die Trainingspartie als Remis-Lernsignal. Phase 9.6 trennt technische Vergleichsenden davon und lässt sie ohne Ergebnis. [Quellcode der adaptiven Merkmale](../ai/adaptive.py).

## 4. Modeling

**Amateur** prüft ein bis zwei Halbzüge mit festem Bewertungsprofil und wählt mit gesetztem Zufall teilweise aus ähnlich bewerteten Alternativen. **Großmeister** nutzt Negamax mit Alpha–Beta, iterative Vertiefung, Zugvorsortierung, begrenzte Ruhesuche und Transpositionstabelle. Zeit- und Knotengrenzen schützen den Rechner. Der Name bezeichnet den Spielmodus, ein Elo-Niveau wurde nicht gemessen. **Adaptive Grandmaster AI** verwendet denselben Suchrahmen, aber eine getrennte Bewertung. Matt und andere Endergebnisse werden vor der statischen Bewertung behandelt.

Die adaptive Bewertung lautet `S = Material + 100 · Σ(wᵢ · xᵢ)`. Das Lernmodell verwendet `V = tanh(S / 600)`. TD(0) bildet nach einem Halbzug das Ziel `0,99 · V(Folgestellung)` und zieht die Vorhersage der Ausgangsstellung ab. Für ein zusätzliches terminales Ereignis ist das Ziel +1 bei Weißsieg, −1 bei Schwarzsieg und 0 bei Remis. Der Gradient je Merkmal lautet `(100/600) · (1 − V²) · xᵢ`. Der Code multipliziert ihn mit TD-Fehler und Lernrate 0,015. Er begrenzt jeden Schritt auf ±0,01 und die Gewichte auf 0,5 bis 1,5. Nicht endliche oder ungültige Parameter werden abgewiesen.

Ein vereinfachtes Rechenbeispiel beginnt mit Vorhersage 0,20 und Folgewert 0,40. Das Ziel ist 0,396, der TD-Fehler +0,196. Ein positiv ausgeprägtes Merkmal mit Wert 0,5 erhält dadurch ein Plus von rund 0,000235. Der kleine Schritt zeigt, dass ein einzelner Zug die Bewertungsstrategie nur gering verschiebt. [TD-Implementierung](../learning/td.py), [Sutton 1988](https://jmvidal.cse.sc.edu/library/sutton88a.pdf).

Jeder Modellstand besitzt eine eigene Revision. Das menschliche Lernen aktualisiert die aktive Adaptive-KI. Der automatische Lauf verarbeitet 600 Partien, je 200 gegen Amateur, Großmeister und eingefrorene Adaptive-Referenz. Je Gegner spielt die Trainingskopie 100-mal Weiß und 100-mal Schwarz. Alle TD-Schritte wirken auf diese Kopie. Pro bestätigter Partie sichert SQLite Ergebnis und Gewichte. Erst der vollständige Lauf veröffentlicht einen Kandidaten. Die Referenz bleibt als Rückfallstand bestehen.

## 5. Evaluation

Automatisierte Tests decken Regelgrenzen, Uhren, gespeicherte Züge, Modelltrennung, Neustart, Worker-Abbruch und GUI-Navigation ab. Der native Test prüft den Einstiegspunkt, alle drei Gegner und die SQLite-Anbindung. Der getrennte Vergleich verwendet 400 Partien, eingefrorene Modelle und je Paar identische Gegner, Farben, Stellung, Seeds und Suchgrenzen. Phase 9.6 nutzt 96 weitere Halbzüge, bis zu 128 Suchknoten und zwei Haupthalbzüge bei Adaptive und Großmeister. Der Schwerpunkt liegt auf Endspielen.

Die Punktequote je Modell verwendet regulär beendete Partien. Der Paarvergleich nutzt nur Paare mit zwei regulären Ergebnissen. Das geschichtete Bootstrap-Intervall beschreibt die beobachteten Paare, und die Ergebnisgrenzen zeigen den möglichen Einfluss technischer Abbrüche. Der historische Vergleich von #228 gegen #1 ergab 48,00 % gegen 47,75 %, mit damaliger Einrechnung technischer Limitremis. Die verbesserte Methode ergab für #229 gegen #1 51,7 % gegen 46,8 % unter regulären Ergebnissen. 346 von 400 Partien endeten regulär. Bei 165 beidseitig regulären Paaren betrug die Differenz +4,85 Prozentpunkte. Die Gesamtdifferenz mit offenen Ausgängen kann zwischen −9,25 und +17,75 Punkten liegen. Der Vorsprung reicht daher nicht zur Freigabe. Diese aggregierten Befunde sind ohne persönliche Spielzüge dokumentiert.

Nächste sinnvolle Schritte wären vielfältigere unabhängige Startstellungen, längere Rechenbudgets und gezielte Mattführungstests. Die Kurztests bilden weder eine echte Rapid-15+10-Uhr noch einen Elo-Vergleich ab.

## 6. Deployment

`main.py` startet PySide6. `ui/` enthält Dialoge und Worker, `game/` Regeln und Uhren, `ai/` Suche, `learning/` Lernlogik und `evaluation/` die automatischen Verfahren. `database/` kapselt SQLite. In PyCharm wird die Projektumgebung mit Python 3.11 ausgewählt. Der Lockfile fixiert PySide6, python-chess, pytest und ihre installierten Abhängigkeiten. SQLite gehört zur Standardbibliothek. [Installation und Tests](../README.md), [Bedienung](BEDIENUNGSANLEITUNG_DE.md).

Die App erstellt ihre private SQLite-Datei lokal. Reproduzierbare Testproben verwenden isolierte Datenbanken mit synthetischen Gewichten. Der spätere GitHub-Bestand ist als Dateiliste vorbereitet. Eine Freigabe des Projektcodes und der Ressourcen steht vor der Veröffentlichung. [Veröffentlichungsprüfung](VEROEFFENTLICHUNG_DE.md).

## Reflexion und Grenzen des Projekts

Ein lernendes Gewicht verändert, wie die Suche bereits definierte Merkmale gegeneinander abwägt. Das Modell erfindet keine neuen Schachmerkmale, erweitert seine Suche durch das Lernen nicht und kann schlechte Positionen ebenso wie nützliche Erfahrungen sehen. Die feste Stellungsrepräsentation, das Rechenbudget, der Startstellungsmix und die gegnerischen Strategien bestimmen, welche Verbesserungen überhaupt messbar werden. Veränderte Gewichte oder eine höhere Kurztestquote beweisen deshalb keine höhere praktische Spielstärke. Auch seltene tote Stellungen jenseits der Materialprüfung bleiben eine Grenze der verwendeten Adjudikation.
