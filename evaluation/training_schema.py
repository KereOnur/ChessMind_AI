"""Additive schema for isolated training checkpoints."""
SCHEMA = {
    'training_schema': 'CREATE TABLE training_schema (version INTEGER PRIMARY KEY CHECK(version=1))',
    'training_runs': """CREATE TABLE training_runs (
        id TEXT PRIMARY KEY, created TEXT NOT NULL, manifest TEXT NOT NULL, digest TEXT NOT NULL,
        initial INTEGER NOT NULL REFERENCES learning_models(id),
        reference INTEGER NOT NULL REFERENCES learning_models(id),
        weights TEXT NOT NULL, weight_digest TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('running','paused','aborted','interrupted','complete')),
        candidate INTEGER UNIQUE REFERENCES learning_models(id))""",
    'training_games': """CREATE TABLE training_games (
        run TEXT NOT NULL REFERENCES training_runs(id), slot INTEGER NOT NULL,
        result TEXT NOT NULL, digest TEXT NOT NULL, PRIMARY KEY(run,slot))""",
}


def exists(con):
    return con.execute("SELECT 1 FROM sqlite_master WHERE name='training_schema'").fetchone() is not None


def validate(con):
    if [tuple(row) for row in con.execute('SELECT version FROM training_schema')] != [(1,)]:
        raise ValueError('Unbekannte Trainingsschemaversion.')


def initialize(con):
    if not exists(con):
        for statement in SCHEMA.values():
            con.execute(statement)
        con.execute('INSERT INTO training_schema VALUES(1)')
    validate(con)
