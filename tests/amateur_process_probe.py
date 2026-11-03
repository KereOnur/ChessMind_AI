"""Child-process crash/restart probe; only paths provided inside the project."""
import json,os,sys,time
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PySide6.QtCore import QCoreApplication,QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from ai.amateur import AmateurConfig
from database.store import GameStore
from ui.main_window import MainWindow
from ui.navigation import Opponent,PlayerColor,Page


def wait(app,predicate):
    deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        app.processEvents()
        if predicate():return
        QTest.qWait(5)
    raise AssertionError('Child-process probe timed out')


def main():
    crash=sys.argv[1]=='--crash';path=Path(sys.argv[2]).resolve()
    app=QApplication([]);w=MainWindow(storage_path=path,startup_prompt=not crash,amateur_config=AmateurConfig(target_seconds=1.2 if crash else .2,max_search_seconds=1.5))
    w.show();wait(app,lambda:w.storage.ready)
    if crash:
        n=w.navigation;n.new_game();n.choose_opponent(Opponent.AMATEUR);n.choose_color(PlayerColor.BLACK);n.show_summary();w.summary_page.play_button.click()
        wait(app,lambda:w.amateur.pending is not None and not w.storage.service.pending)
        saved=GameStore(path).load_active()
        assert saved.session.play_kind=='amateur_ai' and not saved.session.human_turn and not saved.session.records
        assert w.amateur.thread.isRunning()
        os._exit(29) # Deliberately no Qt shutdown; actual old worker process dies.
    wait(app,lambda:w.storage.dialog is not None)
    assert w.amateur.starts==0
    w.storage.dialog_buttons['resume'].click()
    wait(app,lambda:w.rule_page.session is not None and w.rule_page.session.revision==1 and w.amateur.thread is None and not w.storage.service.pending)
    s=w.rule_page.session
    assert w.amateur.starts==w.amateur.accepted==1 and s.clock.completed_moves==1 and 909<s.clock.remaining[True]<=910
    w.close();wait(app,lambda:not w.isVisible() and not w.storage.service.thread.isRunning())
    saved=GameStore(path).load_active()
    assert len(saved.session.records)==1 and saved.session.suspended and saved.session.human_turn
    print(json.dumps({'fresh_jobs':1,'accepted_moves':1,'completed_moves':s.clock.completed_moves,'white_seconds':saved.session.clock.remaining[True],'play_kind':saved.session.play_kind}))
    w.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)


if __name__=='__main__':main()
