"""Phase 9.6 rules, censoring, fair plans and durable outcomes."""
from collections import Counter
from dataclasses import replace
from threading import Event
from types import SimpleNamespace

import chess
import pytest

from evaluation import match, metrics
from evaluation.repository import Reviews
from evaluation.statistics import dashboard
from test_review import run, seed


def end(board, plies=0, limit=96):
    return match.ending(board,plies,limit,technical=True)


def test_regulatory_outcomes_take_priority_over_limit():
    assert end(chess.Board('7k/6Q1/6K1/8/8/8/8/8 b - - 150 80'),96)==('1-0','CHECKMATE')
    assert end(chess.Board('7k/5Q2/6K1/8/8/8/8/8 b - - 0 1'),96)==('1/2-1/2','STALEMATE')
    assert end(chess.Board('7k/8/6K1/8/8/8/8/8 w - - 0 1'))==('1/2-1/2','INSUFFICIENT_MATERIAL')
    assert end(chess.Board('7k/8/6K1/8/8/8/8/R7 w - - 100 80'))==('1/2-1/2','CLAIM')
    assert end(chess.Board('7k/8/6K1/8/8/8/8/R7 w - - 150 80'))==('1/2-1/2','SEVENTYFIVE_MOVES')
    board = chess.Board()
    cycle = ['g1f3','g8f6','f3g1','f6g8']
    for move in cycle*2:
        board.push_uci(move)
    assert end(board)==('1/2-1/2','CLAIM')
    for move in cycle*2:
        board.push_uci(move)
    assert end(board)==('1/2-1/2','FIVEFOLD_REPETITION')
    assert end(chess.Board(),96)==(None,'PLY_LIMIT')


def test_plan_fair_and_valid():
    plan = match.plan(match.REVIEW)
    assert len(plan)==200 and plan==match.plan(match.REVIEW)
    assert Counter((f.opponent,f.white) for f in plan)=={
        (opponent,color):50 for opponent in ('amateur','grandmaster') for color in (True,False)}
    assert sum(isinstance(f,match.EndgameFixture) for f in plan)==160
    assert all(match.initial_board(f).is_valid() and end(match.initial_board(f)) is None for f in plan)


def game(score):
    return dict(score=score,fixture=dict(opponent='amateur',white=True),moves=[],
                seconds=0,cpu=0,reason='PLY_LIMIT' if score is None else 'CHECKMATE')


def test_technical_results_are_not_points_and_missing_pairs_cannot_force_release():
    result = metrics.quality_compare([game('1-0'),game(None)], [game('0-1'),game('1-0')])
    assert result['candidate']['rate']==1 and result['candidate']['draws']==0
    assert result['candidate']['technical']==1 and result['paired']==1
    assert result['reference']['rate']==.5 and result['missing_bounds']==[0,.5]
    assert result['quality_limited'] and result['decision']=='keep_reference'
    result = metrics.quality_compare([game(None)],[game(None)])
    assert result['interval'] is None and result['difference'] is None


def test_watchdog_records_unscored_slot(monkeypatch):
    budget = replace(match.REVIEW,pairs_per_cell=1,endgames=False)
    monkeypatch.setattr(match.adaptive,'search',lambda *_args,**_kwargs:(
        SimpleNamespace(elapsed=.35,move=None)))
    result = match.play(match.plan(budget)[0],budget,(1,)*5,Event())
    assert (result['score'],result['status'],result['reason'])==(None,'technical','SEARCH_LIMIT')


def test_persisted_v2_with_pause_resume_and_legacy_retest(tmp_path):
    repo = Reviews(tmp_path/'quality.sqlite3')
    repo.store.initialize()
    candidate = seed(repo)
    run(repo,match.Budget(1,1))
    assert dashboard(repo.store.path)['candidate']['model']==candidate
    budget = replace(match.REVIEW,pairs_per_cell=1,max_plies=1,endgames=False)
    pause = Event()
    def after_two(*args):
        if sum(map(len,args[-1].values()))==2:
            pause.set()
    run_id = run(repo,budget,pause=pause,status='paused',progress=after_two)
    assert dashboard(repo.store.path)['runs'][0]['count']==2
    run(repo,budget,run_id=run_id)
    new,old = dashboard(repo.store.path)['runs']
    assert new['report']['candidate']['technical']==4 and new['report']['candidate']['draws']==0
    assert old['report']['candidate']['draws']==4
    with repo.store.connection() as con:
        assert con.execute('SELECT count(*) FROM learning_events').fetchone()[0]==0
        assert con.execute('SELECT active,stable FROM learning_state').fetchone()[:]==(1,1)
