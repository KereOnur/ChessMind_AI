"""Read-only projections for the player and evaluation dashboards."""
import json

from database.store import GameStore
from evaluation import schema, training_schema
from evaluation.repository import Reviews, checked, eligible
from learning import repository as learning


def player_stats(path):
    modes = {name:dict(wins=0,draws=0,losses=0,plies=0,recent=[])
             for name in ('amateur','grandmaster','adaptive')}
    with GameStore(path).connection() as con:
        for row in con.execute("""SELECT mode,player_color,result_json,saved_at,
            (SELECT count(*) FROM moves WHERE game_id=games.id) AS plies
            FROM games WHERE status='finished' AND (
            (format_version=2 AND mode='amateur') OR
            (format_version=3 AND mode='grandmaster') OR
            (format_version=4 AND mode='adaptive')) ORDER BY saved_at DESC"""):
            result = json.loads(row['result_json'])
            human_white = row['player_color'] == 'Weiß'
            outcome = 'draws' if result['winner'] is None else ('wins' if result['winner']==human_white else 'losses')
            mode = modes[row['mode']]
            mode[outcome] += 1
            mode['plies'] += row['plies']
            if len(mode['recent']) < 5:
                mode['recent'].append((row['saved_at'][:10], outcome, result['reason'], row['plies']))
    return modes


def dashboard(path, *, recover=False):
    reviews = Reviews(path)
    if recover:
        reviews.recover()
    with reviews.store.connection() as con:
        con.execute('BEGIN')
        result = dict(state=None,candidate=None,models=[],candidates=[],runs=[],decisions=[],
                      progress=None,events=0,games=0,since=0,reason='Noch keine Daten vorhanden. Schließe fünf Adaptive-Lernpartien ab, um einen Kandidaten zu erhalten.')
        if not con.execute("SELECT 1 FROM sqlite_master WHERE name='learning_state'").fetchone():
            return result
        state, candidate = eligible(con)
        result.update(state=dict(state),candidate=dict(candidate) if candidate else None)
        result['events'] = con.execute('SELECT count(*) FROM learning_events').fetchone()[0]
        result['games'] = con.execute("SELECT count(*) FROM learning_events WHERE kind='result'").fetchone()[0]
        result['candidates'] = [tuple(row) for row in con.execute('SELECT milestone,model FROM learning_candidates ORDER BY milestone')]
        model_rows = con.execute('SELECT id,created,status,weights,digest FROM learning_models ORDER BY id')
        for row in model_rows:
            model = dict(id=row['id'], created=row['created'], status=row['status'], weights=None)
            try:
                model['weights'] = learning.read_model(con, row['id'])
            except (ValueError, TypeError, OverflowError):
                pass
            result['models'].append(model)
        result['training_candidates'] = []
        if training_schema.exists(con):
            result['training_candidates'] = [row[0] for row in con.execute(
                'SELECT candidate FROM training_runs WHERE candidate IS NOT NULL ORDER BY candidate')]
        last_checked = 0
        if schema.exists(con):
            result['decisions'] = [dict(row) for row in con.execute('SELECT * FROM review_decisions ORDER BY id DESC')]
            for row in con.execute('SELECT * FROM review_runs ORDER BY created DESC'):
                run = {key:row[key] for key in ('id','candidate','reference','status','created')}
                run['count'] = con.execute('SELECT count(*) FROM review_games WHERE run=?',(row['id'],)).fetchone()[0]
                run['report'] = None
                try:
                    data = checked(row['config'],row['digest'])
                    run['total'] = 8 * data['manifest']['budget']['pairs_per_cell']
                    run['protocol'] = data['manifest']['protocol']
                    run['repeat_of'] = data.get('repeat_of')
                    if row['status']=='complete':
                        run['report'] = checked(row['report'],row['report_digest'])
                        if run['count'] != run['total']:
                            raise ValueError('Unvollständige Testdaten.')
                        for game in con.execute('SELECT result,digest FROM review_games WHERE run=?',(row['id'],)):
                            if not isinstance(game['result'],str) or learning.digest(game['result']) != game['digest']:
                                raise ValueError('Beschädigte Testpartie.')
                        if run['total']==400:
                            last_checked = max(last_checked,run['report'].get('checked_games',data['milestone']))
                except (ValueError, TypeError, KeyError):
                    run['status'] = 'invalid'
                    run['report'] = None
                    run['total'] = 400
                result['runs'].append(run)
        result['since'] = max(0,result['games']-last_checked)
        result['reason'] = 'Keine ungeprüfte Kandidatenversion vorhanden.'
        if candidate:
            try:
                learning.read_model(con,candidate['model'])
                learning.read_model(con,state['stable'])
                result['reason'] = ''
            except (ValueError, TypeError, OverflowError):
                result['reason'] = 'Kandidat oder Referenz enthält ungültige Modellparameter.'
        return result
