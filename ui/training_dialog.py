"""Manual start and progress for the separate 600-game training run."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QProgressBar, QPushButton, QVBoxLayout

from evaluation import training
from ui.review_center import DASHBOARD_STYLE, STATUS, TITLES, ReviewWorker, enable_fullscreen, text


class TrainingWorker(ReviewWorker):
    def run(self):
        try:
            training.Training(self.path).run(
                self.run_id,self.budget,self.cancel,self.pause,lambda:self.status,
                lambda count,total,opponent:self.progress.emit((count,total,opponent)))
        except Exception as exc:
            self.error.emit(str(exc))


class TrainingDialog(QDialog):
    refreshed = Signal()

    def __init__(self, center):
        super().__init__(center)
        self.center = center
        self.worker = None
        self.record = None
        self.error_message = ''
        self.busy = False
        self.ready = False
        self.setWindowTitle('NeuroChess · KI-Training')
        enable_fullscreen(self)
        self.setStyleSheet(DASHBOARD_STYLE)
        self.resize(760,360)
        layout = QVBoxLayout(self)
        heading = text('KI-Training · 600 Partien')
        heading.setObjectName('heroTitle')
        layout.addWidget(heading)
        layout.addWidget(text('Je 200 gegen Amateur, Großmeister und die eingefrorene Adaptive-Referenz. '
                              'Je Gegner spielt das Trainingsmodell 100-mal Weiß und 100-mal Schwarz.'))
        layout.addWidget(text('Nach Abschluss entsteht ein Kandidat. Der separate Modellvergleich '
                              'umfasst 400 Partien mit deaktiviertem Lernen.'))
        self.message = text('Trainingsstatus wird geladen …')
        layout.addWidget(self.message)
        self.bar = QProgressBar()
        self.bar.setRange(0,training.PRODUCTION.count)
        self.bar.setValue(0)
        layout.addWidget(self.bar)
        controls = QHBoxLayout()
        self.buttons = {}
        for key,label,callback in (
            ('start','600 Trainingspartien starten',lambda:self.launch(None)),
            ('pause','Pausieren',lambda:self.worker.stop('paused')),
            ('resume','Fortsetzen',lambda:self.launch(self.record['id'])),
            ('abort','Abbrechen',self.abort), ('close','Schließen',self.reject),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            controls.addWidget(button)
            self.buttons[key] = button
        layout.addLayout(controls)
        self.sync_buttons()

    def open_training(self):
        self.open()
        self.refresh()

    def refresh(self):
        self.busy = True
        self.sync_buttons()
        self.center.request('review_training_status',None,self.loaded)

    def loaded(self,reply):
        self.busy = False
        self.ready = not reply.error
        self.record = reply.result if self.ready else None
        if self.record:
            r = self.record
            self.bar.setValue(r['count'])
            details = f"{STATUS[r['status']]} · {r['count']}/{r['total']} · Adaptive-Referenz #{r['reference']}"
            if r['candidate']:
                details += f" · Kandidat #{r['candidate']} für den Modellvergleich verfügbar."
        else:
            self.bar.setValue(0)
            details = 'Bereit. Das Training startet nach deiner Auswahl.'
        self.message.setText(reply.error or self.error_message or details)
        self.sync_buttons()
        self.refreshed.emit()

    def sync_buttons(self):
        status = self.record['status'] if self.record else None
        idle = self.ready and not self.busy and self.worker is None
        resumable = status in ('paused','interrupted')
        self.buttons['start'].setEnabled(idle and status not in ('running','paused','interrupted'))
        self.buttons['resume'].setEnabled(idle and resumable)
        self.buttons['pause'].setEnabled(self.worker is not None)
        self.buttons['abort'].setEnabled(self.worker is not None or (idle and resumable))
        self.buttons['close'].setEnabled(self.worker is None)

    def launch(self,run_id):
        storage = self.center.window.storage
        if storage.session and storage.session.running:
            self.message.setText('Speichere und verlasse zuerst die laufende Partie.')
            return
        self.error_message = ''
        self.worker = TrainingWorker(storage.service.path,run_id,training.PRODUCTION,self)
        self.worker.progress.connect(self.progress)
        self.worker.error.connect(self.show_error)
        self.worker.finished.connect(self.finished_worker)
        self.sync_buttons()
        self.worker.start()

    def progress(self,data):
        count,total,opponent = data
        self.bar.setValue(count)
        self.message.setText(f'Läuft · {count}/{total} · {TITLES[opponent]}')

    def show_error(self,message):
        self.error_message = message

    def finished_worker(self):
        self.worker.deleteLater()
        self.worker = None
        if not self.center.window.storage.closing:
            self.refresh()

    def abort(self):
        if self.worker:
            self.worker.stop('aborted')
        elif self.record:
            self.busy = True
            self.sync_buttons()
            self.center.request('review_training_abort',self.record['id'],self.aborted)

    def aborted(self,reply):
        self.error_message = reply.error or ''
        self.refresh()

    def prepare_close(self):
        if self.worker:
            self.worker.stop('interrupted')
            return False
        return True

    def reject(self):
        if not self.worker:
            super().reject()
