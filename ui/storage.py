"""Serialized SQLite work off the GUI thread; immutable checkpoints cross threads."""
from dataclasses import dataclass
import logging
from logging.handlers import RotatingFileHandler
from PySide6.QtCore import QObject,QThread,Signal,Slot
from database.store import GameStore,DEFAULT_PATH
from game.checkpoint import pack


@dataclass(frozen=True)
class StorageRequest:
    token:int
    operation:str
    payload:object=None


@dataclass(frozen=True)
class StorageReply:
    token:int
    operation:str
    result:object=None
    error:str|None=None
    skipped:bool=False


class StorageWorker(QObject):
    completed=Signal(object)

    def __init__(self,path,logger):
        super().__init__();self.store=GameStore(path);self.logger=logger;self.blocked=set()

    @Slot(object)
    def perform(self,request):
        op=request.operation;payload=request.payload;game_id=None
        if op in ('create','save','retry'):game_id=payload.data['game_id']
        if op in ('create','save') and game_id in self.blocked:
            self.completed.emit(StorageReply(request.token,op,skipped=True));return
        try:
            if op=='initialize':
                from evaluation.repository import Reviews
                self.store.initialize()
                Reviews(self.store.path).recover()
                result=self.store.load_active()
            elif op=='next_learning_notice':result=self.store.next_learning_notice()
            elif op=='acknowledge_learning_notice':result=self.store.acknowledge_learning_notice(payload)
            elif op.startswith('review_'):
                from evaluation.repository import Reviews, worker_lock
                from evaluation.statistics import dashboard, player_stats
                reviews=Reviews(self.store.path)
                result=None
                if op=='review_dashboard':result=dashboard(self.store.path,recover=payload)
                elif op=='review_training_status':
                    from evaluation.training import Training
                    result=Training(self.store.path).status(recover=True)
                elif op=='review_training_abort':
                    from evaluation.training import Training
                    with worker_lock(self.store):Training(self.store.path).stop(payload,'aborted')
                elif op=='review_statistics':result=(player_stats(self.store.path),dashboard(self.store.path))
                elif op=='review_abort':
                    with worker_lock(self.store):reviews.stop(payload,'aborted')
                elif op=='review_promote':reviews.change_model(run_id=payload)
                elif op=='review_restore':reviews.change_model(restore=payload)
                else:raise ValueError('Unbekannter Prüfauftrag.')
            elif op=='load':result=self.store.load_active()
            elif op=='create':result=self.store.create(payload)
            elif op=='save':result=self.store.save(payload)
            elif op=='discard':result=self.store.discard(*payload)
            elif op=='retry':
                previous=self.store.read_owned(game_id);d=payload.data
                d['sequence']=previous.sequence+1 if previous else 0
                rebased=pack(d)
                result=self.store.save(rebased) if previous else self.store.create(rebased)
                self.blocked.discard(game_id)
            else:raise ValueError('Unbekannter Datenbankauftrag.')
            self.completed.emit(StorageReply(request.token,op,result))
        except Exception as exc:
            if game_id:self.blocked.add(game_id)
            self.logger.exception('Operation %s / Partie %s fehlgeschlagen',op,game_id)
            self.completed.emit(StorageReply(request.token,op,error=str(exc)))


class StorageService(QObject):
    requested=Signal(object)
    completed=Signal(object)

    def __init__(self,path=DEFAULT_PATH,parent=None):
        super().__init__(parent);self.path=path;self.pending=set();self.serial=0
        self.logger=logging.getLogger('neurochess.storage.'+str(id(self)));self.logger.setLevel(logging.ERROR);self.logger.propagate=False
        self.handler=RotatingFileHandler(DEFAULT_PATH.parent/'diagnostics.log',maxBytes=1_000_000,backupCount=2,encoding='utf-8',delay=True)
        self.handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        self.logger.addHandler(self.handler)
        self.thread=QThread(self);self.thread.setObjectName('NeuroChess SQLite')
        self.worker=StorageWorker(path,self.logger);self.worker.moveToThread(self.thread)
        self.requested.connect(self.worker.perform);self.worker.completed.connect(self._finished)
        self.thread.finished.connect(self.worker.deleteLater);self.thread.start()

    def submit(self,operation,payload=None):
        self.serial+=1;self.pending.add(self.serial)
        self.requested.emit(StorageRequest(self.serial,operation,payload));return self.serial

    @Slot(object)
    def _finished(self,reply):
        self.pending.discard(reply.token);self.completed.emit(reply)

    def shutdown(self):
        if self.pending:return False
        self.thread.quit()
        if not self.thread.wait(2000):return False
        self.logger.removeHandler(self.handler);self.handler.close();return True
