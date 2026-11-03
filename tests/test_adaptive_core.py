"""Numerics, transactional recovery and search fixtures for Phase 8."""
import os
import subprocess
import sys
from uuid import NAMESPACE_DNS, uuid5
from threading import Event

import chess
import pytest

from ai import adaptive
from ai.grandmaster import GrandmasterConfig
from database.store import GameStore
from game.checkpoint import export_checkpoint
from game.session import GameSession
from learning.td import INITIAL, GAMMA, RATE, Position, update, validate
from tests_fake_time import FakeTime

FAST = GrandmasterConfig(soft_seconds=0, max_seconds=.4, max_depth=3, tt_entries=512)


def session(*, board=None, human=chess.WHITE, kind='adaptive_ai', initial=900):
    return GameSession(board, now=FakeTime(), play_kind=kind, human_color=human,
                       initial_seconds=initial)


def play(game, uci):
    move = chess.Move.from_uci(uci)
    if not game.human_turn:
        return game.try_engine_move(move, expected_revision=game.revision)
    return game.try_move(move.from_square, move.to_square, move.promotion)


def key(name):
    return str(uuid5(NAMESPACE_DNS, name))


def checkpoint(game, seq=0, game_id='adaptive'):
    mode, theme = {'adaptive_ai': ('adaptive','cyber'), 'amateur_ai': ('amateur','classic'),
                   'grandmaster_ai': ('grandmaster','wood')}[game.play_kind]
    return export_checkpoint(game, mode, 'Weiß' if game.human_color else 'Schwarz',
                             theme, key(game_id), seq)


@pytest.fixture
def store(tmp_path):
    db = GameStore(tmp_path / 'learning.sqlite3')
    db.initialize()
    return db


def test_features_and_white_perspective():
    board = chess.Board()
    assert adaptive.position(board).features == (0,) * 5
    for uci in ('e2e4', 'c7c5', 'g1f3', 'd7d6'):
        board.push_uci(uci)
    p = adaptive.position(board)
    assert len(p.features) == 5 and any(p.features)
    assert all(-1 <= x <= 1 for x in p.features)
    assert adaptive.position(board.mirror()).features == pytest.approx(tuple(-x for x in p.features))
    toggled = board.copy(); toggled.turn = not board.turn
    assert adaptive.position(toggled) == p
    assert adaptive.evaluate(toggled, INITIAL) == -adaptive.evaluate(board, INITIAL)


def test_td_formula_reward_and_stability():
    a = Position(0, (.2,.4,.6,.8,1))
    b = Position(100, a.features)
    weights, value, target, error = update(INITIAL, a, b)
    assert target == pytest.approx(GAMMA*b.value(INITIAL))
    assert error == pytest.approx(target-value)
    assert weights == pytest.approx(tuple(1+RATE*error*(1-value**2)*x/6 for x in a.features))
    positive = update(INITIAL, a, reward=1)[0]
    negative = update(INITIAL, a, reward=-1)[0]
    assert all(p > 1 > n for p,n in zip(positive,negative))
    for reward in (-1, 1):
        w = INITIAL
        for _ in range(2000):
            new, *_ = update(w, a, reward=reward)
            assert max(abs(x-y) for x,y in zip(w,new)) <= .01
            w = new
        assert all(.5 <= x <= 1.5 for x in w)
    for bad in (float('nan'), float('inf'), -1, True):
        with pytest.raises(ValueError):
            validate((bad, *INITIAL[1:]))


@pytest.mark.parametrize('fen,expected', [
    ('r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4', 'h5f7'),
    ('k7/5P2/8/8/8/8/8/K7 w - - 0 1', None),
    ('4k3/8/8/8/8/8/4r3/4K2R w K - 0 1', None),
])
def test_legal_tactical_special_moves(fen, expected):
    board = chess.Board(fen)
    result = adaptive.search(board, 900, config=FAST, weights=(1.5,.5,1.5,.5,1.5))
    assert result.move in board.legal_moves
    if expected:
        assert result.move.uci() == expected
        board.push(result.move)
        assert board.is_checkmate()
    elif board.piece_at(chess.F7):
        assert result.move.promotion is not None


@pytest.mark.parametrize('opening', [[], ['e2e4'], ['d2d4','d7d5'], ['c2c4','e7e5','b1c3']])
def test_openings_time_pressure_and_cancellation(opening):
    board = chess.Board()
    for move in opening:
        board.push_uci(move)
    result = adaptive.search(board, 1.5, config=FAST)
    assert result.move in board.legal_moves and result.budget < .4
    cancel = Event(); cancel.set()
    assert adaptive.search(board, 900, config=FAST, cancel=cancel).cancelled


def test_checkpoint_resume_idempotent_and_clock(store):
    game = session()
    store.create(checkpoint(game))
    play(game,'e2e4')
    saved = checkpoint(game,1)
    record = store.save(saved)
    assert record.learning.revision == 1
    assert store.save(saved).learning.model == record.learning.model
    reopened = GameStore(store.path); reopened.initialize()
    loaded = reopened.load_active()
    assert loaded.learning.weights == record.learning.weights
    assert not loaded.session.human_turn and loaded.session.suspended
    assert loaded.session.clock.remaining == {True:910, False:900}
    loaded.session.clock.now = FakeTime()
    loaded.session.resume()
    play(loaded.session,'c7c5')
    record = reopened.save(checkpoint(loaded.session,2))
    assert record.learning.revision == 2
    assert record.session.clock.completed_moves == 2
    with reopened.connection() as con:
        assert con.execute('SELECT count(*) FROM learning_events').fetchone()[0] == 2


def test_crash_rolls_back_move_and_model_together(store):
    game = session()
    initial = store.create(checkpoint(game))
    play(game,'e2e4')
    saved = checkpoint(game,1)
    probe = """
import os, sys
from database.store import GameStore
from game.checkpoint import Checkpoint
def interrupt(*args):
    os._exit(39)
GameStore(sys.argv[1], fault=interrupt).save(Checkpoint(sys.argv[2], sys.argv[3]))
"""
    result = subprocess.run([sys.executable,'-B','-c',probe,str(store.path),saved.text,saved.digest],
                            env=os.environ.copy(), check=False, timeout=10)
    assert result.returncode == 39
    after = store.load_active()
    assert after.learning.model == initial.learning.model and after.session.revision == 0
    committed = store.save(saved)
    assert store.save(saved).learning.model == committed.learning.model
    with store.connection() as con:
        assert con.execute('SELECT count(*) FROM learning_events').fetchone()[0] == 1


@pytest.mark.parametrize('corruption', ['[1,1,1,1,1]', '[NaN,1,1,1,1]', '[Infinity,1,1,1,1]', b'corrupt BLOB'])
def test_corrupt_model_falls_back_without_overwriting_stable(store, corruption):
    game = session()
    original = store.create(checkpoint(game))
    play(game,'e2e4')
    trained = store.save(checkpoint(game,1))
    with store.connection() as con, store.transaction(con):
        con.execute('UPDATE learning_models SET weights=? WHERE id=?',(corruption, trained.learning.model))
    assert store.load_active().learning.weights == INITIAL
    recovered = store.save(checkpoint(game,2))
    assert recovered.learning.recovered and recovered.learning.weights == INITIAL
    assert recovered.learning.model > trained.learning.model
    restored_id = store.restore_stable_learning_model()
    assert store.load_active().learning.model == restored_id
    with store.connection() as con:
        stable = con.execute('SELECT stable FROM learning_state').fetchone()[0]
        assert stable == original.learning.model
        assert con.execute('SELECT weights FROM learning_models WHERE id=?',(trained.learning.model,)).fetchone()[0] == corruption


def test_five_completed_only_candidate_and_once_notice(store):
    game = session()
    store.create(checkpoint(game,game_id='paused'))
    game.suspend()
    saved = store.save(checkpoint(game,1,'paused'))
    assert not saved.learning.pending_notice
    store.discard(key('paused'),1)
    for index in range(5):
        game = session(human=index % 2 == 0)
        name = f'game{index}'
        store.create(checkpoint(game,game_id=name))
        game.resign()
        finished = checkpoint(game,1,name)
        result = store.save(finished)
        assert result.learning.report['plies'] == 0
        event, = result.learning.report['events']
        assert event['reward'] == (-1 if game.human_color else 1)
        assert store.save(finished).learning.model == result.learning.model
        assert result.learning.pending_notice == (index == 4)
    assert GameStore(store.path).next_learning_notice() == (5,result.learning.model)
    GameStore(store.path).acknowledge_learning_notice(5)
    assert GameStore(store.path).next_learning_notice() is None
    with store.connection() as con:
        assert con.execute('SELECT count(*) FROM learning_events').fetchone()[0] == 5
        assert con.execute('SELECT games FROM learning_models WHERE id=?',(result.learning.model,)).fetchone()[0] == 5


@pytest.mark.parametrize('kind',['amateur_ai','grandmaster_ai'])
def test_no_learning_other_modes(store, kind):
    adaptive_game = session()
    initial = store.create(checkpoint(adaptive_game))
    store.discard(key('adaptive'),0)
    game = session(kind=kind)
    store.create(checkpoint(game,game_id=kind))
    play(game,'e2e4')
    game.resign()
    assert store.save(checkpoint(game,1,kind)).learning is None
    with store.connection() as con:
        assert con.execute('SELECT count(*) FROM learning_events').fetchone()[0] == 0
        assert con.execute('SELECT active FROM learning_state').fetchone()[0] == initial.learning.model


@pytest.mark.parametrize('fen,uci,score', [
    ('r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4','h5f7','1-0'),
    ('7k/8/8/8/8/8/R7/7K w - - 149 80','a2a3','1/2-1/2'),
    ('k7/5P2/8/8/8/8/8/K7 w - - 0 1','f7f8b','1/2-1/2'),
])
def test_engine_terminal_move_records_move_and_result_once(store, fen, uci, score):
    game = session(board=chess.Board(fen), human=chess.BLACK)
    store.create(checkpoint(game))
    play(game, uci)
    assert game.result.score == score
    result = store.save(checkpoint(game,1))
    assert result.learning.report['plies'] == 1
    assert [(row['ply'],row['kind']) for row in result.learning.report['events']] == [(1,'move'),(1,'result')]
    assert store.load_active() is None


def test_incomplete_and_illegal_moves_do_not_train(store):
    game = session(board=chess.Board('k7/5P2/8/8/8/8/8/K7 w - - 0 1'))
    initial = store.create(checkpoint(game))
    game.try_move(chess.F7,chess.F5)
    game.try_move(chess.F7,chess.F8)
    assert game.pending_promotion
    game.cancel_promotion()
    saved = store.save(checkpoint(game,1))
    assert saved.learning.model == initial.learning.model and saved.learning.revision == 0
