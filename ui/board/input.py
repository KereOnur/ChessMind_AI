"""Move-intent boundary for a future legal-move controller; no chess rules."""
from dataclasses import dataclass
from typing import Protocol
from ui.board.demo import PieceSpec, Square


@dataclass(frozen=True)
class MoveIntent:
    source: Square
    target: Square | None
    gesture: str


@dataclass(frozen=True)
class InputDecision:
    accepted: bool
    message: str


class MoveInput(Protocol):
    """A later rules adapter can consume intents independently of animations."""
    def request(self, intent: MoveIntent) -> InputDecision: ...


class DemoInput:
    """Only protect icon placement: any icon may move to any empty square.

    No piece-type rules, turn order, captures, check, or legal-move calculation.
    Mutates only the dictionary owned by this disposable preview.
    """
    def __init__(self, position: dict[Square, PieceSpec]):
        self.position = position

    def request(self, intent: MoveIntent) -> InputDecision:
        target=intent.target
        if target is None or any(not 0<=v<8 for v in target):
            return InputDecision(False,'Demo: Bitte ein Feld innerhalb des Bretts wählen.')
        if intent.source not in self.position or target==intent.source:
            return InputDecision(False,'Demo: Keine Testbewegung ausgeführt.')
        if target in self.position:
            return InputDecision(False,'Demo: Nur freie Felder sind als Testziel verfügbar.')
        self.position[target]=self.position.pop(intent.source)
        return InputDecision(True,'Demo-Bewegung – kein echter Schachzug.')
