"""One cancellable amateur job; only the GUI thread may commit its result."""
from dataclasses import dataclass
from threading import Event
import secrets
from PySide6.QtCore import QObject,QThread,QTimer,Signal,Slot
from ai.amateur import AmateurConfig,search


@dataclass(frozen=True)
class Job:
    generation:int
    session_id:int
    revision:int
    turn:bool
    fen:str


class AmateurThread(QThread):
    completed=Signal(object,object,object)

    def __init__(self,job,board,remaining,config,seed,parent=None):
        super().__init__(parent);self.job=job;self.board=board;self.remaining=remaining
        self.config=config;self.seed=seed;self.cancel_event=Event()
        self.setObjectName('NeuroChess Amateur')

    def run(self):
        try:
            result=search(self.board,self.remaining,seed=self.seed,config=self.config,cancel=self.cancel_event)
            self.completed.emit(self.job,result,None)
        except Exception as exc:self.completed.emit(self.job,None,str(exc))


class AmateurController(QObject):
    play_kind='amateur_ai'
    thread_type=AmateurThread
    config_type=AmateurConfig
    def __init__(self,window,config=None):
        super().__init__(window);self.window=window;self.page=window.rule_page
        self.config=config or self.config_type();self.thread=None;self.pending=None
        self.generation=0;self.starts=0;self.accepted=0;self.discarded=0;self.last_result=None;self.error=False;self.context=None
        self.page.state_changed.connect(self.sync);self.page.deactivated.connect(self.cancel)
        self.page.ai_retry_button.clicked.connect(self.retry)

    def job_config(self):
        return self.config

    def cancel(self):
        self.generation+=1;self.pending=None
        if self.thread is not None:self.thread.cancel_event.set()

    def prepare_close(self):
        self.cancel();return self.thread is None

    def eligible(self):
        s=self.page.session;storage=self.window.storage
        return self.page.active and s is not None and s.play_kind==self.play_kind and s.running and not s.human_turn and not self.error and (storage is None or (storage.session is s and not storage.busy and not storage.failed and not storage.closing))

    @Slot()
    def sync(self):
        if self.context is not self.page.session:
            self.cancel();self.context=self.page.session;self.error=False
        if not self.eligible():
            if self.pending is not None:self.cancel()
            return
        s=self.page.session
        if self.thread is not None:return
        for name in ('amateur','grandmaster','adaptive'):
            other=getattr(self.window,name,None)
            if other is not None and other is not self and other.thread is not None:return
        s.tick()
        if not s.running:return
        self.generation+=1
        job=Job(self.generation,id(s),s.revision,s.board.turn,s.board.fen(en_passant='fen'))
        thread=self.thread_type(job,s.board.copy(stack=True),s.clock.remaining[s.board.turn],self.job_config(),secrets.randbits(64),self)
        self.pending=job;self.thread=thread;self.starts+=1
        thread.completed.connect(self.deliver);thread.finished.connect(lambda:self.finished(thread));thread.start()

    @Slot(object,object,object)
    def deliver(self,job,result,error):
        s=self.page.session
        valid=(self.pending==job and self.eligible() and id(s)==job.session_id and s.revision==job.revision and s.board.turn==job.turn and s.board.fen(en_passant='fen')==job.fen)
        if self.pending!=job:self.discarded+=1;return
        self.pending=None
        if not valid:self.discarded+=1;return
        if error:self.fail(error);return
        self.last_result=result
        if result.cancelled or result.move is None:self.discarded+=1;return
        attempt=s.try_engine_move(result.move,expected_revision=job.revision)
        if attempt.accepted:
            self.accepted+=1;self.page.render_record(attempt.record)
        else:
            self.discarded+=1
            if s.running:self.fail('Kein legaler KI-Zug angenommen.');return
        self.page.refresh_session()

    def fail(self,error):
        self.cancel()
        self.error=True;self.page.session.suspend();self.page.timer.stop()
        self.page.action_notice.setText('KI-Berechnung fehlgeschlagen. Die Partie ist angehalten. '+error)
        self.page.action_notice.show();self.page.ai_retry_button.show();self.page.refresh_session()

    def finished(self,thread):
        if self.thread is thread:self.thread=None;self.pending=None
        thread.deleteLater();QTimer.singleShot(0,self.sync)

    def retry(self):
        storage=self.window.storage
        if not self.page.active or self.page.session is None or self.page.session.play_kind!=self.play_kind or (storage and (storage.failed or storage.busy)):return
        self.error=False;self.page.ai_retry_button.hide()
        self.page.session.resume()
        if self.page.session.running:self.page.timer.start()
        self.page.refresh_session()
