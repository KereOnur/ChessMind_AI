"""Headless, bounded matches with an identical plan for both frozen versions."""
from dataclasses import asdict, dataclass
from random import Random
import time

import chess

from ai import adaptive, amateur, grandmaster

PROTOCOL = 'paired-short-v1'
REVIEW_PROTOCOL = 'paired-quality-v2'
OPENINGS = (
    (), ('e2e4','e7e5'), ('d2d4','d7d5'), ('c2c4','e7e5'),
    ('g1f3','d7d5'), ('e2e4','c7c5'), ('e2e4','e7e6'), ('d2d4','g8f6'),
    ('e2e4','c7c6'), ('b2b3','e7e5'),
)
AMATEUR = amateur.AmateurConfig(target_seconds=0, max_search_seconds=.35, max_nodes=72)
CLASSICAL = grandmaster.GrandmasterConfig(
    soft_seconds=.2, max_seconds=.35, max_depth=1, q_depth=0, max_nodes=72, tt_entries=64,
)

DEEPER = grandmaster.GrandmasterConfig(
    soft_seconds=.2, max_seconds=.35, max_depth=2, q_depth=0, max_nodes=128, tt_entries=96,
)
DEEPER_AMATEUR = amateur.AmateurConfig(target_seconds=0, max_search_seconds=.35, max_nodes=128)
ENDGAMES = (
    '8/8/4k3/8/3K4/8/R7/8 w - - 0 1',
    '8/8/5k2/8/3K4/8/Q7/8 w - - 0 1',
    '8/3k4/8/4P3/4K3/8/8/8 w - - 0 1',
    '8/4k3/4p3/8/4P3/4K3/8/8 w - - 0 1',
    '8/3k4/8/8/3K4/8/R6r/8 w - - 0 1',
    '8/8/4k3/8/3K4/2B5/6B1/8 w - - 0 1',
    '8/2k5/8/5P2/5K2/8/8/8 w - - 0 1',
    '8/4k3/8/8/4K3/8/R5P1/8 w - - 0 1',
)
SEARCH_LIMIT = .35
CPU_LIMIT = 8


@dataclass(frozen=True)
class Budget:
    pairs_per_cell: int = 50
    max_plies: int = 48
    seed: int = 80709
    protocol: str = PROTOCOL
    deeper: bool = False
    endgames: bool = False

    def __post_init__(self):
        limit = 48 if self.protocol == PROTOCOL else 120
        if (self.protocol not in (PROTOCOL, REVIEW_PROTOCOL) or
            not 1 <= self.pairs_per_cell <= 50 or not 1 <= self.max_plies <= limit or
            (self.protocol == PROTOCOL and (self.deeper or self.endgames))):
            raise ValueError('Ungültige Grenzen für den Testplan.')

    @property
    def count(self):
        return 4 * self.pairs_per_cell

    def manifest(self):
        settings = asdict(self)
        if self.protocol == PROTOCOL:
            settings = {key:settings[key] for key in ('pairs_per_cell','max_plies','seed')}
        data = dict(protocol=self.protocol, budget=settings,
                    amateur=asdict(DEEPER_AMATEUR if self.deeper else AMATEUR),
                    classical=asdict(DEEPER if self.deeper else CLASSICAL), openings=OPENINGS,
                    opponents=[amateur.AMATEUR_VERSION, grandmaster.GRANDMASTER_VERSION],
                    adaptive='adaptive-v1', chess=chess.__version__)
        if self.protocol == REVIEW_PROTOCOL:
            data.update(endgame_positions=ENDGAMES if self.endgames else (),
                        cpu_limit=CPU_LIMIT, search_limit=SEARCH_LIMIT,
                        claims='current-position', plan='alternating-mirror-v1')
        return data


PRODUCTION = Budget()  # Frozen legacy protocol, also used by Phase 9.5 training.
REVIEW = Budget(max_plies=96, protocol=REVIEW_PROTOCOL, deeper=True, endgames=True)


@dataclass(frozen=True)
class Fixture:
    slot: int
    opponent: str
    white: bool
    opening: tuple
    seed: int


@dataclass(frozen=True)
class EndgameFixture(Fixture):
    fen: str


def plan(budget):
    rng = Random(budget.seed)
    fixtures = []
    for index in range(budget.pairs_per_cell):
        for opponent in ('amateur', 'grandmaster'):
            for white in (True, False):
                seed = rng.randrange(2**63)
                cycle = index % 10
                if budget.endgames and cycle < len(ENDGAMES):
                    board = chess.Board(ENDGAMES[cycle])
                    if index // 10 % 2:
                        board = board.mirror()
                    fixtures.append(EndgameFixture(len(fixtures),opponent,white,(),seed,board.fen()))
                else:
                    fixtures.append(Fixture(len(fixtures),opponent,white,
                                            OPENINGS[index % len(OPENINGS)],seed))
    return fixtures


class Stopped(Exception):
    """Discard the current unfinished game, retaining all committed games."""


def initial_board(fixture):
    board = chess.Board(fixture.fen) if isinstance(fixture, EndgameFixture) else chess.Board()
    for move in fixture.opening:
        board.push_uci(move)
    return board


def ending(board, plies, limit, *, technical=False):
    outcome = board.outcome(claim_draw=False)
    if outcome:
        return outcome.result(), outcome.termination.name
    if board.is_fifty_moves() or board.is_repetition(3):
        return '1/2-1/2', 'CLAIM'
    if plies >= limit:
        return (None if technical else '1/2-1/2'), 'PLY_LIMIT'
    return None


def play(fixture, budget, weights, cancel, boundary=lambda: None, *, reference=None, learn=None):
    board = initial_board(fixture)
    fen = board.fen(en_passant='fen')
    rng = Random(fixture.seed)
    moves = []
    wall = time.monotonic()
    cpu = time.thread_time()
    technical = getattr(budget,'protocol',PROTOCOL) == REVIEW_PROTOCOL
    deeper = getattr(budget,'deeper',False)
    classical = DEEPER if deeper else CLASSICAL
    amateur_config = DEEPER_AMATEUR if deeper else AMATEUR

    def finish(score, reason, **evidence):
        return dict(fixture=asdict(fixture),fen=fen,moves=moves,score=score,reason=reason,
                    seconds=time.monotonic()-wall,cpu=time.thread_time()-cpu,
                    status='technical' if score is None else 'complete',**evidence)

    while True:
        boundary()
        if cancel.is_set():
            raise Stopped
        outcome = ending(board, len(moves), budget.max_plies, technical=technical)
        if outcome:
            return finish(*outcome)
        if time.thread_time()-cpu > CPU_LIMIT:
            if technical:
                return finish(None,'CPU_LIMIT')
            raise RuntimeError('Rechenzeitgrenze der Partie überschritten. Der Vergleich bleibt unvollständig.')
        seed = rng.randrange(2**63)
        if board.turn == fixture.white:
            result = adaptive.search(board, 900, weights=weights, config=classical, cancel=cancel)
        elif fixture.opponent == 'adaptive' and reference is not None:
            result = adaptive.search(board, 900, weights=reference, config=classical, cancel=cancel)
        elif fixture.opponent == 'amateur':
            result = amateur.search(board, 900, seed=seed, config=amateur_config, cancel=cancel)
        else:
            result = grandmaster.search(board, 900, config=classical, cancel=cancel)
        if cancel.is_set():
            raise Stopped
        if result.elapsed >= SEARCH_LIMIT:
            if technical:
                return finish(None,'SEARCH_LIMIT',search_seconds=result.elapsed)
            raise RuntimeError('Suchzeit-Wächter ausgelöst. Der Vergleich bleibt unvollständig.')
        if result.move not in board.legal_moves:
            raise RuntimeError('Die Suche lieferte keinen legalen Zug.')
        moves.append(result.move.uci())
        before = adaptive.position(board) if learn else None
        board.push(result.move)
        if learn:
            weights = learn(weights, before, adaptive.position(board))
        if cancel.wait(.001):
            raise Stopped
