"""Sequential TD training. Only complete games advance the durable learner."""
from dataclasses import dataclass
import json
from random import Random
from uuid import uuid4

from ai.adaptive import position
from database.store import GameStore
from evaluation import match, training_schema
from evaluation.repository import checked, no_running_game, validate_game, worker_lock
from game.checkpoint import canonical
from learning import repository as models
from learning.td import update, validate

OPPONENTS = ('amateur', 'grandmaster', 'adaptive')


@dataclass(frozen=True)
class TrainingBudget:
    per_cell: int = 100
    max_plies: int = 48
    seed: int = 950600

    def __post_init__(self):
        if not 1 <= self.per_cell <= 100 or not 1 <= self.max_plies <= 48:
            raise ValueError('Ungültiger Trainingsplan.')

    @property
    def count(self):
        return 6 * self.per_cell


PRODUCTION = TrainingBudget()


def plan(budget):
    rng = Random(budget.seed)
    return [match.Fixture(6*i + 2*j + k, opponent, white, match.OPENINGS[i % len(match.OPENINGS)],
                          rng.randrange(2**63))
            for i in range(budget.per_cell) for j,opponent in enumerate(OPPONENTS)
            for k,white in enumerate((True,False))]


def manifest(budget):
    return dict(protocol='training-td-v1', per_cell=budget.per_cell, plies=budget.max_plies,
                seed=budget.seed, search=match.PRODUCTION.manifest())


def step(weights, before, after):
    return update(weights,before,after)[0]


def train_game(fixture,budget,weights,reference,cancel,boundary):
    learned = weights

    def learn(current,before,after):
        nonlocal learned
        learned = step(current,before,after)
        return learned

    result = match.play(fixture,budget,weights,cancel,boundary,reference=reference,learn=learn)
    board = match.initial_board(fixture)
    for uci in result['moves'][:-1]:
        board.push_uci(uci)
    reward = {'1-0':1,'0-1':-1,'1/2-1/2':0}[result['score']]
    learned = update(learned,position(board),reward=reward)[0]
    return result,learned


class Training:
    def __init__(self,path):
        self.store = GameStore(path)

    def status(self, *, recover=False):
        if recover:
            with self.store.connection() as con:
                running = training_schema.exists(con) and con.execute(
                    "SELECT 1 FROM training_runs WHERE status='running'").fetchone()
            if running:
                try:
                    with worker_lock(self.store), self.store.connection() as con, self.store.transaction(con):
                        con.execute("UPDATE training_runs SET status='interrupted' WHERE status='running'")
                except ValueError:
                    pass
        with self.store.connection() as con:
            if not training_schema.exists(con):
                return None
            row = con.execute("""SELECT r.*, (SELECT count(*) FROM training_games WHERE run=r.id) AS count
                FROM training_runs r ORDER BY created DESC LIMIT 1""").fetchone()
            if not row:
                return None
            data = checked(row['manifest'],row['digest'])
            return dict(id=row['id'],status=row['status'], count=row['count'],
                        total=6*data['plan']['per_cell'], candidate=row['candidate'], reference=row['reference'])

    def run(self, run_id, budget, cancel, pause, stop_status, progress):
        with worker_lock(self.store):
            with self.store.connection() as con, self.store.transaction(con):
                no_running_game(con)
                models.initialize(con)
                training_schema.initialize(con)
                if run_id is None:
                    if con.execute("SELECT 1 FROM training_runs WHERE status IN ('running','paused','interrupted')").fetchone():
                        raise ValueError('Setze das vorhandene Training fort oder brich es ab.')
                    initial, reference = con.execute('SELECT active,stable FROM learning_state').fetchone()
                    data = canonical(dict(plan=manifest(budget), initial=models.read_model(con,initial),
                                          reference=models.read_model(con,reference)))
                    weights = canonical(models.read_model(con,initial))
                    run_id = str(uuid4())
                    con.execute('INSERT INTO training_runs VALUES(?,?,?,?,?,?,?,?,?,NULL)',
                                (run_id,models.stamp(),data,models.digest(data),initial,reference,
                                 weights,models.digest(weights),'running'))
                row = con.execute('SELECT * FROM training_runs WHERE id=?',(run_id,)).fetchone()
                if not row or row['status'] not in ('running','paused','interrupted'):
                    raise ValueError('Dieses Training kann nicht fortgesetzt werden.')
                data = checked(row['manifest'],row['digest'])
                settings = data['plan']
                budget = TrainingBudget(settings['per_cell'],settings['plies'],settings['seed'])
                if settings != json.loads(canonical(manifest(budget))):
                    raise ValueError('Das gespeicherte Trainingsprotokoll ist inkompatibel.')
                reference = validate(data['reference'])
                weights = validate(checked(row['weights'],row['weight_digest']))
                fixtures = plan(budget)
                saved = list(con.execute('SELECT * FROM training_games WHERE run=? ORDER BY slot',(run_id,)))
                expected = validate(data['initial'])
                for index, game in enumerate(saved):
                    payload = checked(game['result'],game['digest'])
                    if game['slot'] != index or index >= len(fixtures) or tuple(payload['before']) != expected:
                        raise ValueError('Der Trainingsverlauf ist unvollständig oder inkonsistent.')
                    validate_game(fixtures[index],budget,payload['game'])
                    expected = validate(payload['after'])
                if expected != weights:
                    raise ValueError('Trainingsgewichte stimmen nicht mit dem letzten Checkpoint überein.')
                con.execute("UPDATE training_runs SET status='running' WHERE id=?",(run_id,))

            def boundary():
                if cancel.is_set() or pause.is_set():
                    raise match.Stopped

            try:
                for fixture in fixtures[len(saved):]:
                    boundary()
                    progress(fixture.slot,budget.count,fixture.opponent)
                    result,new = train_game(fixture,budget,weights,reference,cancel,boundary)
                    boundary()
                    payload = canonical(dict(before=weights,after=new,game=result))
                    state = canonical(new)
                    with self.store.connection() as con, self.store.transaction(con):
                        con.execute('INSERT INTO training_games VALUES(?,?,?,?)',
                                    (run_id,fixture.slot,payload,models.digest(payload)))
                        con.execute('UPDATE training_runs SET weights=?,weight_digest=? WHERE id=?',
                                    (state,models.digest(state),run_id))
                    weights = new
                    progress(fixture.slot+1,budget.count,fixture.opponent)
                boundary()
                with self.store.connection() as con, self.store.transaction(con):
                    candidate = None
                    if budget == PRODUCTION:
                        moves,games = con.execute("""SELECT count(*) FILTER (WHERE kind='move'),
                            count(*) FILTER (WHERE kind='result') FROM learning_events""").fetchone()
                        candidate = models.insert_model(con,weights,moves,games,'training-candidate',
                                                        '600 Trainingspartien, Modellvergleich ausstehend')
                    con.execute("UPDATE training_runs SET status='complete',candidate=? WHERE id=?",
                                (candidate,run_id))
            except match.Stopped:
                self.stop(run_id,stop_status())
            except Exception:
                self.stop(run_id,'interrupted')
                raise

    def stop(self,run_id,status):
        with self.store.connection() as con, self.store.transaction(con):
            con.execute("""UPDATE training_runs SET status=? WHERE id=?
                AND status IN ('running','paused','interrupted')""",(status,run_id))
