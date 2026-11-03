"""Search correctness and limits, reproducible strategy fixtures, real save codec."""
from dataclasses import FrozenInstanceError
from threading import Event,Thread
import random,time,uuid
import chess
import pytest
from ai.grandmaster import GrandmasterConfig,Searcher,search,MATE,INF,Entry,position_key,to_table,from_table,time_budget
from ai.grandmaster_evaluation import explain,evaluate,MG
from game.session import GameSession
from game.checkpoint import export_checkpoint,restore_checkpoint,pack,InvalidCheckpoint
from database.store import GameStore,ConflictError
from tests_fake_time import FakeTime

QUICK=GrandmasterConfig(soft_seconds=0,max_seconds=2,max_depth=3,q_depth=2,tt_entries=512)


def pos(moves):
    board=chess.Board()
    for san in moves.split():board.push_san(san)
    return board


def saved(session,sequence=0,game_id=None):
    return export_checkpoint(session,'grandmaster','Weiß' if session.human_color else 'Schwarz','wood',game_id or str(uuid.uuid4()),sequence)


def test_material_phase_symmetry_and_fixed_separate_weights():
    b=chess.Board();assert explain(b).total==0 and explain(b).phase==24
    b.remove_piece_at(chess.D8);assert explain(b).material>900
    assert explain(b.mirror()).total==-explain(b).total
    end=chess.Board('8/8/4k3/8/8/8/P7/4K3 w - - 0 1');assert explain(end).phase==0
    with pytest.raises(TypeError):MG[chess.PAWN]=200
    with pytest.raises(FrozenInstanceError):QUICK.max_depth=6


def test_endgame_active_king_and_passed_pawn_progress():
    distant=chess.Board('7k/8/8/8/8/8/P7/K7 w - - 0 1')
    active=chess.Board('7k/8/8/8/3K4/8/P7/8 w - - 0 1')
    assert explain(active).endgame>explain(distant).endgame
    advanced=chess.Board('7k/P7/8/8/3K4/8/8/8 w - - 0 1')
    assert explain(advanced).pawn_structure>explain(active).pawn_structure


def test_pawn_structure_mobility_and_king_shelter_have_separate_terms():
    doubled=chess.Board('7k/8/8/8/8/P7/P7/7K w - - 0 1')
    connected=chess.Board('7k/8/8/8/8/8/PP6/7K w - - 0 1')
    assert explain(connected).pawn_structure>explain(doubled).pawn_structure
    b=chess.Board();before=explain(b);b.push_san('Nf3')
    assert explain(b).activity>before.activity and explain(b).mobility>before.mobility
    sheltered=pos('e4 e5 Nf3 Nc6 Bc4 Nf6 O-O')
    exposed=sheltered.copy();exposed.remove_piece_at(chess.F2);exposed.remove_piece_at(chess.G2);exposed.remove_piece_at(chess.H2)
    assert explain(sheltered).king_safety>explain(exposed).king_safety


@pytest.mark.parametrize('fen',[
chess.STARTING_FEN,'7k/8/8/4N3/8/8/8/3Q2K1 w - - 0 1',
'4k3/8/8/8/8/8/4r3/4K2R w K - 0 1','7k/8/8/3pP3/8/8/8/7K w - d6 0 1',
'8/5P1k/8/6K1/8/8/8/8 w - - 0 1',
])
def test_legal_deterministic_search_preserves_input(fen):
    b=chess.Board(fen);before=b.fen(en_passant='fen');r=search(b,900,config=QUICK,seed=1)
    assert r.move in b.legal_moves and b.fen(en_passant='fen')==before
    assert r.depth>=1 and r.depth<=3 and r.nodes<=QUICK.max_nodes and r.tt_peak<=512
    again=search(b,900,config=QUICK,seed=99)
    assert (again.move,again.score,again.depth)==(r.move,r.score,r.depth)


def reference(board,depth,ply=0):
    outcome=board.outcome(claim_draw=False)
    if outcome:return 0 if outcome.winner is None else (-MATE+ply if outcome.winner!=board.turn else MATE-ply)
    if depth<=0:
        if not board.is_check():return evaluate(board)
        values=[]
        for move in list(board.legal_moves):
            board.push(move)
            try:
                out=board.outcome(claim_draw=False)
                val=(0 if out.winner is None else -MATE+ply+1) if out else evaluate(board)
                values.append(-val)
            finally:board.pop()
        return max(values)
    values=[]
    for move in list(board.legal_moves):
        board.push(move)
        try:values.append(-reference(board,depth-1,ply+1))
        finally:board.pop()
    return max(values)


@pytest.mark.parametrize('fen',[
'8/8/8/8/4k3/8/4P3/4K3 w - - 0 1',
'7k/8/8/8/8/3p4/3P4/7K w - - 0 1',
])
def test_alpha_beta_matches_unpruned_reference(fen):
    b=chess.Board(fen);expected=reference(b,3)
    r=search(b,900,config=GrandmasterConfig(soft_seconds=0,max_seconds=3,max_depth=3,q_depth=0,tt_entries=128))
    assert r.depth==3 and r.score==expected and r.cutoffs>0


def test_transposition_exact_and_bounds_are_sound_and_bounded():
    b=chess.Board('8/8/8/8/4k3/8/4P3/4K3 w - - 0 1')
    s=Searcher(b,900,GrandmasterConfig(soft_seconds=1,max_seconds=3,max_depth=3,q_depth=0,tt_entries=3));r=s.run()
    assert r.tt_peak<=3 and len(s.table)<=3
    key=s.key();s.store(key,Entry(3,to_table(r.score,0),'exact',r.move));before=s.nodes
    assert s.negamax(3,-INF,INF)==r.score and s.nodes==before+1
    s.table[key]=Entry(3,to_table(r.score,0),'lower',r.move)
    assert s.negamax(3,r.score-2,r.score)==r.score
    s.table[key]=Entry(3,to_table(r.score,0),'upper',r.move)
    assert s.negamax(3,r.score,r.score+2)==r.score
    assert s.tt_hits>=3


def test_cache_key_separates_draw_history_counters_and_mate_distance():
    b=chess.Board()
    for uci in ('g1f3','g8f6','f3g1','f6g8')*2:b.push_uci(uci)
    fresh=chess.Board(b.fen());assert b.fen()==fresh.fen()
    assert Searcher(b,900).key()!=Searcher(fresh,900).key()
    other=fresh.copy();other.halfmove_clock+=1;assert Searcher(other,900).key()!=Searcher(fresh,900).key()
    other=fresh.copy();other.fullmove_number+=1;assert Searcher(other,900).key()!=Searcher(fresh,900).key()
    assert from_table(to_table(MATE-7,7),3)==MATE-3
    assert from_table(to_table(-MATE+7,7),3)==-MATE+3


def test_partial_iteration_cannot_replace_completed_move():
    c=GrandmasterConfig(soft_seconds=1,max_seconds=2,max_depth=5,q_depth=0,max_nodes=50)
    r=search(chess.Board(),900,config=c)
    assert r.stopped and r.depth==1 and len(r.completed)==1 and r.nodes==50
    assert r.move.uci()==r.completed[-1][1] and r.score==r.completed[-1][2]


def test_cancel_interrupts_search_and_does_not_mutate_input():
    b=pos('e4 e5 Nf3 Nc6 Bc4 Nf6 d3 Bc5');fen=b.fen();event=Event();results=[]
    t=Thread(target=lambda:results.append(search(b,900,cancel=event)))
    t.start();time.sleep(.04);started=time.monotonic();event.set();t.join(timeout=.5)
    assert not t.is_alive() and time.monotonic()-started<.5 and results[0].cancelled and results[0].move is None
    assert b.fen()==fen


@pytest.mark.parametrize('remaining',[9.,2.,.2,.04,.005,0.])
def test_emergency_time_budget_and_legal_fallback(remaining):
    soft,hard=time_budget(remaining,GrandmasterConfig());assert 0<=soft<=hard<=remaining
    if remaining<10:assert hard<=remaining*.12+1e-9
    c=GrandmasterConfig(soft_seconds=.01,max_seconds=.03,max_depth=5)
    r=search(chess.Board(),remaining,config=c)
    assert (r.move in chess.Board().legal_moves if remaining>0 else r.move is None) and r.elapsed<.2


def test_quiescence_handles_exchange_and_never_stands_pat_in_check():
    b=chess.Board('3r3k/8/8/8/3p4/8/8/3Q3K w - - 0 1')
    r=search(b,900,config=GrandmasterConfig(soft_seconds=0,max_seconds=2,max_depth=1,q_depth=4))
    assert r.move.uci()!='d1d4' and r.qnodes>0
    b=chess.Board('4k3/8/8/8/8/8/4r3/4K2R w K - 0 1')
    s=Searcher(b,900,QUICK);value=s.quiescence(-INF,INF,0,0)
    assert b.is_check() and value>evaluate(b)+300


def test_mate_in_one_and_mate_threat():
    b=pos('e4 e5 Bc4 Nc6 Qh5 Nf6');r=search(b,900,config=QUICK);b.push(r.move)
    assert b.is_checkmate() and r.score==MATE-1
    b=pos('e4 e5 Bc4 Nc6 Qh5');r=search(b,900,config=QUICK);b.push(r.move)
    for move in list(b.legal_moves):
        b.push(move)
        try:assert not b.is_checkmate()
        finally:b.pop()


def test_knight_fork_and_free_queen_gain():
    b=chess.Board('3q3k/8/8/4N3/8/8/8/6K1 w - - 0 1')
    r=search(b,900,config=QUICK)
    assert r.move.uci()=='e5f7' and r.score>-500
    b=chess.Board('7k/8/8/8/3q4/8/8/3Q3K w - - 0 1')
    assert search(b,900,config=QUICK).move.uci()=='d1d4'


def test_promotion_avoids_stalemate():
    b=chess.Board('8/5P1k/8/6K1/8/8/8/8 w - - 0 1')
    r=search(b,900,config=QUICK);assert r.move.uci()!='f7f8q'
    # A deeper engine may improve its king first to obtain a queen without patt.
    if r.move.promotion:assert r.move.promotion==chess.ROOK
    b=chess.Board('8/5KPk/8/8/8/8/3B4/8 w - - 0 1')
    r=search(b,900,config=QUICK);assert r.move.uci()=='g7g8q' and r.score==MATE-1


@pytest.mark.parametrize('fen',[
'7k/6Q1/6K1/8/8/8/8/8 b - - 150 80',
'7k/5Q2/6K1/8/8/8/8/8 b - - 0 1',
'7k/8/8/8/8/8/8/7K w - - 0 1',
])
def test_terminal_mate_stalemate_and_material_draw(fen):
    b=chess.Board(fen);r=search(b,900,config=QUICK);assert r.move is None
    if b.is_checkmate():assert r.score==-MATE
    else:assert r.score==0


def test_fivefold_repetition_is_terminal_but_threefold_not_automatic():
    b=chess.Board()
    for _ in range(2):
        for uci in ('g1f3','g8f6','f3g1','f6g8'):b.push_uci(uci)
    assert b.is_repetition(3) and search(b,900,config=QUICK).move in b.legal_moves
    for _ in range(2):
        for uci in ('g1f3','g8f6','f3g1','f6g8'):b.push_uci(uci)
    r=search(b,900,config=QUICK);assert r.move is None and r.score==0


@pytest.mark.parametrize('human',[True,False])
def test_grandmaster_session_and_checkpoint_authority_clock_and_resignation(tmp_path,human):
    now=FakeTime();s=GameSession(now=now,play_kind='grandmaster_ai',human_color=human)
    if human:assert s.try_move(chess.E2,chess.E4).accepted
    m=next(iter(s.board.legal_moves));before=dict(s.clock.remaining);revision=s.revision
    assert not s.touch(m.from_square) and not s.try_move(m.from_square,m.to_square).accepted
    assert s.try_engine_move(m,expected_revision=revision).accepted
    assert s.clock.remaining[not human]==before[not human]+10 and not s.try_engine_move(m,expected_revision=revision).accepted
    s.suspend();p=saved(s);assert p.data['format_version']==3
    store=GameStore(tmp_path/'gm.sqlite3');store.initialize();store.create(p)
    r=store.load_active().session;assert r.play_kind=='grandmaster_ai' and r.human_color==human and r.clock.remaining==s.clock.remaining
    assert r.board.fen()==s.board.fen() and r.records[-1].san==s.records[-1].san
    r.resume();assert r.resign() and r.result.winner!=human
    store.save(saved(r,1,p.data['game_id']));assert store.load_active() is None
    assert store.read_owned(p.data['game_id']).session.resigned_color==human


def test_format_three_validation_and_legacy_two_unchanged():
    s=GameSession(now=FakeTime(),play_kind='grandmaster_ai',human_color=False);p=saved(s)
    for key,value in [('play_kind','amateur_ai'),('mode','amateur'),('theme','classic'),('human_color',True),('ai_model_version','adaptive-v1')]:
        d=p.data;d[key]=value
        with pytest.raises(InvalidCheckpoint):restore_checkpoint(pack(d))
    a=GameSession(now=FakeTime(),play_kind='amateur_ai',human_color=False)
    p=export_checkpoint(a,'amateur','Schwarz','classic',str(uuid.uuid4()),0)
    assert p.data['format_version']==2 and restore_checkpoint(p).session.play_kind=='amateur_ai'


def test_forced_mate_in_two_requires_the_extra_ply():
    b=chess.Board('5Q2/8/8/8/8/1K6/8/3k4 w - - 0 1')
    r=search(b,900,config=QUICK);assert r.depth==3 and r.score==MATE-3
    b.push(r.move)
    for reply in list(b.legal_moves):
        b.push(reply)
        try:
            mates=[]
            for move in list(b.legal_moves):
                b.push(move);mates.append(b.is_checkmate());b.pop()
            assert any(mates)
        finally:b.pop()


def test_actual_process_crash_and_restart_starts_one_new_grandmaster_job(tmp_path):
    import json,subprocess,sys
    from database.store import PROJECT_ROOT
    probe=PROJECT_ROOT/'tests/grandmaster_process_probe.py';path=tmp_path/'gm-crash.sqlite3'
    p=subprocess.run([sys.executable,'-B',str(probe),'--crash',str(path)],cwd=PROJECT_ROOT,capture_output=True,text=True,timeout=15)
    assert p.returncode==29,p.stderr
    assert GameStore(path).load_active().session.play_kind=='grandmaster_ai'
    p=subprocess.run([sys.executable,'-B',str(probe),'--resume',str(path)],cwd=PROJECT_ROOT,capture_output=True,text=True,timeout=15)
    assert p.returncode==0,p.stderr
    r=json.loads(p.stdout.strip().splitlines()[-1]);assert r['new_jobs']==r['accepted']==r['increments']==1
    with GameStore(path).connection() as con:assert con.execute('SELECT count(*) FROM moves').fetchone()[0]==1
