"""Reproduce Phase 9.6 measurements using read-only model snapshots."""
from collections import Counter
from dataclasses import replace
from argparse import ArgumentParser
import json
from pathlib import Path
import sqlite3
import sys
from threading import Event
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from evaluation import match, metrics, runner
from evaluation.repository import Reviews
from evaluation.statistics import dashboard
from learning import repository as learning


def snapshots():
    path = ROOT/'database/neurochess.sqlite3'
    with sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1',uri=True) as con:
        versions = {model:json.loads(weights) for model,weights in con.execute(
            'SELECT id,weights FROM learning_models WHERE id IN (1,229)')}
        return versions[1],versions[229]


def sample(reference,candidate):
    base = replace(match.REVIEW, pairs_per_cell=10, max_plies=48,deeper=False,endgames=False)
    configurations = {'legacy':match.Budget(10), 'limit_only':replace(base,max_plies=96),
                      'depth_only':replace(base,deeper=True),
                      'combined_openings':replace(base,max_plies=96,deeper=True),
                      'new_mixture':replace(match.REVIEW,pairs_per_cell=10)}
    for label,budget in configurations.items():
        started = time.monotonic()
        games = [match.play(f,budget,w,Event()) for f in match.plan(budget) if f.slot//4 in (0,2,4,8,9) for w in (candidate,reference)]
        counts = Counter(g['reason'] for g in games)
        print(json.dumps(dict(name=label,seconds=time.monotonic()-started,reasons=counts,
                              mean_plies=sum(len(g['moves']) for g in games)/len(games))),flush=True)
    for f in match.plan(match.REVIEW):
        if isinstance(f,match.EndgameFixture) and f.opponent=='grandmaster' and f.white and 'Q' in f.fen:
            for deeper in (False,True):
                budget = replace(match.REVIEW,deeper=deeper)
                game = match.play(f,budget,reference,Event())
                print(json.dumps(dict(probe='queen_endgame',deeper=deeper,reason=game['reason'],
                                      plies=len(game['moves']),first_moves=game['moves'][:16])),flush=True)
            break


def full(reference,candidate):
    db = ROOT/'.venv/.tmp'/f'quality-{uuid4()}'/'probe.sqlite3'
    service = Reviews(db)
    service.store.initialize()
    with service.store.connection() as con, service.store.transaction(con):
        learning.initialize(con)
        assert tuple(reference)==learning.read_model(con,1)
        model = learning.insert_model(con,candidate,0,5,'fixture','Isolierter Kandidaten-Snapshot')
        con.execute('INSERT INTO learning_candidates VALUES(5,?,?,1)',(model,'Probe'))
    started = time.monotonic()
    run_id = runner.run(service,None,match.REVIEW,Event(),Event(),lambda:'interrupted',lambda *_:None)
    row = dashboard(db)['runs'][0]
    assert row['count']==row['total']==400
    with service.store.connection() as con:
        assert learning.read_model(con,1)==tuple(reference) and learning.read_model(con,model)==tuple(candidate)
        assert con.execute('SELECT count(*) FROM learning_events').fetchone()[0]==0
    print(json.dumps(dict(run=run_id,seconds=time.monotonic()-started,report=row['report']),indent=2))


if __name__=='__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--sample',action='store_true',help='Run the smaller protocol comparison')
    parser.add_argument('--local-models',action='store_true',help='Read local snapshots #1 and #229')
    args = parser.parse_args()
    pair = snapshots() if args.local_models else ((1,)*5,(1.04,.98,1.02,.99,1.01))
    (sample if args.sample else full)(*pair)
