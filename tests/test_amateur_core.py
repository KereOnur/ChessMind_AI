"""Reproducible amateur strength fixtures, legal moves, clocks and save protocol."""
from dataclasses import FrozenInstanceError
from threading import Event,Thread
import random,time,uuid
import chess
import pytest
from ai.amateur import AmateurConfig,Candidate,choose_candidate,search,time_budget
from ai.evaluation import VALUES,MATE,explain
from game.session import GameSession
from game.checkpoint import export_checkpoint,restore_checkpoint,pack,InvalidCheckpoint
from database.store import GameStore,ConflictError
from tests_fake_time import FakeTime

FAST=AmateurConfig(target_seconds=0,max_search_seconds=2.4)


def position(sans):
    b=chess.Board()
    for san in sans.split():b.push_san(san)
    return b


def save(session,sequence=0,game_id=None):
    return export_checkpoint(session,'amateur','Weiß' if session.human_color else 'Schwarz','classic',game_id or str(uuid.uuid4()),sequence)


def test_fixed_evaluation_material_symmetry_and_no_learned_mutations():
    b=chess.Board();assert explain(b).total==0
    b.remove_piece_at(chess.D8);assert explain(b).material==900
    assert explain(b.mirror()).total==-explain(b).total
    with pytest.raises(TypeError):VALUES[chess.PAWN]=101
    with pytest.raises(FrozenInstanceError):FAST.weak_probability=1


@pytest.mark.parametrize('seed',range(8))
def test_legal_varied_openings_leave_input_unchanged(seed):
    b=chess.Board();before=b.fen();r=search(b,900,seed=seed,config=FAST)
    assert r.move in b.legal_moves and r.depth==2 and r.nodes<=FAST.max_nodes
    assert b.fen()==before and not b.move_stack
    assert all(c.move in b.legal_moves for c in r.candidates)


def test_multiple_openings_and_seeded_reproducibility():
    results=[search(chess.Board(),900,seed=s,config=FAST) for s in range(24)]
    assert len({r.move for r in results})>=4
    a=search(chess.Board(),900,seed=19,config=FAST);b=search(chess.Board(),900,seed=19,config=FAST)
    assert a.move==b.move and a.candidates==b.candidates


def test_controlled_weakness_has_explicit_reproducible_regret_bounds():
    candidates=tuple(Candidate(chess.Move.from_uci(m),score) for m,score in [('e2e4',100),('d2d4',85),('g1f3',20),('b1c3',-400),('f2f3',-MATE)])
    strong,weakened=choose_candidate(candidates,random.Random(3),AmateurConfig(weak_probability=0))
    weak,flag=choose_candidate(candidates,random.Random(3),AmateurConfig(weak_probability=1))
    assert 100-strong.score<=45 and not weakened
    assert 45<100-weak.score<=130 and flag and weak.move.uci()=='g1f3'
    mate=Candidate(chess.Move.from_uci('e2e4'),MATE)
    assert choose_candidate((mate,*candidates),random.Random(1),AmateurConfig(weak_probability=1))[0]==mate


@pytest.mark.parametrize('seed',range(4))
def test_scholars_mate_is_taken_even_in_weaker_profile(seed):
    b=position('e4 e5 Bc4 Nc6 Qh5 Nf6')
    r=search(b,900,seed=seed,config=AmateurConfig(target_seconds=0,weak_probability=1))
    b.push(r.move);assert b.is_checkmate()


@pytest.mark.parametrize('seed',range(4))
def test_simple_mate_threat_is_avoided(seed):
    b=position('e4 e5 Bc4 Nc6 Qh5')
    r=search(b,900,seed=seed,config=AmateurConfig(target_seconds=0,weak_probability=1))
    assert r.depth==2;b.push(r.move)
    for move in list(b.legal_moves):
        b.push(move)
        try:assert not b.is_checkmate(),('Allowed immediate mate',r.move,move)
        finally:b.pop()


def test_free_queen_is_captured_and_check_is_obeyed():
    b=chess.Board('7k/8/8/8/3q4/8/8/3Q3K w - - 0 1')
    assert search(b,900,seed=2,config=FAST).move.uci()=='d1d4'
    b=chess.Board('4k3/8/8/8/8/8/4r3/4K2R w K - 0 1');assert b.is_check()
    r=search(b,900,seed=5,config=FAST);assert r.move in b.legal_moves
    b.push(r.move);assert not b.was_into_check()


def test_rook_underpromotion_avoids_queen_stalemate():
    b=chess.Board('8/5P1k/8/6K1/8/8/8/8 w - - 0 1');assert b.is_valid()
    q=chess.Move.from_uci('f7f8q');b.push(q);assert b.is_stalemate();b.pop()
    r=search(b,900,seed=6,config=FAST)
    assert r.move.uci()=='f7f8r'


@pytest.mark.parametrize('fen',[
'chess-start','4k3/8/8/8/8/8/4r3/4K2R w K - 0 1',
'7k/P7/8/8/8/8/8/7K w - - 0 1','7k/8/8/3pP3/8/8/8/7K w - d6 0 1',
'r3k2r/8/8/8/8/8/8/R3K2R b KQkq - 0 1',
])
def test_time_pressure_shortens_search_with_legal_fallback(fen):
    b=chess.Board() if fen=='chess-start' else chess.Board(fen)
    started=time.monotonic();r=search(b,.04,seed=7)
    assert r.move in b.legal_moves and r.budget<=.01+1e-9 and time.monotonic()-started<.15
    target,limit=time_budget(.04,AmateurConfig());assert target==0 and limit<.04


def test_cancel_wakes_thinking_wait_and_discards_result():
    cancel=Event();results=[]
    thread=Thread(target=lambda:results.append(search(chess.Board(),900,cancel=cancel,seed=2)))
    thread.start();time.sleep(.08);started=time.monotonic();cancel.set();thread.join(timeout=.5)
    assert not thread.is_alive() and time.monotonic()-started<.5
    assert results[0].cancelled and results[0].move is None


@pytest.mark.parametrize('fen',['7k/5Q2/6K1/8/8/8/8/8 b - - 0 1','7k/6Q1/6K1/8/8/8/8/8 b - - 0 1','7k/8/8/8/8/8/8/7K w - - 0 1'])
def test_no_move_after_automatic_game_end(fen):
    b=chess.Board(fen);assert b.outcome() is not None
    assert search(b,900,config=FAST).move is None


@pytest.mark.parametrize('human',[True,False])
def test_session_color_authority_unique_increment_and_deadline(human):
    now=FakeTime();s=GameSession(now=now,play_kind='amateur_ai',human_color=human)
    m=chess.Move.from_uci('e2e4')
    if human:
        assert not s.try_engine_move(m,expected_revision=0).accepted
        assert s.try_move(m.from_square,m.to_square).accepted;m=chess.Move.from_uci('e7e5')
    assert not s.touch(m.from_square) and not s.try_move(m.from_square,m.to_square).accepted
    revision=s.revision;before=dict(s.clock.remaining)
    assert s.try_engine_move(m,expected_revision=revision).accepted
    assert s.clock.completed_moves==revision+1 and s.clock.remaining[not human]==before[not human]+10
    assert not s.try_engine_move(m,expected_revision=revision).accepted
    s=GameSession(now=now,play_kind='amateur_ai',human_color=False);now.advance(901)
    assert not s.try_engine_move(chess.Move.from_uci('e2e4'),expected_revision=0).accepted
    assert s.result and not s.board.move_stack and s.clock.completed_moves==0


@pytest.mark.parametrize('fen,uci',[
('r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1','e1g1'),
('r3k2r/8/8/8/8/8/8/R3K2R b KQkq - 0 1','e8c8'),
('7k/8/8/3pP3/8/8/8/7K w - d6 0 1','e5d6'),
*[('7k/P7/8/8/8/8/8/7K w - - 0 1','a7a8'+kind) for kind in 'qrbn'],
])
def test_engine_special_move_uses_normal_rule_clock_san_and_replay(tmp_path,fen,uci):
    b=chess.Board(fen);s=GameSession(b,now=FakeTime(),play_kind='amateur_ai',human_color=not b.turn)
    assert s.try_engine_move(chess.Move.from_uci(uci),expected_revision=0).accepted
    s.suspend();p=save(s);store=GameStore(tmp_path/'special.sqlite3');store.initialize();store.create(p)
    r=store.read_owned(p.data['game_id']).session
    assert r.play_kind=='amateur_ai' and r.human_color==s.human_color
    assert r.board.fen(en_passant='fen')==s.board.fen(en_passant='fen') and r.records[-1].san==s.records[-1].san
    assert r.clock.remaining==s.clock.remaining and r.pending_promotion is None


@pytest.mark.parametrize('human',[True,False])
def test_resignation_during_ai_turn_always_loses_for_human_and_roundtrips(human):
    s=GameSession(now=FakeTime(),play_kind='amateur_ai',human_color=human)
    if human:assert s.try_move(chess.E2,chess.E4).accepted
    assert not s.human_turn and s.resign() and s.result.winner!=human
    r=restore_checkpoint(save(s)).session
    assert r.result==s.result and r.resigned_color==human and r.clock.active is None


def test_old_rule_save_stays_manual_and_ai_color_metadata_cannot_be_changed(tmp_path):
    old=GameSession(now=FakeTime());p=export_checkpoint(old,'amateur','Schwarz','classic',str(uuid.uuid4()),0)
    assert p.data['format_version']==1 and restore_checkpoint(p).session.play_kind=='rule_test'
    s=GameSession(now=FakeTime(),play_kind='amateur_ai',human_color=False);p=save(s)
    assert p.data['format_version']==2
    d=p.data;d['human_color']=True
    with pytest.raises(InvalidCheckpoint):restore_checkpoint(pack(d))
    store=GameStore(tmp_path/'identity.sqlite3');store.initialize();store.create(p)
    other=export_checkpoint(GameSession(now=FakeTime()),'amateur','Schwarz','classic',p.data['game_id'],1)
    with pytest.raises(ConflictError):store.save(other)


def test_threefold_claim_and_penalty_stay_manual_reproducible_against_ai():
    s=GameSession(now=FakeTime(),play_kind='amateur_ai',human_color=True)
    assert s.claim_draw().penalty_seconds==60 and s.clock.remaining[False]==960
    for uci in ('g1f3','g8f6','f3g1','f6g8')*2:
        m=chess.Move.from_uci(uci)
        a=s.try_move(m.from_square,m.to_square) if s.human_turn else s.try_engine_move(m,expected_revision=s.revision)
        assert a.accepted
    assert s.result is None and s.claim_draw().drawn
    assert restore_checkpoint(save(s)).session.result==s.result


def test_real_process_crash_during_ai_and_restart_runs_one_fresh_job(tmp_path):
    import json,subprocess,sys
    from database.store import PROJECT_ROOT
    probe=PROJECT_ROOT/'tests/amateur_process_probe.py';path=tmp_path/'crash-ai.sqlite3'
    crash=subprocess.run([sys.executable,'-B',str(probe),'--crash',str(path)],cwd=PROJECT_ROOT,capture_output=True,text=True,timeout=12)
    assert crash.returncode==29,crash.stderr
    saved=GameStore(path).load_active()
    assert saved.session.play_kind=='amateur_ai' and not saved.session.records and not saved.session.human_turn
    resumed=subprocess.run([sys.executable,'-B',str(probe),'--resume',str(path)],cwd=PROJECT_ROOT,capture_output=True,text=True,timeout=12)
    assert resumed.returncode==0,resumed.stderr
    data=json.loads(resumed.stdout.strip().splitlines()[-1]);assert data['fresh_jobs']==data['accepted_moves']==data['completed_moves']==1
    with GameStore(path).connection() as c:assert c.execute('SELECT count(*) FROM moves').fetchone()[0]==1
