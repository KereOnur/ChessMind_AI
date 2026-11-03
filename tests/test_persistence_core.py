"""Real SQLite, replay validation, monotonic restoration and failure/crash tests."""
import hashlib,json,os,signal,sqlite3,subprocess,sys,time,uuid
from pathlib import Path
import chess
import pytest
from database.store import GameStore,ConflictError,DamagedSave,StorageError,UnsupportedSchema,PROJECT_ROOT
from game.checkpoint import Checkpoint,InvalidCheckpoint,export_checkpoint,restore_checkpoint,pack
from game.session import GameSession
from tests_fake_time import FakeTime


def move(session,uci):
    m=chess.Move.from_uci(uci);attempt=session.try_move(m.from_square,m.to_square,m.promotion)
    assert attempt.accepted,attempt.message
    return attempt


def checkpoint(session,sequence=0,game_id=None,mode='amateur',color='Weiß',theme='classic'):
    return export_checkpoint(session,mode,color,theme,game_id or str(uuid.uuid4()),sequence)


@pytest.fixture
def store(tmp_path):
    result=GameStore(tmp_path/'games.sqlite3');result.initialize();return result


def test_database_schema_local_path_version_and_integrity(store):
    with store.connection() as con:
        assert con.execute('PRAGMA user_version').fetchone()[0]==1
        assert con.execute('PRAGMA quick_check').fetchone()[0]=='ok'
        assert con.execute('PRAGMA journal_mode').fetchone()[0]=='delete'
        assert con.execute('PRAGMA synchronous').fetchone()[0]==2
        assert {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}=={'schema_info','games','moves','active_game'}
    assert store.load_active() is None and store.path.is_relative_to(PROJECT_ROOT)
    with pytest.raises(StorageError):GameStore('/tmp/neurochess-forbidden.sqlite3')


@pytest.mark.parametrize('mode,theme',[('amateur','classic'),('grandmaster','wood'),('adaptive','cyber')])
@pytest.mark.parametrize('color',['Weiß','Schwarz'])
def test_full_game_metadata_roundtrip_all_designs_and_colors(store,mode,theme,color):
    now=FakeTime();session=GameSession(now=now)
    for uci in ('e2e4','d7d5','e4d5','d8d5','b1c3'):
        now.advance(1.25);move(session,uci)
    session.suspend();before=dict(session.clock.remaining)
    p=checkpoint(session,mode=mode,theme=theme,color=color);store.create(p)
    restored=store.load_active();s=restored.session
    assert restored.mode==mode and restored.theme==theme and restored.player_color==color
    assert s.board.fen(en_passant='fen')==session.board.fen(en_passant='fen')
    assert [m.uci() for m in s.board.move_stack]==[m.uci() for m in session.board.move_stack]
    assert [r.san for r in s.records]==[r.san for r in session.records]
    assert s.captured_by==session.captured_by and s.clock.remaining==before
    assert s.suspended and not s.running and s.clock.active is None
    assert s.clock.completed_moves==5 and s.revision==5


def test_remaining_times_downtime_no_bonus_and_save_immediately_after_load(store):
    now=FakeTime();s=GameSession(now=now);now.advance(8);move(s,'e2e4');now.advance(3);s.suspend()
    p=checkpoint(s);store.create(p);saved=dict(s.clock.remaining)
    restored=restore_checkpoint(p,now=now);s=restored.session
    now.advance(100000);s.tick();assert s.clock.remaining==saved
    assert s.resume() and not s.resume()
    assert s.clock.remaining==saved and s.clock.active==chess.BLACK
    now.advance(2);s.tick();assert s.clock.remaining[chess.BLACK]==895
    move(s,'e7e5');assert s.clock.remaining[chess.BLACK]==905 and s.clock.completed_moves==2
    s.suspend();store.save(checkpoint(s,1,restored.game_id))
    reloaded=store.load_active();assert reloaded.session.clock.remaining==s.clock.remaining
    store.save(checkpoint(reloaded.session,2,restored.game_id));again=store.load_active()
    assert again.session.clock.remaining==s.clock.remaining and len(again.session.records)==2


SPECIALS=[
('r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1','e1g1'),
('r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1','e1c1'),
('r3k2r/8/8/8/8/8/8/R3K2R b KQkq - 0 1','e8g8'),
('r3k2r/8/8/8/8/8/8/R3K2R b KQkq - 0 1','e8c8'),
('7k/8/8/3pP3/8/8/8/7K w - d6 0 1','e5d6'),
*[(('7k/P7/8/8/8/8/8/7K w - - 0 1'),('a7a8'+p)) for p in 'qrbn'],
]


@pytest.mark.parametrize('fen,uci',SPECIALS)
def test_special_moves_preserve_history_san_captures_and_rights(store,fen,uci):
    s=GameSession(chess.Board(fen),now=FakeTime());move(s,uci);s.suspend();p=checkpoint(s);store.create(p)
    restored=store.read_owned(p.data['game_id']).session
    assert restored.board.fen(en_passant='fen')==s.board.fen(en_passant='fen')
    assert restored.board.peek().uci()==uci and restored.records[-1].san==s.records[-1].san
    assert restored.records[-1].rook_shift==s.records[-1].rook_shift and restored.captured_by==s.captured_by
    assert restored.result==s.result


def test_en_passant_available_on_load_then_legal_capture(store):
    s=GameSession(chess.Board('7k/3p4/8/4P3/8/8/8/7K b - - 0 1'),now=FakeTime())
    move(s,'d7d5');s.suspend();store.create(checkpoint(s))
    restored=store.load_active().session
    assert restored.board.ep_square==chess.D6 and restored.board.has_legal_en_passant()
    restored.resume();move(restored,'e5d6');assert restored.captured_by[chess.WHITE]==[chess.Piece(chess.PAWN,chess.BLACK)]


def test_castling_rights_after_rook_moves_away_and_back_not_regenerated(store):
    s=GameSession(chess.Board('r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1'),now=FakeTime())
    for uci in ('h1h2','h8h7','h2h1','h7h8'):move(s,uci)
    s.suspend();store.create(checkpoint(s));r=store.load_active().session
    assert not r.board.has_kingside_castling_rights(True) and not r.board.has_kingside_castling_rights(False)
    assert r.board.has_queenside_castling_rights(True)


def repetition_session(cycles=2):
    s=GameSession(now=FakeTime())
    for uci in ('g1f3','g8f6','f3g1','f6g8')*cycles:move(s,uci)
    return s


def test_threefold_survives_replay_but_is_not_automatic_and_can_be_claimed(store):
    s=repetition_session();s.suspend();store.create(checkpoint(s));r=store.load_active().session
    assert r.result is None and r.board.is_repetition(3) and r.board.can_claim_threefold_repetition()
    r.resume();assert r.claim_draw().drawn and r.result.winner is None


def test_repetition_after_loading_continues_to_automatic_fivefold(store):
    s=repetition_session();s.suspend();p=checkpoint(s);store.create(p);r=store.load_active().session;r.resume()
    for uci in ('g1f3','g8f6','f3g1','f6g8')*2:move(r,uci)
    assert 'Fünffache' in r.result.reason
    store.save(checkpoint(r,1,p.data['game_id']));assert store.load_active() is None


@pytest.mark.parametrize('intended',[False,True])
def test_claimed_draw_result_and_intended_move_proof_reload(store,intended):
    s=GameSession(now=FakeTime());ucis=('g1f3','g8f6','f3g1','f6g8')*2
    for uci in ucis[:-1] if intended else ucis:move(s,uci)
    assert s.claim_draw(chess.Move.from_uci('f6g8') if intended else None).drawn
    p=checkpoint(s);store.create(p);r=store.read_owned(p.data['game_id']).session
    assert r.result==s.result and r.board.move_stack==s.board.move_stack
    assert r.draw_claim_basis==s.draw_claim_basis and r.clock.remaining==s.clock.remaining
    assert store.load_active() is None


@pytest.mark.parametrize('halfmove',[99,100,149])
def test_halfmove_fifty_and_seventyfive_survive_load(store,halfmove):
    s=GameSession(chess.Board(f'7k/8/8/8/8/8/R7/7K w - - {halfmove} 80'),now=FakeTime());s.suspend();p=checkpoint(s);store.create(p)
    r=store.load_active().session;r.resume();assert r.board.halfmove_clock==halfmove
    if halfmove==100:assert r.claim_draw().drawn
    elif halfmove==99:assert r.claim_draw(chess.Move.from_uci('a2b2')).drawn
    else:move(r,'a2b2');assert r.result.reason=='75-Züge-Regel'
    store.save(checkpoint(r,1,p.data['game_id']));assert store.read_owned(p.data['game_id']).session.result==r.result


@pytest.mark.parametrize('kind',['resign','timeout','mate','stalemate'])
def test_official_game_end_saved_never_resumable(store,kind):
    now=FakeTime()
    fen='7k/5Q2/6K1/8/8/8/8/8 b - - 0 1' if kind=='stalemate' else chess.STARTING_FEN
    s=GameSession(chess.Board(fen),now=now)
    if kind=='resign':assert s.resign()
    elif kind=='timeout':now.advance(901);s.tick()
    elif kind=='mate':
        for uci in ('f2f3','e7e5','g2g4','d8h4'):move(s,uci)
    p=checkpoint(s);store.create(p);assert store.load_active() is None
    r=store.read_owned(p.data['game_id']).session
    assert r.result==s.result and r.clock.remaining==s.clock.remaining and not r.resume()


def test_touch_castling_binding_pending_promotion_and_claim_bar_survive(store):
    now=FakeTime();s=GameSession(chess.Board('r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1'),now=now)
    s.touch(chess.E1);s.touch(chess.H1);s.suspend();r=restore_checkpoint(checkpoint(s),now=now).session;r.resume()
    assert r.bound_source==chess.E1 and r.bound_castle==chess.Move.from_uci('e1g1') and r.draw_claim_barred
    assert not r.try_move(chess.E1,chess.C1).accepted
    move(r,'e1g1')
    s=GameSession(chess.Board('7k/P7/8/8/8/8/8/7K w - - 0 1'),now=now)
    assert s.try_move(chess.A7,chess.A8).promotion_choices;s.suspend()
    r=restore_checkpoint(checkpoint(s),now=now).session;r.resume()
    assert r.pending_promotion==(chess.A7,chess.A8,0) and r.bound_source==chess.A7
    assert not r.try_move(chess.H1,chess.H2).accepted
    move(r,'a7a8n');assert r.clock.completed_moves==1


def test_invalid_move_not_stored_as_move_or_increment(store):
    s=GameSession(now=FakeTime());p=checkpoint(s);store.create(p)
    assert not s.try_move(chess.E2,chess.E5).accepted
    store.save(checkpoint(s,1,p.data['game_id']))
    r=store.load_active().session;assert not r.records and r.board.fen()==chess.STARTING_FEN
    assert r.clock.remaining=={True:900.,False:900.} and r.bound_source==chess.E2
    with store.connection() as c:assert c.execute('SELECT count(*) FROM moves').fetchone()[0]==0


def test_penalty_saved_without_spurious_increment_then_resumed(store):
    s=GameSession(now=FakeTime());assert s.claim_draw().penalty_seconds==60;s.suspend();store.create(checkpoint(s))
    r=store.load_active().session;assert r.clock.remaining=={True:900.,False:960.} and r.clock.completed_moves==0
    r.resume();move(r,'e2e4');assert r.clock.remaining[True]<=910 and r.clock.remaining[False]<=960


def test_multiple_saves_idempotent_no_duplicate_rows_or_increments(store):
    s=GameSession(now=FakeTime());p=checkpoint(s);store.create(p)
    for sequence,uci in enumerate(('e2e4','e7e5','g1f3','b8c6'),1):
        move(s,uci);p=checkpoint(s,sequence,p.data['game_id']);store.save(p);store.save(p)
    with store.connection() as con:
        assert con.execute('SELECT count(*) FROM moves').fetchone()[0]==4
        assert con.execute('SELECT count(DISTINCT ply) FROM moves').fetchone()[0]==4
    r=store.load_active().session;assert r.clock.remaining=={True:920.,False:920.} and r.clock.completed_moves==4


def test_only_one_current_game_stale_sequence_and_rewound_history_rejected(store):
    s=GameSession(now=FakeTime());p=checkpoint(s);store.create(p)
    with pytest.raises(ConflictError):store.create(checkpoint(GameSession(now=FakeTime())))
    move(s,'e2e4');latest=checkpoint(s,1,p.data['game_id']);store.save(latest)
    with pytest.raises(ConflictError):store.save(p)
    with pytest.raises(ConflictError):store.save(checkpoint(s,4,p.data['game_id']))
    rewind=checkpoint(GameSession(now=FakeTime()),2,p.data['game_id'])
    with pytest.raises(ConflictError):store.save(rewind)
    assert store.load_active().session.board.peek().uci()=='e2e4'


def test_discard_requires_current_id_sequence_then_preserves_archive(store):
    p=checkpoint(GameSession(now=FakeTime()));store.create(p)
    with pytest.raises(ConflictError):store.discard(p.data['game_id'],8)
    assert store.load_active() is not None
    store.discard(p.data['game_id'],0);assert store.load_active() is None
    with pytest.raises(ConflictError):store.save(checkpoint(GameSession(now=FakeTime()),2,p.data['game_id']))
    with store.connection() as c:assert c.execute('SELECT status FROM games').fetchone()[0]=='discarded'
    store.create(checkpoint(GameSession(now=FakeTime())))


def test_transaction_exception_rolls_back_moves_times_and_header(store):
    s=GameSession(now=FakeTime());p=checkpoint(s);store.create(p);move(s,'e2e4')
    def fail(stage,connection):raise sqlite3.OperationalError('simulated disk full')
    store.fault=fail
    with pytest.raises(StorageError,match='disk full'):store.save(checkpoint(s,1,p.data['game_id']))
    store.fault=None;r=store.load_active()
    assert r.sequence==0 and not r.session.records and r.session.clock.remaining=={True:900.,False:900.}
    with store.connection() as c:assert c.execute('SELECT count(*) FROM moves').fetchone()[0]==0


def test_database_busy_write_error_keeps_previous_checkpoint(store):
    s=GameSession(now=FakeTime());p=checkpoint(s);store.create(p);move(s,'e2e4')
    with sqlite3.connect(store.path) as lock:
        lock.execute('BEGIN IMMEDIATE')
        with pytest.raises(StorageError,match='locked'):store.save(checkpoint(s,1,p.data['game_id']))
        lock.rollback()
    assert store.load_active().sequence==0
    store.save(checkpoint(s,1,p.data['game_id']));assert store.load_active().sequence==1


@pytest.mark.parametrize('data',[b'not a sqlite database',b''])
def test_corrupt_database_file_unchanged_and_no_crash(tmp_path,data):
    path=tmp_path/'damaged.sqlite3';path.write_bytes(data);digest=hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(StorageError):GameStore(path).initialize()
    assert hashlib.sha256(path.read_bytes()).hexdigest()==digest


def test_future_schema_and_incomplete_existing_schema_not_overwritten(store,tmp_path):
    with store.connection() as con:con.execute('UPDATE schema_info SET version=99')
    before=store.path.read_bytes()
    with pytest.raises(UnsupportedSchema):store.initialize()
    assert store.path.read_bytes()==before
    path=tmp_path/'foreign.sqlite3'
    with sqlite3.connect(path) as con:con.execute('CREATE TABLE unrelated (x)')
    before=path.read_bytes()
    with pytest.raises(UnsupportedSchema):GameStore(path).initialize()
    assert path.read_bytes()==before


@pytest.mark.parametrize('column,value', [('sha256','broken'),('current_fen',chess.STARTING_FEN),('sequence',99),('white_seconds',123),('status','finished')])
def test_corrupt_inconsistent_sql_rows_detected_without_repair_or_delete(store,column,value):
    s=GameSession(now=FakeTime());move(s,'e2e4');p=checkpoint(s);store.create(p)
    with store.connection() as c:c.execute('UPDATE games SET '+column+'=?',(value,))
    before=store.path.read_bytes()
    with pytest.raises(DamagedSave):store.load_active()
    assert store.path.read_bytes()==before


def test_missing_or_changed_move_and_active_slot_detected(store):
    s=GameSession(now=FakeTime());move(s,'e2e4');store.create(checkpoint(s))
    with store.connection() as con:con.execute('DELETE FROM moves')
    with pytest.raises(DamagedSave):store.load_active()
    with store.connection() as con:con.execute('DELETE FROM active_game')
    with pytest.raises(DamagedSave):store.load_active()


@pytest.mark.parametrize('mutation',[
 lambda d:d.update(format_version=999),lambda d:d.update(fen=chess.STARTING_FEN),
 lambda d:d.update(uci_moves=['e2e5']),lambda d:d.update(uci_moves=['e2e4','e7e5']),
 lambda d:d.update(white_seconds=-1),lambda d:d.update(white_seconds=9999),
 lambda d:d.update(bound_source=chess.A8),lambda d:d.update(pending_promotion=[12,60]),
 lambda d:d.update(result={'reason':'pretend','winner':True,'score':'1-0'},status='finished'),
 lambda d:d.update(theme='cyber'),lambda d:d.update(turn=True),lambda d:d.update(castling_rights='0'),
 lambda d:d.update(ep_square=None),lambda d:d.update(fullmove_number=999),
])
def test_valid_checksum_does_not_replace_legal_replay_validation(mutation):
    s=GameSession(now=FakeTime());move(s,'e2e4');d=checkpoint(s).data;mutation(d)
    with pytest.raises(InvalidCheckpoint):restore_checkpoint(pack(d))


def test_invalid_json_and_truncated_payload_reported():
    for text in ('{}','{','null'):
        p=Checkpoint(text,hashlib.sha256(text.encode()).hexdigest())
        with pytest.raises(InvalidCheckpoint):restore_checkpoint(p)


def test_real_process_killed_mid_transaction_recovers_previous_commit(store,tmp_path):
    s=GameSession(now=FakeTime());p=checkpoint(s);store.create(p);move(s,'e2e4')
    payload=tmp_path/'next.json';payload.write_text(checkpoint(s,1,p.data['game_id']).text)
    marker=tmp_path/'uncommitted.marker'
    script='''
import sys,time,hashlib
from pathlib import Path
from database.store import GameStore
from game.checkpoint import Checkpoint
path,payload,marker=sys.argv[1:]
def fault(stage,connection):
    Path(marker).write_text('transaction-open')
    while True:time.sleep(.05)
s=GameStore(path,fault=fault)
t=Path(payload).read_text();s.save(Checkpoint(t,hashlib.sha256(t.encode()).hexdigest()))
'''
    process=subprocess.Popen([sys.executable,'-B','-c',script,str(store.path),str(payload),str(marker)],cwd=PROJECT_ROOT)
    try:
        deadline=time.monotonic()+8
        while not marker.exists() and time.monotonic()<deadline and process.poll() is None:time.sleep(.01)
        assert marker.exists(),'Child never entered open transaction'
        process.kill();process.wait(timeout=5);assert process.returncode<0
    finally:
        if process.poll() is None:process.kill();process.wait(timeout=5)
    GameStore(store.path).initialize();r=store.load_active()
    assert r.sequence==0 and not r.session.records
    with store.connection() as c:assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'


def test_abrupt_exit_after_confirmed_commit_recovers_latest_move(store,tmp_path):
    script='''
import os,sys,uuid
from database.store import GameStore
from game.session import GameSession
from game.checkpoint import export_checkpoint
s=GameSession();s.try_move(12,28);s.suspend()
store=GameStore(sys.argv[1]);store.create(export_checkpoint(s,'adaptive','Schwarz','cyber',str(uuid.uuid4()),0))
os._exit(27)
'''
    process=subprocess.run([sys.executable,'-B','-c',script,str(store.path)],cwd=PROJECT_ROOT,check=False)
    assert process.returncode==27
    store.initialize();r=store.load_active()
    assert r.session.board.peek().uci()=='e2e4' and r.theme=='cyber' and r.player_color=='Schwarz'


def test_new_sequence_does_not_allow_older_clock_or_incomplete_events_to_replace_latest(store):
    now=FakeTime();s=GameSession(now=now);p=checkpoint(s);store.create(p)
    now.advance(20);new=checkpoint(s,1,p.data['game_id']);store.save(new)
    old=p.data;old['sequence']=2
    with pytest.raises(ConflictError,match='Uhrstand'):store.save(pack(old))
    s.touch(chess.E2);bound=checkpoint(s,2,p.data['game_id']);store.save(bound)
    d=bound.data;d['sequence']=3;d['events']=[]
    with pytest.raises(ConflictError,match='Ereignisliste'):store.save(pack(d))
    d=bound.data;d['sequence']=3;d['bound_source']=None;d['draw_claim_barred']=False
    with pytest.raises(ConflictError,match='Auswahlverpflichtung'):store.save(pack(d))
    assert store.load_active().session.bound_source==chess.E2
