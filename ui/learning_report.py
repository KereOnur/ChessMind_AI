"""Read-only view of the persisted adaptive game report."""
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QHeaderView, QLabel,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)
from learning.td import NAMES


class Plot(QWidget):
    def __init__(self, report):
        super().__init__()
        self.report = report
        self.setMinimumHeight(140)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#101c33'))
        middle = self.height() / 2
        painter.setPen(QPen(QColor('#667899'), 1))
        painter.drawLine(QPointF(0, middle), QPointF(self.width(), middle))
        painter.setPen(QPen(QColor('#48dcff'), 2))
        values = [row['evaluation_after'] for row in self.report['events']]
        previous = None
        for index, value in enumerate(values):
            point = QPointF(10 + index * (self.width()-20) / max(1, len(values)-1),
                            middle - value * (middle-10))
            if previous is not None:
                painter.drawLine(previous, point)
            else:
                painter.drawEllipse(point, 2, 2)
            previous = point


def table(headers, rows):
    widget = QTableWidget(len(rows), len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.verticalHeader().hide()
    widget.setAlternatingRowColors(True)
    widget.setStyleSheet("""
        QTableWidget { background:#101c33; alternate-background-color:#152740;
            color:#edf3ff; gridline-color:#263d57; border:1px solid #2a4059; }
        QHeaderView::section { background:#1b3049; color:#b8dcff;
            border:0; padding:6px; }
    """)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    for row, values in enumerate(rows):
        for column, value in enumerate(values):
            widget.setItem(row, column, QTableWidgetItem(str(value)))
    return widget


class LearningReport(QDialog):
    def __init__(self, report, parent):
        super().__init__(parent)
        self.setWindowTitle('Adaptive Grandmaster AI – Lernbericht')
        self.resize(840, 710)
        layout = QVBoxLayout(self)
        title = QLabel(f"{report['result']} · {report['plies']} Halbzüge · "
                       f"Modell {report['initial_model']} → {report['model']} · "
                       f"{len(report['events'])} Lernereignisse")
        title.setWordWrap(True)
        layout.addWidget(title)
        weights = []
        changes = [after-before for before, after in zip(report['initial'], report['final'])]
        max_change = max(map(abs, changes))
        for name, before, after, delta in zip(NAMES, report['initial'], report['final'], changes):
            bar = '▰' * round(7 * abs(delta) / max_change) if max_change else ''
            weights.append((name, f'{before:.5f}', f'{after:.5f}', f'{delta:+.5f} {bar}'))
        layout.addWidget(table(('Merkmal', 'Vorher', 'Nachher', 'Änderung'), weights))
        layout.addWidget(QLabel('Bewertungsverlauf aus Sicht von Weiß · Skala −1 bis +1'))
        layout.addWidget(Plot(report))
        rows = [(row['ply'], 'Ergebnis' if row['kind']=='result' else 'Zug',
                 row['model'], f"{row['prediction']:+.4f}", f"{row['target']:+.4f}",
                 f"{row['error']:+.4f}") for row in report['events']]
        layout.addWidget(table(('Halbzug', 'Signal', 'Modell', 'V(s)', 'Ziel', 'TD-Fehler'), rows))
        largest = max(report['events'], key=lambda row: abs(row['error']))
        strongest = NAMES[max(range(len(changes)), key=lambda index: abs(changes[index]))]
        change_note = (f'Größte Gewichtsänderung bei {strongest}. ' if max_change
                       else 'Alle Gewichte blieben unverändert. ')
        note = QLabel(change_note + f"Größter absoluter TD-Fehler bei Halbzug {largest['ply']} "
                      f"({largest['error']:+.4f}). Die Änderung hängt vom Fehler, "
                      "den Merkmalen und den Schutzgrenzen ab. Höhere Gewichte oder ein "
                      "kleinerer TD-Fehler belegen keine bessere Spielstärke.")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText('Schließen')
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
