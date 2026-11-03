"""Bounded one/two-ply minimax and controlled variation for a beginner opponent."""
from dataclasses import dataclass
import math,random,time
from threading import Event
import chess
from ai.evaluation import evaluate,MATE,VALUES

AMATEUR_VERSION='amateur-v1'


@dataclass(frozen=True)
class AmateurConfig:
    target_seconds:float=1.2
    max_search_seconds:float=2.4
    max_nodes:int=6000
    weak_probability:float=.22
    normal_band:int=35
    weak_band:int=130
    temperature:float=18.

    def __post_init__(self):
        if not (math.isfinite(self.target_seconds) and math.isfinite(self.max_search_seconds) and 0<=self.target_seconds<=self.max_search_seconds<=2.8):raise ValueError('Ungültige Amateur-Denkzeit.')
        if not 0<=self.weak_probability<=1 or not 0<=self.normal_band<=self.weak_band<1000 or self.temperature<=0 or self.max_nodes<1:raise ValueError('Ungültige Amateur-Variation.')


@dataclass(frozen=True)
class Candidate:
    move:chess.Move
    score:int


@dataclass(frozen=True)
class SearchResult:
    move:chess.Move|None
    candidates:tuple[Candidate,...]
    depth:int
    nodes:int
    elapsed:float
    budget:float
    varied_weaker:bool=False
    cancelled:bool=False


def time_budget(remaining,config):
    if not math.isfinite(remaining) or remaining<=0:return 0.,0.
    maximum=min(config.max_search_seconds,remaining*.25)
    target=min(config.target_seconds,maximum*.8)
    if remaining<5:target=min(target,remaining*.03)
    if remaining<2:target=0.
    return target,maximum


def choose_candidate(candidates,rng,config):
    """Never deliberately vary out of a proven mate or into a proven mate loss."""
    if not candidates:return None,False
    best=max(c.score for c in candidates)
    if best>=MATE:return rng.choice([c for c in candidates if c.score==best]),False
    safe=[c for c in candidates if c.score>-MATE] or list(candidates)
    best=max(c.score for c in safe)
    weaker=[c for c in safe if config.normal_band<best-c.score<=config.weak_band]
    weaken=bool(weaker) and rng.random()<config.weak_probability
    pool=weaker if weaken else [c for c in safe if best-c.score<=config.normal_band]
    weights=[math.exp(-(best-c.score)/config.temperature) for c in pool]
    return rng.choices(pool,weights=weights,k=1)[0],weaken


def search(board,remaining,*,seed=None,config=None,cancel=None):
    """Own board copy only. Depth never exceeds two plies; no alpha-beta/engine."""
    config=config or AmateurConfig();cancel=cancel or Event();rng=random.Random(seed)
    started=time.monotonic();target,budget=time_budget(remaining,config);deadline=started+budget
    board=board.copy(stack=True);nodes=0;depth=0;weaker=False
    def stopped():return cancel.is_set() or time.monotonic()>=deadline or nodes>=config.max_nodes
    legal=list(board.legal_moves)
    if board.outcome(claim_draw=False) is not None or not legal or remaining<=0:
        return SearchResult(None,(),0,0,time.monotonic()-started,budget,cancelled=cancel.is_set())
    rng.shuffle(legal)
    # Deterministic tactical ordering after the seeded tie shuffle; useful when
    # a very short deadline permits only a legal fallback and a few evaluations.
    def priority(move):
        captured=board.piece_at(move.to_square)
        return (VALUES.get(move.promotion,0)+(VALUES[captured.piece_type] if captured else (100 if board.is_en_passant(move) else 0)))
    legal.sort(key=priority,reverse=True)
    fallback=legal[0];one=[]
    perspective=board.turn
    for move in legal:
        if stopped():break
        board.push(move)
        try:score=evaluate(board,perspective);nodes+=1
        finally:board.pop()
        one.append(Candidate(move,score))
    candidates=one or [Candidate(fallback,0)]
    if len(one)==len(legal):
        depth=1;two=[]
        for candidate in one:
            if stopped():break
            move=candidate.move;board.push(move)
            try:
                outcome=board.outcome(claim_draw=False)
                if outcome:worst=candidate.score
                else:
                    worst=MATE+1;complete=True
                    replies=list(board.legal_moves);rng.shuffle(replies)
                    for reply in replies:
                        if stopped():complete=False;break
                        board.push(reply)
                        try:value=evaluate(board,perspective);nodes+=1
                        finally:board.pop()
                        worst=min(worst,value)
                        # A mating reply already proves the worst possible score.
                        if worst<=-MATE:break
                    if not complete:break
                two.append(Candidate(move,worst))
            finally:board.pop()
        # Do not mix shallow and deeper values or favor the first searched root.
        if len(two)==len(legal):candidates=two;depth=2
        else:
            unsafe={c.move for c in two if c.score<=-MATE}
            filtered=[c for c in candidates if c.move not in unsafe]
            if filtered:candidates=filtered
    choice,weaker=choose_candidate(candidates,rng,config)
    # Event.wait consumes no busy-loop CPU and wakes immediately on cancellation.
    delay=max(0.,min(started+target,deadline)-time.monotonic())
    if delay:cancel.wait(delay)
    cancelled=cancel.is_set()
    return SearchResult(None if cancelled else choice.move,tuple(candidates),depth,nodes,time.monotonic()-started,budget,weaker,cancelled)
