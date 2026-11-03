"""Deterministic phase-four rule/clock tests. No real-time sleeps or AI."""
import chess
import pytest
from game.clock import ChessClock
from game.session import GameSession, RAPID_CLAIM_PENALTY


class FakeTime:
    def __init__(self):self.value=0.
    def __call__(self):return self.value
    def advance(self,seconds):self.value+=seconds


@pytest.fixture
def now():return FakeTime()


def play(session,uci):
    move=chess.Move.from_uci(uci)
    result=session.try_move(move.from_square,move.to_square,move.promotion)
    assert result.accepted,(uci,result)
    return result


def game(fen,now,**kwargs):return GameSession(chess.Board(fen),now=now,**kwargs)


@pytest.mark.parametrize('source,legal,illegal',[('a2','a4','a5'),('g1','f3','g3'),('f1','c4','f4'),('a1','a3','b3'),('d1','h5','d7'),('e1','e2','e3')])
def test_only_library_legal_moves_for_all_six_types(now,source,legal,illegal):
    board=chess.Board()
    if source in ('f1','d1','e1'):board.remove_piece_at(chess.E2)
    if source=='a1':board.remove_piece_at(chess.A2)
    s=GameSession(board,now=now);before=s.board.fen()
    attempt=s.try_move(chess.parse_square(source),chess.parse_square(illegal))
    assert not attempt.accepted and s.board.fen()==before and s.revision==0
    assert s.clock.completed_moves==0
    play(s,source+legal)
    assert s.revision==s.clock.completed_moves==1


def test_scholars_mate_san_capture_and_stopped_clocks(now):
    s=GameSession(now=now)
    for uci in ('e2e4','e7e5','f1c4','b8c6','d1h5','g8f6','h5f7'):play(s,uci)
    assert [r.san for r in s.records]==['e4','e5','Bc4','Nc6','Qh5','Nf6','Qxf7#']
    assert s.result.reason=='Schachmatt' and s.result.winner==chess.WHITE
    assert s.captured_by[chess.WHITE]==[chess.Piece(chess.PAWN,chess.BLACK)]
    remaining=dict(s.clock.remaining);now.advance(100);s.tick()
    assert s.clock.remaining==remaining and s.clock.active is None
    assert not s.try_move(chess.A7,chess.A6).accepted


def test_fools_mate_and_check(now):
    s=GameSession(now=now)
    for move in ('f2f3','e7e5','g2g4','d8h4'):play(s,move)
    assert s.board.is_check() and s.result.winner==chess.BLACK
    assert s.records[-1].san=='Qh4#'


@pytest.mark.parametrize('fen,reason',[
    ('7k/5Q2/6K1/8/8/8/8/8 b - - 0 1','Patt'),
    ('7k/6Q1/6K1/8/8/8/8/8 b - - 0 1','Schachmatt'),
    ('7k/8/6K1/8/8/8/8/8 w - - 0 1','Material'),
    ('7k/8/6K1/8/8/8/8/1B6 w - - 0 1','Material'),
])
def test_terminal_positions_are_detected_at_initialization(now,fen,reason):
    s=game(fen,now);assert reason in s.result.reason
    assert s.clock.active is None


@pytest.mark.parametrize('color,uci,rook_from,rook_to,san',[
    ('w','e1g1',chess.H1,chess.F1,'O-O'),('w','e1c1',chess.A1,chess.D1,'O-O-O'),
    ('b','e8g8',chess.H8,chess.F8,'O-O'),('b','e8c8',chess.A8,chess.D8,'O-O-O')])
def test_both_castles_for_both_colors(now,color,uci,rook_from,rook_to,san):
    s=game(f'r3k2r/8/8/8/8/8/8/R3K2R {color} KQkq - 0 1',now)
    record=play(s,uci).record
    assert record.san==san and record.rook_shift==(rook_from,rook_to)
    assert s.board.piece_at(rook_from) is None
    assert s.board.piece_type_at(rook_to)==chess.ROOK


def test_castling_touch_order_and_forced_side(now):
    fen='r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1'
    s=game(fen,now);assert s.touch(chess.E1)
    s.touch(chess.H1)
    assert s.bound_castle==chess.Move.from_uci('e1g1')
    s.touch(chess.A1)
    assert s.bound_castle==chess.Move.from_uci('e1g1')
    assert not s.try_move(chess.E1,chess.D1).accepted
    play(s,'e1h1');assert s.records[-1].san=='O-O'
    s=game(fen,now);assert s.touch(chess.H1);s.touch(chess.E1)
    assert not s.try_move(chess.E1,chess.G1).accepted
    assert s.bound_source==chess.H1


def test_castle_through_check_is_refused_by_engine(now):
    s=game('r3kr1r/8/8/8/8/8/8/R3K2R w KQ - 0 1',now)
    before=s.board.fen();assert not s.try_move(chess.E1,chess.G1).accepted
    assert s.board.fen()==before and s.bound_source==chess.E1


def test_en_passant_actual_capture(now):
    s=GameSession(now=now)
    for move in ('e2e4','a7a6','e4e5','d7d5','e5d6'):play(s,move)
    assert s.records[-1].san=='exd6'
    assert s.board.piece_at(chess.D5) is None and s.board.piece_at(chess.D6).color==chess.WHITE
    assert s.captured_by[chess.WHITE]==[chess.Piece(chess.PAWN,chess.BLACK)]


def test_pinned_en_passant_is_not_legal(now):
    s=game('k3r3/8/8/3pP3/8/8/8/4K3 w - d6 0 1',now)
    before=s.board.fen();assert not s.try_move(chess.E5,chess.D6).accepted
    assert s.board.fen()==before


@pytest.mark.parametrize('promotion',[chess.QUEEN,chess.ROOK,chess.BISHOP,chess.KNIGHT])
@pytest.mark.parametrize('color',['w','b'])
def test_all_four_promotions_both_colors_and_no_automatic_queen(now,promotion,color):
    fen='7k/P7/8/8/8/8/8/7K w - - 0 1' if color=='w' else '7k/8/8/8/8/8/p7/7K b - - 0 1'
    s=game(fen,now);source,target=(chess.A7,chess.A8) if color=='w' else (chess.A2,chess.A1)
    before=s.board.fen();attempt=s.try_move(source,target)
    assert not attempt.accepted and set(attempt.promotion_choices)=={2,3,4,5}
    assert s.board.fen()==before and not s.records and s.clock.completed_moves==0
    assert s.try_move(source,target,promotion).accepted
    assert s.board.piece_type_at(target)==promotion and s.clock.completed_moves==1
    assert '=' in s.records[-1].san


def test_cancel_promotion_retains_binding_and_charges_elapsed_time(now):
    s=game('7k/P7/8/8/8/8/8/7K w - - 0 1',now)
    before=s.board.fen();s.try_move(chess.A7,chess.A8);now.advance(7);s.cancel_promotion()
    assert s.board.fen()==before and s.bound_source==chess.A7
    assert s.clock.remaining[chess.WHITE]==893 and s.clock.active==chess.WHITE
    assert not s.try_move(chess.H1,chess.G1).accepted


def test_promotion_capture_and_later_capture_of_promoted_piece(now):
    s=game('1r5k/P7/8/8/8/8/8/7K w - - 0 1',now)
    record=play(s,'a7b8q').record
    assert record.captured.piece_type==chess.ROOK and 'axb8=Q' in record.san
    s=game('1Q5k/8/8/8/8/8/1r6/7K b - - 0 1',now)
    record=play(s,'b2b8').record
    assert record.captured.piece_type==chess.QUEEN
    assert s.captured_by[chess.BLACK][0].piece_type==chess.QUEEN


CYCLE=('g1f3','g8f6','f3g1','f6g8')

def test_threefold_requires_a_claim_and_fivefold_is_automatic(now):
    s=GameSession(now=now)
    for move in CYCLE*2:play(s,move)
    assert s.board.is_repetition(3) and s.result is None
    before=s.board.fen();decision=s.claim_draw()
    assert decision.drawn and s.result.winner is None and s.board.fen()==before
    s=GameSession(now=now)
    for move in CYCLE*4:play(s,move)
    assert s.result.reason=='Fünffache Stellungswiederholung'
    assert s.revision==16


def test_intended_threefold_exact_move_not_any_possible_move(now):
    s=GameSession(now=now)
    for move in (CYCLE*2)[:-1]:play(s,move)
    assert not s.board.is_repetition(3) and s.board.can_claim_threefold_repetition()
    before=s.board.fen();decision=s.claim_draw(chess.Move.from_uci('f6g8'))
    assert decision.drawn and s.board.fen()==before and len(s.records)==7
    s=GameSession(now=now)
    for move in (CYCLE*2)[:-1]:play(s,move)
    decision=s.claim_draw()  # Must not silently choose the available future move.
    assert not decision.drawn and decision.penalty_seconds==60 and s.result is None


def test_wrong_intended_repetition_move_is_forced_once(now):
    s=GameSession(now=now)
    for move in (CYCLE*2)[:-1]:play(s,move)
    revision=s.revision;white=s.clock.remaining[chess.WHITE];black=s.clock.remaining[chess.BLACK]
    decision=s.claim_draw(chess.Move.from_uci('f6h5'))
    assert not decision.drawn and decision.forced_move.san=='Nh5'
    assert s.revision==revision+1 and s.clock.completed_moves==revision+1
    assert s.clock.remaining[chess.WHITE]==white+60
    assert s.clock.remaining[chess.BLACK]==black+10
    assert not s.try_move(chess.F6,chess.H5).accepted


@pytest.mark.parametrize('halfmoves',[99,100])
def test_fifty_move_claim_current_or_intended(now,halfmoves):
    s=game(f'7k/8/8/8/8/8/8/R5K1 w - - {halfmoves} 1',now)
    assert s.result is None
    move=chess.Move.from_uci('a1a2') if halfmoves==99 else None
    decision=s.claim_draw(move)
    assert decision.drawn and s.result.reason=='50-Züge-Regel (Antrag)'
    assert not s.records and s.clock.completed_moves==0


def test_fifty_is_not_automatic_and_pawn_move_cannot_support_claim(now):
    s=game('7k/8/8/8/8/8/4P3/R5K1 w - - 99 1',now)
    decision=s.claim_draw(chess.Move.from_uci('e2e3'))
    assert not decision.drawn and decision.forced_move.san=='e3'
    assert s.board.halfmove_clock==0
    s=game('7k/8/8/8/8/8/8/R5K1 w - - 100 1',now)
    assert s.result is None;play(s,'a1a2');assert s.result is None


def test_seventyfive_automatic_and_mate_has_priority(now):
    s=game('7k/8/8/8/8/8/8/R5K1 w - - 149 1',now)
    play(s,'a1a2');assert s.result.reason=='75-Züge-Regel'
    s=game('7k/5Q2/6K1/8/8/8/8/8 w - - 149 1',now)
    play(s,'f7g7')
    assert s.board.halfmove_clock==150 and s.result.reason=='Schachmatt' and s.result.winner==chess.WHITE


def test_incorrect_claim_adds_rapid_penalty_but_no_increment_or_switch(now):
    s=GameSession(now=now);now.advance(12)
    decision=s.claim_draw()
    assert RAPID_CLAIM_PENALTY==60 and decision.penalty_seconds==60
    assert s.clock.remaining=={True:888.,False:960.}
    assert s.clock.active==chess.WHITE and s.clock.completed_moves==0 and not s.records
    now.advance(4);s.tick();assert s.clock.remaining[chess.WHITE]==884


def test_invalid_intended_move_is_preparation_error_not_a_formal_claim(now):
    s=GameSession(now=now);now.advance(5)
    decision=s.claim_draw(chess.Move.from_uci('e2e5'))
    assert not decision.submitted and decision.penalty_seconds==0
    assert s.clock.remaining=={True:895.,False:900.} and s.revision==0


def test_touch_move_binding_wrong_color_and_immovable_piece(now):
    s=GameSession(now=now)
    assert not s.touch(chess.E7) and s.bound_source is None
    assert not s.touch(chess.A1) and s.bound_source is None
    assert s.draw_claim_barred  # FIDE 9.4 applies even to touching an immobile own piece.
    assert s.touch(chess.E2);s.touch(chess.D2)
    before=s.board.fen();assert not s.try_move(chess.D2,chess.D4).accepted
    assert not s.try_move(chess.E2,chess.E5).accepted
    assert s.bound_source==chess.E2 and s.board.fen()==before
    decision=s.claim_draw()
    assert not decision.submitted and decision.penalty_seconds==0
    play(s,'e2e4');assert s.bound_source is None and not s.draw_claim_barred


def test_clock_exact_increment_switch_and_duplicate_token(now):
    s=GameSession(now=now);now.advance(2.5);play(s,'e2e4')
    assert s.clock.remaining=={True:907.5,False:900.} and s.clock.active==chess.BLACK
    assert not s.clock.complete_move(chess.WHITE,1)
    assert s.clock.remaining[chess.WHITE]==907.5
    now.advance(4.25);play(s,'e7e5')
    assert s.clock.remaining[chess.BLACK]==905.75 and s.clock.active==chess.WHITE
    before=s.board.fen();revision=s.revision
    assert not s.try_move(chess.G1,chess.F3,expected_revision=revision-1).accepted
    assert s.board.fen()==before and s.revision==revision


def test_invalid_input_has_no_bonus_and_wrong_turn_does_not_move(now):
    s=GameSession(now=now);now.advance(3)
    assert not s.try_move(chess.E7,chess.E5).accepted
    assert not s.try_move(chess.E2,chess.E5).accepted
    assert s.clock.remaining=={True:897.,False:900.} and s.clock.active==chess.WHITE
    assert s.clock.completed_moves==0


def test_deadline_no_resurrection_and_move_after_flag_is_refused(now):
    s=GameSession(now=now,initial_seconds=.01);now.advance(.01)
    before=s.board.fen();attempt=s.try_move(chess.E2,chess.E4)
    assert not attempt.accepted and s.result.winner==chess.BLACK
    assert s.board.fen()==before and s.clock.completed_moves==0
    assert not s.clock.resume() and not s.clock.add_time(chess.WHITE,10)
    assert not s.claim_draw().submitted and not s.resign()


def test_move_just_before_deadline_is_accepted_once(now):
    s=GameSession(now=now,initial_seconds=.01);now.advance(.009)
    play(s,'e2e4');assert s.clock.remaining[chess.WHITE]==pytest.approx(10.001)
    now.advance(.01);s.tick();assert s.result.winner==chess.WHITE


@pytest.mark.parametrize('fen,expected_winner',[
    ('7k/8/8/8/8/8/8/R5K1 w - - 0 1',None),  # Winner would only have a king.
    ('6nk/8/8/8/8/8/Q7/6K1 w - - 0 1',None), # K+N vs K+Q is certified insufficient.
    ('6nk/8/8/8/8/8/8/R5K1 w - - 0 1',chess.BLACK), # Enemy rook can assist a knight mate.
    ('5nnk/8/8/8/8/8/8/6K1 w - - 0 1',chess.BLACK), # Two knights may mate cooperatively.
    ('6bk/8/8/8/8/8/Q7/6K1 w - - 0 1',None),
    ('6bk/8/8/8/8/8/8/5NK1 w - - 0 1',chess.BLACK),
])
def test_timeout_material_exceptions_use_possible_not_forced_mate(now,fen,expected_winner):
    s=game(fen,now,initial_seconds=1);assert s.result is None
    now.advance(1);s.tick();assert s.result.winner==expected_winner
    assert s.clock.active is None


def test_resign_and_existing_game_end_take_precedence(now):
    s=GameSession(now=now);assert s.resign()
    assert s.result.winner==chess.BLACK and s.result.reason=='Aufgabe'
    assert not s.try_move(chess.E2,chess.E4).accepted
    s=game('7k/8/8/8/8/8/8/R5K1 w - - 0 1',now)
    assert s.resign() and s.result.winner is None
    s=game('7k/6Q1/6K1/8/8/8/8/8 b - - 0 1',now)
    result=s.result;now.advance(1000)
    assert not s.resign() and not s.claim_draw().submitted and s.result==result


def test_abandon_stops_without_fabricating_result_or_resuming(now):
    s=GameSession(now=now);now.advance(4);s.abandon()
    remaining=dict(s.clock.remaining);now.advance(20);s.tick()
    assert s.closed and s.result is None and s.clock.remaining==remaining
    assert not s.try_move(chess.E2,chess.E4).accepted


def test_identical_piece_layout_with_changed_castling_rights_is_not_threefold(now):
    s=game('r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1',now)
    for move in ('e1f1','e8f8','f1e1','f8e8')*2:play(s,move)
    assert s.board.board_fen()=='r3k2r/8/8/8/8/8/8/R3K2R'
    assert not s.board.is_repetition(3)
    decision=s.claim_draw();assert not decision.drawn and decision.penalty_seconds==60


def test_intended_checkmate_cannot_be_replaced_by_a_fifty_move_draw_claim(now):
    s=game('7k/5Q2/6K1/8/8/8/8/8 w - - 149 1',now)
    decision=s.claim_draw(chess.Move.from_uci('f7g7'))
    assert not decision.drawn and decision.forced_move.san=='Qg7#'
    assert s.result.reason=='Schachmatt' and s.result.winner==chess.WHITE
    assert s.revision==s.clock.completed_moves==1


def test_incorrect_claim_with_explicit_underpromotion_has_one_normal_increment(now):
    s=game('7k/P7/8/8/8/8/8/7K w - - 0 1',now)
    decision=s.claim_draw(chess.Move.from_uci('a7a8n'))
    assert not decision.drawn and decision.forced_move.move.promotion==chess.KNIGHT
    assert s.board.piece_type_at(chess.A8)==chess.KNIGHT
    assert s.clock.remaining=={True:910.,False:960.} and s.clock.completed_moves==1
    assert s.result.winner is None and 'Material' in s.result.reason


def test_leaving_cannot_hide_a_flag_that_already_fell(now):
    s=GameSession(now=now,initial_seconds=1)
    now.advance(1)
    s.abandon()
    assert s.closed and s.result.winner==chess.BLACK
    assert s.result.reason=='Zeitüberschreitung' and s.clock.active is None
