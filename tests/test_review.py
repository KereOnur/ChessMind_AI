"""Phase 9 protocol, persisted control flow, qualification and statistics."""
from collections import Counter
from dataclasses import asdict
from threading import Event
from types import SimpleNamespace

import chess
import pytest

from evaluation import match, metrics, runner
from evaluation.repository import Reviews
from evaluation.statistics import dashboard, player_stats
from game.checkpoint import canonical
from learning import repository as learning
from test_adaptive_core import checkpoint, session


@pytest.fixture
def repo(tmp_path):
    reviews = Reviews(tmp_path/'review.sqlite3')
    reviews.store.initialize()
    return reviews


def seed(repo, weights=(1.1,1,1,1,1)):
    with repo.store.connection() as con, repo.store.transaction(con):
        learning.initialize(con)
        candidate = learning.insert_model(con, weights, 0, 5, 'fixture', 'Prüfstand')
        con.execute('INSERT INTO learning_candidates VALUES(5,?,?,0)',(candidate,'Prüfstand'))
    return candidate


def run(repo, budget, *, run_id=None, cancel=None, pause=None, status='interrupted', progress=lambda *_:None):
    return runner.run(repo,run_id,budget,cancel or Event(),pause or Event(),lambda:status,progress)


def test_exact_production_plan():
    fixtures = match.plan(match.PRODUCTION)
    assert len(fixtures) == 200
    assert Counter((p.opponent,p.white) for p in fixtures) == {
        (opponent,white):50 for opponent in ('amateur','grandmaster') for white in (True,False)}
    assert fixtures == match.plan(match.PRODUCTION)
    assert len({p.seed for p in fixtures}) == 200
    assert all(match.initial_board(p).is_valid() for p in fixtures)


def test_real_seeded_match_reproducible():
    budget = match.Budget(1,12)
    fixture = match.plan(budget)[0]
    a,b = (match.play(fixture,budget,(1,)*5,Event()) for _ in range(2))
    assert (a['moves'],a['score'],a['reason']) == (b['moves'],b['score'],b['reason'])


def test_terminal_and_watchdog(monkeypatch):
    assert match.ending(chess.Board('7k/5Q2/6K1/8/8/8/8/8 b - - 0 1'),0,48) == ('1/2-1/2','STALEMATE')
    assert match.ending(chess.Board('7k/6Q1/6K1/8/8/8/8/8 b - - 0 1'),0,48) == ('1-0','CHECKMATE')
    assert match.ending(chess.Board(),1,1) == ('1/2-1/2','PLY_LIMIT')
    monkeypatch.setattr(match.adaptive,'search',lambda *_args,**_kwargs:SimpleNamespace(elapsed=.35))
    with pytest.raises(RuntimeError,match='Suchzeit'):
        match.play(match.plan(match.PRODUCTION)[0],match.PRODUCTION,(1,)*5,Event())


def test_no_automatic_start_and_empty_stats(repo):
    assert dashboard(repo.store.path,recover=True)['runs'] == []
    assert all(r['recent']==[] for r in player_stats(repo.store.path).values())
    with pytest.raises(ValueError,match='fünf'):
        run(repo,match.Budget(1,2))
    seed(repo)
    assert dashboard(repo.store.path)['candidate'] and dashboard(repo.store.path)['runs']==[]


@pytest.mark.parametrize('status',['paused','aborted','interrupted'])
def test_stop_resume_and_unchanged_weights(repo,status):
    candidate = seed(repo)
    cancel,pause = Event(),Event()
    budget = match.Budget(1,6)
    def stop_after_two(*args):
        if sum(map(len,args[-1].values())) == 2:
            (pause if status=='paused' else cancel).set()
    run_id = run(repo,budget,cancel=cancel,pause=pause,status=status,progress=stop_after_two)
    saved = dashboard(repo.store.path)['runs'][0]
    assert saved['status']==status and saved['count']==2
    if status=='aborted':
        with pytest.raises(ValueError,match='fortgesetzt'):
            run(repo,budget,run_id=run_id)
    else:
        run(Reviews(repo.store.path),budget,run_id=run_id)
        done = dashboard(repo.store.path)['runs'][0]
        assert done['status']=='complete' and done['count']==8
        with pytest.raises(ValueError,match='Freigabe'):
            repo.change_model(run_id=run_id)
    with repo.store.connection() as con:
        assert con.execute('SELECT count(*) FROM learning_events').fetchone()[0] == 0
        assert learning.read_model(con,candidate)==(1.1,1,1,1,1)
        assert con.execute('SELECT active FROM learning_state').fetchone()[0] == 1


def test_restart_detects_abandoned_run_and_ignores_duplicate(repo):
    seed(repo)
    budget = match.Budget(1,2)
    run_id,_,_ = repo.prepare(None,budget)
    fixture = match.plan(budget)[0]
    row = match.play(fixture,budget,(1,)*5,Event())
    repo.append(run_id,1,fixture,row)
    with pytest.raises(RuntimeError,match='UNIQUE'):
        repo.append(run_id,1,fixture,row)
    assert dashboard(repo.store.path,recover=True)['runs'][0]['status']=='interrupted'
    run(repo,budget,run_id=run_id)
    assert dashboard(repo.store.path)['runs'][0]['count']==8


def test_invalid_model_and_database(repo):
    candidate = seed(repo)
    with repo.store.connection() as con, repo.store.transaction(con):
        con.execute("UPDATE learning_models SET weights='corrupt' WHERE id=?",(candidate,))
    assert 'ungültige' in dashboard(repo.store.path)['reason']
    with pytest.raises(ValueError,match='[Pp]rüfsumme'):
        run(repo,match.Budget(1,1))
    damaged = repo.store.path.with_name('broken.sqlite3')
    damaged.write_bytes(b'not sqlite')
    with pytest.raises(RuntimeError):
        dashboard(damaged)


def test_human_parties_only_and_running_game_blocks_test(repo):
    seed(repo)
    for index,kind in enumerate(('amateur_ai','grandmaster_ai','adaptive_ai')):
        game = session(kind=kind)
        repo.store.create(checkpoint(game,game_id=str(index)))
        with pytest.raises(ValueError,match='laufende Partie'):
            run(repo,match.Budget(1,1))
        game.resign()
        repo.store.save(checkpoint(game,1,str(index)))
    assert all(x['losses']==1 for x in player_stats(repo.store.path).values())
    run(repo,match.Budget(1,1))
    assert all(x['losses']==1 for x in player_stats(repo.store.path).values())


def test_provisional_release_validates_all_rows_and_preserves_fallback(repo,monkeypatch):
    # Scripted legal end states exercise the release path. The full probe uses actual engines.
    monkeypatch.setattr(match,'OPENINGS',(('f2f3','e7e5','g2g4'),))
    candidate = seed(repo)
    monkeypatch.setattr(match,'REVIEW',match.Budget(protocol=match.REVIEW_PROTOCOL))
    run_id, budget, _ = repo.prepare(None,match.REVIEW)
    with repo.store.connection() as con, repo.store.transaction(con):
        for fixture in match.plan(budget):
            for version in (candidate,1):
                board = match.initial_board(fixture)
                win = version==candidate and not fixture.white
                moves = ['d8h4'] if win else ['g8f6','g1h3','f6g8','h3g1']*2
                for uci in moves:
                    board.push_uci(uci)
                score,reason = match.ending(board,len(moves),budget.max_plies)
                game = dict(fixture=asdict(fixture),fen=match.initial_board(fixture).fen(en_passant='fen'),
                            moves=moves,score=score,reason=reason,seconds=.02,cpu=.01,status='complete')
                payload = canonical(game)
                con.execute('INSERT INTO review_games VALUES(?,?,?,?,?)',
                            (run_id,version,fixture.slot,payload,learning.digest(payload)))
    assert repo.complete(run_id)['difference'] == .25
    game = session()
    repo.store.create(checkpoint(game))
    game.suspend()
    repo.store.save(checkpoint(game,1))
    with pytest.raises(ValueError,match='Adaptive-Partie'):
        repo.change_model(run_id=run_id)
    repo.store.discard(checkpoint(game).data['game_id'],1)
    with repo.store.connection() as con, repo.store.transaction(con):
        payload,digest = con.execute('SELECT result,digest FROM review_games WHERE version=? AND slot=0',(candidate,)).fetchone()
        con.execute("UPDATE review_games SET digest='bad' WHERE version=? AND slot=0",(candidate,))
    with pytest.raises(ValueError,match='[Pp]rüfsumme'):
        repo.change_model(run_id=run_id)
    with repo.store.connection() as con, repo.store.transaction(con):
        con.execute('UPDATE review_games SET digest=? WHERE version=? AND slot=0',(digest,candidate))
    repo.change_model(run_id=run_id)
    assert dashboard(repo.store.path)['state']['stable']==candidate
    repo.change_model(restore=1)
    assert dashboard(repo.store.path)['state']['stable']==1
    assert dashboard(repo.store.path)['decisions'][0]['action']=='restored'


def test_paired_uncertainty_and_score():
    games = [dict(fixture={'white':True,'opponent':'amateur'},score='1/2-1/2',
                  reason='PLY_LIMIT',moves=['x'],seconds=.1,cpu=.05)]
    report = metrics.compare(games,games)
    assert report['candidate']['points']==.5 and report['interval']==[0,0]
    assert report['uncertain'] and report['decision']=='keep_reference'


def test_cancelling_mid_game_keeps_only_confirmed_results(repo,monkeypatch):
    seed(repo)
    cancel = Event()
    original = match.play
    calls = 0

    def interrupt_second(fixture,budget,weights,stop,boundary):
        nonlocal calls
        calls += 1
        if calls == 1:
            return original(fixture,budget,weights,stop,boundary)
        steps = 0
        def interrupt():
            nonlocal steps
            steps += 1
            if steps == 2:
                cancel.set()
            boundary()
        return original(fixture,budget,weights,stop,interrupt)

    monkeypatch.setattr(match,'play',interrupt_second)
    run(repo,match.Budget(1,5),cancel=cancel,status='aborted')
    saved = dashboard(repo.store.path)['runs'][0]
    assert saved['status']=='aborted' and saved['count']==1 and saved['report'] is None
