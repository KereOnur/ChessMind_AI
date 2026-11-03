"""Resource measurement for the real Phase 9 production protocol, isolated data."""
import json
from pathlib import Path
import resource
import sys
import time
from threading import Event
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.match import PRODUCTION
from evaluation.repository import Reviews
from evaluation.runner import run
from evaluation.statistics import dashboard
from learning import repository as learning

if __name__ == '__main__':
    path = ROOT / '.venv/.tmp' / f'review-full-{uuid4()}' / 'test.sqlite3'
    repo = Reviews(path)
    repo.store.initialize()
    with repo.store.connection() as con, repo.store.transaction(con):
        learning.initialize(con)
        model = learning.insert_model(con, (1.04,.98,1.02,.99,1.01), 0, 5, 'probe', 'Isolierter Prüfstand')
        con.execute('INSERT INTO learning_candidates VALUES(5,?,?,1)',(model,'Prüfstand'))
    start = time.monotonic()
    run_id = run(repo,None,PRODUCTION,Event(),Event(),lambda:'interrupted',
                 lambda _id,_model,_op,_total,saved: print(sum(map(len,saved.values())),flush=True)
                 if sum(map(len,saved.values())) % 100 == 0 else None)
    data = dashboard(path)['runs'][0]
    assert data['status']=='complete' and data['count']==data['total']==400
    print(json.dumps(dict(seconds=time.monotonic()-start,
                          peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                          run=run_id, report=data['report']),indent=2))
