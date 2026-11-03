"""Production Qt wiring, gated searches and committed learning reports."""
from threading import Event

import chess
import pytest
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox, QTableWidget

from database.store import GameStore
from ui.adaptive_controller import AdaptiveThread
from ui.main_window import MainWindow
from ui.navigation import Opponent, PlayerColor, Page
from test_adaptive_core import FAST
from test_grandmaster_ui import close
from test_persistence_ui import until, settle, resume
from test_rule_ui import sqclick
from tests_fake_time import FakeTime


@pytest.fixture
def adaptive_window(app, tmp_path):
    release = Event()

    class GatedThread(AdaptiveThread):
        def run(self):
            while not release.is_set() and not self.cancel_event.wait(.005):
                pass
            super().run()

    window = MainWindow(storage_path=tmp_path/'adaptive.sqlite3', startup_prompt=False,
                        clock_now=FakeTime(), adaptive_config=FAST)
    window.adaptive.thread_type = GatedThread
    window.release = release
    window.show()
    until(app, lambda: window.storage.ready)
    settle(window, app)
    yield window
    if window.isVisible():
        close(window, app)


def start(window, app, color):
    n = window.navigation
    n.new_game()
    n.choose_opponent(Opponent.ADAPTIVE)
    n.choose_color(color)
    n.show_summary()
    assert window.summary_page.play_button.text() == 'Partie gegen Adaptive Grandmaster AI starten'
    window.summary_page.play_button.click()
    until(app, lambda: window.navigation.page == Page.RULE_TEST and window.rule_page.session.running)
    return window.rule_page


def result_count(window):
    with GameStore(window.storage.service.path).connection() as con:
        return con.execute('SELECT count(*) FROM learning_events').fetchone()[0]


@pytest.mark.parametrize('color', list(PlayerColor))
def test_cyber_both_colors_autosave_heartbeat_and_single_reply(adaptive_window, app, color):
    w = adaptive_window
    p = start(w, app, color)
    s = p.session
    assert p.theme.key == 'cyber'
    assert p.board.orientation == ('white' if color == PlayerColor.WHITE else 'black')
    assert not p.learning_button.isVisible()
    if color == PlayerColor.WHITE:
        assert w.adaptive.starts == 0
        sqclick(p,chess.E2); sqclick(p,chess.E4)
    until(app, lambda: w.adaptive.pending is not None)
    revision = s.revision
    assert 'Adaptive Grandmaster AI überlegt' in p.context_label.text()
    for _ in range(10):
        sqclick(p,chess.D2); sqclick(p,chess.D4)
    assert s.revision == revision and w.adaptive.starts == 1
    heartbeats = []
    timer = QTimer(); timer.timeout.connect(lambda: heartbeats.append(1)); timer.start(10)
    QTest.qWait(90)
    assert len(heartbeats) >= 3
    w.release.set()
    until(app, lambda: s.revision == revision + 1)
    settle(w, app)
    timer.stop()
    assert w.adaptive.accepted == 1 and w.amateur.starts == w.grandmaster.starts == 0
    assert s.clock.completed_moves == s.revision
    assert result_count(w) == s.revision


def test_save_during_thinking_and_resume_after_new_window(adaptive_window, app):
    w = adaptive_window
    p = start(w, app, PlayerColor.WHITE)
    sqclick(p,chess.E2); sqclick(p,chess.E4)
    until(app, lambda: w.adaptive.pending is not None)
    w._clock_now.advance(2)
    p.save_button.click()
    until(app, lambda: w.navigation.page == Page.MENU and w.adaptive.thread is None)
    settle(w, app)
    path = w.storage.service.path
    saved = GameStore(path).load_active()
    assert saved.session.revision == saved.learning.revision == 1
    assert saved.session.clock.remaining == {True:910, False:898}
    second = MainWindow(storage_path=path, startup_prompt=False, clock_now=FakeTime(), adaptive_config=FAST)
    second.show()
    try:
        until(app, lambda: second.storage.ready)
        resume(second, app)
        until(app, lambda: second.rule_page.session.revision == 2)
        settle(second, app)
        assert second.adaptive.starts == second.adaptive.accepted == 1
        assert second.rule_page.session.clock.remaining[False] == 908
        assert result_count(second) == 2
    finally:
        close(second, app)


@pytest.mark.parametrize('cause',['resign','clock'])
def test_stop_during_thinking_and_open_read_only_report(adaptive_window, app, cause):
    w = adaptive_window
    p = start(w, app, PlayerColor.BLACK)
    until(app, lambda: w.adaptive.pending is not None)
    if cause == 'resign':
        p.resign_button.click()
        p.dialog.button(QMessageBox.StandardButton.Yes).click()
    else:
        w._clock_now.advance(901)
        p.refresh_session()
    until(app, lambda: p.learning_button.isVisible() and w.adaptive.thread is None)
    assert p.session.revision == w.adaptive.accepted == 0
    assert not p.session.running and result_count(w) == 1
    p.learning_button.click()
    assert 'Lernbericht' in p.dialog.windowTitle()
    weights, events = p.dialog.findChildren(QTableWidget)
    assert weights.rowCount() == 5 and events.rowCount() == 1
    assert events.item(0,1).text() == 'Ergebnis'
    p.dialog.reject()
    assert result_count(w) == 1


def test_milestone_visible_and_acknowledged(adaptive_window, app):
    from test_adaptive_core import checkpoint, session

    w = adaptive_window
    store = GameStore(w.storage.service.path)
    for i in range(4):
        game = session()
        game.resign()
        store.create(checkpoint(game, game_id=f'prior-{i}'))
    page = start(w, app, PlayerColor.WHITE)
    page.resign_button.click()
    page.dialog.button(QMessageBox.StandardButton.Yes).click()

    def notice():
        return next((box for box in w.findChildren(QMessageBox)
                     if box.isVisible() and 'Fünf Lernpartien abgeschlossen' in box.text()), None)

    until(app, notice)
    box = notice()
    assert 'manuell starten' in box.informativeText()
    buttons = {button.text(): button for button in box.buttons()}
    assert buttons.keys() == {'Später','KI-Testzentrum'}
    buttons['Später'].click()
    until(app, lambda: store.next_learning_notice() is None)
    settle(w, app)
    assert not notice()
