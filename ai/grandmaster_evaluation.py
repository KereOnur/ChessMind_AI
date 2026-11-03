"""Fixed tapered evaluation, independent of the Amateur profile. No learning."""
from dataclasses import dataclass
from types import MappingProxyType
import chess

MG=MappingProxyType({1:100,2:320,3:335,4:500,5:950,6:0})
EG=MappingProxyType({1:120,2:310,3:340,4:525,5:930,6:0})
PHASE=MappingProxyType({1:0,2:1,3:1,4:2,5:4,6:0})
CENTER=(chess.D4,chess.E4,chess.D5,chess.E5)


@dataclass(frozen=True,slots=True)
class Evaluation:
    material:int
    activity:int
    center:int
    king_safety:int
    pawn_structure:int
    mobility:int
    endgame:int
    phase:int

    @property
    def total(self):return self.material+self.activity+self.center+self.king_safety+self.pawn_structure+self.mobility+self.endgame


def explain(board):
    phase=min(24,sum(PHASE[p.piece_type] for p in board.piece_map().values()))
    def taper(mg,eg):return (mg*phase+eg*(24-phase))//24
    material=activity=center=safety=pawns=mobility=endgame=0
    pawn_sets={color:list(board.pieces(chess.PAWN,color)) for color in (True,False)}
    for square,piece in board.piece_map().items():
        color=piece.color;sign=1 if color else -1;kind=piece.piece_type
        rank=chess.square_rank(square);file=chess.square_file(square);forward=rank if color else 7-rank
        central=7-int(abs(file-3.5)+abs(rank-3.5))
        material+=sign*taper(MG[kind],EG[kind])
        if kind in (chess.KNIGHT,chess.BISHOP):
            activity+=sign*taper(central*7+(14 if forward>0 else -14),central*5)
            if kind==chess.KNIGHT and file in (0,7):activity-=sign*20
        if kind in (chess.KNIGHT,chess.BISHOP,chess.ROOK,chess.QUEEN):
            count=(board.attacks_mask(square)&~board.occupied_co[color]).bit_count()
            mobility+=sign*taper(count*(4 if kind in (2,3) else 2),count*3)
            if board.is_attacked_by(not color,square) and not board.is_attacked_by(color,square):activity-=sign*(MG[kind]//8)
        if kind==chess.QUEEN and board.fullmove_number<8 and forward>2:activity-=sign*taper(16,0)
        if kind==chess.ROOK:
            own_file=any(chess.square_file(p)==file for p in pawn_sets[color])
            enemy_file=any(chess.square_file(p)==file for p in pawn_sets[not color])
            if not own_file:activity+=sign*taper(10 if enemy_file else 22,16 if enemy_file else 25)
            if forward==6:activity+=sign*taper(18,25)
        if kind==chess.PAWN:
            own=pawn_sets[color];enemy=pawn_sets[not color]
            if sum(chess.square_file(p)==file for p in own)>1:pawns-=sign*taper(12,18)
            if not any(abs(chess.square_file(p)-file)==1 for p in own):pawns-=sign*taper(14,12)
            if any(abs(chess.square_file(p)-file)==1 and abs(chess.square_rank(p)-rank)<=1 for p in own):pawns+=sign*taper(7,10)
            passed=not any(abs(chess.square_file(p)-file)<=1 and (chess.square_rank(p) if color else 7-chess.square_rank(p))>forward for p in enemy)
            if passed:
                pawns+=sign*taper(6+forward*forward,12+forward*forward*4)
                enemy_king=board.king(not color);own_king=board.king(color)
                if own_king is not None and enemy_king is not None:
                    next_square=chess.square(file,min(7,rank+1) if color else max(0,rank-1))
                    endgame+=sign*taper(0,4*(chess.square_distance(enemy_king,next_square)-chess.square_distance(own_king,next_square)))
            if square in CENTER:center+=sign*taper(28,8)
            if board.fullmove_number<8 and file in (0,5,6,7) and forward>1:activity-=sign*taper(12*(forward-1),0)
        if kind==chess.KING:
            endgame+=sign*taper(0,central*13)
            shield=0;ahead=rank+(1 if color else -1)
            if 0<=ahead<8:
                shield=sum(board.piece_at(chess.square(f,ahead))==chess.Piece(chess.PAWN,color) for f in range(max(0,file-1),min(7,file+1)+1))
            danger=sum(len(board.attackers(not color,s)) for s in board.attacks(square))
            castled=square in ((chess.G1,chess.C1) if color else (chess.G8,chess.C8))
            safety+=sign*taper(shield*12-danger*7-central*6+(25 if castled else 0),-danger*2)
    for square in CENTER:center+=taper(6,3)*(len(board.attackers(True,square))-len(board.attackers(False,square)))
    for color in (True,False):
        if len(board.pieces(chess.BISHOP,color))>=2:activity+=(1 if color else -1)*taper(25,38)
    return Evaluation(material,activity,center,safety,pawns,mobility,endgame,phase)


def evaluate(board):
    """Static value from the side to move; search owns terminal adjudication."""
    value=explain(board).total
    return max(-25000,min(25000,value if board.turn else -value))
