"""One sequential worker, shared by the application and reproducible test probes."""
from evaluation import match, metrics
from evaluation.repository import worker_lock


def run(reviews, run_id, budget, cancel, pause, stopped_status, progress, *, repeat_of=None):
    with worker_lock(reviews.store):
        run_id, budget, contract = reviews.prepare(run_id, budget, repeat_of=repeat_of)
        try:
            saved = reviews.saved_games(run_id, budget)
            total = 2 * budget.count

            def boundary():
                if pause.is_set() or cancel.is_set():
                    raise match.Stopped

            for fixture in match.plan(budget):
                for role in ('candidate', 'reference'):
                    model, weights = contract[role]
                    if fixture.slot in saved[model]:
                        continue
                    boundary()
                    progress(run_id, model, fixture.opponent, total, saved)
                    game = match.play(fixture, budget, weights, cancel, boundary)
                    reviews.append(run_id, model, fixture, game)
                    saved[model][fixture.slot] = game
                    progress(run_id, model, fixture.opponent, total, saved)
            boundary()
            reviews.complete(run_id)
        except match.Stopped:
            reviews.stop(run_id, stopped_status())
        except Exception:
            reviews.stop(run_id, 'interrupted')
            raise
        return run_id


def progress_snapshot(run_id, model, opponent, total, saved):
    return dict(id=run_id, model=model, opponent=opponent, total=total,
                count=sum(len(rows) for rows in saved.values()),
                models={version:metrics.summary([dict(game,score=None) if game['reason']=='PLY_LIMIT' else game
                                                for game in rows.values()]) for version, rows in saved.items()})
