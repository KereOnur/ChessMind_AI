# NeuroChess bedienen

## Start und erste Partie

1. Öffne den bestehenden Projektordner in PyCharm.
2. Wähle unter **Python Interpreter** die Datei `.venv/bin/python` im Projekt. Auf einer neuen Kopie installierst du die Abhängigkeiten nach der Anleitung im [README](../README.md).
3. Starte `main.py` mit dem Projektordner als Arbeitsverzeichnis.
4. Wähle **Neues Spiel**, einen KI-Gegner und **Weiß** oder **Schwarz**. Öffne die Zusammenfassung und starte die Partie. Weiß zieht zuerst. Spielst du Schwarz, beginnt die KI.
5. Klicke auf eine Figur und ihr Zielfeld oder ziehe sie mit der Maus. Bei Berührt-geführt bleibt eine ausgewählte bewegliche Figur gebunden. Bei einer Bauernumwandlung öffnet sich eine Auswahl.
6. Beide Uhren beginnen bei 15 Minuten. Ein abgeschlossener Zug bringt der ziehenden Seite zehn Sekunden. Während der KI-Suche läuft deren Uhr. **Remis beantragen** prüft einen regelgerechten Anspruch. **Aufgeben** verlangt eine Bestätigung.

**Schachbrett-Vorschau öffnen** zeigt das gewählte Design. **Regeltest-Partie starten** eröffnet eine separate Partie, in der du beide Farben steuerst. Über die macOS-Fenstersteuerung oder Control–Command–F gelangst du ins Vollbild.

## Speichern und nachschauen

- Klicke auf **Speichern & verlassen**, um die Uhren anzuhalten und die Partie lokal zu sichern. **Spiel fortsetzen** lädt den einen fortsetzbaren Spielstand. Bestätige das Fortsetzen.
- Öffne **Statistiken** für Ergebnisse menschlicher Partien pro Gegner. Die Lernansicht zeigt Modellrevisionen und Gewichte. Automatische Vergleichspartien zählen separat.
- Nach Abschluss einer Adaptive-Partie öffnet **Lernbericht öffnen** die Werte und Lernereignisse dieser Partie.

## Automatisches Training

1. Speichere und verlasse eine laufende Partie.
2. Öffne **KI-Testzentrum → KI-Training · 600 Partien** und klicke **600 Trainingspartien starten**.
3. Der Rechner führt die Züge aus. Gegen jeden der drei Gegner spielt das Trainingsmodell 100-mal Weiß und 100-mal Schwarz. Die Adaptive-Gegenseite verwendet eine eingefrorene Referenz.
4. Mit **Pausieren** hältst du den Lauf am nächsten sicheren Punkt an. **Fortsetzen** übernimmt bestätigte Partien. Eine noch nicht bestätigte Partie beginnt erneut. **Abbrechen** beendet den Lauf und behält bereits gespeicherte Ergebnisse.
5. Erst nach 600 abgeschlossenen Trainingspartien erscheint ein neuer Kandidat. Mehr Trainingspartien oder veränderte Gewichte sind für sich genommen kein Beleg für bessere Spielstärke.

## Modellvergleich

1. Öffne das **KI-Testzentrum**. **200 Testpartien starten** bedeutet 200 je Modell und 400 insgesamt.
2. Wähle für eine Wiederholung einen abgeschlossenen Lauf mit der aktuellen Referenz in der Historie und klicke **Auswahl erneut testen**. Die Historie unterscheidet Altverfahren und Phase 9.6.
3. Lies die Spalten für Siege, reguläre Remis, Niederlagen und technische Abbrüche. Nur reguläre Ergebnisse zählen zur angezeigten Punktequote. Der Paarvergleich verwendet Fälle, die für beide Versionen regulär endeten. Das Intervall und die Grenzen für offene Ergebnisse zeigen, wie sicher die Differenz ist.
4. Die **Referenz** ist der gespeicherte Vergleichs- und Rückfallstand. Ein Kandidat wird erst nach qualifiziertem Ergebnis und ausdrücklicher Bestätigung bevorzugt. Der Kurztest verwendet weniger Suchzeit und andere Startstellungen als eine echte Rapid-Partie.
