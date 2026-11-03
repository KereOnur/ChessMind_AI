"""Production GUI/storage wiring; gated jobs make lifecycle races reproducible."""
from dataclasses import replace
from threading import Event
import json,sqlite3,time,uuid
import chess
import pytest
from PySide6.QtCore import QCoreApplication,QEvent,QTimer,Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel,QMessageBox
from ai.grandmaster import GrandmasterConfig,search
from game.session import GameSession
from game.checkpoint import export_checkpoint
from database.store import GameStore
from ui.grandmaster_controller import GrandmasterThread
from ui.main_window import MainWindow
from ui.navigation import Opponent,PlayerColor,Page
from test_persistence_ui import until,settle,choose,resume,save_to_menu
from test_rule_ui import sqclick,drag,consistent
from tests_fake_time import FakeTime

FAST=GrandmasterConfig(soft_seconds=0,max_seconds=.3,max_depth=3,q_depth=2,tt_entries=512)


def close(w,app):
    if w.storage.dialog is not None:choose(w,'ok' if 'ok' in w.storage.dialog_buttons else 'later',app)
    if w.storage.failed:w.storage.retry();until(app,lambda:not w.storage.service.pending)
    w.close();until(app,lambda:not w.isVisible() and w.grandmaster.thread is None and w.amateur.thread is None and not w.storage.service.thread.isRunning())
    w.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)


@pytest.fixture
def gm_window(app,tmp_path):
    release=Event()
    class GatedThread(GrandmasterThread):
        def run(self):
            while not release.is_set() and not self.cancel_event.wait(.005):pass
            super().run()
    w=MainWindow(storage_path=tmp_path/'gm.sqlite3',startup_prompt=False,clock_now=FakeTime(),grandmaster_config=FAST)
    w.grandmaster.thread_type=GatedThread;w.test_release=release;w.show();until(app,lambda:w.storage.ready)
    yield w
    close(w,app)


def start(w,app,color=PlayerColor.WHITE):
    n=w.navigation;n.new_game();n.choose_opponent(Opponent.GRANDMASTER);n.choose_color(color);n.show_summary()
    assert w.summary_page.play_button.text()=='Partie gegen Großmeister starten'
    w.summary_page.play_button.click();until(app,lambda:w.navigation.page==Page.RULE_TEST and w.rule_page.session.running)
    return w.rule_page


@pytest.mark.parametrize('color',list(PlayerColor))
def test_both_colors_automatic_reply_input_lock_wood_san_clock_and_sql(gm_window,app,color):
    w=gm_window;p=start(w,app,color);s=p.session
    assert s.play_kind=='grandmaster_ai' and p.theme.key=='wood' and p.mode_label.text()=='Großmeister'
    assert p.board.orientation==('white' if color==PlayerColor.WHITE else 'black')
    if color==PlayerColor.WHITE:
        assert w.grandmaster.starts==0;sqclick(p,chess.E2);sqclick(p,chess.E4)
    until(app,lambda:w.grandmaster.pending is not None)
    rev=s.revision;assert 'Großmeister-KI überlegt' in p.context_label.text()
    for _ in range(25):sqclick(p,chess.E2);sqclick(p,chess.E4);sqclick(p,chess.E7);sqclick(p,chess.E5)
    assert s.revision==rev and s.bound_source is None and w.grandmaster.starts==1 and w.amateur.starts==0
    assert not p.claim_button.isEnabled()
    w._clock_now.advance(2);p.refresh_session();assert s.clock.remaining[not s.human_color]==898
    w.test_release.set();until(app,lambda:s.revision==rev+1);until(app,lambda:w.grandmaster.thread is None);settle(w,app)
    assert s.clock.remaining[not s.human_color]==908 and s.clock.completed_moves==s.revision
    assert 'Großmeister-KI hat gezogen' in p.context_label.text() and s.human_turn
    saved=GameStore(w.storage.service.path).load_active().session
    assert saved.play_kind=='grandmaster_ai' and saved.clock.remaining==s.clock.remaining
    assert [r.san for r in saved.records]==[r.san for r in s.records]
    with sqlite3.connect(w.storage.service.path) as c:assert c.execute('SELECT count(*) FROM moves').fetchone()[0]==s.revision
    QTest.qWait(350);consistent(p)


@pytest.mark.parametrize('gesture',['click','drag'])
def test_repeated_human_moves_get_one_answer_each(gm_window,app,gesture):
    w=gm_window;p=start(w,app);w.test_release.set()
    if gesture=='click':sqclick(p,chess.E2);sqclick(p,chess.E4)
    else:drag(p,chess.E2,chess.E4)
    until(app,lambda:p.session.revision==2);QTest.qWait(350)
    m=next(iter(p.session.board.legal_moves))
    if gesture=='click':sqclick(p,m.from_square);sqclick(p,m.to_square)
    else:drag(p,m.from_square,m.to_square)
    until(app,lambda:p.session.revision==4);until(app,lambda:w.grandmaster.thread is None);settle(w,app)
    assert w.grandmaster.starts==w.grandmaster.accepted==2 and p.session.clock.completed_moves==4


@pytest.mark.parametrize('action',['save','back','home','close'])
def test_leave_cancels_work_and_keeps_ai_to_move_without_extra_increment(gm_window,app,action):
    w=gm_window;p=start(w,app);sqclick(p,chess.E2);sqclick(p,chess.E4)
    until(app,lambda:w.grandmaster.pending is not None);w._clock_now.advance(3)
    if action=='save':p.save_button.click()
    elif action=='back':p.back_button.click()
    elif action=='home':p.home_button.click()
    else:w.close()
    until(app,lambda:w.grandmaster.thread is None and not w.storage.service.pending)
    until(app,lambda:w.navigation.page!=Page.RULE_TEST or not w.isVisible())
    r=GameStore(w.storage.service.path).load_active().session
    assert r.revision==1 and not r.human_turn and r.clock.remaining[False]==897
    assert w.grandmaster.accepted==0 and not p.board.animator.busy and not p.timer.isActive()


def test_resume_starts_one_new_job_and_stale_result_cannot_replace_it(gm_window,app):
    w=gm_window;p=start(w,app);sqclick(p,chess.E2);sqclick(p,chess.E4)
    until(app,lambda:w.grandmaster.pending is not None);job=w.grandmaster.pending
    save_to_menu(w,app);until(app,lambda:w.grandmaster.thread is None)
    before=GameStore(w.storage.service.path).load_active().session.clock.remaining
    p=resume(w,app);until(app,lambda:w.grandmaster.pending is not None);new=w.grandmaster.pending
    assert w.grandmaster.starts==2 and p.session.revision==1 and p.session.clock.remaining==before
    old_result=search(chess.Board(),900,config=FAST)
    w.grandmaster.deliver(job,old_result,None);assert w.grandmaster.pending==new
    w.test_release.set();until(app,lambda:p.session.revision==2);until(app,lambda:w.grandmaster.thread is None);settle(w,app)
    assert p.session.clock.completed_moves==2 and w.grandmaster.accepted==1
    w.grandmaster.deliver(job,old_result,None);assert p.session.revision==2
    with sqlite3.connect(w.storage.service.path) as c:assert c.execute('SELECT count(*) FROM moves').fetchone()[0]==2


def test_startup_recovery_stays_paused_before_explicit_confirmation(tmp_path,app):
    s=GameSession(now=FakeTime(),play_kind='grandmaster_ai',human_color=False);s.suspend()
    path=tmp_path/'recover.sqlite3';store=GameStore(path);store.initialize()
    store.create(export_checkpoint(s,'grandmaster','Schwarz','wood',str(uuid.uuid4()),0))
    w=MainWindow(storage_path=path,startup_prompt=True,clock_now=FakeTime(),grandmaster_config=FAST);w.show()
    try:
        until(app,lambda:w.storage.dialog is not None);QTest.qWait(100)
        assert w.grandmaster.starts==0 and w.storage.known_active.session.clock.active is None
        choose(w,'resume',app);until(app,lambda:w.rule_page.session is not None and w.rule_page.session.revision==1)
        until(app,lambda:w.grandmaster.thread is None);settle(w,app)
        assert w.grandmaster.starts==w.grandmaster.accepted==1 and w.rule_page.session.clock.remaining[True]==910
    finally:close(w,app)


def test_resign_during_search_is_loss_of_human_not_ai(gm_window,app):
    w=gm_window;p=start(w,app,PlayerColor.BLACK);until(app,lambda:w.grandmaster.pending is not None)
    p.resign_button.click();app.processEvents();p.dialog.button(QMessageBox.StandardButton.Yes).click()
    until(app,lambda:w.grandmaster.thread is None);settle(w,app)
    assert p.session.result.winner is True and p.session.result.reason=='Aufgabe' and p.session.revision==0
    assert GameStore(w.storage.service.path).load_active() is None
    with GameStore(w.storage.service.path).connection() as c:game_id=c.execute('SELECT id FROM games').fetchone()[0]
    assert GameStore(w.storage.service.path).read_owned(game_id).session.resigned_color is False


def test_timeout_cancels_and_rejects_late_move(gm_window,app):
    w=gm_window;p=start(w,app,PlayerColor.BLACK);until(app,lambda:w.grandmaster.pending is not None)
    w._clock_now.advance(901);p.refresh_session();until(app,lambda:w.grandmaster.thread is None);settle(w,app)
    assert p.session.result.reason=='Zeitüberschreitung' and p.session.clock.remaining[True]==0
    assert p.session.revision==p.session.clock.completed_moves==0 and GameStore(w.storage.service.path).load_active() is None


def test_illegal_result_fails_visibly_and_retry_uses_only_its_own_controller(gm_window,app):
    w=gm_window;p=start(w,app,PlayerColor.BLACK);until(app,lambda:w.grandmaster.pending is not None)
    result=replace(search(chess.Board(),900,config=FAST),move=chess.Move.from_uci('e2e5'))
    w.grandmaster.deliver(w.grandmaster.pending,result,None)
    until(app,lambda:w.grandmaster.thread is None)
    assert p.session.suspended and w.grandmaster.error and p.ai_retry_button.isVisible()
    w.test_release.set();p.ai_retry_button.click();until(app,lambda:p.session.revision==1);until(app,lambda:w.grandmaster.thread is None)
    assert w.amateur.starts==0 and w.grandmaster.accepted==1 and p.session.clock.completed_moves==1


def test_storage_failure_cancels_search_then_retry_saves_and_restarts_once(gm_window,app):
    w=gm_window;p=start(w,app)
    with sqlite3.connect(w.storage.service.path) as lock:
        lock.execute('BEGIN IMMEDIATE');sqclick(p,chess.E2);sqclick(p,chess.E4)
        until(app,lambda:w.storage.failed);until(app,lambda:w.grandmaster.thread is None and not w.storage.service.pending)
        assert p.session.suspended and p.session.revision==1
        choose(w,'ok',app);lock.rollback()
    w.test_release.set();w.storage.retry_button.click();until(app,lambda:p.session.revision==2)
    until(app,lambda:w.grandmaster.thread is None);settle(w,app)
    assert w.grandmaster.accepted==1 and p.session.clock.completed_moves==2


@pytest.mark.parametrize('fen,expected',[
('8/5KPk/8/8/8/8/3B4/8 w - - 0 1','promotion_mate'),
('7k/8/8/3pP3/8/8/8/7K w - d6 0 1','en_passant'),
('4k3/8/8/8/8/8/4r3/4K2R w K - 0 1','check'),
('7k/8/8/8/8/8/R7/7K w - - 149 80','automatic_draw'),
])
def test_real_search_special_positions_render_and_save(tmp_path,app,fen,expected):
    b=chess.Board(fen);s=GameSession(b,now=FakeTime(),play_kind='grandmaster_ai',human_color=not b.turn);s.suspend()
    path=tmp_path/'fixture.sqlite3';store=GameStore(path);store.initialize()
    store.create(export_checkpoint(s,'grandmaster','Schwarz' if b.turn else 'Weiß','wood',str(uuid.uuid4()),0))
    w=MainWindow(storage_path=path,startup_prompt=True,clock_now=FakeTime(),grandmaster_config=FAST);w.show()
    try:
        until(app,lambda:w.storage.dialog is not None);choose(w,'resume',app)
        until(app,lambda:w.rule_page.session is not None and w.rule_page.session.revision==1)
        until(app,lambda:w.grandmaster.thread is None);settle(w,app)
        p=w.rule_page;s=p.session
        if expected=='promotion_mate':assert s.records[-1].move.uci()=='g7g8q' and s.result.reason=='Schachmatt'
        elif expected=='en_passant':assert s.records[-1].san=='exd6' and len(s.captured_by[True])==1
        elif expected=='check':assert not s.board.was_into_check()
        else:assert s.result.reason=='75-Züge-Regel'
        assert s.clock.completed_moves==1 and p.dialog is None
        QTest.qWait(350);consistent(p)
    finally:close(w,app)


def test_real_computation_keeps_gui_heartbeat_and_clock_running(tmp_path,app):
    config=GrandmasterConfig(soft_seconds=.4,max_seconds=.7,max_depth=5,q_depth=6)
    w=MainWindow(storage_path=tmp_path/'heartbeat.sqlite3',startup_prompt=False,grandmaster_config=config);w.show()
    beats=[];timer=QTimer();timer.setInterval(5);timer.timeout.connect(lambda:beats.append(time.monotonic()));timer.start()
    try:
        until(app,lambda:w.storage.ready);p=start(w,app,PlayerColor.BLACK)
        until(app,lambda:p.session.revision==1);until(app,lambda:w.grandmaster.thread is None)
        assert len(beats)>10 and max(b-a for a,b in zip(beats,beats[1:]))<.25
        assert 908<p.session.clock.remaining[True]<910 and p.session.clock.active is False
        assert w.grandmaster.last_result.depth>=3 and w.grandmaster.last_result.elapsed<1
        assert w.amateur.starts==0
    finally:timer.stop();close(w,app)
