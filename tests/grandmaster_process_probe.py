"""Real process crash/restart while a Grandmaster job is alive; isolated DB only."""
from pathlib import Path
import json,os,sys,time
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PySide6.QtCore import QCoreApplication,QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from ai.grandmaster import GrandmasterConfig
from database.store import GameStore
from ui.main_window import MainWindow
from ui.navigation import Opponent,PlayerColor


def wait(app,predicate):
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        app.processEvents()
        if predicate():return
        QTest.qWait(5)
    raise AssertionError('Grandmaster subprocess timed out')


def main():
    crash=sys.argv[1]=='--crash';path=Path(sys.argv[2]).resolve()
    config=GrandmasterConfig(soft_seconds=.5 if crash else 0,max_seconds=1.5 if crash else .3,max_depth=5 if crash else 3,q_depth=4)
    app=QApplication([]);w=MainWindow(storage_path=path,startup_prompt=not crash,grandmaster_config=config);w.show()
    wait(app,lambda:w.storage.ready)
    if crash:
        n=w.navigation;n.new_game();n.choose_opponent(Opponent.GRANDMASTER);n.choose_color(PlayerColor.BLACK);n.show_summary();w.summary_page.play_button.click()
        wait(app,lambda:w.grandmaster.pending is not None and not w.storage.service.pending)
        saved=GameStore(path).load_active()
        assert saved.session.play_kind=='grandmaster_ai' and not saved.session.human_turn and not saved.session.records
        assert w.grandmaster.thread.isRunning();os._exit(29)
    wait(app,lambda:w.storage.dialog is not None);assert w.grandmaster.starts==0
    w.storage.dialog_buttons['resume'].click()
    wait(app,lambda:w.rule_page.session is not None and w.rule_page.session.revision==1 and w.grandmaster.thread is None and not w.storage.service.pending)
    s=w.rule_page.session
    assert w.grandmaster.starts==w.grandmaster.accepted==1 and w.amateur.starts==0 and s.clock.completed_moves==1
    assert 908<s.clock.remaining[True]<=910
    w.close();wait(app,lambda:not w.isVisible() and not w.storage.service.thread.isRunning())
    saved=GameStore(path).load_active();assert len(saved.session.records)==1 and saved.session.suspended
    print(json.dumps({'new_jobs':1,'accepted':1,'increments':1,'kind':saved.session.play_kind,'white_seconds':saved.session.clock.remaining[True]}))
    w.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)


if __name__=='__main__':main()
