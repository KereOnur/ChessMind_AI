"""Presentation-only fixtures. This module does NOT represent a regular game."""
from dataclasses import dataclass

Square = tuple[int, int]  # file and rank, both 0..7; a1 == (0,0)


@dataclass(frozen=True)
class PieceSpec:
    color: str
    kind: str


def initial_preview() -> dict[Square, PieceSpec]:
    """Describe the 32 starting icons without invoking move/rule logic."""
    back = ('rook','knight','bishop','queen','king','bishop','knight','rook')
    result = {}
    for color, rank, pawns in (('white',0,1),('black',7,6)):
        for file,kind in enumerate(back):
            result[file,rank] = PieceSpec(color,kind)
            result[file,pawns] = PieceSpec(color,'pawn')
    return result


# Deliberately separate from initial_preview: illustrative widgets, not history.
DEMO_ROWS = ((1,'C2 → C5','G7 → G4'),(2,'B1 → B4','B8 → E5'))
CAPTURED_BY = {
    'white': (PieceSpec('black','pawn'),PieceSpec('black','knight')),
    'black': (PieceSpec('white','pawn'),),
}


def square_name(square: Square) -> str:
    return chr(65+square[0])+str(square[1]+1)
