"""Persistence navigation and recovery; game rules stay in GameSession."""
from dataclasses import replace
from datetime import datetime
import uuid
from PySide6.QtCore import QObject,QTimer,Qt
from PySide6.QtWidgets import QLabel,QMessageBox,QPushButton
from database.store import DEFAULT_PATH
from game.checkpoint import export_checkpoint,RestoredGame
from game.session import GameSession,PROMOTIONS
from ui.navigation import GameSetup,Opponent,PlayerColor,OPPONENTS
from ui.board.themes import THEMES
from ui.storage import StorageService


class PersistenceCoordinator(QObject):
    def __init__(self,window,path=DEFAULT_PATH,*,startup_prompt=True):
        super().__init__(window);self.window=window;self.now=window._clock_now;self.startup_prompt=startup_prompt
        self.ready=False;self.failed=False;self.busy=None;self.known_active=None
        self.current=None;self.session=None;self.next_sequence=-1;self.last_confirmed=-1
        self.callbacks={};self.dialog=None;self.dialog_buttons={};self.exit_destination=None
        self.learning_notice_busy=False
        self.fingerprint=None;self.pending_setup=None;self.pending_kind='rule_test';self.retrying=False;self.closing=False
        self.status=QLabel('Lokale Spielstände werden geprüft …');self.status.setWordWrap(True)
        self.retry_button=QPushButton('Erneut versuchen');self.retry_button.hide();self.retry_button.clicked.connect(self.retry)
        window.statusBar().setSizeGripEnabled(False)
        window.statusBar().setStyleSheet('QStatusBar {background:#0b1421;color:#adc6e6;} QStatusBar QLabel {background:transparent;color:#adc6e6;font-size:11px;padding:4px;} QStatusBar::item {border:none;}')
        window.statusBar().addWidget(self.status,1);window.statusBar().addPermanentWidget(self.retry_button)
        self.service=StorageService(path,self);self.service.completed.connect(self._reply)
        window.rule_page.state_changed.connect(self.observe)
        window.rule_page.save_requested.connect(lambda:self.save_leave('menu'))
        QTimer.singleShot(0,self.initialize)

    def _subtitle(self,text):
        button=self.window.menu_page.menu_buttons['Spiel fortsetzen']
        for child in button.findChildren(QLabel):
            if child.objectName()=='navSubtitle':child.setText(text)

    def _set_busy(self,value):
        self.busy=value
        self.window.summary_page.rule_test_button.setEnabled(value is None and self.ready and not self.failed)
        self.window.summary_page.play_button.setEnabled(value is None and self.ready and not self.failed)
        self.window.menu_page.menu_buttons['Spiel fortsetzen'].setEnabled(value is None)
        self.window.menu_page.menu_buttons['Neues Spiel'].setEnabled(value is None)

    def _submit(self,op,payload,callback):
        token=self.service.submit(op,payload);self.callbacks[token]=callback;return token

    def initialize(self):
        if self.closing or not self.service.thread.isRunning() or self.service.pending:return
        self._set_busy('initialize');self._subtitle('Spielstand wird geprüft …')
        self._submit('initialize',None,self._initialized)

    def _initialized(self,reply):
        self.ready=True;self.failed=False;self.retry_button.hide();self.known_active=reply.result;self._set_busy(None)
        self._refresh_menu();self.status.setText('Lokale Spielstände bereit.')
        self._check_learning_notice()
        if self.known_active and self.startup_prompt and not self.closing:self._offer_resume(self.known_active)

    def _refresh_menu(self):
        self._subtitle('Gespeicherte Partie fortsetzen' if self.known_active else 'Keine unterbrochene Partie')

    def _reply(self,reply):
        callback=self.callbacks.pop(reply.token,None)
        if reply.skipped:
            self.retry_button.setEnabled(not self.service.pending)
        elif reply.error and reply.operation.startswith('review_'):
            if callback:callback(reply)
        elif reply.error:
            if reply.operation in ('next_learning_notice','acknowledge_learning_notice'):
                self.learning_notice_busy=False
                self.status.setText('Der Lernhinweis konnte nicht verarbeitet werden.')
            else:self._failure(reply.error,reply.operation)
        elif callback:callback(reply)
        if self.failed:self.retry_button.setEnabled(not self.service.pending and self.dialog is None)
        if self.closing and self.session is None and not self.service.pending:self._finish_close()

    def _failure(self,message,operation):
        first=not self.failed;self.failed=True;self._set_busy(None)
        if self.session:
            self.session.suspend();page=self.window.rule_page
            page.timer.stop();page.board.stop()
            if page.dialog is not None:
                dialog=page.dialog;page.dialog=None;dialog.reject()
            page.refresh_session()
        self.status.setText('Speichern fehlgeschlagen. Zustand bleibt im Speicher; letzter bestätigter Spielstand bleibt geschützt. '+message)
        self.retry_button.setText('Erneut speichern' if self.session else 'Datenbank erneut prüfen');self.retry_button.show()
        self.retry_button.setEnabled(not self.service.pending)
        self.window.menu_page.notice.setText('Datenbankfehler: '+message+' Diagnose: database/diagnostics.log')
        self._subtitle('Datenbankfehler – Spielstand nicht überschrieben')
        if first and self.dialog is None:
            self._prompt('Datenbankfehler',message+'\n\nDie Partie bleibt angehalten. Es wurde kein erfolgreicher Speichervorgang bestätigt. Vorhandene Daten werden nicht gelöscht. Details: database/diagnostics.log', [('ok','Verstanden',QMessageBox.ButtonRole.AcceptRole)],lambda key:None,'ok',icon=QMessageBox.Icon.Warning)

    def _prompt(self,title,text,choices,callback,default,*,icon=QMessageBox.Icon.Question):
        if self.dialog is not None:return
        box=QMessageBox(self.window);box.setWindowTitle(title);box.setIcon(icon);box.setText(text)
        box.setWindowModality(Qt.WindowModality.WindowModal);box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.dialog_buttons={key:box.addButton(caption,role) for key,caption,role in choices}
        self.dialog=box;box.setDefaultButton(self.dialog_buttons[default]);box.setEscapeButton(self.dialog_buttons.get('cancel',self.dialog_buttons.get('later',self.dialog_buttons[default])))
        mapping=dict(self.dialog_buttons);handled=False
        def finished(code):
            nonlocal handled
            if handled:return
            handled=True
            if self.dialog is not box:return
            clicked=box.clickedButton();key=next((key for key,button in mapping.items() if button is clicked),default)
            self.dialog=None;self.dialog_buttons={};callback(key)
            if self.failed:self.retry_button.setEnabled(not self.service.pending)
        box.finished.connect(finished);box.open()

    def request_resume(self):
        if not self.ready or self.failed or self.busy:return
        self._set_busy('load');self._submit('load',None,self._loaded)

    def _loaded(self,reply):
        self.known_active=reply.result;self._set_busy(None);self._refresh_menu()
        if self.closing:return
        if reply.result:self._offer_resume(reply.result)
        else:self.window.menu_page.notice.setText('Es ist keine unterbrochene Partie vorhanden.')

    def _offer_resume(self,record):
        kind={'adaptive_ai':'Adaptive-Partie', 'grandmaster_ai':'Großmeister-Partie', 'amateur_ai':'Amateur-Partie'}.get(record.session.play_kind,'Regeltest-Partie')
        text='Eine unterbrochene '+kind+' ist vorhanden.\n'+OPPONENTS[Opponent(record.mode)].title+' · '+record.player_color+' · '+THEMES[Opponent(record.mode)].title+'\nGespeichert: '+datetime.fromisoformat(record.saved_at).astimezone().strftime('%d.%m.%Y, %H:%M Uhr')+'\n\nWährend dieser Abfrage stehen beide Uhren. KI-Partien werden automatisch fortgesetzt; der Regeltest bleibt manuell.'
        self._prompt('Partie wiederherstellen',text,[('resume','Partie fortsetzen',QMessageBox.ButtonRole.AcceptRole),('later','Später / zum Hauptmenü',QMessageBox.ButtonRole.RejectRole)],lambda key:self._activate(record) if key=='resume' else None,'later')

    def begin_adaptive(self):
        if self.window.navigation.setup.opponent == Opponent.ADAPTIVE:
            self.begin_new(play_kind="adaptive_ai")

    def begin_grandmaster(self):
        if self.window.navigation.setup.opponent!=Opponent.GRANDMASTER:return
        self.begin_new(play_kind='grandmaster_ai')

    def begin_amateur(self):
        if self.window.navigation.setup.opponent!=Opponent.AMATEUR:return
        self.begin_new(play_kind='amateur_ai')

    def begin_new(self,*,play_kind='rule_test'):
        if not self.ready or self.failed or self.busy:return
        self.pending_kind=play_kind
        self.pending_setup=replace(self.window.navigation.setup)
        self._set_busy('check_new');self._submit('load',None,self._checked_new)

    def _checked_new(self,reply):
        if self.closing:self._set_busy(None);return
        self.known_active=reply.result;self._set_busy(None);self._refresh_menu()
        if reply.result:
            def chosen(key):
                if key=='resume':self._activate(reply.result)
                elif key=='discard':self._confirm_discard(reply.result)
            self._prompt('Unterbrochene Partie vorhanden','Es kann nur eine fortsetzbare Partie geben. Möchtest du sie fortsetzen oder bewusst verwerfen?',[('resume','Vorhandene Partie fortsetzen',QMessageBox.ButtonRole.AcceptRole),('discard','Verwerfen und neu beginnen …',QMessageBox.ButtonRole.DestructiveRole),('cancel','Abbrechen',QMessageBox.ButtonRole.RejectRole)],chosen,'cancel')
        else:self._create_new()

    def _confirm_discard(self,record):
        def chosen(key):
            if key=='discard':
                self._set_busy('discard');self._submit('discard',(record.game_id,record.sequence),lambda reply:self._discarded())
        self._prompt('Spielstand endgültig verwerfen?','Diese unterbrochene Partie kann danach nicht mehr fortgesetzt werden. Es gibt keine Zugrücknahme und keine Auswahl älterer Spielstände.',[('discard','Spielstand bewusst verwerfen',QMessageBox.ButtonRole.DestructiveRole),('cancel','Behalten',QMessageBox.ButtonRole.RejectRole)],chosen,'cancel')

    def _discarded(self):
        self.known_active=None
        if self.closing:self._set_busy(None);return
        self._create_new()

    def _create_new(self):
        setup=self.pending_setup
        session=GameSession(now=self.now,start_clock=False,play_kind=self.pending_kind,human_color=(setup.player_color==PlayerColor.WHITE) if self.pending_kind in ('amateur_ai','grandmaster_ai','adaptive_ai') else None)
        self.current=RestoredGame(session,str(uuid.uuid4()),-1,setup.opponent.value,setup.player_color.value,THEMES[setup.opponent].key,'')
        self.session=session;self.next_sequence=-1;self.last_confirmed=-1
        self._set_busy('create');self._submit('create',self._checkpoint(status='running'),self._activated)

    def _activate(self,record):
        self.current=record;self.session=record.session;self.next_sequence=record.sequence;self.last_confirmed=record.sequence
        self._set_busy('activate');self._submit('save',self._checkpoint(status='running'),self._activated)

    def _checkpoint(self,*,status=None):
        self.next_sequence+=1
        c=self.current
        return export_checkpoint(self.session,c.mode,c.player_color,c.theme,c.game_id,self.next_sequence,status=status)

    def _activated(self,reply):
        self.current=reply.result;self.session=reply.result.session;self.next_sequence=reply.result.sequence;self.last_confirmed=reply.result.sequence
        self.session.clock.now=self.now
        self.known_active=reply.result;self.failed=False;self.retry_button.hide()
        if self.closing:
            self._set_busy(None);self.exit_destination=None;self.save_leave('close');return
        setup=GameSetup(Opponent(reply.result.mode),PlayerColor(reply.result.player_color))
        self.window.install_rule_session(setup,self.session)
        self._set_busy(None);self._resume_live();self._refresh_menu();self._saved_status()
        self._apply_learning(reply.result)

    def _resume_live(self):
        self.session.resume();page=self.window.rule_page
        if self.session.running:page.timer.start()
        page.board.select(page.adapter.selected_square);page.refresh_session()
        self.fingerprint=self._fingerprint()
        if self.session.pending_promotion and page.dialog is None:page.open_promotion(PROMOTIONS)

    def _fingerprint(self):
        s=self.session
        return (s.revision,len(s.events),s.bound_source,s.bound_castle,s.draw_claim_barred,s.pending_promotion,s.result)

    def observe(self):
        if self.session is None or self.window.rule_page.session is not self.session or self.busy or self.failed:return
        fingerprint=self._fingerprint()
        if fingerprint==self.fingerprint:return
        self.fingerprint=fingerprint
        self._submit('save',self._checkpoint(),self._autosaved)
        self.status.setText('Spielstand wird automatisch gesichert …')

    def _autosaved(self,reply):
        self.last_confirmed=max(self.last_confirmed,reply.result.sequence)
        if self.current and self.current.game_id==reply.result.game_id:self.current.sequence=reply.result.sequence
        self.known_active=None if reply.result.session.result else reply.result
        self._refresh_menu()
        if not self.failed:
            if self.service.pending:self.status.setText('Weitere Änderungen werden noch gesichert …')
            else:self._saved_status()

        self._apply_learning(reply.result)

    def _apply_learning(self, record):
        state = record.learning
        if state is None:
            return
        if self.current and self.current.game_id == record.game_id:
            self.current.learning = state
            if state.report:
                self.window.rule_page.set_learning_report(state.report)
            if state.recovered:
                self.status.setText('Adaptive Gewichte aus stabilem Ausgangsstand wiederhergestellt.')
        if state.pending_notice:
            self._check_learning_notice()

    def _check_learning_notice(self):
        if not self.learning_notice_busy and not self.closing:
            self.learning_notice_busy=True
            self._submit('next_learning_notice', None, self._show_learning_notice)

    def _show_learning_notice(self, reply):
        if not reply.result or self.closing:
            self.learning_notice_busy=False
            return
        milestone, _ = reply.result
        box = QMessageBox(self.window)
        box.setWindowTitle('Adaptive Grandmaster AI')
        box.setText('Fünf Lernpartien abgeschlossen. Eine Überprüfung der aktuellen Adaptive-KI ist empfohlen.')
        box.setInformativeText('Im KI-Testzentrum kannst du den Vergleich manuell starten.')
        later = box.addButton('Später', QMessageBox.ButtonRole.RejectRole)
        center = box.addButton('KI-Testzentrum', QMessageBox.ButtonRole.ActionRole)
        box.setDefaultButton(later)
        box.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        box.setModal(False)

        def acknowledge(_):
            if self.closing:
                self.learning_notice_busy=False
                return
            if box.clickedButton() is center and self.window.review_center:
                self.window.review_center.open_center()
            self._submit('acknowledge_learning_notice', milestone, acknowledged)

        def acknowledged(_):
            self.learning_notice_busy=False
            self._check_learning_notice()

        box.finished.connect(acknowledge)
        box.show()

    def _saved_status(self):
        self.status.setText('Automatisch lokal gespeichert.')

    def save_leave(self,destination='menu'):
        if self.session is None:
            if destination=='close':self._request_idle_close()
            return
        if self.busy or self.failed:return
        self.exit_destination=destination;self._set_busy('leave')
        self.session.suspend();page=self.window.rule_page;page.timer.stop();page.board.stop()
        if page.dialog is not None:
            dialog=page.dialog;page.dialog=None;dialog.reject()
        page.refresh_session()
        self._submit('save',self._checkpoint(status='suspended'),self._left)
        self.status.setText('Uhren angehalten. Spielstand wird gesichert …')

    def _left(self,reply):
        self._apply_learning(reply.result)
        self.last_confirmed=reply.result.sequence;self.known_active=None if reply.result.session.result else reply.result
        destination=self.exit_destination;self.exit_destination=None
        self.session=None;self.current=None;self.fingerprint=None
        self._set_busy(None);self._refresh_menu()
        self.window.rule_page.leave()
        self.status.setText('Erfolgreich lokal gespeichert. Beide Uhren stehen.')
        if destination=='close':self._finish_close()
        elif destination=='summary':self.window.navigation.show_summary()
        else:self.window.navigation.home()

    def retry(self):
        if self.service.pending or self.dialog is not None:return
        self.retry_button.setEnabled(False)
        if self.session is None:self.initialize();return
        self._set_busy('retry');self.retrying=True
        status='suspended' if self.exit_destination else 'running'
        self._submit('retry',self._checkpoint(status=status),self._retried)

    def _retried(self,reply):
        self.failed=False;self.retrying=False;self.retry_button.hide()
        self.next_sequence=reply.result.sequence;self.last_confirmed=reply.result.sequence;self.current.sequence=reply.result.sequence
        if self.closing:
            self._set_busy(None);self.exit_destination=None;self.save_leave('close');return
        if self.exit_destination:self._left(reply)
        elif self.window.rule_page.session is not self.session:self._activated(reply)
        else:
            self._set_busy(None);self._resume_live();self._autosaved(reply)

    def request_close(self):
        if self.dialog is not None:
            dialog=self.dialog;self.dialog=None;dialog.reject();self.dialog_buttons={}
        if self.busy=='retry':
            self.closing=True;return False
        if self.failed and self.session is not None:
            def chosen(key):
                if key=='retry':self.exit_destination='close';self.retry()
                elif key=='force':self._confirm_unsaved_close()
            self._prompt('Nicht gesicherte Änderungen','Die aktuelle Partie konnte nicht vollständig gespeichert werden. Der letzte bestätigte Datenbankstand bleibt erhalten.',[('retry','Erneut speichern und beenden',QMessageBox.ButtonRole.AcceptRole),('keep','Offen halten',QMessageBox.ButtonRole.RejectRole),('force','Ohne Speichern beenden …',QMessageBox.ButtonRole.DestructiveRole)],chosen,'keep',icon=QMessageBox.Icon.Warning)
            return False
        if self.session is not None:
            self.closing=True
            if self.busy:
                if self.busy=='leave':self.exit_destination='close'
                return False
            self.save_leave('close');return False
        self._request_idle_close();return False

    def _confirm_unsaved_close(self):
        def chosen(key):
            if key=='force':
                self.window.rule_page.leave();self.session=None;self.current=None
                self._request_idle_close()
        self._prompt('Ungesicherte Änderungen wirklich verlieren?','Nur der letzte erfolgreich gespeicherte Checkpoint bleibt erhalten. Noch nicht gesicherte Züge und Zeiten gehen verloren. Die Datenbank wird nicht gelöscht.',[('force','Verlust bestätigen und beenden',QMessageBox.ButtonRole.DestructiveRole),('keep','Offen halten',QMessageBox.ButtonRole.RejectRole)],chosen,'keep',icon=QMessageBox.Icon.Warning)

    def _request_idle_close(self):
        self.closing=True
        if not self.service.pending:self._finish_close()

    def _finish_close(self):
        if self.window._allow_close or self.service.pending:return
        if self.window.review_center and not self.window.review_center.prepare_close():
            QTimer.singleShot(20,self._finish_close);return
        if not self.window.amateur.prepare_close() or not self.window.grandmaster.prepare_close() or not self.window.adaptive.prepare_close():
            QTimer.singleShot(10,self._finish_close);return
        if self.service.shutdown():
            self.window._allow_close=True;QTimer.singleShot(0,self.window.close)
