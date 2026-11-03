"""Phase 9.5 training contract, isolation and recovery."""
from collections import Counter
from threading import Event

import chess
import pytest

from evaluation import match, training
from evaluation.repository import Reviews
from evaluation.statistics import dashboard
from learning import repository as models


def test_600_game_plan_and_separate_400_game_comparison():
    plan = training.plan(training.PRODUCTION)
    assert len(plan)==600 and len({row.seed for row in plan})==600
    assert Counter((row.opponent,row.white) for row in plan)=={
        (opponent,color):100 for opponent in training.OPPONENTS for color in (True,False)}
    assert plan==training.plan(training.PRODUCTION)
    assert 2*match.PRODUCTION.count==400
    assert all(match.initial_board(row).is_valid() for row in plan)


def test_adaptive_opponent_only_uses_frozen_weights(monkeypatch):
    calls = []
    original = match.adaptive.search
    def search(board,remaining,**kwargs):
        calls.append((board.turn,kwargs['weights']))
        return original(board,remaining,**kwargs)
    monkeypatch.setattr(match.adaptive,'search',search)
    budget = training.TrainingBudget(1,8)
    fixture = training.plan(budget)[4]
    reference = (.9,1,1,1,1)
    result,updated = training.train_game(fixture,budget,(1,)*5,reference,Event(),lambda:None)
    assert updated!=(1,)*5
    assert all(weights==reference for white,weights in calls if white!=fixture.white)
    assert len({weights for white,weights in calls if white==fixture.white})>1
    board = match.initial_board(fixture)
    for move in result['moves']:
        assert chess.Move.from_uci(move) in board.legal_moves
        board.push_uci(move)


@pytest.mark.parametrize('stop_status',['paused','aborted','interrupted'])
def test_persisted_checkpoint_and_no_learning_history(tmp_path,stop_status):
    service = training.Training(tmp_path/'test.sqlite3')
    service.store.initialize()
    assert service.status() is None
    pause = Event()
    budget = training.TrainingBudget(1,4)
    def progress(count,*_):
        if count==2:
            pause.set()
    service.run(None,budget,Event(),pause,lambda:stop_status,progress)
    state = service.status()
    assert state['count']==2 and state['status']==stop_status
    service.store.initialize()
    if stop_status!='aborted':
        service.run(state['id'],budget,Event(),Event(),lambda:'interrupted',lambda *_:None)
        assert service.status()['count']==6 and service.status()['status']=='complete'
    assert not service.status()['candidate']
    assert dashboard(service.store.path)['candidate'] is None
    with service.store.connection() as con:
        assert con.execute('SELECT count(*) FROM learning_events').fetchone()[0]==0
        assert tuple(con.execute('SELECT active,stable FROM learning_state').fetchone())==(1,1)
        assert models.read_model(con,1)==(1,)*5


def test_completed_training_enters_comparison_without_switching_models(tmp_path,monkeypatch):
    # A deliberately shortened production fixture exercises atomic publication.
    budget = training.TrainingBudget(1,4)
    monkeypatch.setattr(training,'PRODUCTION',budget)
    service = training.Training(tmp_path/'test.sqlite3')
    service.store.initialize()
    service.run(None,budget,Event(),Event(),lambda:'interrupted',lambda *_:None)
    state = service.status()
    candidate = state['candidate']
    assert dashboard(service.store.path)['candidate']['model']==candidate
    reviews = Reviews(service.store.path)
    _, comparison, data = reviews.prepare(None,match.PRODUCTION)
    assert data['candidate'][0]==candidate and data['reference'][0]==state['reference']
    assert comparison.count==200
    service.store.initialize()
    with service.store.connection() as con:
        assert tuple(con.execute('SELECT active,stable FROM learning_state').fetchone())==(1,1)
