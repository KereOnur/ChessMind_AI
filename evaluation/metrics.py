"""Paired score summaries and a descriptive, stratified bootstrap interval."""
from collections import defaultdict
from random import Random
from statistics import mean


def points(game):
    if game['score'] == '1/2-1/2':
        return .5
    return float((game['score'] == '1-0') == game['fixture']['white'])


def summary(games):
    scores = [points(game) for game in games if game['score'] is not None]
    return dict(wins=scores.count(1), draws=scores.count(.5), losses=scores.count(0),
                points=sum(scores), rate=mean(scores) if scores else None,
                plies=mean(len(g['moves']) for g in games) if games else None,
                seconds=mean(g['seconds'] for g in games) if games else None,
                cpu=sum(g['cpu'] for g in games),
                limited=sum(g['reason']=='PLY_LIMIT' for g in games),
                technical=len(games)-len(scores), regular=len(scores), total=len(games))


def compare(candidate, reference):
    cells = defaultdict(list)
    for a, b in zip(candidate, reference, strict=True):
        if a['fixture'] != b['fixture']:
            raise ValueError('Die Paarbedingungen sind unterschiedlich.')
        fixture = a['fixture']
        cells[fixture['opponent'], fixture['white']].append(points(a)-points(b))
    a, b = summary(candidate), summary(reference)
    for row in (a,b):
        for key in ('technical','regular','total'):
            del row[key]
    difference = a['rate'] - b['rate']
    rng = Random(9049)
    distribution = sorted(sum(sum(rng.choices(cell, k=len(cell))) for cell in cells.values())
                          / len(candidate) for _ in range(2000))
    low, high = distribution[49], distribution[1949]
    return dict(candidate=a, reference=b, difference=difference, interval=[low, high],
                uncertain=low <= 0 <= high or abs(difference) < .02,
                decision='eligible' if difference > 0 else 'keep_reference')


def quality_compare(candidate, reference):
    """Use paired complete cases and bound the effect of all omitted outcomes."""
    cells = defaultdict(list)
    all_cells = set()
    pairs = 0
    lower = upper = 0.
    for a,b in zip(candidate,reference,strict=True):
        if a['fixture'] != b['fixture']:
            raise ValueError('Die Paarbedingungen sind unterschiedlich.')
        f = a['fixture']
        cell = f['opponent'],f['white']
        all_cells.add(cell)
        x,y = (points(game) if game['score'] is not None else None for game in (a,b))
        pairs += 1
        lower += (0 if x is None else x) - (1 if y is None else y)
        upper += (1 if x is None else x) - (0 if y is None else y)
        if x is not None and y is not None:
            cells[cell].append(x-y)
    used = sum(map(len,cells.values()))
    coverage = used/pairs
    difference = sum(map(sum,cells.values()))/used if used else None
    interval = None
    if used:
        rng = Random(9049)
        distribution = sorted(sum(sum(rng.choices(cell,k=len(cell))) for cell in cells.values())
                              / used for _ in range(2000))
        interval = [distribution[49],distribution[1949]]
    limited = coverage < .8 or used < 80 or any(len(cells[cell]) < 20 for cell in all_cells)
    bounds = [lower/pairs,upper/pairs]
    uncertain = (limited or interval is None or interval[0]<=0<=interval[1]
                 or abs(difference)<.02 or bounds[0]<=0<=bounds[1])
    return dict(candidate=summary(candidate),reference=summary(reference),difference=difference,
                interval=interval,uncertain=uncertain,quality_limited=limited,
                paired=used,planned_pairs=pairs,missing_bounds=bounds,
                decision='eligible' if not limited and difference>0 and bounds[0]>0 else 'keep_reference')
