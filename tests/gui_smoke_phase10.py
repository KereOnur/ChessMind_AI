"""Native Cocoa integration through main.py with an isolated database."""
from pathlib import Path
import runpy
import sys
import time
from uuid import uuid4

import chess
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from database.store import GameStore
from ui import main_window
from ui.navigation import Opponent, Page, PlayerColor

DB = ROOT/'.venv/.tmp'/f'phase10-{uuid4()}'/'integration.sqlite3'
OriginalWindow = main_window.MainWindow


def wait(condition, seconds=20):
    deadline = time.monotonic()+seconds
    while time.monotonic()<deadline:
        QApplication.instance().processEvents()
        if condition():
            return
        time.sleep(.01)
    raise AssertionError('Native integration timed out')


def exercise(window):
    assert QApplication.instance().platformName()=='cocoa'
    wait(lambda:window.storage.ready)
    assert window.isVisible() and window.navigation.page==Page.MENU
    window.resize(940,720)
    window.showFullScreen()
    wait(window.isFullScreen)
    window.showNormal()
    wait(lambda:not window.isFullScreen())
    for opponent,theme,controller in (
        (Opponent.AMATEUR,'classic',window.amateur),
        (Opponent.GRANDMASTER,'wood',window.grandmaster),
        (Opponent.ADAPTIVE,'cyber',window.adaptive),
    ):
        window.menu_page.menu_buttons['Neues Spiel'].click()
        window.navigation.choose_opponent(opponent)
        window.navigation.choose_color(PlayerColor.BLACK)
        window.navigation.show_summary()
        window.summary_page.play_button.click()
        page=window.rule_page
        wait(lambda:page.active and page.session.revision==1)
        wait(lambda:not window.storage.service.pending)
        assert page.theme.key==theme and controller.accepted==1
        game=page.session
        assert game.records[0].move in chess.Board().legal_moves
        assert game.clock.completed_moves==1 and game.human_turn
        saved=GameStore(DB).load_active()
        assert saved.session.revision==1 and saved.theme==theme
        page.resign_button.click()
        page.dialog.button(QMessageBox.StandardButton.Yes).click()
        wait(lambda:game.result and not window.storage.service.pending)
        if opponent==Opponent.ADAPTIVE:
            wait(page.learning_button.isVisible)
            page.learning_button.click()
            assert 'Lernbericht' in page.dialog.windowTitle()
            page.dialog.reject()
        page.save_button.click()
        wait(lambda:window.navigation.page==Page.MENU and not window.storage.service.pending)
        print(f'{opponent.value}: legal opening, theme, autosave, result',flush=True)
    window.menu_page.menu_buttons['Statistiken'].click()
    wait(lambda:window.statistics_page.tabs.count()==2)
    window.statistics_page.reject()
    window.menu_page.menu_buttons['KI-Testzentrum'].click()
    center=window.review_center
    wait(lambda:center.data is not None)
    assert center.data['events']==2 and not center.buttons['start'].isEnabled()
    center.training_button.click()
    wait(center.training.buttons['start'].isEnabled)
    assert center.training.bar.maximum()==600 and center.training.worker is None
    center.training.reject()
    center.reject()
    print('Cocoa startup, fullscreen, statistics and training navigation passed',flush=True)


class SmokeWindow(OriginalWindow):
    def __init__(self):
        super().__init__(storage_path=DB,startup_prompt=False)
        QTimer.singleShot(200,self.verify)

    def verify(self):
        try:
            exercise(self)
        except Exception:
            import traceback
            traceback.print_exc()
            self.failed=True
        self.close()


window_ref = []
class IntegrationWindow(SmokeWindow):
    def __init__(self):
        super().__init__()
        window_ref.append(self)

main_window.MainWindow=IntegrationWindow
try:
    runpy.run_path(str(ROOT/'main.py'),run_name='__main__')
except SystemExit as exc:
    raise SystemExit(1 if getattr(window_ref[0],'failed',False) else exc.code)
