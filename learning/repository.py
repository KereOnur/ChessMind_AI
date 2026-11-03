"""Adaptive records written inside the existing game transaction."""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import time

from ai.adaptive import position
from learning.td import INITIAL, update, validate

SCHEMA = {
    'learning_models': """CREATE TABLE learning_models (
        id INTEGER PRIMARY KEY, created TEXT NOT NULL, weights TEXT NOT NULL,
        digest TEXT NOT NULL, moves INTEGER NOT NULL, games INTEGER NOT NULL,
        status TEXT NOT NULL, review TEXT NOT NULL)""",
    'learning_state': """CREATE TABLE learning_state (
        slot INTEGER PRIMARY KEY CHECK(slot=1), version INTEGER NOT NULL CHECK(version=1),
        active INTEGER NOT NULL REFERENCES learning_models(id),
        stable INTEGER NOT NULL REFERENCES learning_models(id))""",
    'learning_games': """CREATE TABLE learning_games (
        game_id TEXT PRIMARY KEY REFERENCES games(id), initial_model INTEGER NOT NULL
        REFERENCES learning_models(id), initial_weights TEXT NOT NULL)""",
    'learning_events': """CREATE TABLE learning_events (
        game_id TEXT NOT NULL REFERENCES learning_games(game_id), ply INTEGER NOT NULL,
        kind TEXT NOT NULL CHECK(kind IN ('move','result')), model INTEGER NOT NULL
        REFERENCES learning_models(id), details TEXT NOT NULL, created TEXT NOT NULL,
        PRIMARY KEY(game_id, ply, kind))""",
    'learning_candidates': """CREATE TABLE learning_candidates (
        milestone INTEGER PRIMARY KEY, model INTEGER NOT NULL REFERENCES learning_models(id),
        review TEXT NOT NULL, announced INTEGER NOT NULL DEFAULT 0)""",
}


@dataclass(frozen=True)
class LearningState:
    revision: int
    model: int
    weights: tuple
    report: dict | None = None
    recovered: bool = False
    pending_notice: bool = False


def stamp():
    return datetime.now(timezone.utc).isoformat()


def digest(payload):
    return hashlib.sha256(payload.encode()).hexdigest()


def insert_model(con, weights, moves, games, status, review):
    payload = json.dumps(validate(weights), allow_nan=False)
    return con.execute(
        'INSERT INTO learning_models VALUES(NULL,?,?,?,?,?,?,?)',
        (stamp(), payload, digest(payload), moves, games, status, review),
    ).lastrowid


def initialize(con):
    for name, statement in SCHEMA.items():
        if not con.execute('SELECT 1 FROM sqlite_master WHERE name=?', (name,)).fetchone():
            con.execute(statement)
    if not con.execute('SELECT 1 FROM learning_state').fetchone():
        stable = insert_model(con, INITIAL, 0, 0, 'stable', 'Fester Ausgangsstand, ohne Vergleichsprüfung')
        con.execute('INSERT INTO learning_state VALUES(1,1,?,?)', (stable, stable))


def read_model(con, model):
    row = con.execute('SELECT * FROM learning_models WHERE id=?', (model,)).fetchone()
    if row is None or not isinstance(row['weights'], str) or digest(row['weights']) != row['digest']:
        raise ValueError('Modellprüfsumme ungültig.')
    return validate(json.loads(row['weights']))


def active_model(con, *, repair=True):
    state = con.execute('SELECT active, stable FROM learning_state WHERE slot=1').fetchone()
    try:
        return state['active'], read_model(con, state['active']), False
    except (ValueError, TypeError, OverflowError):
        try:
            weights = read_model(con, state['stable'])
        except (ValueError, TypeError, OverflowError):
            weights = INITIAL
        if not repair:
            return state['stable'], weights, True
        counts = con.execute("""SELECT count(*) FILTER (WHERE kind='move'),
            count(*) FILTER (WHERE kind='result') FROM learning_events""").fetchone()
        model = insert_model(con, weights, *counts, 'recovered', 'Rückfall auf stabilen Ausgangsstand')
        con.execute('UPDATE learning_state SET active=? WHERE slot=1', (model,))
        return model, weights, True


def snapshot(con, restored):
    if restored.session.play_kind != 'adaptive_ai':
        return None
    check_progress(con, restored.game_id, restored.session.revision)
    model, weights, recovered = active_model(con, repair=False)
    return LearningState(restored.session.revision, model, weights, recovered=recovered)


def check_progress(con, game_id, revision):
    game = con.execute('SELECT 1 FROM learning_games WHERE game_id=?', (game_id,)).fetchone()
    cursor = con.execute("""SELECT count(*), coalesce(max(ply),0) FROM learning_events
        WHERE game_id=? AND kind='move'""", (game_id,)).fetchone()
    if game is None or tuple(cursor) != (revision, revision):
        raise ValueError('Lernfortschritt und gesicherte Zugliste widersprechen sich.')


def restore_stable(con):
    initialize(con)
    stable = con.execute('SELECT stable FROM learning_state WHERE slot=1').fetchone()[0]
    weights = read_model(con, stable)
    moves, games = con.execute("""SELECT count(*) FILTER (WHERE kind='move'),
        count(*) FILTER (WHERE kind='result') FROM learning_events""").fetchone()
    model = insert_model(con, weights, moves, games, 'restored', 'Stabiler Ausgangsstand wieder aktiviert')
    con.execute('UPDATE learning_state SET active=? WHERE slot=1', (model,))
    return model


def record_event(con, game_id, ply, kind, model, weights, before, after=None, reward=None):
    started = time.perf_counter()
    new, prediction, target, error = update(weights, before, after, reward)
    counts = con.execute('SELECT moves,games FROM learning_models WHERE id=?', (model,)).fetchone()
    next_model = insert_model(con, new, counts['moves'] + (kind == 'move'),
                              counts['games'] + (kind == 'result'), 'learning', 'Phase 9 ausstehend')
    details = dict(before=weights, after=new, prediction=prediction, target=target, error=error,
                   reward=reward, features=before.features, previous_model=model,
                   evaluation_after=(after or before).value(new),
                   seconds=time.perf_counter()-started)
    con.execute('INSERT INTO learning_events VALUES(?,?,?,?,?,?)',
                (game_id, ply, kind, next_model, json.dumps(details, allow_nan=False), stamp()))
    con.execute('UPDATE learning_state SET active=? WHERE slot=1', (next_model,))
    return next_model, new


def sync(con, restored, previous_revision=None):
    """Apply the validated suffix and terminal signal once, then return committed data."""
    session = restored.session
    if session.play_kind != 'adaptive_ai':
        return None
    game_id = restored.game_id
    if previous_revision is None:
        initialize(con)
    model, weights, recovered = active_model(con)
    if previous_revision is None:
        con.execute('INSERT INTO learning_games VALUES(?,?,?)',
                    (game_id, model, json.dumps(weights)))
        previous_revision = 0
    check_progress(con, game_id, previous_revision)
    if previous_revision < session.revision or session.result:
        board = session.board.copy(stack=True)
        moves = board.move_stack[previous_revision:]
        for _ in moves:
            board.pop()
        before = position(board)
        for ply, move in enumerate(moves, previous_revision + 1):
            board.push(move)
            after = position(board)
            model, weights = record_event(con, game_id, ply, 'move', model, weights, before, after)
            before = after
        if session.result and not con.execute(
            "SELECT 1 FROM learning_events WHERE game_id=? AND kind='result'", (game_id,)
        ).fetchone():
            if board.move_stack:
                board.pop()
            reward = {'1-0': 1, '0-1': -1, '1/2-1/2': 0}[session.result.score]
            model, weights = record_event(con, game_id, session.revision, 'result',
                                          model, weights, position(board), after=before, reward=reward)
            games = con.execute('SELECT games FROM learning_models WHERE id=?', (model,)).fetchone()[0]
            if games % 5 == 0:
                con.execute('INSERT INTO learning_candidates VALUES(?,?,?,0)',
                            (games, model, 'Kandidat, Prüfung und Freigabe ausstehend'))
    report = None
    if session.result:
        initial = con.execute('SELECT * FROM learning_games WHERE game_id=?', (game_id,)).fetchone()
        events = [dict(json.loads(row['details']), ply=row['ply'], kind=row['kind'],
                       model=row['model'], created=row['created']) for row in con.execute(
            "SELECT * FROM learning_events WHERE game_id=? ORDER BY ply, kind", (game_id,)
        )]
        report = dict(result=session.result.text, plies=session.revision,
                      initial=json.loads(initial['initial_weights']), initial_model=initial['initial_model'],
                      final=events[-1]['after'], model=events[-1]['model'], events=events)
    return LearningState(session.revision, model, weights, report, recovered, next_notice(con) is not None)


def next_notice(con):
    exists = con.execute("SELECT 1 FROM sqlite_master WHERE name='learning_candidates'").fetchone()
    if not exists:
        return None
    row = con.execute("""SELECT milestone,model FROM learning_candidates
        WHERE announced=0 ORDER BY milestone LIMIT 1""").fetchone()
    return tuple(row) if row else None


def acknowledge_notice(con, milestone):
    con.execute('UPDATE learning_candidates SET announced=1 WHERE milestone=?', (milestone,))
