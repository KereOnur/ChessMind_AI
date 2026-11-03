"""Production storage wiring, real widget gestures and isolated SQLite files."""
import hashlib,sqlite3,time
from pathlib import Path
import chess
import pytest
from PySide6.QtCore import Qt,QCoreApplication,QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox
from database.store import GameStore
from ui.main_window import MainWindow
from ui.navigation import Opponent,PlayerColor,Page
from ui.rule_test.dialogs import PromotionDialog
from tests_fake_time import FakeTime
from test_rule_ui import sqclick,drag,consistent


def until(app,predicate,seconds=8):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        app.processEvents()
        if predicate():return
        QTest.qWait(5)
    assert predicate(),'Timed out waiting for asynchronous UI/SQLite state'


def settle(window,app):
    until(app,lambda:not window.storage.service.pending and window.storage.busy is None)


def choose(window,key,app):
    coordinator=window.storage
    assert coordinator.dialog is not None,(key,coordinator.status.text())
    coordinator.dialog_buttons[key].click();app.processEvents()


@pytest.fixture
def persistent_window(app,tmp_path):
    window=MainWindow(storage_path=tmp_path/'ui.sqlite3',startup_prompt=False,clock_now=FakeTime())
    window.show();until(app,lambda:window.storage.ready or window.storage.failed)
    yield window
    if window.storage.dialog is not None:
        key='ok' if 'ok' in window.storage.dialog_buttons else next(iter(window.storage.dialog_buttons))
        choose(window,key,app)
    if window.storage.failed and window.storage.session is not None:
        window.storage.retry();until(app,lambda:not window.storage.service.pending)
    window.close();until(app,lambda:not window.storage.service.thread.isRunning() and not window.isVisible())
    app.processEvents();window.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)


def open_new(window,app,opponent=Opponent.AMATEUR,color=PlayerColor.WHITE):
    nav=window.navigation;nav.new_game();nav.choose_opponent(opponent);nav.choose_color(color);nav.show_summary()
    window.summary_page.rule_test_button.click()
    until(app,lambda:window.navigation.page==Page.RULE_TEST and window.rule_page.session.running)
    settle(window,app);return window.rule_page


def save_to_menu(window,app):
    window.rule_page.save_button.click();until(app,lambda:window.navigation.page==Page.MENU)
    settle(window,app)


def resume(window,app):
    window.menu_page.menu_buttons['Spiel fortsetzen'].click();until(app,lambda:window.storage.dialog is not None)
    choose(window,'resume',app)
    until(app,lambda:window.navigation.page==Page.RULE_TEST and window.rule_page.session.running)
    settle(window,app);return window.rule_page


@pytest.mark.parametrize('opponent',list(Opponent))
@pytest.mark.parametrize('color',list(PlayerColor))
def test_production_autosave_save_exit_resume_all_themes_orientations(persistent_window,app,opponent,color):
    w=persistent_window;p=open_new(w,app,opponent,color);now=w._clock_now
    assert len(w.menu_page.menu_buttons)==5 and len(p.board.squares)==64
    now.advance(4);sqclick(p,chess.E2);sqclick(p,chess.E4);settle(w,app)
    saved=GameStore(w.storage.service.path).load_active()
    assert saved.session.records[-1].san=='e4' and saved.session.clock.remaining=={True:906.,False:900.}
    assert saved.session.board.turn==chess.BLACK and p.session.clock.completed_moves==1
    QTest.qWait(350);drag(p,chess.D7,chess.D5);settle(w,app);QTest.qWait(350)
    now.advance(3);p.refresh_session();save_to_menu(w,app)
    assert not p.timer.isActive() and not p.board.animator.busy
    before=GameStore(w.storage.service.path).load_active().session
    assert before.clock.remaining=={True:903.,False:910.}
    now.advance(80000);w.menu_page.menu_buttons['Spiel fortsetzen'].click();until(app,lambda:w.storage.dialog is not None)
    offered=w.storage.known_active.session
    assert offered.clock.active is None and offered.clock.remaining==before.clock.remaining
    now.advance(500);choose(w,'resume',app)
    until(app,lambda:w.navigation.page==Page.RULE_TEST and w.rule_page.session.running);settle(w,app)
    p=w.rule_page;s=p.session
    assert p.theme.key=={'amateur':'classic','grandmaster':'wood','adaptive':'cyber'}[opponent.value]
    assert p.board.orientation==('white' if color==PlayerColor.WHITE else 'black')
    assert s.clock.remaining==before.clock.remaining and s.clock.active==chess.WHITE and s.clock.completed_moves==2
    assert p.move_list.rows==((1,'e4','d5'),) and s.board.fen()==before.board.fen()
    assert len(p.board.status_marks)==2;consistent(p)
    save_to_menu(w,app);assert GameStore(w.storage.service.path).load_active().session.clock.remaining==before.clock.remaining


def test_startup_recovery_later_keeps_save_and_explicit_resume_starts_correct_clock(persistent_window,app):
    w=persistent_window;p=open_new(w,app);sqclick(p,chess.E2);sqclick(p,chess.E4);settle(w,app);save_to_menu(w,app)
    path=w.storage.service.path;before=GameStore(path).load_active().session.clock.remaining
    fresh=MainWindow(storage_path=path,startup_prompt=True,clock_now=FakeTime());fresh.show()
    try:
        until(app,lambda:fresh.storage.dialog is not None)
        fresh._clock_now.advance(10000);assert fresh.storage.known_active.session.clock.active is None
        choose(fresh,'later',app);assert fresh.navigation.page==Page.MENU
        assert GameStore(path).load_active().session.clock.remaining==before
        p=resume(fresh,app);assert p.session.clock.active==chess.BLACK and p.session.clock.remaining==before
    finally:
        fresh.close();until(app,lambda:not fresh.storage.service.thread.isRunning() and not fresh.isVisible())


def test_new_game_requires_discard_choice_and_second_confirmation(persistent_window,app):
    w=persistent_window;p=open_new(w,app);sqclick(p,chess.E2);sqclick(p,chess.E4);settle(w,app);save_to_menu(w,app)
    old=GameStore(w.storage.service.path).load_active();nav=w.navigation
    nav.new_game();nav.choose_opponent(Opponent.ADAPTIVE);nav.choose_color(PlayerColor.BLACK);nav.show_summary()
    w.summary_page.rule_test_button.click();until(app,lambda:w.storage.dialog is not None)
    choose(w,'cancel',app);assert GameStore(w.storage.service.path).load_active().game_id==old.game_id
    w.summary_page.rule_test_button.click();until(app,lambda:w.storage.dialog is not None)
    choose(w,'discard',app);assert w.storage.dialog is not None
    choose(w,'cancel',app);assert GameStore(w.storage.service.path).load_active().game_id==old.game_id
    w.summary_page.rule_test_button.click();until(app,lambda:w.storage.dialog is not None)
    choose(w,'discard',app);choose(w,'discard',app)
    until(app,lambda:w.navigation.page==Page.RULE_TEST and w.rule_page.session.running);settle(w,app)
    new=GameStore(w.storage.service.path).load_active()
    assert new.game_id!=old.game_id and not new.session.records and new.theme=='cyber' and new.player_color=='Schwarz'
    with GameStore(w.storage.service.path).connection() as con:
        assert con.execute('SELECT status FROM games WHERE id=?',(old.game_id,)).fetchone()[0]=='discarded'
        assert con.execute('SELECT count(*) FROM active_game').fetchone()[0]==1


def test_save_write_failure_freezes_retains_state_and_retry_does_not_duplicate(persistent_window,app):
    w=persistent_window;p=open_new(w,app);path=w.storage.service.path
    with sqlite3.connect(path) as lock:
        lock.execute('BEGIN IMMEDIATE');sqclick(p,chess.E2);sqclick(p,chess.E4)
        until(app,lambda:w.storage.failed);until(app,lambda:not w.storage.service.pending)
        assert p.session.suspended and p.session.revision==1 and not p.timer.isActive()
        assert w.navigation.page==Page.RULE_TEST and 'fehlgeschlagen' in w.storage.status.text()
        assert GameStore(path).load_active().session.revision==0
        before=dict(p.session.clock.remaining);w._clock_now.advance(200);p.refresh_session();assert p.session.clock.remaining==before
        choose(w,'ok',app);assert w.storage.retry_button.isEnabled()
        lock.rollback()
    w.storage.retry_button.click();until(app,lambda:not w.storage.failed and not w.storage.service.pending)
    assert p.session.running and p.session.clock.remaining==before
    r=GameStore(path).load_active().session
    assert len(r.records)==1 and r.clock.completed_moves==1 and r.clock.remaining==before
    with sqlite3.connect(path) as con:assert con.execute('SELECT count(*) FROM moves').fetchone()[0]==1


def test_save_exit_failure_never_navigates_or_claims_success(persistent_window,app):
    w=persistent_window;p=open_new(w,app);path=w.storage.service.path
    w._clock_now.advance(17)
    with sqlite3.connect(path) as lock:
        lock.execute('BEGIN IMMEDIATE');p.save_button.click();until(app,lambda:w.storage.failed)
        assert w.navigation.page==Page.RULE_TEST and p.session.suspended
        assert 'Erfolgreich' not in w.storage.status.text()
        choose(w,'ok',app);lock.rollback()
    until(app,lambda:not w.storage.service.pending);w.storage.retry_button.click()
    until(app,lambda:w.navigation.page==Page.MENU)
    assert GameStore(path).load_active().session.clock.remaining[True]==883
    assert 'Erfolgreich' in w.storage.status.text()


def test_rapid_duplicate_clicks_only_one_move_and_one_increment(persistent_window,app):
    w=persistent_window;p=open_new(w,app)
    for _ in range(30):sqclick(p,chess.E2);sqclick(p,chess.E4)
    settle(w,app);assert p.session.revision==p.session.clock.completed_moves==1
    r=GameStore(w.storage.service.path).load_active().session
    assert r.clock.remaining=={True:910.,False:900.} and len(r.records)==1


def test_closed_window_saves_stops_thread_clock_animation_then_new_window_loads(persistent_window,app):
    w=persistent_window;p=open_new(w,app);sqclick(p,chess.E2);sqclick(p,chess.E4)
    w._clock_now.advance(5);w.close();until(app,lambda:not w.storage.service.thread.isRunning() and not w.isVisible())
    assert not w.isVisible() and not p.timer.isActive() and not p.board.animator.busy
    r=GameStore(w.storage.service.path).load_active()
    assert r.session.clock.remaining=={True:910.,False:895.} and r.session.board.turn==False


def test_close_during_initialization_and_immediate_startup_does_not_leave_thread(tmp_path,app):
    w=MainWindow(storage_path=tmp_path/'close.sqlite3',startup_prompt=False)
    w.show();app.processEvents();w.close()
    until(app,lambda:not w.storage.service.thread.isRunning() and not w.isVisible());assert not w.isVisible()


def test_corrupted_database_reports_error_preserves_bytes_and_can_close(tmp_path,app):
    path=tmp_path/'broken.sqlite3';path.write_bytes(b'broken sqlite header');before=hashlib.sha256(path.read_bytes()).hexdigest()
    w=MainWindow(storage_path=path,startup_prompt=True);w.show()
    until(app,lambda:w.storage.failed)
    assert w.storage.dialog is not None and not w.rule_page.active
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before
    assert (Path(__file__).resolve().parents[1]/'database/diagnostics.log').exists()
    choose(w,'ok',app);w.close();until(app,lambda:not w.storage.service.thread.isRunning() and not w.isVisible())


def test_finished_game_is_saved_with_result_and_not_resumable(persistent_window,app):
    w=persistent_window;p=open_new(w,app)
    for uci in ('f2f3','e7e5','g2g4','d8h4'):
        m=chess.Move.from_uci(uci);a=p.session.try_move(m.from_square,m.to_square);assert a.accepted
        p.render_record(a.record);p.refresh_session();p.board.animator.cancel()
    settle(w,app);assert GameStore(w.storage.service.path).load_active() is None
    with GameStore(w.storage.service.path).connection() as con:
        row=con.execute('SELECT status,result_json FROM games').fetchone();assert row[0]=='finished' and 'Schachmatt' in row[1]
    assert not p.timer.isActive();save_to_menu(w,app)
    w.menu_page.menu_buttons['Spiel fortsetzen'].click();settle(w,app)
    assert w.storage.dialog is None and 'keine unterbrochene' in w.menu_page.notice.text()


def test_preview_is_still_disposable_and_does_not_change_saved_game(persistent_window,app):
    w=persistent_window;p=open_new(w,app);save_to_menu(w,app);old=GameStore(w.storage.service.path).load_active()
    nav=w.navigation;nav.new_game();nav.choose_opponent(Opponent.GRANDMASTER);nav.choose_color(PlayerColor.BLACK);nav.show_summary()
    w.summary_page.preview_button.click();p=w.preview_page;sqclick(p,chess.E2);sqclick(p,chess.E5)
    p.board.animator.cancel();p.home_button.click();app.processEvents()
    after=GameStore(w.storage.service.path).load_active()
    assert after.game_id==old.game_id and after.sequence==old.sequence and after.session.board.fen()==old.session.board.fen()


def test_repeated_resume_back_and_menu_keeps_moves_and_times(persistent_window,app):
    w=persistent_window;p=open_new(w,app);sqclick(p,chess.E2);sqclick(p,chess.E4);settle(w,app)
    before=dict(p.session.clock.remaining)
    for _ in range(4):
        save_to_menu(w,app);p=resume(w,app)
        assert p.session.clock.remaining==before and len(p.session.records)==1
        p.back_button.click();until(app,lambda:w.navigation.page==Page.SUMMARY)
        w.navigation.home();p=resume(w,app)
        assert p.session.clock.completed_moves==1 and p.session.clock.remaining==before
    assert len(w.menu_page.menu_buttons)==5


def test_gui_timeout_autosaves_final_result_and_stops_both_clocks(persistent_window,app):
    w=persistent_window;p=open_new(w,app);w._clock_now.advance(901);p.refresh_session();settle(w,app)
    assert p.session.result.reason=='Zeitüberschreitung' and not p.timer.isActive()
    assert GameStore(w.storage.service.path).load_active() is None
    with GameStore(w.storage.service.path).connection() as c:
        row=c.execute('SELECT status,white_seconds,result_json FROM games').fetchone()
        assert row[0]=='finished' and row[1]==0 and 'Zeitüberschreitung' in row[2]


def test_gui_draw_penalty_and_resignation_are_durable(persistent_window,app):
    w=persistent_window;p=open_new(w,app);p.claim_button.click();app.processEvents();p.dialog.submit();settle(w,app)
    r=GameStore(w.storage.service.path).load_active().session
    assert r.clock.remaining=={True:900.,False:960.} and not r.records
    p.resign_button.click();app.processEvents();p.dialog.button(QMessageBox.StandardButton.Yes).click();settle(w,app)
    assert GameStore(w.storage.service.path).load_active() is None
    with GameStore(w.storage.service.path).connection() as c:assert 'Aufgabe' in c.execute('SELECT result_json FROM games').fetchone()[0]


def test_replay_of_pending_promotion_opens_choice_after_resume_not_before(tmp_path,app):
    from game.session import GameSession
    from game.checkpoint import export_checkpoint
    import uuid
    now=FakeTime();s=GameSession(chess.Board('7k/P7/8/8/8/8/8/7K w - - 0 1'),now=now)
    s.try_move(chess.A7,chess.A8);s.suspend();path=tmp_path/'promotion.sqlite3';store=GameStore(path);store.initialize()
    store.create(export_checkpoint(s,'grandmaster','Schwarz','wood',str(uuid.uuid4()),0))
    w=MainWindow(storage_path=path,clock_now=now,startup_prompt=True);w.show()
    try:
        until(app,lambda:w.storage.dialog is not None)
        assert w.rule_page.dialog is None and not w.rule_page.active
        choose(w,'resume',app);until(app,lambda:isinstance(w.rule_page.dialog,PromotionDialog))
        p=w.rule_page;assert not p.session.records and p.session.bound_source==chess.A7
        p.dialog.choice_buttons[chess.ROOK].click();settle(w,app)
        r=store.load_active().session
        assert r.board.piece_type_at(chess.A8)==chess.ROOK and r.records[-1].move.uci()=='a7a8r'
        assert r.clock.remaining=={True:910.,False:900.}
    finally:
        w.close();until(app,lambda:not w.storage.service.thread.isRunning() and not w.isVisible())


def test_error_close_needs_two_explicit_loss_confirmations_and_keeps_old_save(persistent_window,app):
    w=persistent_window;p=open_new(w,app);path=w.storage.service.path
    with sqlite3.connect(path) as lock:
        lock.execute('BEGIN IMMEDIATE');sqclick(p,chess.E2);sqclick(p,chess.E4)
        until(app,lambda:w.storage.failed);until(app,lambda:not w.storage.service.pending);choose(w,'ok',app)
        w.close();assert w.isVisible() and 'force' in w.storage.dialog_buttons
        choose(w,'keep',app);assert w.isVisible() and p.session.suspended
        w.close();choose(w,'force',app);assert w.isVisible() and 'force' in w.storage.dialog_buttons
        choose(w,'force',app);until(app,lambda:not w.storage.service.thread.isRunning() and not w.isVisible());lock.rollback()
    assert GameStore(path).load_active().session.revision==0


def test_close_while_create_is_queued_does_not_start_unattended_clock(persistent_window,app):
    w=persistent_window;nav=w.navigation
    nav.new_game();nav.choose_opponent(Opponent.AMATEUR);nav.choose_color(PlayerColor.WHITE);nav.show_summary()
    w.storage.pending_setup=__import__('dataclasses').replace(nav.setup)
    w.storage._create_new();w.close()
    until(app,lambda:not w.storage.service.thread.isRunning() and not w.isVisible())
    r=GameStore(w.storage.service.path).load_active()
    assert r.session.clock.remaining=={True:900.,False:900.} and r.session.suspended


def test_persistence_status_bar_keeps_dark_background_and_readable_text(persistent_window,app):
    from PySide6.QtGui import QPalette
    w=persistent_window;app.processEvents()
    image=w.statusBar().grab().toImage();color=image.pixelColor(3,3)
    assert max(color.red(),color.green(),color.blue())<60
    assert w.storage.status.palette().color(QPalette.ColorRole.WindowText).lightness()>120


def test_close_immediately_after_retry_waits_for_commit_without_restarting_clock(persistent_window,app):
    w=persistent_window;p=open_new(w,app);path=w.storage.service.path
    with sqlite3.connect(path) as lock:
        lock.execute('BEGIN IMMEDIATE');sqclick(p,chess.E2);sqclick(p,chess.E4)
        until(app,lambda:w.storage.failed);until(app,lambda:not w.storage.service.pending)
        choose(w,'ok',app);frozen=dict(p.session.clock.remaining);lock.rollback()
    w.storage.retry_button.click();w.close();w._clock_now.advance(1000)
    until(app,lambda:not w.storage.service.thread.isRunning() and not w.isVisible())
    assert GameStore(path).load_active().session.clock.remaining==frozen
    assert not w.isVisible()


def test_close_before_initialization_timer_never_submits_to_stopped_worker(tmp_path,app):
    w=MainWindow(storage_path=tmp_path/'immediate.sqlite3',startup_prompt=False)
    w.show();w.close()
    until(app,lambda:not w.storage.service.thread.isRunning() and not w.isVisible())
    app.processEvents();assert not w.storage.service.pending
