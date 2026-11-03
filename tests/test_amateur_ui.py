"""Actual amateur/storage widgets, cancellation, recovery and deadline races."""
from dataclasses import replace
import sqlite3,time,uuid
import chess
import pytest
from PySide6.QtCore import QCoreApplication,QEvent,QTimer,Qt,QThread
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox
from ai.amateur import AmateurConfig,SearchResult,Candidate
from game.session import GameSession
from game.checkpoint import export_checkpoint
from database.store import GameStore
from ui.main_window import MainWindow
from ui.navigation import OPPONENTS, Opponent,PlayerColor,Page
from test_persistence_ui import until,settle,choose,resume,save_to_menu
from test_rule_ui import sqclick,drag,consistent
from tests_fake_time import FakeTime

CONFIG=AmateurConfig(target_seconds=.2,max_search_seconds=.35,weak_probability=0,normal_band=0)


def close(window,app):
    if window.storage.dialog is not None:choose(window,'ok' if 'ok' in window.storage.dialog_buttons else 'later',app)
    if window.storage.failed:
        window.storage.retry();until(app,lambda:not window.storage.service.pending)
    window.close();until(app,lambda:not window.isVisible() and window.amateur.thread is None and not window.storage.service.thread.isRunning())
    window.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)


@pytest.fixture
def ai_window(app,tmp_path):
    w=MainWindow(storage_path=tmp_path/'amateur.sqlite3',startup_prompt=False,clock_now=FakeTime(),amateur_config=CONFIG)
    w.show();until(app,lambda:w.storage.ready)
    yield w
    close(w,app)


def start(window,app,color=PlayerColor.WHITE):
    n=window.navigation;n.new_game();n.choose_opponent(Opponent.AMATEUR);n.choose_color(color);n.show_summary()
    assert window.summary_page.play_button.text()=='Partie gegen Amateur starten'
    window.summary_page.play_button.click()
    until(app,lambda:window.navigation.page==Page.RULE_TEST and window.rule_page.session.running)
    return window.rule_page


@pytest.mark.parametrize('color',list(PlayerColor))
def test_both_player_colors_autoplay_legal_san_single_increment_and_color_lock(ai_window,app,color):
    w=ai_window;p=start(w,app,color);s=p.session
    assert s.play_kind=='amateur_ai' and p.theme.key=='classic' and p.mode_label.text()=='Amateur'
    assert p.board.orientation==('white' if color==PlayerColor.WHITE else 'black')
    if color==PlayerColor.WHITE:
        assert w.amateur.starts==0 and s.human_turn and 'Du bist am Zug' in p.context_label.text()
        sqclick(p,chess.E2);sqclick(p,chess.E4)
    until(app,lambda:w.amateur.pending is not None)
    revision=s.revision;starts=w.amateur.starts
    assert 'überlegt' in p.context_label.text() and not p.claim_button.isEnabled()
    for _ in range(20):sqclick(p,chess.E7);sqclick(p,chess.E5);sqclick(p,chess.E2);sqclick(p,chess.E4)
    assert s.revision==revision and s.bound_source is None and w.amateur.starts==starts
    until(app,lambda:s.human_turn and s.revision==revision+1);until(app,lambda:w.amateur.thread is None);settle(w,app)
    assert w.amateur.starts==starts and w.amateur.accepted==1
    assert s.clock.completed_moves==s.revision and s.clock.remaining[not s.human_color]==910
    assert 'Amateur-KI hat gezogen' in p.context_label.text()
    r=GameStore(w.storage.service.path).load_active().session
    assert r.play_kind=='amateur_ai' and r.human_color==s.human_color and len(r.records)==s.revision
    assert [rec.san for rec in r.records]==[rec.san for rec in s.records]
    with sqlite3.connect(w.storage.service.path) as c:assert c.execute('SELECT count(*) FROM moves').fetchone()[0]==s.revision
    QTest.qWait(300);consistent(p)


@pytest.mark.parametrize('gesture',['click','drag'])
def test_each_human_move_automatically_gets_one_reply(ai_window,app,gesture):
    w=ai_window;p=start(w,app)
    if gesture=='click':sqclick(p,chess.E2);sqclick(p,chess.E4)
    else:drag(p,chess.E2,chess.E4)
    until(app,lambda:p.session.revision==2);QTest.qWait(300)
    move=next(iter(p.session.board.legal_moves))
    if gesture=='click':sqclick(p,move.from_square);sqclick(p,move.to_square)
    else:drag(p,move.from_square,move.to_square)
    until(app,lambda:p.session.revision==4);until(app,lambda:w.amateur.thread is None);settle(w,app)
    assert w.amateur.starts==w.amateur.accepted==2 and p.session.clock.completed_moves==4


@pytest.mark.parametrize('action',['save','back','home','close'])
def test_leaving_during_thinking_cancels_and_never_applies_late_move(ai_window,app,action):
    w=ai_window;p=start(w,app);sqclick(p,chess.E2);sqclick(p,chess.E4)
    until(app,lambda:w.amateur.pending is not None);s=p.session;w._clock_now.advance(2)
    if action=='save':p.save_button.click()
    elif action=='back':p.back_button.click()
    elif action=='home':p.home_button.click()
    else:w.close()
    until(app,lambda:w.amateur.thread is None and not w.storage.service.pending)
    if action=='close':until(app,lambda:not w.isVisible())
    else:until(app,lambda:w.navigation.page!=Page.RULE_TEST)
    QTest.qWait(250)
    saved=GameStore(w.storage.service.path).load_active().session
    assert len(saved.records)==1 and not saved.human_turn and saved.clock.remaining[False]==898
    assert w.amateur.accepted==0 and not p.timer.isActive() and not p.board.animator.busy


def test_save_and_resume_ai_turn_starts_exactly_one_fresh_job(ai_window,app):
    w=ai_window;p=start(w,app);sqclick(p,chess.E2);sqclick(p,chess.E4)
    until(app,lambda:w.amateur.pending is not None)
    job=w.amateur.pending;old_session=p.session
    save_to_menu(w,app);until(app,lambda:w.amateur.thread is None)
    assert w.amateur.starts==1 and w.amateur.accepted==0
    before=GameStore(w.storage.service.path).load_active().session.clock.remaining
    p=resume(w,app);assert p.session is not old_session
    assert p.session.clock.remaining==before and w.amateur.starts==2
    pending=w.amateur.pending
    fake=SearchResult(chess.Move.from_uci('e7e5'),(),2,1,0,.1)
    w.amateur.deliver(job,fake,None)
    assert w.amateur.pending==pending and p.session.revision==1
    until(app,lambda:p.session.revision==2);until(app,lambda:w.amateur.thread is None);settle(w,app)
    assert w.amateur.accepted==1 and w.amateur.starts==2 and p.session.clock.remaining[False]==before[False]+10
    w.amateur.deliver(job,fake,None);assert p.session.revision==2
    with sqlite3.connect(w.storage.service.path) as c:assert c.execute('SELECT count(*) FROM moves').fetchone()[0]==2


def test_new_window_recovery_ai_to_move_waits_for_confirmation(tmp_path,app):
    now=FakeTime();s=GameSession(now=now,play_kind='amateur_ai',human_color=False);s.suspend()
    path=tmp_path/'recover.sqlite3';store=GameStore(path);store.initialize()
    store.create(export_checkpoint(s,'amateur','Schwarz','classic',str(uuid.uuid4()),0))
    w=MainWindow(storage_path=path,startup_prompt=True,clock_now=now,amateur_config=CONFIG);w.show()
    try:
        until(app,lambda:w.storage.dialog is not None);QTest.qWait(250)
        assert w.amateur.starts==0 and w.storage.known_active.session.clock.active is None
        now.advance(10000);choose(w,'later',app);assert w.amateur.starts==0
        p=resume(w,app);until(app,lambda:p.session.revision==1);until(app,lambda:w.amateur.thread is None);settle(w,app)
        assert w.amateur.starts==w.amateur.accepted==1 and p.session.clock.remaining[True]==910
    finally:close(w,app)


def test_resigning_while_ai_thinks_is_human_loss_saved_correctly(ai_window,app):
    w=ai_window;p=start(w,app,PlayerColor.BLACK);until(app,lambda:w.amateur.pending is not None)
    p.resign_button.click();app.processEvents();assert isinstance(p.dialog,QMessageBox)
    p.dialog.button(QMessageBox.StandardButton.Yes).click();app.processEvents()
    until(app,lambda:w.amateur.thread is None);settle(w,app)
    assert p.session.result.reason=='Aufgabe' and p.session.result.winner==True
    assert p.session.revision==0 and not p.timer.isActive() and GameStore(w.storage.service.path).load_active() is None
    with GameStore(w.storage.service.path).connection() as c:
        row=c.execute('SELECT id FROM games').fetchone();r=GameStore(w.storage.service.path).read_owned(row[0]).session
        assert r.result.winner==True and r.resigned_color==False


def test_timeout_during_ai_thinking_discards_result_and_grants_no_bonus(ai_window,app):
    w=ai_window;p=start(w,app,PlayerColor.BLACK);until(app,lambda:w.amateur.pending is not None)
    w._clock_now.advance(901);p.refresh_session();until(app,lambda:w.amateur.thread is None);settle(w,app)
    assert p.session.result.reason=='Zeitüberschreitung' and p.session.result.winner==False
    assert p.session.revision==p.session.clock.completed_moves==0 and p.session.clock.remaining[True]==0
    assert GameStore(w.storage.service.path).load_active() is None and 'Partie beendet' in p.context_label.text()


def test_low_time_shortens_worker_without_minimum_delay(ai_window,app):
    w=ai_window;p=start(w,app)
    # Explicit low-clock fixture prepared before the human move starts any job.
    p.session.clock.remaining[False]=.08
    started=time.monotonic();sqclick(p,chess.E2);sqclick(p,chess.E4)
    until(app,lambda:p.session.revision==2)
    assert time.monotonic()-started<.3 and w.amateur.last_result.budget<=.02+1e-6
    assert p.session.clock.remaining[False]==10.08


def test_malformed_or_duplicate_worker_result_never_creates_duplicate_move(ai_window,app):
    w=ai_window;p=start(w,app,PlayerColor.BLACK);until(app,lambda:w.amateur.pending is not None)
    job=w.amateur.pending;result=SearchResult(chess.Move.from_uci('e2e5'),(),1,1,0,.1)
    w.amateur.deliver(job,result,None)
    assert p.session.suspended and w.amateur.error and p.session.revision==0
    assert p.ai_retry_button.isVisible() and p.session.clock.completed_moves==0
    until(app,lambda:w.amateur.thread is None)
    p.ai_retry_button.click();until(app,lambda:p.session.revision==1);until(app,lambda:w.amateur.thread is None);settle(w,app)
    assert p.session.clock.completed_moves==1
    w.amateur.deliver(job,result,None);assert p.session.revision==1


def test_storage_failure_while_ai_thinks_cancels_then_retry_starts_one_job(ai_window,app):
    w=ai_window;p=start(w,app)
    with sqlite3.connect(w.storage.service.path) as lock:
        lock.execute('BEGIN IMMEDIATE');sqclick(p,chess.E2);sqclick(p,chess.E4)
        # Artificial longer target ensures the writer's busy timeout wins this fixture.
        w.amateur.cancel();w.amateur.error=True
        until(app,lambda:w.amateur.thread is None)
        w.amateur.error=False;w.amateur.config=AmateurConfig(target_seconds=.8,max_search_seconds=1)
        w.amateur.sync();until(app,lambda:w.storage.failed)
        until(app,lambda:w.amateur.thread is None and not w.storage.service.pending)
        assert p.session.suspended and p.session.revision==1
        choose(w,'ok',app);lock.rollback()
    w.storage.retry_button.click();until(app,lambda:not w.storage.failed)
    until(app,lambda:p.session.revision==2);until(app,lambda:w.amateur.thread is None);settle(w,app)
    assert p.session.clock.completed_moves==2 and w.amateur.accepted==1


@pytest.mark.parametrize('opponent',[Opponent.GRANDMASTER,Opponent.ADAPTIVE])
def test_other_ai_buttons_preserve_preview_and_rule_test(ai_window,app,opponent):
    w=ai_window;n=w.navigation;n.new_game();n.choose_opponent(opponent);n.choose_color(PlayerColor.WHITE);n.show_summary()
    assert w.summary_page.play_button.text()==f'Partie gegen {OPPONENTS[opponent].title} starten'
    assert w.navigation.page==Page.SUMMARY and w.amateur.starts==0
    w.summary_page.preview_button.click();assert w.navigation.page==Page.PREVIEW
    w.preview_page.back_button.click()
    n.choose_opponent(Opponent.AMATEUR);n.choose_color(PlayerColor.WHITE);n.show_summary()
    assert 'Alle drei KI-Gegner sind spielbar' in w.summary_page.availability.text()
    n.choose_opponent(opponent);n.choose_color(PlayerColor.WHITE);n.show_summary()
    w.summary_page.rule_test_button.click()
    until(app,lambda:w.navigation.page==Page.RULE_TEST)
    assert w.rule_page.session.play_kind=='rule_test' and w.amateur.starts==0


@pytest.mark.parametrize('fen,expected',[
('8/5P1k/8/6K1/8/8/8/8 w - - 0 1','underpromotion'),
('7k/8/8/3pP3/8/8/8/7K w - d6 0 1','en_passant'),
('4k3/8/8/8/8/8/4r3/4K2R w K - 0 1','check_evasion'),
('r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4','mate'),
('7k/8/8/8/8/8/R7/7K w - - 149 80','automatic_draw'),
])
def test_real_search_special_fixtures_render_and_save(tmp_path,app,fen,expected):
    board=chess.Board(fen);assert board.is_valid()
    s=GameSession(board,now=FakeTime(),play_kind='amateur_ai',human_color=not board.turn);s.suspend()
    path=tmp_path/'fixture.sqlite3';store=GameStore(path);store.initialize()
    store.create(export_checkpoint(s,'amateur','Schwarz' if board.turn else 'Weiß','classic',str(uuid.uuid4()),0))
    w=MainWindow(storage_path=path,startup_prompt=True,clock_now=FakeTime(),amateur_config=CONFIG);w.show()
    try:
        until(app,lambda:w.storage.dialog is not None);choose(w,'resume',app)
        until(app,lambda:w.rule_page.session is not None and w.rule_page.session.revision==1);until(app,lambda:w.amateur.thread is None);settle(w,app)
        p=w.rule_page;s=p.session;record=s.records[-1]
        assert s.clock.completed_moves==1 and p.dialog is None
        if expected=='underpromotion':assert record.move.uci()=='f7f8r' and p.board.pieces[(5,7)].piece.kind=='rook'
        elif expected=='en_passant':assert record.san=='exd6' and len(s.captured_by[True])==1 and (3,4) not in p.board.pieces
        elif expected=='check_evasion':assert not s.board.was_into_check()
        elif expected=='mate':assert s.result.reason=='Schachmatt' and 'Partie beendet' in p.context_label.text()
        else:assert s.result.reason=='75-Züge-Regel'
        with store.connection() as c:game_id=c.execute('SELECT id FROM games').fetchone()[0]
        saved=store.read_owned(game_id).session;assert saved.board.fen()==s.board.fen() and saved.result==s.result
        QTest.qWait(300);consistent(p)
    finally:close(w,app)


def test_heartbeat_and_real_clock_continue_during_default_thinking(tmp_path,app):
    w=MainWindow(storage_path=tmp_path/'realclock.sqlite3',startup_prompt=False);w.show()
    beats=[];timer=QTimer();timer.setInterval(5);timer.timeout.connect(lambda:beats.append(time.monotonic()));timer.start()
    try:
        until(app,lambda:w.storage.ready);started=time.monotonic();p=start(w,app,PlayerColor.BLACK)
        until(app,lambda:p.session.revision==1);elapsed=time.monotonic()-started
        assert .5<=elapsed<3 and 906.5<p.session.clock.remaining[True]<909.6
        assert len(beats)>30 and max(b-a for a,b in zip(beats,beats[1:]))<.25
        assert QThread.currentThread() is app.thread()
        until(app,lambda:w.amateur.thread is None)
    finally:timer.stop();close(w,app)
