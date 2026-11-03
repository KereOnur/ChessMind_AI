"""Explicit retests create an independent run from a history entry."""
from dataclasses import replace
from threading import Event

import pytest

from evaluation import match, runner
from evaluation.repository import Reviews
from evaluation.statistics import dashboard
from learning.repository import read_model
from test_persistence_ui import until
from test_review import run, seed
from ui.main_window import MainWindow


@pytest.fixture
def prepared(tmp_path):
    repo = Reviews(tmp_path/'repeat.sqlite3')
    repo.store.initialize()
    model = seed(repo)
    old_id = run(repo,match.Budget(1,2))
    budget = replace(match.REVIEW,pairs_per_cell=1,max_plies=2,endgames=False)
    current_id = run(repo,budget)
    return repo,model,old_id,current_id,budget


def test_repeat_snapshot_provenance_and_preserved_history(prepared):
    repo,model,old_id,current_id,budget = prepared
    assert dashboard(repo.store.path)['candidate'] is None
    with repo.store.connection() as con:
        previous = [tuple(r) for r in con.execute('SELECT * FROM review_runs ORDER BY id')]
    new_id = runner.run(repo,None,budget,Event(),Event(),lambda:'interrupted',
                        lambda *_:None,repeat_of=old_id)
    assert len({old_id,current_id,new_id})==3
    data = dashboard(repo.store.path)
    assert data['runs'][0]['repeat_of']==old_id
    assert data['runs'][0]['protocol']==match.REVIEW_PROTOCOL
    with repo.store.connection() as con:
        assert [tuple(r) for r in con.execute('SELECT * FROM review_runs WHERE id<>? ORDER BY id',(new_id,))]==previous
        assert con.execute('SELECT count(*) FROM review_games').fetchone()[0]==24
        assert tuple(con.execute('SELECT active,stable FROM learning_state').fetchone())==(1,1)
        assert read_model(con,model)==(1.1,1,1,1,1)
        assert con.execute('SELECT count(*) FROM learning_events').fetchone()[0]==0
        assert not con.execute("SELECT 1 FROM review_decisions WHERE action='promoted'").fetchone()


def test_retest_respects_current_reference_and_pending_run(prepared):
    repo,model,old_id,current_id,budget = prepared
    new_id,_,_ = repo.prepare(None,budget,repeat_of=current_id)
    with pytest.raises(ValueError,match='vorhandenen Vergleich'):
        repo.prepare(None,budget,repeat_of=old_id)
    repo.stop(new_id,'aborted')
    with repo.store.connection() as con, repo.store.transaction(con):
        con.execute('UPDATE learning_state SET stable=?',(model,))
    with pytest.raises(ValueError,match='aktuellen Referenz'):
        repo.prepare(None,budget,repeat_of=old_id)


def test_history_button_can_repeat_when_standard_start_is_disabled(app,prepared):
    repo,_,old_id,_,budget = prepared
    window = MainWindow(storage_path=repo.store.path,startup_prompt=False,review_budget=budget)
    window.show()
    try:
        until(app,lambda:window.storage.ready)
        window.menu_page.menu_buttons['KI-Testzentrum'].click()
        center = window.review_center
        until(app,lambda:center.data is not None)
        assert not center.buttons['start'].isEnabled()
        index = next(i for i in range(center.history.count()) if center.history.itemData(i)['id']==old_id)
        center.history.setCurrentIndex(index)
        assert 'Altverfahren' in center.history.currentText()
        assert center.buttons['repeat'].isEnabled()
        center.buttons['repeat'].click()
        until(app,lambda:center.worker is None and center.history.count()==3)
        assert center.history.itemData(0)['repeat_of']==old_id
        assert 'Phase 9.6' in center.history.itemText(0)
        center.reject()
    finally:
        window.close()
        until(app,lambda:not window.storage.service.thread.isRunning())
