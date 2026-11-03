"""Immutable records produced only by the authoritative game session."""
from dataclasses import dataclass
import chess


@dataclass(frozen=True)
class MoveRecord:
    revision:int
    number:int
    color:bool
    move:chess.Move
    san:str
    captured:chess.Piece|None
    rook_shift:tuple[int,int]|None=None


@dataclass(frozen=True)
class GameEvent:
    kind:str
    message:str
    revision:int


@dataclass(frozen=True)
class Attempt:
    accepted:bool
    message:str
    record:MoveRecord|None=None
    promotion_choices:tuple[int,...]=()


@dataclass(frozen=True)
class ClaimDecision:
    submitted:bool
    drawn:bool
    message:str
    penalty_seconds:int=0
    forced_move:MoveRecord|None=None
