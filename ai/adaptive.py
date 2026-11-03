"""Separate learned evaluator on the existing bounded classical search."""
from functools import partial
from ai.grandmaster import GrandmasterConfig, Searcher
from ai.grandmaster_evaluation import explain
from learning.td import INITIAL, SCALES, Position, validate

DEFAULT = GrandmasterConfig(soft_seconds=6, max_seconds=9)


def position(board):
    terms = explain(board)
    raw = (terms.activity + terms.mobility, terms.center, terms.king_safety,
           terms.pawn_structure, terms.endgame)
    features = tuple(max(-1.0, min(1.0, value / scale))
                     for value, scale in zip(raw, SCALES))
    return Position(terms.material, features)


def evaluate(board, weights):
    score = round(position(board).score(weights))
    return score if board.turn else -score


def search(board, remaining, *, weights=INITIAL, config=None, cancel=None):
    evaluator = partial(evaluate, weights=validate(weights))
    return Searcher(board, remaining, config or DEFAULT, cancel, evaluator=evaluator).run()
