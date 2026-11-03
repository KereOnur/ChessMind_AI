"""Additive evaluation schema. Existing game and learning formats stay readable."""
SCHEMA = {
    'review_schema': """CREATE TABLE review_schema (
        slot INTEGER PRIMARY KEY CHECK(slot=1), version INTEGER NOT NULL CHECK(version=1))""",
    'review_runs': """CREATE TABLE review_runs (
        id TEXT PRIMARY KEY, created TEXT NOT NULL, updated TEXT NOT NULL,
        candidate INTEGER NOT NULL REFERENCES learning_models(id),
        reference INTEGER NOT NULL REFERENCES learning_models(id),
        config TEXT NOT NULL, digest TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('running','paused','interrupted','aborted','complete')),
        report TEXT, report_digest TEXT)""",
    'review_games': """CREATE TABLE review_games (
        run TEXT NOT NULL REFERENCES review_runs(id), version INTEGER NOT NULL REFERENCES learning_models(id),
        slot INTEGER NOT NULL, result TEXT NOT NULL, digest TEXT NOT NULL,
        PRIMARY KEY(run, version, slot))""",
    'review_decisions': """CREATE TABLE review_decisions (
        id INTEGER PRIMARY KEY, run TEXT REFERENCES review_runs(id), created TEXT NOT NULL,
        previous INTEGER NOT NULL REFERENCES learning_models(id),
        selected INTEGER NOT NULL REFERENCES learning_models(id), action TEXT NOT NULL)""",
}


def exists(con):
    return con.execute("SELECT 1 FROM sqlite_master WHERE name='review_schema'").fetchone() is not None


def initialize(con):
    if not exists(con):
        for statement in SCHEMA.values():
            con.execute(statement)
        con.execute('INSERT INTO review_schema VALUES(1,1)')
    validate(con)


def validate(con):
    if not exists(con) or [tuple(row) for row in con.execute('SELECT * FROM review_schema')] != [(1, 1)]:
        raise ValueError('Unbekannte Version der Testdatenbank.')
