"""Real local rule test using the existing board, themes and responsive layout."""
import time
import chess
from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import QDialog, QMessageBox, QPushButton, QScrollArea
from game.session import GameSession, AI_KINDS
from ui.navigation import OPPONENTS, PlayerColor
from ui.board.demo import PieceSpec
from ui.board.page import BoardPreviewPage
from ui.board.themes import THEMES
from ui.rule_test.dialogs import DrawClaimDialog, PromotionDialog
from ui.rule_test.input import RuleInput, square_index, square_tuple
from ui.rule_test.panels import LivePlayerBar, SanMoveList


class RuleTestPage(BoardPreviewPage):
    deactivated=Signal()
    state_changed=Signal()
    save_requested=Signal()
    def __init__(self,parent=None):
        self.persistence_enabled=False;self.session=None;self.dialog=None;self.last_rendered=-1;self.last_result=None
        super().__init__(parent)
        self.timer=QTimer(self);self.timer.setInterval(50)
        self.timer.timeout.connect(self.refresh_session)
        self.claim_button=QPushButton('Remis beantragen')
        self.claim_button.clicked.connect(self.prepare_claim)
        self.sidebar_layout.insertWidget(self.sidebar_layout.indexOf(self.save_button),self.claim_button)
        self.sidebar_title.setText('REGELTEST · LOKAL')
        self.banner.setText('Regeltest – zwei manuelle Spieler, noch keine KI')
        self.board.setAccessibleName('Regeltest-Schachbrett mit Berührt-geführt')
        self.claim_button.setToolTip('Regelanspruch, kein freiwilliges Remisangebot. Vor dem Berühren beantragen; unbegründet: 60 Sekunden für den Gegner.')
        self.ai_retry_button=QPushButton('KI-Berechnung erneut starten');self.ai_retry_button.hide()
        self.sidebar_layout.insertWidget(self.sidebar_layout.indexOf(self.save_button),self.ai_retry_button)

        self.learning_report = None
        self.learning_button = QPushButton('Lernbericht öffnen')
        self.learning_button.hide()
        self.learning_button.clicked.connect(self.show_learning_report)
        self.sidebar_layout.addWidget(self.learning_button)

    def show_learning_report(self):
        if self.learning_report is not None and self.active and self.session.result:
            from ui.learning_report import LearningReport
            self.open_dialog(LearningReport(self.learning_report, self), lambda *_: None)

    def set_learning_report(self, report):
        self.learning_report = report
        self.learning_button.setVisible(report is not None)
        if report is not None:
            self.fit_preview()

    def create_player_bar(self):return LivePlayerBar()

    def create_move_list(self):return SanMoveList()

    def configure(self,setup,*,board=None,now=time.monotonic,initial_seconds=900,session=None):
        self.leave();self.active=True
        self.set_learning_report(None)
        self.setup=setup;self.theme=THEMES[setup.opponent]
        self.own_color=setup.player_color==PlayerColor.WHITE
        self.session=session if session is not None else GameSession(board,now=now,initial_seconds=initial_seconds)
        self.is_amateur=self.session.play_kind=='amateur_ai'
        self.is_ai=self.session.play_kind in AI_KINDS
        self.ai_title=OPPONENTS[setup.opponent].title
        self.ai_name=self.session.ai_name
        self.ai_retry_button.hide()
        self.sidebar_title.setText(self.ai_title.upper()+' · LOKAL' if self.is_ai else 'REGELTEST · LOKAL')
        self.banner.setText('Partie gegen '+self.ai_title+' · Rapid 15+10' if self.is_ai else 'Regeltest – zwei manuelle Spieler, noch keine KI')
        self.adapter=RuleInput(self)
        self.position=self.snapshot()
        self.board.configure(self.theme,'white' if self.own_color else 'black',self.position,self.adapter)
        self.mode_label.setText(self.ai_title if self.is_ai else OPPONENTS[setup.opponent].title+' · Brettdesign')
        self.theme_label.setText(self.theme.title+'  ·  Rapid 15+10')
        self.player_label.setText(('Du spielst ' if self.is_ai else 'Zwei manuelle Spieler · deine Brettseite: ')+setup.player_color.value)
        self.input_hint.setText('Nur legale Züge. Berührt-geführt: Eine bewegliche eigene Figur bleibt verbindlich ausgewählt. Keine Zughilfe.')
        self.action_notice.hide();self.exit_button.hide()
        self.last_rendered=-1;self.last_result=None
        self.verticalScrollBar().setValue(0)
        if session is not None:self.render_record(None)
        self.refresh_session()
        if self.session.running:self.timer.start()
        QTimer.singleShot(0,self.fit_preview)

    def snapshot(self):
        return {square_tuple(square):PieceSpec('white' if piece.color else 'black',chess.piece_name(piece.piece_type)) for square,piece in self.session.board.piece_map().items()}

    def render_record(self,record):
        movements=[]
        if record:
            movements.append((square_tuple(record.move.from_square),square_tuple(record.move.to_square)))
            if record.rook_shift:movements.append(tuple(square_tuple(square) for square in record.rook_shift))
        self.board.apply_position(self.snapshot(),movements)
        self.position=self.board.position
        self.last_rendered=self.session.revision
        last=self.session.records[-1].move if self.session.records else None
        check=self.session.board.king(self.session.board.turn) if self.session.board.is_check() else None
        self.board.mark_status((square_tuple(last.from_square),square_tuple(last.to_square)) if last else None,square_tuple(check) if check is not None else None)
        self.move_list.update_records(self.session.records)

    def refresh_session(self):
        if not self.active or self.session is None:return
        self.session.tick()
        if self.last_rendered!=self.session.revision:
            self.render_record(self.session.records[-1] if self.session.records else None)
        for bar,color in ((self.top_player,not self.own_color),(self.bottom_player,self.own_color)):
            name=('Du' if color==self.session.human_color else self.ai_name) if self.is_ai else 'Spieler '+('Weiß' if color else 'Schwarz')
            bar.update_live(name,color,self.session,self.theme,self.board.resources)
        turn='Weiß' if self.session.board.turn else 'Schwarz'
        self.context_label.setText(('Am Zug: '+turn+(' · Schach!' if self.session.board.is_check() else '')+'\nRapid 15+10 · beide Farben manuell') if self.session.running else ('Partie angehalten · beide Uhren stehen' if self.session.suspended and self.session.result is None else 'Partie beendet · beide Uhren stehen'))
        if self.is_ai:
            if self.session.result:status='Partie beendet'
            elif self.session.suspended:status='Partie angehalten · beide Uhren stehen'
            elif self.session.human_turn:
                last=self.session.records[-1] if self.session.records else None
                status=(self.ai_name+' hat gezogen · ' if last and last.color!=self.own_color else '')+'Du bist am Zug'
            else:status=self.ai_name+' überlegt …'
            self.context_label.setText(status+(' · Schach!' if self.session.board.is_check() else '')+'\nRapid 15+10')
        self.claim_button.setEnabled(self.session.running and self.session.human_turn and not self.session.draw_claim_barred and self.dialog is None)
        self.resign_button.setEnabled(self.session.running and self.dialog is None)
        if self.session.result is not None:
            self.timer.stop()
            if self.last_result!=self.session.result:
                self.last_result=self.session.result
                self.action_notice.setText(self.session.result.text);self.action_notice.show()
                if self.session.result.reason.startswith(('Zeit','Aufgabe')):self.board.stop()
                if self.dialog is not None:self.dialog.reject()
                self.board.select(None)
                self.fit_preview()
                QTimer.singleShot(0,self.reveal_notice)

        self.state_changed.emit()

    def show_save_notice(self):
        if self.persistence_enabled:self.save_requested.emit()
        else:
            # Historical non-persistent test harness; normal application uses SQLite.
            self.action_notice.setText('Spielstände sind ab Phase 5 verfügbar.')
            self.action_notice.show();self.exit_button.show();self.fit_preview()
            QTimer.singleShot(0,self.reveal_notice)

    def handle_attempt(self,attempt,intent):
        self.input_hint.setText(attempt.message)
        if attempt.accepted:self.render_record(attempt.record)
        else:
            item=self.board.pieces.get(intent.source)
            if item and item.pos()!=self.board.square_center(intent.source):
                self.board.animator.animate(item,self.board.square_center(intent.source),self.theme)
            if attempt.promotion_choices:self.open_promotion(attempt.promotion_choices)
        self.refresh_session()

    def open_dialog(self,dialog,callback):
        if self.dialog is not None:return
        self.dialog=dialog;session=self.session
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        handled=False
        def finished(code):
            nonlocal handled
            if handled:return
            handled=True
            if self.dialog is not dialog:return
            self.dialog=None
            if self.active and self.session is session:callback(dialog,code)
            self.refresh_session()
        dialog.finished.connect(finished)
        dialog.open();self.refresh_session()

    def open_promotion(self,choices):
        pending=self.session.pending_promotion
        dialog=PromotionDialog(choices,self)
        def done(dialog,code):
            if code==QDialog.DialogCode.Accepted and self.session.pending_promotion==pending:
                source,target,revision=pending
                attempt=self.session.try_move(source,target,dialog.selected_piece,expected_revision=revision)
                self.input_hint.setText(attempt.message)
                if attempt.accepted:self.render_record(attempt.record)
            else:self.session.cancel_promotion()
            self.board.select(self.adapter.selected_square)
        self.open_dialog(dialog,done)

    def prepare_claim(self):
        self.refresh_session()
        if not self.session.running or not self.session.human_turn or self.session.draw_claim_barred or self.dialog is not None:return
        revision=self.session.revision
        dialog=DrawClaimDialog(self.session,self)
        def done(dialog,code):
            if code!=QDialog.DialogCode.Accepted:return
            if revision!=self.session.revision:return
            decision=self.session.claim_draw(dialog.intended_move)
            if decision.forced_move:self.render_record(decision.forced_move)
            self.action_notice.setText(decision.message);self.action_notice.show()
            self.fit_preview();QTimer.singleShot(0,self.reveal_notice)
        self.open_dialog(dialog,done)

    def show_resign_notice(self):
        self.refresh_session()
        if not self.session.running or self.dialog is not None:return
        revision=self.session.revision
        who='Weiß' if (self.session.human_color if self.is_ai else self.session.board.turn) else 'Schwarz'
        dialog=QMessageBox(QMessageBox.Icon.Question,'Aufgabe bestätigen',('Möchtest du als '+who+' aufgeben?' if self.is_ai else who+' ist am Zug. Möchtest du für '+who+' aufgeben?'),QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,self)
        dialog.button(QMessageBox.StandardButton.Yes).setText('Aufgeben')
        dialog.button(QMessageBox.StandardButton.No).setText('Weiter spielen')
        dialog.setDefaultButton(QMessageBox.StandardButton.No)
        def done(dialog,code):
            if code==QMessageBox.StandardButton.Yes and (self.is_ai or revision==self.session.revision):self.session.resign()
        self.open_dialog(dialog,done)

    def leave(self):
        self.deactivated.emit()
        self.active=False
        if hasattr(self,'timer'):self.timer.stop()
        if self.session is not None:self.session.abandon()
        if self.dialog is not None:
            dialog=self.dialog;self.dialog=None;dialog.reject()
        self.board.stop()

    def hideEvent(self,event):
        # Minimizing must not stop or abandon a running clock. Navigation and
        # application close call leave() explicitly in the main window.
        self.board.stop();QScrollArea.hideEvent(self,event)
