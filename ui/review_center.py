"""Local evaluation center and read-only statistics dialogs."""
import sys
from threading import Event
import time

from PySide6.QtCore import QPointF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QKeySequence, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QMessageBox, QProgressBar,
    QPushButton, QScrollArea, QTabWidget, QVBoxLayout, QWidget,
)

from evaluation import match, runner
from evaluation.repository import Reviews
from learning.td import NAMES
from ui.learning_report import table

STATUS = {'running':'Läuft','paused':'Pausiert','interrupted':'Unterbrochen',
          'aborted':'Abgebrochen','complete':'Abgeschlossen','invalid':'Ungültig'}
TITLES = {'amateur':'Amateur','grandmaster':'Großmeister','adaptive':'Adaptive Grandmaster AI'}
DASHBOARD_STYLE = """
QScrollArea#reviewScroll, QWidget#reviewCanvas { background:#101e30; border:0; }
QTabWidget::pane { border:1px solid #294562; background:#101e30; }
QTabBar::tab { background:#152740; color:#c4d9f1; padding:9px 16px; }
QTabBar::tab:selected { background:#214a70; color:#ffffff; border-bottom:2px solid #52d8ff; }
QPushButton:disabled { color:#7287a3; background:#0d192c; border-color:#20364f; }
QProgressBar { border:1px solid #38546f; border-radius:7px; min-height:22px;
    background:#102139; color:#ffffff; text-align:center; }
QProgressBar::chunk { background:#2279c5; border-radius:6px; }
"""


def enable_fullscreen(dialog):
    dialog.setWindowFlag(Qt.WindowType.WindowFullscreenButtonHint, True)
    action = QAction('Vollbild umschalten', dialog)
    action.setShortcut(QKeySequence('Ctrl+Meta+F' if sys.platform=='darwin' else 'F11'))
    action.triggered.connect(lambda: dialog.showNormal() if dialog.isFullScreen() else dialog.showFullScreen())
    dialog.addAction(action)


def text(value):
    widget = QLabel(value)
    widget.setWordWrap(True)
    return widget


def page(tabs, name):
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setObjectName('reviewScroll')
    canvas = QWidget()
    canvas.setObjectName('reviewCanvas')
    layout = QVBoxLayout(canvas)
    layout.setContentsMargins(14,14,14,14)
    area.setWidget(canvas)
    tabs.addTab(area, name)
    return layout


def add_table(layout, headers, rows):
    widget = table(headers, rows)
    widget.setFixedHeight(min(330, 42 + widget.verticalHeader().defaultSectionSize()*len(rows)))
    layout.addWidget(widget)


class Chart(QWidget):
    def __init__(self, series, low, high):
        super().__init__()
        self.series, self.low, self.high = series, low, high
        self.setMinimumHeight(155)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#101e30'))
        painter.setPen(QColor('#a9cde9'))
        painter.drawText(8, 18, f'{self.high:g}')
        painter.drawText(8, self.height()-8, f'{self.low:g}')
        for values, color in self.series:
            painter.setPen(QPen(QColor(color), 2))
            previous = None
            for index, value in enumerate(values):
                if value is None:
                    previous = None
                    continue
                point = QPointF(48 + index*(self.width()-60)/max(1,len(values)-1),
                                12 + (self.high-value)*(self.height()-26)/(self.high-self.low))
                if previous is not None:
                    painter.drawLine(previous, point)
                painter.drawEllipse(point, 2, 2)
                previous = point


class ReviewWorker(QThread):
    progress = Signal(object)
    error = Signal(str)

    def __init__(self, path, run_id, budget, parent, *, repeat_of=None):
        super().__init__(parent)
        self.path, self.run_id, self.budget = path, run_id, budget
        self.repeat_of = repeat_of
        self.cancel = Event()
        self.pause = Event()
        self.status = 'interrupted'

    def run(self):
        last = None

        def publish(run_id, model, opponent, total, saved):
            nonlocal last
            key = (sum(map(len, saved.values())), model, opponent)
            if key != last:
                self.progress.emit(runner.progress_snapshot(run_id,model,opponent,total,saved))
                last = key

        try:
            runner.run(Reviews(self.path), self.run_id, self.budget, self.cancel, self.pause,
                       lambda: self.status, publish, repeat_of=self.repeat_of)
        except Exception as exc:
            self.error.emit(str(exc))

    def stop(self, status):
        self.status = status
        (self.pause if status=='paused' else self.cancel).set()


class Center(QDialog):
    def __init__(self, window, budget=match.REVIEW):
        super().__init__(window)
        self.window, self.budget = window, budget
        self.data = None
        self.worker = None
        self.live = None
        self.error_message = ''
        self.mutating = False
        self.setWindowTitle('NeuroChess · KI-Testzentrum')
        enable_fullscreen(self)
        self.resize(1050, 760)
        self.setStyleSheet(DASHBOARD_STYLE)
        outer = QVBoxLayout(self)
        heading = text('KI-Testzentrum · Lokaler Modellvergleich')
        heading.setObjectName('heroTitle')
        outer.addWidget(heading)
        scope = f'{budget.count} Partien pro Version · {2*budget.count} Partien insgesamt.'
        outer.addWidget(text(scope + ' Eingefrorene Gewichte und verkürztes Suchbudget.'))
        self.message = text('Lokale Prüfdaten werden geladen …')
        outer.addWidget(self.message)
        self.progress = QProgressBar()
        outer.addWidget(self.progress)
        self.live_text = text('')
        outer.addWidget(self.live_text)
        self.buttons = {}
        for actions in (
            (('start',f'{budget.count} Testpartien starten',self.start), ('pause','Test pausieren',lambda:self.stop('paused')),
             ('resume','Test fortsetzen',self.resume), ('abort','Test abbrechen',self.abort)),
            (('repeat','Auswahl erneut testen',self.repeat), ('approve','Vorläufig bevorzugen',self.approve), ('restore','Referenz wiederherstellen',self.restore),
             ('close','Schließen',self.reject)),
        ):
            layout = QHBoxLayout()
            for key,title,callback in actions:
                button = QPushButton(title)
                button.clicked.connect(callback)
                layout.addWidget(button)
                self.buttons[key] = button
            outer.addLayout(layout)
        self.history = QComboBox()
        self.history.setPlaceholderText('Noch keine bisherigen Prüfläufe')
        self.history.currentIndexChanged.connect(self.show_report)
        outer.addWidget(self.history)
        self.tabs = QTabWidget()
        outer.addWidget(self.tabs, 1)
        self.clock = QTimer(self)
        self.clock.setInterval(500)
        self.clock.timeout.connect(self.show_live)
        from ui.training_dialog import TrainingDialog
        self.training = TrainingDialog(self)
        self.training.refreshed.connect(self.refresh)
        self.training_button = QPushButton('KI-Training · 600 Partien')
        self.training_button.clicked.connect(self.training.open_training)
        outer.insertWidget(2,self.training_button)
        self.refresh_buttons()

    def open_center(self):
        self.open()
        self.refresh()

    def request(self, operation, payload, callback):
        self.window.storage._submit(operation,payload,callback)

    def refresh(self):
        self.request('review_dashboard', True, self.loaded)

    def loaded(self, reply):
        if reply.error:
            self.message.setText(reply.error)
            return
        self.data = reply.result
        state = self.data['state']
        candidate = self.data['candidate']
        active_run = self.pending_run()
        self.message.setText(
            (f"Aktiv #{state['active']} · Referenz #{state['stable']} · "
             f"Kandidat {('#'+str(candidate['model'])) if candidate else '—'} · "
             f"{self.data['since']} Lernpartien seit der letzten Prüfung\n" if state else '')
            + (self.error_message or self.data['reason'] or 'Kandidat und Referenz sind für den Vergleich verfügbar.'))
        if self.data['reason'] == 'Keine ungeprüfte Kandidatenversion vorhanden.' and self.data['runs']:
            self.message.setText(self.message.text() + ' Wähle für eine Wiederholung einen abgeschlossenen Lauf mit der aktuellen Referenz.')
        self.history.blockSignals(True)
        selected = self.history.currentData()
        self.history.clear()
        index = 0
        for offset, run in enumerate(self.data['runs']):
            protocol = {match.PROTOCOL:'Altverfahren',match.REVIEW_PROTOCOL:'Phase 9.6'}.get(
                run.get('protocol'),'Unbekanntes Verfahren')
            self.history.addItem(f"{run['created'][:16]} · #{run['candidate']} gegen #{run['reference']} · "
                                 f"{protocol} · {STATUS[run['status']]} · {run['count']}/{run['total']} "
                                 f"· {run['id'][:8]}", run)
            if selected and selected['id']==run['id']:
                index = offset
        self.history.setCurrentIndex(index if self.history.count() else -1)
        self.history.blockSignals(False)
        if not self.worker:
            latest = active_run or self.history.currentData()
            count = latest['count'] if latest else 0
            self.progress.setValue(round(100*count/latest['total']) if latest else 0)
            self.live_text.setText(f"{STATUS[latest['status']]} · {count}/{latest['total']} Partien" if latest else 'Noch keine Daten vorhanden')
        self.show_report()
        self.refresh_buttons()

    def pending_run(self):
        return next((run for run in self.data['runs'] if run['status'] in
                     ('running','paused','interrupted')), None) if self.data else None

    def refresh_buttons(self):
        pending = self.pending_run()
        selected = self.history.currentData()
        ready = bool(self.data and not self.worker and not self.mutating)
        self.training_button.setEnabled(ready)
        self.buttons['start'].setEnabled(ready and not pending and not self.data['reason'])
        self.buttons['repeat'].setEnabled(ready and not pending and bool(
            selected and selected['status']=='complete' and self.data['state']
            and selected['reference']==self.data['state']['stable']
            and selected['candidate']!=selected['reference']))
        self.buttons['resume'].setEnabled(ready and bool(pending and pending['status']!='running'))
        self.buttons['pause'].setEnabled(self.worker is not None)
        self.buttons['abort'].setEnabled(bool(self.worker or (pending and pending['status']!='running')))
        self.buttons['close'].setEnabled(not self.worker)
        self.buttons['restore'].setEnabled(ready and bool(self.data['state']))
        self.buttons['approve'].setEnabled(ready and bool(selected and selected['total']==400 and selected.get('protocol')==match.REVIEW_PROTOCOL and
            selected['report'] and selected['report']['decision']=='eligible' and
            self.data['state']['stable']==selected['reference'] and
            not any(d['run']==selected['id'] and d['action']=='promoted' for d in self.data['decisions'])))

    def start(self):
        if self.worker is None and self.buttons['start'].isEnabled():
            self.launch(None)

    def resume(self):
        if self.buttons['resume'].isEnabled():
            self.launch(self.pending_run()['id'])

    def repeat(self):
        if self.buttons['repeat'].isEnabled():
            self.launch(None,repeat_of=self.history.currentData()['id'])

    def launch(self, run_id, *, repeat_of=None):
        if self.window.storage.session and self.window.storage.session.running:
            self.message.setText('Speichere und verlasse zuerst die laufende Partie.')
            return
        self.error_message = ''
        self.live = None
        self.started = time.monotonic()
        self.worker = ReviewWorker(self.window.storage.service.path, run_id, self.budget, self, repeat_of=repeat_of)
        self.worker.progress.connect(self.update_live)
        self.worker.error.connect(self.show_error)
        self.worker.finished.connect(self.finished_worker)
        self.refresh_buttons()
        self.clock.start()
        self.show_live()
        self.worker.start()

    def show_error(self, message):
        self.error_message = message
        self.message.setText(message)

    def update_live(self, progress):
        self.live = progress
        self.show_live()

    def show_live(self):
        if not self.worker:
            return
        elapsed = int(time.monotonic()-self.started)
        if not self.live:
            self.live_text.setText('Läuft · Testplan wird geprüft …')
            return
        data = self.live
        self.progress.setValue(round(100*data['count']/data['total']))
        lines = [f"Läuft · {data['count']}/{data['total']} · Modell #{data['model']} · "
                 f"{TITLES[data['opponent']]} · {elapsed//60}:{elapsed%60:02d} min"]
        for model, row in data['models'].items():
            lines.append(f"#{model} · {row['wins']} Siege · {row['draws']} Remis · "
                         f"{row['losses']} Niederlagen · {row['technical']} technische Abbrüche · {row['points']:g} Punkte")
        self.live_text.setText('\n'.join(lines))

    def stop(self, status):
        if self.worker:
            self.worker.stop(status)
            self.live_text.setText('Laufender Schritt wird sicher beendet …')

    def abort(self):
        if self.worker:
            self.stop('aborted')
        elif self.pending_run():
            self.mutate('review_abort', self.pending_run()['id'])

    def finished_worker(self):
        self.clock.stop()
        self.worker.deleteLater()
        self.worker = None
        if self.isVisible() and not self.window.storage.closing:
            self.refresh()

    def prepare_close(self):
        if not self.training.prepare_close():
            return False
        if self.worker:
            self.stop('interrupted')
            return False
        return True

    def reject(self):
        if not self.worker:
            super().reject()

    def mutate(self, operation, payload):
        if not self.worker and not self.mutating:
            self.mutating = True
            self.refresh_buttons()
            self.request(operation,payload,self.changed)

    def changed(self, reply):
        self.mutating = False
        self.error_message = reply.error or ''
        self.refresh()

    def confirm(self, title, message, operation, payload):
        box = QMessageBox(QMessageBox.Icon.Question,title,message,
                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,self)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        box.finished.connect(lambda code: self.mutate(operation,payload)
                             if code==QMessageBox.StandardButton.Yes else None)
        box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        box.open()

    def approve(self):
        selected = self.history.currentData()
        if selected and self.buttons['approve'].isEnabled():
            self.confirm('Vorläufige Freigabe','Kandidat als neue Referenz und Ausgangspunkt des Lernens übernehmen? '
                         'Die bisherige Referenz und die Lernhistorie bleiben erhalten.',
                         'review_promote',selected['id'])

    def restore(self):
        if self.data and self.data['state']:
            from PySide6.QtWidgets import QInputDialog
            stable = self.data['state']['stable']
            ids = {stable}
            for decision in self.data['decisions']:
                if decision['action'] in ('promoted','restored'):
                    ids.update((decision['previous'],decision['selected']))
            picker = QInputDialog(self)
            picker.setWindowTitle('Referenz wählen')
            picker.setLabelText('Unveränderter Referenzstand')
            picker.setComboBoxItems([str(model) for model in sorted(ids, reverse=True)])
            picker.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
            picker.textValueSelected.connect(lambda value:self.confirm(
                'Wiederherstellung bestätigen','Ausgewählten Referenzstand wiederherstellen und Lernhistorie behalten?',
                'review_restore',int(value)))
            picker.open()

    def show_report(self):
        if not self.data:
            return
        clear_tabs(self.tabs)
        layout = page(self.tabs, 'Vergleich')
        selected = self.history.currentData()
        report = selected['report'] if selected else None
        if selected and selected.get('repeat_of'):
            layout.addWidget(text(f"Wiederholung des Laufs {selected['repeat_of']}"))
        if not report:
            layout.addWidget(text('Noch keine Daten vorhanden' if not selected else 'Für diesen Lauf liegt kein gültiger vollständiger Vergleich vor.'))
        else:
            rows = []
            legacy = selected.get('protocol') != match.REVIEW_PROTOCOL
            for role,name in (('candidate','Kandidat'),('reference','Referenz')):
                stats = report[role]
                technical = stats['limited'] if legacy else stats['technical']
                draws = stats['draws']-technical if legacy else stats['draws']
                regular = stats['wins']+draws+stats['losses']
                total = regular+technical
                points = stats['points']-.5*technical if legacy else stats['points']
                rate = f'{points/regular:.1%}' if regular else '—'
                rows.append((name,stats['wins'],draws,stats['losses'],f'{technical} ({technical/total:.1%})',
                             f'{regular} ({regular/total:.1%})',rate,f"{stats['plies']:.1f}",
                             f"{stats['seconds']:.3f} s"))
            add_table(layout, ('Modell','Siege','Reguläre Remis','Niederlagen','Technisch','Regulär',
                               'Punktequote','Ø Halbzüge','Ø Zeit'),rows)
            decisions = [row for row in self.data['decisions'] if row['run']==selected['id']]
            if legacy:
                layout.addWidget(text('Historischer Lauf. Frühere Limitremis sind hier aus den Punktequoten '
                                      'herausgerechnet. Die alte Vergleichsentscheidung bleibt protokolliert.'))
            else:
                used,planned = report['paired'],report['planned_pairs']
                quality = 'Eingeschränkt aussagekräftig' if report['quality_limited'] else 'Ausreichende Paarabdeckung'
                layout.addWidget(text(f'{quality} · {used}/{planned} beidseitig reguläre Paare. '
                                      'Der Paarvergleich verwendet ausschließlich diese Paare.'))
                low,high = report['missing_bounds']
                layout.addWidget(text(f'Mögliche Gesamtdifferenz mit offenen Ausgängen [{low*100:+.2f}, '
                                      f'{high*100:+.2f}] Prozentpunkte.'))
                if report['interval']:
                    low,high = report['interval']
                    layout.addWidget(text(f"Paardifferenz {report['difference']*100:+.2f} Prozentpunkte · "
                                          f"95-%-Bootstrapintervall [{low*100:+.2f}, {high*100:+.2f}]. "
                                          + ('Statistisch unsicher.' if report['uncertain'] else '')))
                else:
                    layout.addWidget(text('Zu wenige reguläre Paare für eine Unsicherheitsabschätzung.'))
                if report['decision'] != 'eligible':
                    layout.addWidget(text('Die Referenz bleibt bevorzugt.'))
                layout.addWidget(text('Der Kurztest misst keine Rapid-Spielstärke.'))
            labels = {'promoted':'Vorläufig übernommen','eligible':'Kandidat besser im Kurztest',
                      'keep_reference':'Referenz bleibt bevorzugt'}
            layout.addWidget(text('Entscheidungsverlauf · '+' · '.join(labels[row['action']] for row in decisions)))
        layout.addStretch()
        add_learning(self.tabs,self.data)
        self.refresh_buttons()


def clear_tabs(tabs):
    while tabs.count():
        widget = tabs.widget(0)
        tabs.removeTab(0)
        widget.deleteLater()


def add_learning(tabs, data):
    layout = page(tabs, 'Adaptive-Lernen')
    if not data['state']:
        layout.addWidget(text('Noch keine Daten vorhanden'))
        layout.addStretch()
        return
    state = data['state']
    layout.addWidget(text(f"{data['games']} abgeschlossene Lernpartien · {data['events']} Lernereignisse · "
                          f"Aktiv #{state['active']} · Referenz #{state['stable']}"))
    layout.addWidget(text('Kandidaten · '+(', '.join(f'#{model} ({milestone})' for milestone,model in data['candidates']) or 'Noch keine Daten vorhanden')))
    training_candidates = data.get('training_candidates', [])
    if training_candidates:
        layout.addWidget(text('Trainingskandidaten · '+', '.join(f'#{model}' for model in training_candidates)))
    layout.addWidget(text('Gewichtsverlauf nach Modellrevision. Geänderte Gewichte belegen keine bessere Spielstärke.'))
    models = data['models']
    colors = ('#5be4ff','#f8ba75','#cbaaef','#7ee3a3','#ed8aa6')
    layout.addWidget(Chart([(tuple(m['weights'][i] if m['weights'] else None for m in models), colors[i])
                            for i in range(len(NAMES))], .5, 1.5))
    legend = QLabel(' &nbsp; '.join(f'<span style="color:{color}">{name}</span>' for name,color in zip(NAMES,colors)))
    legend.setWordWrap(True)
    layout.addWidget(legend)
    def score_rate(report, role, legacy):
        row = report[role]
        if not legacy:
            return row['rate']
        regular = row['wins'] + row['draws'] + row['losses'] - row['limited']
        return (row['points']-.5*row['limited'])/regular if regular else None

    for protocol, title in ((match.PROTOCOL,'Historische Vergleiche ohne Limitremis'),
                            (match.REVIEW_PROTOCOL,'Phase 9.6')):
        reports = [run['report'] for run in reversed(data['runs'])
                   if run['report'] and run.get('protocol')==protocol]
        if reports:
            layout.addWidget(text(f'{title} · Punktequote · Cyan: Kandidat · Orange: Referenz'))
            layout.addWidget(Chart([([score_rate(r,key,protocol==match.PROTOCOL) for r in reports],color)
                                    for key,color in zip(('candidate','reference'),colors)],0,1))
    if data['runs']:
        add_table(layout,('Datum','Kandidat','Referenz','Status','Partien'),[
            (r['created'][:10],r['candidate'],r['reference'],STATUS[r['status']],r['count']) for r in data['runs']])
    else:
        layout.addWidget(text('Modellprüfungen · Noch keine Daten vorhanden'))
    changes = [row for row in data['decisions'] if row['action'] in ('promoted','restored')]
    if changes:
        add_table(layout, ('UTC','Bisherige Referenz','Neue Referenz','Modellwechsel'), [
            (row['created'][:16],row['previous'],row['selected'],
             'Vorläufig übernommen' if row['action']=='promoted' else 'Wiederhergestellt')
            for row in changes])
    add_table(layout, ('Version','Erstellt (UTC)','Status','Gewichte'), [
        (m['id'],m['created'][:16],m['status'], ' / '.join(f'{w:.4f}' for w in m['weights'])
         if m['weights'] else 'Ungültig') for m in reversed(models)])
    layout.addStretch()


class Statistics(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle('NeuroChess · Statistiken')
        enable_fullscreen(self)
        self.resize(960, 710)
        self.setStyleSheet(DASHBOARD_STYLE)
        outer = QVBoxLayout(self)
        heading = text('Statistiken · Menschliche Partien und Adaptive-Lernen')
        heading.setObjectName('heroTitle')
        outer.addWidget(heading)
        self.tabs = QTabWidget()
        outer.addWidget(self.tabs)
        button = QPushButton('Schließen')
        button.clicked.connect(self.reject)
        outer.addWidget(button)

    def open_statistics(self):
        self.open()
        self.window.storage._submit('review_statistics',None,self.loaded)

    def loaded(self, reply):
        clear_tabs(self.tabs)
        layout = page(self.tabs,'Menschliche Partien')
        if reply.error:
            layout.addWidget(text(reply.error))
            return
        players,data = reply.result
        layout.addWidget(text('Abgeschlossene Partien gegen KI. Automatische Modelltests erscheinen separat im KI-Testzentrum.'))
        outcomes = {'wins':'Sieg','draws':'Remis','losses':'Niederlage'}
        for mode,row in players.items():
            total = sum(row[k] for k in outcomes)
            layout.addWidget(text(TITLES[mode]))
            if total:
                noun = 'Partie' if total==1 else 'Partien'
                wins = 'Sieg' if row['wins']==1 else 'Siege'
                losses = 'Niederlage' if row['losses']==1 else 'Niederlagen'
                layout.addWidget(text(f"{total} {noun} · {row['wins']} {wins} · {row['draws']} Remis · "
                                      f"{row['losses']} {losses} · Gewinnquote {row['wins']/total:.1%} · "
                                      f"Ø {row['plies']/total:.1f} Halbzüge"))
                add_table(layout,('Datum','Ausgang','Endgrund','Halbzüge'),
                          [(date,outcomes[kind],reason,plies) for date,kind,reason,plies in row['recent']])
            else:
                layout.addWidget(text('Noch keine Daten vorhanden'))
        layout.addStretch()
        add_learning(self.tabs,data)
