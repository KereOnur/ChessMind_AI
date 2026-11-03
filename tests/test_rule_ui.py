"""Real gestures, modal choices and lifecycle tests for the local rule test."""
import chess
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel, QMessageBox
from ui.navigation import Opponent, Page, PlayerColor
from ui.rule_test.dialogs import DrawClaimDialog, PromotionDialog
from ui.rule_test.input import square_tuple
from tests_fake_time import FakeTime


def pump(app):
    for _ in range(8):app.processEvents()


def click(button,app):
    QTest.mouseClick(button,Qt.MouseButton.LeftButton);pump(app)


def open_rule(window,app,opponent=Opponent.AMATEUR,color=PlayerColor.WHITE,*,board=None,now=None,initial=900):
    window.navigation.home();pump(app)
    click(window.menu_page.menu_buttons['Neues Spiel'],app)
    click(window.opponent_page.opponent_cards[opponent],app)
    click(window.color_page.color_cards[color],app)
    click(window.color_page.continue_button,app)
    click(window.summary_page.rule_test_button,app)
    page=window.rule_page
    if board is not None or now is not None:
        kwargs={'board':board,'initial_seconds':initial}
        if now is not None:kwargs['now']=now
        page.configure(window.navigation.setup,**kwargs);pump(app)
    assert window.navigation.page==Page.RULE_TEST
    return page


def sqclick(page,square):
    board=page.board
    QTest.mouseClick(board.viewport(),Qt.MouseButton.LeftButton,pos=board.mapFromScene(board.square_center(square_tuple(square))))


def drag(page,source,target):
    board=page.board;start=board.mapFromScene(board.square_center(square_tuple(source)))
    end=board.mapFromScene(board.square_center(square_tuple(target))) if target is not None else QPoint(5,5)
    QTest.mousePress(board.viewport(),Qt.MouseButton.LeftButton,pos=start)
    QTest.mouseMove(board.viewport(),QPoint((start.x()+end.x())//2,(start.y()+end.y())//2),delay=15)
    QTest.mouseMove(board.viewport(),end,delay=15)
    QTest.mouseRelease(board.viewport(),Qt.MouseButton.LeftButton,pos=end)


def consistent(page):
    expected={square_tuple(square):piece for square,piece in page.session.board.piece_map().items()}
    assert set(page.board.pieces)==set(page.board.position)==set(expected)
    for square,item in page.board.pieces.items():
        assert item.piece.kind==chess.piece_name(expected[square].piece_type)
        assert item.piece.color==('white' if expected[square].color else 'black')
        if not page.board.animator.busy:assert item.pos()==page.board.square_center(square)


@pytest.mark.parametrize('opponent',list(Opponent))
@pytest.mark.parametrize('color',list(PlayerColor))
def test_all_themes_colors_legal_click_drag_and_no_demo_rows(window,app,opponent,color):
    page=open_rule(window,app,opponent,color);s=page.session
    assert page.banner.text()=='Regeltest – zwei manuelle Spieler, noch keine KI'
    assert page.board.orientation==('white' if color==PlayerColor.WHITE else 'black')
    assert len(page.board.squares)==64 and len(page.board.pieces)==32
    assert page.move_list.rows==() and not page.top_player.captured_pieces and not page.bottom_player.captured_pieces
    assert all('Demo' not in text.text() for text in page.findChildren(QLabel) if text.isVisibleTo(page))
    sqclick(page,chess.E7);assert s.bound_source is None
    sqclick(page,chess.E2);assert s.bound_source==chess.E2 and page.board.selected==(4,1)
    sqclick(page,chess.D2);assert s.bound_source==chess.E2 and s.revision==0
    sqclick(page,chess.E5);assert s.bound_source==chess.E2 and s.revision==0
    sqclick(page,chess.E4);assert s.revision==1 and s.records[-1].san=='e4'
    QTest.qWait(page.theme.duration_ms+40);pump(app)
    drag(page,chess.E7,chess.E5)
    QTest.qWait(page.theme.duration_ms+40);pump(app)
    assert s.revision==s.clock.completed_moves==2 and s.clock.active==chess.WHITE
    assert page.move_list.rows==((1,'e4','e5'),)
    assert len(page.board.status_marks)==2
    assert len(window.menu_page.menu_buttons)==5
    consistent(page)


def test_binding_survives_focus_resize_outside_drop_and_disabled_draw_claim(window,app):
    page=open_rule(window,app);s=page.session
    drag(page,chess.E2,None);QTest.qWait(300);pump(app)
    assert s.bound_source==chess.E2
    page.save_button.setFocus();window.resize(640,480);pump(app)
    assert page.board.selected==(4,1) and not page.claim_button.isEnabled()
    page.prepare_claim();assert page.dialog is None
    sqclick(page,chess.D2);sqclick(page,chess.D4)
    assert s.revision==0 and s.bound_source==chess.E2
    sqclick(page,chess.E3);QTest.qWait(300);pump(app)
    assert s.records[-1].san=='e3'


@pytest.mark.parametrize('gesture',['click','drag'])
def test_rapid_input_does_not_duplicate_moves_and_opponent_clock_runs_during_animation(window,app,gesture):
    now=FakeTime();page=open_rule(window,app,now=now);s=page.session
    if gesture=='click':sqclick(page,chess.E2);sqclick(page,chess.E4)
    else:drag(page,chess.E2,chess.E4)
    assert page.board.animator.busy and s.revision==1
    now.advance(.5);page.refresh_session()
    assert s.clock.remaining[chess.BLACK]==899.5 and s.clock.remaining[chess.WHITE]==910
    for _ in range(15):sqclick(page,chess.E7);sqclick(page,chess.E5)
    assert s.revision==1 and s.clock.completed_moves==1
    QTest.qWait(320);pump(app);consistent(page)


@pytest.mark.parametrize('kind',[chess.QUEEN,chess.ROOK,chess.BISHOP,chess.KNIGHT])
def test_promotion_requires_dialog_choice_and_uses_selected_svg(window,app,kind):
    now=FakeTime();page=open_rule(window,app,board=chess.Board('7k/P7/8/8/8/8/8/7K w - - 0 1'),now=now)
    sqclick(page,chess.A7);sqclick(page,chess.A8);pump(app)
    dialog=page.dialog;assert isinstance(dialog,PromotionDialog)
    assert set(dialog.choice_buttons)=={chess.QUEEN,chess.ROOK,chess.BISHOP,chess.KNIGHT}
    assert not page.session.records and page.session.clock.completed_moves==0
    now.advance(2);page.refresh_session();assert page.session.clock.remaining[chess.WHITE]==898
    dialog.choice_buttons[kind].click();pump(app)
    assert page.session.board.piece_type_at(chess.A8)==kind
    assert page.session.clock.completed_moves==1 and page.session.clock.remaining[chess.WHITE]==908
    assert page.board.pieces[(0,7)].piece.kind==chess.piece_name(kind)
    QTest.qWait(300);consistent(page)


def test_promotion_cancel_keeps_board_binding_and_time(window,app):
    now=FakeTime();page=open_rule(window,app,board=chess.Board('7k/P7/8/8/8/8/8/7K w - - 0 1'),now=now)
    before=page.session.board.fen();sqclick(page,chess.A7);sqclick(page,chess.A8);pump(app)
    now.advance(4);page.dialog.reject();pump(app)
    assert page.dialog is None and page.session.board.fen()==before
    assert page.session.bound_source==chess.A7 and page.board.selected==(0,6)
    assert page.session.clock.remaining[chess.WHITE]==896 and not page.session.records


def test_timeout_during_promotion_rejects_pending_move_and_closes_dialog(window,app):
    now=FakeTime();page=open_rule(window,app,board=chess.Board('7k/P7/8/8/8/8/8/7K w - - 0 1'),now=now,initial=.01)
    before=page.session.board.fen();sqclick(page,chess.A7);sqclick(page,chess.A8);pump(app)
    assert page.dialog is not None
    now.advance(.02);page.refresh_session();pump(app)
    assert page.dialog is None and page.session.result is not None
    assert page.session.board.fen()==before and not page.session.records and page.session.clock.completed_moves==0
    assert not page.timer.isActive()


def test_draw_form_preparation_keeps_clock_running_and_incorrect_claim_only_penalizes_opponent(window,app):
    now=FakeTime();page=open_rule(window,app,now=now);s=page.session
    page.claim_button.click();pump(app);assert isinstance(page.dialog,DrawClaimDialog)
    now.advance(7);page.refresh_session();assert s.clock.remaining[chess.WHITE]==893
    page.dialog.reject();pump(app)
    assert s.clock.active==chess.WHITE and s.clock.remaining[chess.BLACK]==900
    page.claim_button.click();pump(app);page.dialog.submit();pump(app)
    assert '60 Sekunden' in page.action_notice.text()
    assert s.clock.remaining=={True:893.,False:960.} and s.clock.completed_moves==0
    assert not page.move_list.rows and s.clock.active==chess.WHITE


def test_intended_claim_dialog_forces_wrong_claim_move_exactly_once(window,app):
    now=FakeTime();page=open_rule(window,app,now=now)
    page.claim_button.click();pump(app);dialog=page.dialog
    dialog.basis.setCurrentIndex(1);dialog.source.setText('e2');dialog.target.setText('e4');dialog.submit();pump(app)
    assert page.session.revision==1 and page.move_list.rows==((1,'e4',''),)
    assert page.session.clock.remaining=={True:910.,False:960.}
    QTest.qWait(300);consistent(page)


def test_invalid_intended_form_stays_open_without_time_credit(window,app):
    now=FakeTime();page=open_rule(window,app,now=now)
    page.claim_button.click();pump(app);dialog=page.dialog
    dialog.basis.setCurrentIndex(1);dialog.source.setText('e2');dialog.target.setText('e5');dialog.submit();pump(app)
    assert page.dialog is dialog and dialog.error.isVisible()
    now.advance(3);page.refresh_session()
    assert page.session.clock.remaining=={True:897.,False:900.} and page.session.revision==0
    dialog.reject();pump(app)


def test_correct_intended_claim_ends_without_pushing_the_move(window,app):
    board=chess.Board()
    for move in ('g1f3','g8f6','f3g1','f6g8','g1f3','g8f6','f3g1'):board.push_uci(move)
    page=open_rule(window,app,board=board,now=FakeTime())
    before=page.session.board.fen();page.claim_button.click();pump(app)
    dialog=page.dialog;dialog.basis.setCurrentIndex(1);dialog.source.setText('f6');dialog.target.setText('g8');dialog.submit();pump(app)
    assert page.session.result.winner is None and 'Dreifache' in page.session.result.reason
    assert page.session.board.fen()==before and page.session.clock.completed_moves==0
    assert not page.timer.isActive() and not page.session.records


def test_resignation_requires_confirmation_and_ends_without_resume(window,app):
    now=FakeTime();page=open_rule(window,app,now=now)
    page.resign_button.click();pump(app);assert isinstance(page.dialog,QMessageBox)
    now.advance(3);page.refresh_session();page.dialog.done(QMessageBox.StandardButton.No);pump(app)
    assert page.session.running and page.session.clock.remaining[chess.WHITE]==897
    page.resign_button.click();pump(app);page.dialog.done(QMessageBox.StandardButton.Yes);pump(app)
    assert page.session.result.reason=='Aufgabe' and page.session.result.winner==chess.BLACK
    assert not page.timer.isActive() and page.session.clock.active is None
    sqclick(page,chess.E2);sqclick(page,chess.E4);assert not page.session.records


def test_save_exit_stops_clock_and_animation_but_does_not_save_or_fake_result(window,app):
    now=FakeTime();page=open_rule(window,app,now=now)
    sqclick(page,chess.E2);sqclick(page,chess.E4);assert page.board.animator.busy
    session=page.session;page.save_button.click();pump(app)
    assert page.action_notice.text()=='Spielstände sind ab Phase 5 verfügbar.'
    page.exit_button.click();pump(app)
    assert window.navigation.page==Page.MENU and session.closed and session.result is None
    assert not page.timer.isActive() and not page.board.animator.busy
    remaining=dict(session.clock.remaining);now.advance(20);session.tick();assert session.clock.remaining==remaining
    page=open_rule(window,app,now=FakeTime())
    assert page.session is not session and page.session.board.fen()==chess.STARTING_FEN
    assert page.session.clock.remaining=={True:900.,False:900.}


def test_castle_and_en_passant_update_both_visual_pieces_and_capture_widgets(window,app):
    page=open_rule(window,app,board=chess.Board('r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1'),now=FakeTime())
    sqclick(page,chess.E1);sqclick(page,chess.H1);pump(app)
    assert page.session.records[-1].san=='O-O' and len(page.board.animator.motions)==2
    assert page.board.pieces[(6,0)].piece.kind=='king' and page.board.pieces[(5,0)].piece.kind=='rook'
    QTest.qWait(300);consistent(page)
    page=open_rule(window,app,board=chess.Board('7k/8/8/3pP3/8/8/8/7K w - d6 0 1'),now=FakeTime())
    drag(page,chess.E5,chess.D6);QTest.qWait(300);pump(app)
    assert page.session.records[-1].san=='exd6' and (3,4) not in page.board.pieces
    assert len(page.bottom_player.captured_pieces)==1 and page.bottom_player.captured_pieces[0].kind=='pawn'
    consistent(page)


def test_check_and_checkmate_status_and_real_san_in_ui(window,app):
    page=open_rule(window,app,now=FakeTime())
    for uci in ('f2f3','e7e5','g2g4','d8h4'):
        move=chess.Move.from_uci(uci)
        attempt=page.session.try_move(move.from_square,move.to_square)
        assert attempt.accepted
        page.render_record(attempt.record);page.refresh_session()
        page.board.animator.cancel()
    assert page.session.result.reason=='Schachmatt'
    assert 'Schachmatt' in page.action_notice.text() and '0-1' in page.action_notice.text()
    assert page.move_list.rows[-1]==(2,'g4','Qh4#') and len(page.board.status_marks)==3
    assert page.top_player.clock.text()==page.session.clock.display(chess.BLACK)


@pytest.mark.parametrize('size',[(420,300),(768,600),(1280,600),(1440,900)])
def test_rule_layout_remains_square_and_fully_visible(window,app,size):
    page=open_rule(window,app,Opponent.ADAPTIVE,PlayerColor.BLACK,now=FakeTime())
    window.resize(*size);pump(app);page.verticalScrollBar().setValue(0);pump(app)
    rect=page.board.mapFromScene(page.board.sceneRect()).boundingRect()
    assert abs(rect.width()-rect.height())<=1
    for point in page.board.mapFromScene(page.board.sceneRect()):
        assert page.viewport().rect().adjusted(-1,-1,1,1).contains(page.board.viewport().mapTo(page.viewport(),point))
    assert page.horizontalScrollBar().maximum()==0


def test_minimizing_hiding_does_not_pause_clock_or_break_binding(window,app):
    now=FakeTime();page=open_rule(window,app,now=now)
    sqclick(page,chess.E2);window.hide();now.advance(4);page.refresh_session()
    assert page.session.clock.remaining[chess.WHITE]==896 and page.session.bound_source==chess.E2
    window.show();pump(app)
    assert page.session.running and page.board.selected==(4,1)
    window.close();assert page.session.closed and not page.timer.isActive()


def test_duplicate_dialog_completion_cannot_apply_the_same_penalty_twice(window,app):
    now=FakeTime();page=open_rule(window,app,now=now)
    page.claim_button.click();pump(app);dialog=page.dialog
    dialog.done(1)
    dialog.done(1)  # Duplicate completion before deferred deletion is processed.
    pump(app)
    assert page.session.clock.remaining=={True:900.,False:960.}
    assert len([event for event in page.session.events if event.kind=='claim_rejected'])==1
