"""Persistent runs, immutable snapshots and explicitly approved model changes."""
from contextlib import contextmanager
import fcntl
import json
import math
from uuid import uuid4
from dataclasses import asdict

from database.store import GameStore
from evaluation import match, metrics, schema, training_schema
from game.checkpoint import canonical
from learning import repository as learning


@contextmanager
def worker_lock(store):
    with store.path.with_suffix('.review.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError('Eine andere Instanz prüft bereits ein Modell.') from exc
        yield


def no_running_game(con, *, switching=False):
    states = ('running', 'suspended') if switching else ('running',)
    rows = con.execute('SELECT status,format_version FROM games JOIN active_game ON games.id=game_id')
    if any(row['status'] in states and (not switching or row['format_version']==4) for row in rows):
        raise ValueError('Beende zuerst die laufende beziehungsweise gespeicherte Adaptive-Partie.' if switching
                         else 'Speichere und verlasse zuerst die laufende Partie.')


def eligible(con, protocol=match.REVIEW_PROTOCOL):
    state = con.execute('SELECT active,stable FROM learning_state').fetchone()
    candidate = con.execute('SELECT milestone,model FROM learning_candidates ORDER BY milestone DESC LIMIT 1').fetchone()
    if training_schema.exists(con):
        trained = con.execute("""SELECT candidate AS model, m.games AS milestone FROM training_runs
            JOIN learning_models m ON m.id=candidate WHERE training_runs.status='complete'
            ORDER BY candidate DESC LIMIT 1""").fetchone()
        if trained and (not candidate or trained['model'] > candidate['model']):
            candidate = trained
    if candidate and (candidate['model'] == state['stable'] or (schema.exists(con) and con.execute(
            """SELECT 1 FROM review_runs WHERE candidate=? AND reference=? AND status='complete'
            AND CASE WHEN json_valid(config) THEN json_extract(config,'$.manifest.protocol') END=?""",
            (candidate['model'],state['stable'],protocol)).fetchone())):
        candidate = None
    return state, candidate


def checked(payload, digest):
    if not isinstance(payload, str) or learning.digest(payload) != digest:
        raise ValueError('Prüfsumme der Testdaten ungültig.')
    return json.loads(payload)


def contract(con, run):
    data = checked(run['config'], run['digest'])
    budget = match.Budget(**data['manifest']['budget'])
    if data['manifest'] != json.loads(canonical(budget.manifest())):
        raise ValueError('Die gespeicherten Suchbedingungen werden von dieser Version nicht unterstützt.')
    for role in ('candidate', 'reference'):
        model = run[role]
        if data[role] != [model, list(learning.read_model(con, model))]:
            raise ValueError('Die Modellversion stimmt nicht mit ihrem eingefrorenen Snapshot überein.')
    return budget, data


def validate_game(fixture, budget, game):
    technical = getattr(budget,'protocol',match.PROTOCOL)==match.REVIEW_PROTOCOL
    expected_status = 'technical' if technical and game['score'] is None else 'complete'
    if game['fixture'] != json.loads(canonical(asdict(fixture))) or game['status'] != expected_status:
        raise ValueError('Testpartie und Testplan widersprechen sich.')
    board = match.initial_board(fixture)
    if game['fen'] != board.fen(en_passant='fen') or len(game['moves']) > budget.max_plies:
        raise ValueError('Ungültiger Start oder Umfang einer Testpartie.')
    for ply, uci in enumerate(game['moves']):
        if match.ending(board, ply, budget.max_plies, technical=technical):
            raise ValueError('Testpartie wurde nach ihrem Ende fortgesetzt.')
        board.push_uci(uci)
    ending = match.ending(board,len(game['moves']),budget.max_plies,technical=technical)
    watchdog = technical and ending is None and game['score'] is None and (
        (game['reason']=='CPU_LIMIT' and game['cpu'] >= match.CPU_LIMIT) or
        (game['reason']=='SEARCH_LIMIT' and math.isfinite(game.get('search_seconds',0))
         and match.SEARCH_LIMIT <= game['search_seconds'] <= game['seconds']))
    if not watchdog and ending != (game['score'],game['reason']):
        raise ValueError('Ungültiges Partieergebnis.')
    if any(not math.isfinite(game[key]) or game[key] < 0 for key in ('seconds','cpu')):
        raise ValueError('Ungültige Testzeiten.')


class Reviews:
    def __init__(self, path):
        self.store = GameStore(path)

    def prepare(self, run_id, budget, *, repeat_of=None):
        with self.store.connection() as con, self.store.transaction(con):
            no_running_game(con)
            if run_id is not None and repeat_of is not None:
                raise ValueError('Fortsetzen und Wiederholen sind getrennte Vorgänge.')
            if run_id is None:
                if not con.execute("SELECT 1 FROM sqlite_master WHERE name='learning_state'").fetchone():
                    raise ValueError('Spiele zuerst fünf menschliche Adaptive-Lernpartien.')
                schema.initialize(con)
                if con.execute("SELECT 1 FROM review_runs WHERE status IN ('running','paused','interrupted')").fetchone():
                    raise ValueError('Setze den vorhandenen Vergleich fort oder brich ihn ab.')
                state, candidate = eligible(con,budget.protocol)
                b = state['stable']
                if repeat_of is not None:
                    source = con.execute('SELECT * FROM review_runs WHERE id=?',(repeat_of,)).fetchone()
                    if (source is None or source['status'] != 'complete'
                            or source['reference'] != b or source['candidate'] == b):
                        raise ValueError('Wähle einen abgeschlossenen Vergleich mit der aktuellen Referenz.')
                    if budget.protocol != match.REVIEW_PROTOCOL:
                        raise ValueError('Wiederholungen verwenden das aktuelle Prüfverfahren.')
                    _, previous = contract(con,source)
                    a, milestone = source['candidate'], previous['milestone']
                else:
                    if not candidate:
                        raise ValueError('Keine ungeprüfte Kandidatenversion vorhanden.')
                    a, milestone = candidate['model'], candidate['milestone']
                data = dict(manifest=budget.manifest(),candidate=[a,learning.read_model(con,a)],
                            reference=[b,learning.read_model(con,b)],milestone=milestone)
                if repeat_of is not None:
                    data['repeat_of'] = repeat_of
                config = canonical(data)
                run_id = str(uuid4())
                con.execute('INSERT INTO review_runs VALUES(?,?,?,?,?,?,?,?,NULL,NULL)',
                            (run_id, learning.stamp(), learning.stamp(), a, b, config,
                             learning.digest(config), 'running'))
            row = con.execute('SELECT * FROM review_runs WHERE id=?', (run_id,)).fetchone()
            if row is None or row['status'] not in ('running','paused','interrupted'):
                raise ValueError('Dieser Vergleich kann nicht fortgesetzt werden.')
            saved_budget, data = contract(con, row)
            con.execute("UPDATE review_runs SET status='running',updated=? WHERE id=?", (learning.stamp(),run_id))
            return run_id, saved_budget, data

    def collect(self, con, run, budget):
        fixtures = match.plan(budget)
        games = {run['candidate']: {}, run['reference']: {}}
        for row in con.execute('SELECT * FROM review_games WHERE run=? ORDER BY slot', (run['id'],)):
            slot, model = row['slot'], row['version']
            if model not in games or not 0 <= slot < len(fixtures):
                raise ValueError('Unerwartete Partie im Testlauf.')
            game = checked(row['result'], row['digest'])
            validate_game(fixtures[slot], budget, game)
            games[model][slot] = game
        return games

    def saved_games(self, run_id, budget):
        with self.store.connection() as con:
            con.execute('BEGIN')
            run = con.execute('SELECT * FROM review_runs WHERE id=?',(run_id,)).fetchone()
            return self.collect(con, run, budget)

    def append(self, run_id, version, fixture, game):
        payload = canonical(game)
        with self.store.connection() as con, self.store.transaction(con):
            row = con.execute('SELECT candidate,reference,status FROM review_runs WHERE id=?',(run_id,)).fetchone()
            if row['status'] != 'running' or version not in (row['candidate'],row['reference']):
                raise ValueError('Der Testlauf nimmt keine Partien an.')
            con.execute('INSERT INTO review_games VALUES(?,?,?,?,?)',
                        (run_id,version,fixture.slot,payload,learning.digest(payload)))

    def calculate(self, con, run):
        budget, _ = contract(con, run)
        games = self.collect(con, run, budget)
        if any(len(rows) != budget.count for rows in games.values()):
            raise ValueError('Der Vergleich ist unvollständig.')
        compare = metrics.quality_compare if budget.protocol==match.REVIEW_PROTOCOL else metrics.compare
        return compare(*(list(games[run[role]].values()) for role in ('candidate','reference')))

    def complete(self, run_id):
        with self.store.connection() as con, self.store.transaction(con):
            run = con.execute('SELECT * FROM review_runs WHERE id=?',(run_id,)).fetchone()
            if run['status'] != 'running':
                raise ValueError('Der Testlauf ist nicht aktiv.')
            report = self.calculate(con, run)
            report['checked_games'] = con.execute(
                "SELECT count(*) FROM learning_events WHERE kind='result'"
            ).fetchone()[0]
            payload = canonical(report)
            con.execute("UPDATE review_runs SET status='complete',report=?,report_digest=?,updated=? WHERE id=?",
                        (payload,learning.digest(payload),learning.stamp(),run_id))
            con.execute('INSERT INTO review_decisions VALUES(NULL,?,?,?,?,?)',
                        (run_id,learning.stamp(),run['reference'],run['candidate'],report['decision']))
            return report

    def stop(self, run_id, status):
        with self.store.connection() as con, self.store.transaction(con):
            con.execute("""UPDATE review_runs SET status=?,updated=? WHERE id=?
                AND status IN ('running','paused','interrupted')""", (status,learning.stamp(),run_id))

    def recover(self):
        with self.store.connection() as con:
            if not schema.exists(con) or not con.execute("SELECT 1 FROM review_runs WHERE status='running'").fetchone():
                return
        try:
            with worker_lock(self.store), self.store.connection() as con:
                if schema.exists(con) and con.execute("SELECT 1 FROM review_runs WHERE status='running'").fetchone():
                    with self.store.transaction(con):
                        con.execute("UPDATE review_runs SET status='interrupted',updated=? WHERE status='running'",
                                    (learning.stamp(),))
        except ValueError:
            # The process holding the lock still owns the running record.
            pass

    def change_model(self, *, run_id=None, restore=None):
        with worker_lock(self.store), self.store.connection() as con, self.store.transaction(con):
            no_running_game(con, switching=True)
            current = con.execute('SELECT stable FROM learning_state').fetchone()[0]
            if run_id:
                run = con.execute('SELECT * FROM review_runs WHERE id=?',(run_id,)).fetchone()
                if not run or run['status'] != 'complete' or run['reference'] != current:
                    raise ValueError('Der vollständige Vergleich muss zur aktuellen Referenz passen.')
                budget, _ = contract(con, run)
                report = self.calculate(con, run)
                previous_report = checked(run['report'],run['report_digest'])
                previous_report.pop('checked_games',None)
                if (budget != match.REVIEW or report != previous_report
                        or report['decision'] != 'eligible'):
                    raise ValueError('Dieser Vergleich erlaubt keine vorläufige Freigabe.')
                if con.execute("SELECT 1 FROM review_decisions WHERE run=? AND action='promoted'",(run_id,)).fetchone():
                    raise ValueError('Diese Freigabe wurde bereits verwendet.')
                target, action = run['candidate'], 'promoted'
            else:
                allowed = con.execute("""SELECT previous FROM review_decisions WHERE action IN ('promoted','restored')
                    UNION SELECT selected FROM review_decisions WHERE action IN ('promoted','restored')""")
                if restore != current and restore not in {row[0] for row in allowed}:
                    raise ValueError('Diese Version war kein Referenzstand.')
                target, action = restore, 'restored'
            learning.read_model(con, target)
            con.execute('UPDATE learning_state SET stable=? WHERE slot=1',(target,))
            learning.restore_stable(con)
            con.execute('INSERT INTO review_decisions VALUES(NULL,?,?,?,?,?)',
                        (run_id,learning.stamp(),current,target,action))
