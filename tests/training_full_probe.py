"""Run the real training schedule in an isolated database."""
from collections import Counter
import json
from pathlib import Path
import resource
import sys
from threading import Event
from time import monotonic
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from evaluation.training import PRODUCTION, Training
from learning.repository import read_model

if __name__ == '__main__':
    path = ROOT/'.venv/.tmp'/f'training-{uuid4()}'/'probe.sqlite3'
    training = Training(path)
    training.store.initialize()
    start = monotonic()
    training.run(None,PRODUCTION,Event(),Event(),lambda:'interrupted',
                 lambda count,total,_:print(f'{count}/{total}',flush=True) if count%100==0 else None)
    status = training.status()
    assert status['count']==600 and status['status']=='complete' and status['candidate']
    with training.store.connection() as con:
        active,stable = con.execute('SELECT active,stable FROM learning_state').fetchone()
        fixtures = [json.loads(row[0])['game']['fixture'] for row in con.execute('SELECT result FROM training_games')]
        counts = Counter((row['opponent'],row['white']) for row in fixtures)
        assert sorted(counts.values())==[100]*6 and active==stable==status['reference']
        assert con.execute('SELECT count(*) FROM learning_events').fetchone()[0]==0
        assert read_model(con,stable)==(1,)*5
        weights = read_model(con,status['candidate'])
    print(json.dumps(dict(seconds=monotonic()-start, peak_rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                          cells={f'{opp}/{white}':n for (opp,white),n in counts.items()},
                          status=status, weights=weights),indent=2))
