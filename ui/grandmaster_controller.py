"""Grandmaster job binding; lifecycle shared, search/evaluation fully independent."""
from PySide6.QtCore import QThread,Signal
from threading import Event
from ai.grandmaster import GrandmasterConfig,search
from ui.amateur_controller import AmateurController


class GrandmasterThread(QThread):
    completed=Signal(object,object,object)

    def __init__(self,job,board,remaining,config,seed,parent=None):
        super().__init__(parent);self.job=job;self.board=board;self.remaining=remaining
        self.config=config;self.cancel_event=Event();self.setObjectName('NeuroChess Großmeister')

    def run(self):
        try:self.completed.emit(self.job,search(self.board,self.remaining,config=self.config,cancel=self.cancel_event),None)
        except Exception as exc:self.completed.emit(self.job,None,str(exc))


class GrandmasterController(AmateurController):
    play_kind='grandmaster_ai'
    thread_type=GrandmasterThread
    config_type=GrandmasterConfig
