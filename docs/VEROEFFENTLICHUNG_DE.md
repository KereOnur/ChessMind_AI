# GitHub-Vorbereitung

Das [Dateimanifest](VEROEFFENTLICHUNG_DATEIEN.txt) listet den vorgesehenen öffentlichen Stand einzeln auf. Die Liste enthält Quellcode, SVGs, reproduzierbare Tests und die bereinigten Anleitungen. Alte Berichte mit persönlichen Pfaden, Screenshots, Rohmessungen, lokale SQLite-Dateien und der interne Abschlussbericht bleiben im lokalen Projekt. Die Testproben können synthetische Daten erzeugen.

## Git und Datenschutz

Der lokale Stand hatte bei der Prüfung keine Commits, Branch-Referenzen oder Remotes. Fünf PyCharm-Pfade waren bereits im Index. Sie wurden aus dem Index entfernt. Vorhandene Arbeitskopien blieben erhalten. Die ursprünglichen Indexobjekte sind keine veröffentlichte Historie. Eine zukünftige Veröffentlichung sollte ausschließlich einen Commit aus dem geprüften Manifest übertragen. Das lokale `.git/`-Verzeichnis gehört nicht in einen Export.

Die Ignore-Regeln erfassen unter anderem IDE-Dateien, Python-Umgebungen, Caches, Datenbanken, Journale, Spiel- und Modellexporte sowie typische Zugangsdatenformate. Der Dateiscan prüft zusätzlich die tatsächlichen Kandidaten auf lokale Benutzerpfade, Geheimnismuster, eingebettete Ressourcen und Datenbankdateien. Ein Musterscan ersetzt keine manuelle Kontrolle neuer Änderungen. Prüfe vor einem späteren Commit den Index mit `git diff --cached --name-only` gegen das Manifest und danach alle zu übertragenden Referenzen. Benutzername und E-Mail des späteren Commits müssen ebenfalls zur beabsichtigten öffentlichen Identität passen.

## Assets, Abhängigkeiten und Rechte

Die sechs Menüillustrationen und 38 Brettressourcen lassen sich aus den beiden lokalen SVG-Generatoren rekonstruieren. Die Dateien nutzen Vektorformen und lokale Gradienten. Schrift kommt vom Betriebssystem. Schriftdateien, externe Bilder und Drittanbieter-Binärdateien gehören nicht in den Export. [Menü-Assets](../assets/README.md), [Brett-Assets](../assets/board/README.md).

python-chess weist upstream die GPL aus. PySide6 bietet mehrere Lizenzwege. Das Manifest enthält nur Installationslisten für diese Bibliotheken. Ein späteres Paket mit Bibliotheken oder eine öffentliche Quellcodefreigabe erfordert die Prüfung der anwendbaren Bedingungen und die Auswahl einer kompatiblen Projektlizenz. Die Herkunft der SVGs ist dokumentiert. Die Zustimmung zur öffentlichen Weitergabe von eigenem Code und eigenen Grafiken sowie die konkrete Lizenzwahl stehen noch aus. Das Projekt setzt dafür keine Lizenz voraus. [python-chess-Lizenz](https://github.com/niklasf/python-chess/blob/master/LICENSE.txt), [Qt-Lizenzinformationen](https://doc.qt.io/qt-6/licensing.html).

Vor einer Veröffentlichung sind Rechte, Projektlizenz, finaler Index und der Zielort ausdrücklich freizugeben. Die vorliegende Vorbereitung hat kein Remote eingerichtet und keine Dateien übertragen.
