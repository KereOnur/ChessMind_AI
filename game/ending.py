"""python-chess adjudication. No second move or mating-search engine."""
from dataclasses import dataclass
import chess


@dataclass(frozen=True)
class GameResult:
    reason:str
    winner:bool|None

    @property
    def score(self):return '1/2-1/2' if self.winner is None else ('1-0' if self.winner else '0-1')

    @property
    def text(self):
        winner='Remis' if self.winner is None else ('Weiß gewinnt' if self.winner else 'Schwarz gewinnt')
        return f'{self.score} · {winner} · {self.reason}'


REASONS={
    chess.Termination.CHECKMATE:'Schachmatt',
    chess.Termination.STALEMATE:'Patt',
    chess.Termination.INSUFFICIENT_MATERIAL:'Keine Mattsetzung möglich (Materialprüfung)',
    chess.Termination.SEVENTYFIVE_MOVES:'75-Züge-Regel',
    chess.Termination.FIVEFOLD_REPETITION:'Fünffache Stellungswiederholung',
}


def automatic_result(board):
    # The library tests checkmate BEFORE the automatic 75-move rule.
    outcome=board.outcome(claim_draw=False)
    return GameResult(REASONS.get(outcome.termination,outcome.termination.name),outcome.winner) if outcome else None


def loss_or_material_draw(board,loser,reason):
    """FIDE 6.9 / 5.1.2: the prospective winner must be able to mate.

    Uses python-chess's certified material test, NOT 'can force mate'. Its
    documented limitation is that positional fortresses/forced dead lines are
    not all detected. This project does not add an unreliable mating engine.
    """
    winner=not loser
    if board.has_insufficient_material(winner):
        return GameResult(reason+' · Gegner hat kein mattsetzendes Material',None)
    return GameResult(reason,winner)
