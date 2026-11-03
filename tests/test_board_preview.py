"""Phase-three rendering, rule-free input, animation, and lifecycle checks."""
from collections import Counter

import chess
import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton

from ui.board.demo import CAPTURED_BY, DEMO_ROWS, initial_preview
from ui.board.input import DemoInput, MoveIntent
from ui.board.resources import PieceItem
from ui.board.themes import THEMES
from ui.board.view import BOARD_SIZE, GUTTER, BoardView
from ui.navigation import Opponent, Page, PlayerColor
from ui.widgets import ASSETS


def pump(app):
    for _ in range(8): app.processEvents()


def click(button,app):
    QTest.mouseClick(button,Qt.MouseButton.LeftButton)
    pump(app)


def open_preview(window,app,opponent=Opponent.AMATEUR,color=PlayerColor.WHITE):
    window.navigation.home()
    click(window.menu_page.menu_buttons['Neues Spiel'],app)
    click(window.opponent_page.opponent_cards[opponent],app)
    click(window.color_page.color_cards[color],app)
    click(window.color_page.continue_button,app)
    click(window.summary_page.preview_button,app)
    assert window.navigation.page==Page.PREVIEW
    pump(app)
    return window.preview_page


def square_click(board,square):
    QTest.mouseClick(board.viewport(),Qt.MouseButton.LeftButton,pos=board.mapFromScene(board.square_center(square)))


def drag(board,source,target=None):
    start=board.mapFromScene(board.square_center(source))
    end=board.mapFromScene(board.square_center(target)) if target is not None else QPoint(6,6)
    QTest.mousePress(board.viewport(),Qt.MouseButton.LeftButton,pos=start)
    QTest.mouseMove(board.viewport(),QPoint((start.x()+end.x())//2,(start.y()+end.y())//2),delay=15)
    QTest.mouseMove(board.viewport(),end,delay=15)
    QTest.mouseRelease(board.viewport(),Qt.MouseButton.LeftButton,pos=end)


def assert_consistent(board):
    assert len(board.pieces)==32
    assert len(board.position)==32
    assert set(board.pieces)==set(board.position)
    assert len({id(item) for item in board.pieces.values()})==32
    assert sum(isinstance(item,PieceItem) for item in board.scene().items())==32
    for square,item in board.pieces.items():
        assert all(0<=v<8 for v in square)
        assert item.piece==board.position[square]
        if not board.animator.busy: assert item.pos()==board.square_center(square)


def test_initial_layout_matches_independent_standard_position():
    # python-chess is used ONLY as an independent test fixture, not by the UI.
    expected=chess.Board().piece_map()
    pieces=initial_preview()
    assert len(pieces)==len(expected)==32
    for square,piece in expected.items():
        actual=pieces[chess.square_file(square),chess.square_rank(square)]
        assert actual.kind==chess.piece_name(piece.piece_type)
        assert actual.color==('white' if piece.color else 'black')
    assert Counter(p.kind for p in pieces.values())=={'pawn':16,'rook':4,'knight':4,'bishop':4,'queen':2,'king':2}


@pytest.mark.parametrize('opponent',list(Opponent))
@pytest.mark.parametrize('color',list(PlayerColor))
def test_all_modes_colors_coordinates_and_demo_widgets(window,app,opponent,color):
    page=open_preview(window,app,opponent,color);board=page.board
    assert isinstance(board,BoardView)
    assert len(board.squares)==64
    assert len({item.square for item in board.squares})==64
    assert all(item.rect().width()==item.rect().height() for item in board.squares)
    assert not next(item for item in board.squares if item.square==(0,0)).light
    assert board.theme==THEMES[opponent]
    assert board.position==initial_preview()
    white=color==PlayerColor.WHITE
    assert board.coordinate_files==list('ABCDEFGH' if white else 'HGFEDCBA')
    assert board.coordinate_ranks==list('87654321' if white else '12345678')
    assert board.square_at(QPointF(GUTTER+1,BOARD_SIZE-GUTTER-1))==((0,0) if white else (7,7))
    for square in board.position: assert board.square_at(board.square_center(square))==square
    own='white' if white else 'black'
    other='black' if white else 'white'
    assert page.bottom_player.captured_pieces==CAPTURED_BY[own]
    assert page.top_player.captured_pieces==CAPTURED_BY[other]
    assert all(piece.color!=own for piece in page.bottom_player.captured_pieces)
    assert page.move_list.rows==DEMO_ROWS
    assert 'Demonstr' in page.move_list.findChildren(type(page.banner))[0].text().title()
    assert page.banner.text()=='Vorschau – Schachregeln und KI noch nicht verfügbar'
    image=page.sidebar.grab().toImage()
    corner=image.pixelColor(image.width()-2,image.height()-2)
    assert max(corner.red(),corner.green(),corner.blue())<80
    assert page.top_player.clock.text()==page.bottom_player.clock.text()=='15:00'
    assert_consistent(board)


@pytest.mark.parametrize('opponent',list(Opponent))
def test_click_motion_is_nonblocking_and_state_is_independent_of_animation(window,app,opponent):
    page=open_preview(window,app,opponent);board=page.board
    source,target=(4,1),(4,4)  # Deliberately not a legal starting pawn move.
    item=board.pieces[source];start=item.pos();end=board.square_center(target)
    setup=(window.navigation.setup.opponent,window.navigation.setup.player_color)
    square_click(board,source)
    assert board.selected==source and board.selection.isVisible()
    square_click(board,target)
    assert board.animator.busy
    assert board.animator.group.duration()==board.theme.duration_ms
    assert 200<=board.theme.duration_ms<=400
    assert target in page.position and source not in page.position
    assert board.animator.glow is not None if board.theme.neon else board.animator.glow is None
    QTest.qWait(65)
    assert item.pos()!=start and item.pos()!=end
    # A different UI action remains responsive while the visual animation runs.
    page.resign_button.click()
    assert page.action_notice.text()=='Die Aufgabe-Funktion ist erst mit einer echten Schachpartie verfügbar.'
    QTest.qWait(360)
    assert not board.animator.busy and board.animator.glow is None
    assert item.pos()==end
    assert page.move_list.rows==DEMO_ROWS
    assert setup==(window.navigation.setup.opponent,window.navigation.setup.player_color)
    assert page.top_player.clock.text()==page.bottom_player.clock.text()=='15:00'
    assert_consistent(board)


@pytest.mark.parametrize('opponent',list(Opponent))
@pytest.mark.parametrize('color',list(PlayerColor))
def test_drag_drop_in_all_themes_and_orientations(window,app,opponent,color):
    board=open_preview(window,app,opponent,color).board
    drag(board,(3,1),(3,3))
    assert (3,3) in board.position and (3,1) not in board.position
    QTest.qWait(390)
    assert_consistent(board)


def test_invalid_inputs_and_outside_drop_do_not_damage_scene(window,app):
    page=open_preview(window,app);board=page.board
    original=dict(page.position)
    for intent in (MoveIntent((0,1),(0,0),'test'),MoveIntent((0,1),(9,2),'test'),MoveIntent((7,3),(7,4),'test')):
        decision=board.input_handler.request(intent)
        assert not decision.accepted
        assert page.position==original
    square_click(board,(4,3))  # Empty click without selecting a piece.
    QTest.mouseClick(board.viewport(),Qt.MouseButton.RightButton,pos=board.mapFromScene(board.square_center((0,1))))
    assert board.selected is None
    drag(board,(0,1),None)
    QTest.qWait(350)
    assert page.position==original
    assert_consistent(board)


def test_rapid_clicks_navigation_and_repeated_opening_are_safe(window,app):
    page=open_preview(window,app,Opponent.ADAPTIVE);board=page.board
    square_click(board,(0,1));square_click(board,(0,3))
    for index in range(50):
        square_click(board,(index%8,index%4+2))
    QTest.qWait(380)
    assert_consistent(board)
    window.navigation.back();pump(app)
    assert window.navigation.page==Page.SUMMARY
    assert not board.animator.busy and board.animator.glow is None
    for _ in range(10):
        click(window.summary_page.preview_button,app)
        assert page.position==initial_preview()
        square_click(board,(1,1));square_click(board,(1,3))
        assert board.animator.busy
        window.navigation.back();pump(app)
        assert not board.animator.busy
        assert board.animator.glow is None
        assert_consistent(board)
    click(window.summary_page.preview_button,app)
    click(page.home_button,app)
    assert window.navigation.page==Page.MENU
    assert window.navigation.setup.opponent==Opponent.ADAPTIVE
    assert len(window.menu_page.menu_buttons)==5


@pytest.mark.parametrize('size',[(420,300),(640,480),(768,600),(1280,850),(1440,900),(900,1200)])
@pytest.mark.parametrize('color',list(PlayerColor))
def test_board_is_square_and_entirely_visible_at_every_size(window,app,size,color):
    page=open_preview(window,app,Opponent.ADAPTIVE,color)
    window.resize(*size);pump(app)
    page.verticalScrollBar().setValue(0);pump(app)
    board=page.board
    polygon=board.mapFromScene(board.sceneRect())
    rect=polygon.boundingRect()
    assert abs(rect.width()-rect.height())<=1
    for point in polygon:
        assert board.viewport().rect().adjusted(-1,-1,1,1).contains(point)
        outer=board.viewport().mapTo(page.viewport(),point)
        assert page.viewport().rect().adjusted(-1,-1,1,1).contains(outer)
    assert page.horizontalScrollBar().maximum()==0
    assert_consistent(board)


def test_buttons_do_not_save_or_record_a_result_and_clocks_are_static(window,app):
    page=open_preview(window,app)
    window.resize(1280,600);pump(app)
    position=dict(page.position)
    page.resign_button.click();pump(app)
    assert page.action_notice.text()=='Die Aufgabe-Funktion ist erst mit einer echten Schachpartie verfügbar.'
    assert page.position==position
    page.save_button.click();pump(app)
    assert page.action_notice.text()=='Die Vorschau wird nicht gespeichert. Speichern ist nur in einer Regeltest-Partie verfügbar.'
    assert page.exit_button.isVisible()
    assert page.side_scroll.verticalScrollBar().maximum()>0
    assert page.verticalScrollBar().value()==0
    for point in page.board.mapFromScene(page.board.sceneRect()):
        assert page.viewport().rect().adjusted(-1,-1,1,1).contains(page.board.viewport().mapTo(page.viewport(),point))
    QTest.qWait(1050)
    assert page.top_player.clock.text()==page.bottom_player.clock.text()=='15:00'
    page.exit_button.click();pump(app)
    assert window.navigation.page==Page.MENU
    labels=[b.text().lower() for b in page.findChildren(QPushButton)]
    assert not any(word in text for text in labels for word in ('rücknahme','drehen','zughilfe','tipp'))


def test_close_during_animation_and_reopen_reset_only_demo_state(window,app):
    page=open_preview(window,app,Opponent.GRANDMASTER)
    square_click(page.board,(5,1));square_click(page.board,(5,3))
    window.close();pump(app)
    assert not page.board.animator.busy
    window.show();pump(app)
    open_preview(window,app,Opponent.GRANDMASTER)
    assert page.position==initial_preview()
    assert_consistent(page.board)


def test_board_assets_are_original_local_static_svg():
    paths=list((ASSETS/'board').rglob('*.svg'))
    assert len(paths)==38
    assert len({path.read_bytes() for path in paths})==38
    for path in paths:
        renderer=QSvgRenderer(str(path))
        assert renderer.isValid() and not renderer.animated(),path
        assert 'href=' not in path.read_text() and '<image' not in path.read_text()
