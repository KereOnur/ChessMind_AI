"""Deterministic bounded negamax, alpha-beta, iterative deepening and quiescence.

No opening book, external engine, training or Amateur evaluation imports.
"""
from collections import OrderedDict
from dataclasses import dataclass
from threading import Event
import math,time
import chess
from ai.grandmaster_evaluation import evaluate,MG

GRANDMASTER_VERSION='grandmaster-v1'
MATE=100000
INF=1000000
MAX_PLY=32


@dataclass(frozen=True)
class GrandmasterConfig:
    soft_seconds:float=4.
    max_seconds:float=8.
    max_depth:int=5
    q_depth:int=4
    max_nodes:int=250000
    tt_entries:int=16384

    def __post_init__(self):
        if not(math.isfinite(self.soft_seconds) and math.isfinite(self.max_seconds) and 0<=self.soft_seconds<=self.max_seconds<=9.5):raise ValueError('Ungültiges Großmeister-Zeitbudget.')
        if not 1<=self.max_depth<=5 or not 0<=self.q_depth<=6 or self.max_nodes<1 or not 0<=self.tt_entries<=32768:raise ValueError('Ungültige Großmeister-Suchgrenze.')


@dataclass(frozen=True,slots=True)
class Entry:
    depth:int
    score:int
    bound:str
    move:chess.Move|None


@dataclass(frozen=True)
class SearchResult:
    move:chess.Move|None
    score:int
    depth:int
    nodes:int
    qnodes:int
    elapsed:float
    cpu_seconds:float
    budget:float
    tt_peak:int
    tt_hits:int
    cutoffs:int
    completed:tuple
    cancelled:bool=False
    stopped:bool=False


def time_budget(remaining,config):
    if not math.isfinite(remaining) or remaining<=0:return 0.,0.
    reserve=min(1.,max(.05,remaining*.06)) if remaining>=.1 else remaining*.5
    hard=min(config.max_seconds,remaining*(.12 if remaining<10 else .2),max(0.,remaining-reserve))
    soft=min(config.soft_seconds,hard*.65)
    return soft,hard


def position_key(board):
    return (board.pawns,board.knights,board.bishops,board.rooks,board.queens,board.kings,board.promoted,board.occupied_co[True],board.occupied_co[False],board.turn,board.clean_castling_rights(),board.ep_square)


def to_table(score,ply):return score+ply if score>MATE-1000 else (score-ply if score<-MATE+1000 else score)
def from_table(score,ply):return score-ply if score>MATE-1000 else (score+ply if score<-MATE+1000 else score)


class SearchStopped(Exception):pass


class Searcher:
    def __init__(self,board,remaining,config=None,cancel=None,*,evaluator=evaluate):
        self.config=config or GrandmasterConfig();self.cancel=cancel or Event();self.remaining=remaining;self.evaluate=evaluator
        self.board=board.copy(stack=True);self.started=time.monotonic();self.cpu_started=time.thread_time()
        self.soft,self.budget=time_budget(remaining,self.config);self.deadline=self.started+self.budget
        self.nodes=0;self.qnodes=0;self.cutoffs=0;self.tt_hits=0;self.tt_peak=0
        self.table=OrderedDict();self.killers={};self.history={};self.completed=[]
        # Exact reversible history prevents reuse across different draw contexts.
        # Irreversible moves reset it; the automatic 75-move rule bounds it.
        probe=board.copy(stack=True);reverse=[position_key(probe)]
        for _ in range(min(150,board.halfmove_clock,len(board.move_stack))):
            move=probe.pop()
            if probe.is_irreversible(move):break
            reverse.append(position_key(probe))
        self.reversible=list(reversed(reverse))

    def visit(self,quiescent=False):
        if self.cancel.is_set() or time.monotonic()>=self.deadline or self.nodes>=self.config.max_nodes:raise SearchStopped
        self.nodes+=1
        # Explicit GIL handoff also keeps PySide callbacks responsive when a
        # native event-loop/test wait would otherwise starve behind Python CPU.
        if self.nodes%256==0:
            if self.cancel.wait(.001) or time.monotonic()>=self.deadline:raise SearchStopped
        if quiescent:self.qnodes+=1

    def key(self):return (position_key(self.board),self.board.halfmove_clock,self.board.fullmove_number,tuple(self.reversible))

    def push(self,move):
        previous=self.reversible;irreversible=self.board.is_irreversible(move);self.board.push(move)
        key=position_key(self.board)
        self.reversible=[key] if irreversible else previous+[key]
        return previous

    def pop(self,previous):self.board.pop();self.reversible=previous

    def terminal(self,ply):
        outcome=self.board.outcome(claim_draw=False)
        if outcome is None:return None
        if outcome.winner is None:return 0
        return MATE-ply if outcome.winner==self.board.turn else -MATE+ply

    def store(self,key,entry):
        if not self.config.tt_entries:return
        old=self.table.get(key)
        if old and old.depth>entry.depth:return
        if key not in self.table and len(self.table)>=self.config.tt_entries:self.table.popitem(last=False)
        self.table[key]=entry;self.tt_peak=max(self.tt_peak,len(self.table))

    def ordered(self,moves,ply,preferred=None):
        board=self.board;killers=self.killers.get(ply,())
        def rating(move):
            if move==preferred:return 10000000
            victim=board.piece_type_at(move.to_square)
            value=0
            if board.is_capture(move):value=100000+16*(MG[victim] if victim else 100)-MG[board.piece_type_at(move.from_square)]
            if move.promotion:value+=90000+MG[move.promotion]
            if value:return value
            if move in killers:return 80000-killers.index(move)
            return self.history.get((board.turn,move.from_square,move.to_square),0)
        return sorted(moves,key=lambda move:(-rating(move),move.uci()))

    def quiescence(self,alpha,beta,remaining,ply):
        self.visit(True);terminal=self.terminal(ply)
        if terminal is not None:return terminal
        check=self.board.is_check()
        if remaining<=0 or ply>=MAX_PLY:
            if not check:return self.evaluate(self.board)
            # Never stand pat in check: evaluate at least one legal evasion layer.
            best=-INF
            for move in self.ordered(list(self.board.legal_moves),ply):
                self.visit(True);old=self.push(move)
                try:
                    terminal=self.terminal(ply+1)
                    value=-(terminal if terminal is not None else self.evaluate(self.board))
                finally:self.pop(old)
                best=max(best,value)
                if best>=beta:self.cutoffs+=1;break
            return best
        if not check:
            stand=self.evaluate(self.board)
            if stand>=beta:self.cutoffs+=1;return stand
            alpha=max(alpha,stand)
            moves=[m for m in self.board.legal_moves if self.board.is_capture(m) or m.promotion]
        else:moves=list(self.board.legal_moves)
        for move in self.ordered(moves,ply):
            old=self.push(move)
            try:value=-self.quiescence(-beta,-alpha,remaining-1,ply+1)
            finally:self.pop(old)
            if value>=beta:self.cutoffs+=1;return value
            alpha=max(alpha,value)
        return alpha

    def negamax(self,depth,alpha,beta,ply=0):
        self.visit();terminal=self.terminal(ply)
        if terminal is not None:return terminal
        if depth<=0:return self.quiescence(alpha,beta,self.config.q_depth,ply)
        original_alpha=alpha;key=self.key();entry=self.table.get(key);preferred=None
        if entry:
            self.tt_hits+=1;preferred=entry.move
            if entry.depth>=depth:
                value=from_table(entry.score,ply)
                if entry.bound=='exact':return value
                if entry.bound=='lower' and value>=beta:return value
                if entry.bound=='upper' and value<=alpha:return value
        best=-INF;best_move=None
        for move in self.ordered(list(self.board.legal_moves),ply,preferred):
            quiet=not self.board.is_capture(move) and not move.promotion
            old=self.push(move)
            try:value=-self.negamax(depth-1,-beta,-alpha,ply+1)
            finally:self.pop(old)
            if value>best:best=value;best_move=move
            alpha=max(alpha,value)
            if alpha>=beta:
                self.cutoffs+=1
                if quiet:
                    killers=list(self.killers.get(ply,()))
                    if move not in killers:killers.insert(0,move)
                    self.killers[ply]=tuple(killers[:2])
                    h=(self.board.turn,move.from_square,move.to_square);self.history[h]=min(8000,self.history.get(h,0)+depth*depth)
                break
        bound='upper' if best<=original_alpha else ('lower' if best>=beta else 'exact')
        self.store(key,Entry(depth,to_table(best,ply),bound,best_move));return best

    def root(self,depth,preferred):
        self.visit();alpha=-INF;best=-INF;best_move=None
        for move in self.ordered(list(self.board.legal_moves),0,preferred):
            old=self.push(move)
            try:value=-self.negamax(depth-1,-INF,-alpha,1)
            finally:self.pop(old)
            if value>best:best=value;best_move=move
            alpha=max(alpha,value)
        self.store(self.key(),Entry(depth,to_table(best,0),'exact',best_move))
        return best_move,best

    def run(self):
        legal=list(self.board.legal_moves);terminal=self.terminal(0)
        move=self.ordered(legal,0)[0] if legal and terminal is None and self.remaining>0 else None
        score=terminal or 0;depth=0;stopped=False
        if move is not None:
            for current in range(1,self.config.max_depth+1):
                try:candidate,value=self.root(current,move)
                except SearchStopped:stopped=True;break
                move=candidate;score=value;depth=current
                self.completed.append((current,move.uci(),score,self.nodes,time.monotonic()-self.started))
                if abs(score)>=MATE-MAX_PLY:break
                if current>=3 and time.monotonic()-self.started>=self.soft:break
        cancelled=self.cancel.is_set()
        return SearchResult(None if cancelled else move,score,depth,self.nodes,self.qnodes,time.monotonic()-self.started,time.thread_time()-self.cpu_started,self.budget,self.tt_peak,self.tt_hits,self.cutoffs,tuple(self.completed),cancelled,stopped)


def search(board,remaining,*,config=None,cancel=None,seed=None):
    # seed accepted only for compatibility with the job interface; no randomness.
    return Searcher(board,remaining,config,cancel).run()
