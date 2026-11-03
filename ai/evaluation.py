"""Small fixed amateur evaluation in centipawn units, always from White's side.

No training, external engine, opening book, or shared future-AI parameters.
"""
from dataclasses import dataclass
from types import MappingProxyType
import chess

VALUES=MappingProxyType({chess.PAWN:100,chess.KNIGHT:310,chess.BISHOP:325,chess.ROOK:500,chess.QUEEN:900,chess.KING:0})
CENTER=(chess.D4,chess.E4,chess.D5,chess.E5)
MATE=100_000


@dataclass(frozen=True)
class Evaluation:
    material:int
    activity:int
    center:int
    king_safety:int
    loose_pieces:int

    @property
    def total(self):return self.material+self.activity+self.center+self.king_safety+self.loose_pieces


def explain(board):
    material=activity=center=kings=loose=0
    queens=bool(board.queens)
    for square,piece in board.piece_map().items():
        sign=1 if piece.color else -1;kind=piece.piece_type
        material+=sign*VALUES[kind]
        file=chess.square_file(square);rank=chess.square_rank(square)
        forward=rank if piece.color else 7-rank
        central=7-int(abs(file-3.5)+abs(rank-3.5))
        if kind in (chess.KNIGHT,chess.BISHOP):
            activity+=sign*(central*5+(12 if forward>0 else -8))
            if kind==chess.KNIGHT and file in (0,7):activity-=sign*18
        elif kind==chess.PAWN:
            activity+=sign*(max(0,forward-1)*5+central*2)
            if square in CENTER:activity+=sign*35
            if board.fullmove_number<8 and file in (0,5,6,7) and forward>1:activity-=sign*18*(forward-1)
        elif kind==chess.QUEEN and forward>2 and board.fullmove_number<8:activity-=sign*12
        if kind!=chess.KING and board.is_attacked_by(not piece.color,square) and not board.is_attacked_by(piece.color,square):
            loose-=sign*int(VALUES[kind]*(.06 if kind==chess.PAWN else .18))
    for square in CENTER:
        center+=6*(len(board.attackers(True,square))-len(board.attackers(False,square)))
    for color in (True,False):
        king=board.king(color)
        if king is None:continue
        sign=1 if color else -1;rank=chess.square_rank(king);file=chess.square_file(king)
        if queens:
            ahead=rank+(1 if color else -1)
            for f in range(max(0,file-1),min(7,file+1)+1):
                if 0<=ahead<8 and board.piece_at(chess.square(f,ahead))==chess.Piece(chess.PAWN,color):kings+=sign*9
            if king in ((chess.G1,chess.C1) if color else (chess.G8,chess.C8)):kings+=sign*18
            for square in board.attacks(king):kings-=sign*4*len(board.attackers(not color,square))
        if board.is_attacked_by(not color,king):kings-=sign*35
    return Evaluation(material,activity,center,kings,loose)


def evaluate(board,perspective):
    outcome=board.outcome(claim_draw=False)
    if outcome:return 0 if outcome.winner is None else (MATE if outcome.winner==perspective else -MATE)
    score=explain(board).total
    return score if perspective else -score
