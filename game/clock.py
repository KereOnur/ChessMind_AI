"""Monotonic Fischer clock, independent of Qt, frames, and animations."""
import math
import time
from collections.abc import Callable


class ChessClock:
    def __init__(self, initial_seconds=900.0, increment_seconds=10.0, now: Callable[[], float]=time.monotonic):
        if initial_seconds<0 or increment_seconds<0: raise ValueError('Negative Zeitvorgabe')
        self.initial_seconds=float(initial_seconds)
        self.remaining={True:float(initial_seconds),False:float(initial_seconds)}
        self.increment=float(increment_seconds);self.now=now
        self.active=None;self.paused_color=None;self.expired_color=None
        self.anchor=None;self.started=False;self.finished=False;self.completed_moves=0

    def start(self,color=True):
        if self.started: raise RuntimeError('Die Uhr wurde bereits gestartet.')
        self.started=True;self.active=color;self.anchor=self.now()

    def settle(self,at=None):
        at=self.now() if at is None else at
        if self.active is not None:
            at=max(at,self.anchor)
            self.remaining[self.active]=max(0.,self.remaining[self.active]-(at-self.anchor))
            self.anchor=at
            if self.remaining[self.active]<=0:
                self.expired_color=self.active;self.active=None;self.finished=True
        return self.expired_color

    def complete_move(self,mover,token,at=None):
        """A unique increasing move token protects against duplicate increments."""
        at=self.now() if at is None else at
        if self.settle(at) is not None or self.finished:return False
        if self.active!=mover or token!=self.completed_moves+1:return False
        self.remaining[mover]+=self.increment
        self.completed_moves=token;self.active=not mover;self.anchor=at
        return True

    def pause_for_adjudication(self):
        if self.settle() is not None or self.finished:return False
        self.paused_color=self.active;self.active=None
        return True

    def resume(self):
        if self.finished or self.paused_color is None:return False
        self.active=self.paused_color;self.paused_color=None;self.anchor=self.now()
        return True

    def add_time(self,color,seconds):
        if seconds<0:raise ValueError('Negative Zeitgutschrift')
        if self.finished:return False
        self.remaining[color]+=seconds
        return True

    def stop(self):
        self.settle();self.active=None;self.paused_color=None;self.finished=True

    def display(self,color):
        # Presentation does not advance the clock; the session settles it first.
        seconds=max(0,math.ceil(self.remaining[color]-1e-9))
        return f'{seconds//60:02d}:{seconds%60:02d}'
