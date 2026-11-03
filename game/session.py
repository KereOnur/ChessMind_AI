"""The only authority for legal moves, touch-move, clocks and game events."""
import time
import chess
from game.clock import ChessClock
from game.ending import GameResult, automatic_result, loss_or_material_draw
from game.events import Attempt, ClaimDecision, GameEvent, MoveRecord

RAPID_CLAIM_PENALTY=60  # User resolved the 120s/rapid conflict in favor of FIDE A.3.
AI_KINDS=('amateur_ai','grandmaster_ai','adaptive_ai')
PROMOTIONS=(chess.QUEEN,chess.ROOK,chess.BISHOP,chess.KNIGHT)


class GameSession:
    def __init__(self,board=None,*,now=time.monotonic,initial_seconds=900,increment_seconds=10,start_clock=True,play_kind="rule_test",human_color=None):
        if play_kind not in ('rule_test',*AI_KINDS) or (play_kind in AI_KINDS and type(human_color)!=bool):raise ValueError('Ungültiger Spieltyp oder Spielerfarbe.')
        self.play_kind=play_kind;self.human_color=human_color;self.resigned_color=None
        self.board=(board if board is not None else chess.Board()).copy(stack=True)
        if not self.board.is_valid():raise ValueError('Ungültige Teststellung')
        self.clock=ChessClock(initial_seconds,increment_seconds,now)
        self.revision=0;self.records=[];self.events=[]
        self.captured_by={chess.WHITE:[],chess.BLACK:[]}
        self.bound_source=None;self.bound_castle=None;self.draw_claim_barred=False;self.pending_promotion=None
        self.closed=False;self.suspended=not start_clock;self.draw_claim_basis=None;self.result=automatic_result(self.board)
        if self.result:self.clock.stop()
        elif start_clock:self.clock.start(self.board.turn)
        else:self.clock.started=True;self.clock.paused_color=self.board.turn

    @property
    def running(self):return not self.closed and not self.suspended and self.result is None

    def _event(self,kind,message):self.events.append(GameEvent(kind,message,self.revision))

    def finish(self,result):
        if self.result is not None or self.closed:return
        self.result=result;self.bound_source=None;self.bound_castle=None;self.pending_promotion=None
        self.clock.stop();self._event('ended',result.text)

    def tick(self,at=None):
        if not self.running:return self.result
        expired=self.clock.settle(at)
        if expired is not None:self.finish(loss_or_material_draw(self.board,expired,'Zeitüberschreitung'))
        return self.result

    def touch(self,square):
        self.tick()
        if not self.running or square is None or not self.human_turn:return False
        if self.bound_source is not None:
            king=self.board.piece_at(self.bound_source);rook=self.board.piece_at(square)
            if self.bound_castle is None and king and rook and king.piece_type==chess.KING and rook.piece_type==chess.ROOK and king.color==rook.color:
                target=self._normalize_castle_gesture(self.bound_source,square)
                move=chess.Move(self.bound_source,target)
                if move in self.board.legal_moves and self.board.is_castling(move):self.bound_castle=move
            return square==self.bound_source
        piece=self.board.piece_at(square)
        if piece is None or piece.color!=self.board.turn:return False
        # Art.9.4 also applies if the touched own piece cannot move (Art.4.5).
        self.draw_claim_barred=True
        if any(move.from_square==square for move in self.board.legal_moves):
            self.bound_source=square;self._event('touch','Berührt-geführt: '+chess.square_name(square))
            return True
        return False

    def _normalize_castle_gesture(self,source,target):
        """King then rook is a castling intention; python-chess supplies the move."""
        king=self.board.piece_at(source);rook=self.board.piece_at(target)
        if king and rook and king.color==rook.color and king.piece_type==chess.KING and rook.piece_type==chess.ROOK:
            for move in self.board.legal_moves:
                if move.from_square==source and self.board.is_castling(move):
                    same_side=(chess.square_file(target)>chess.square_file(source))==self.board.is_kingside_castling(move)
                    if same_side and chess.square_rank(source)==chess.square_rank(target):return move.to_square
        return target

    def try_move(self,source,target,promotion=None,*,expected_revision=None):
        self.tick()
        if not self.running:return Attempt(False,'Die Partie ist beendet oder verlassen.')
        if not self.human_turn:return Attempt(False,self.ai_name+' ist am Zug.')
        if expected_revision is not None and expected_revision!=self.revision:return Attempt(False,'Veraltete Eingabe verworfen.')
        if source not in chess.SQUARES or target not in chess.SQUARES:return Attempt(False,'Kein gültiges Zielfeld.')
        if self.bound_source is None:self.touch(source)
        if self.bound_source!=source:return Attempt(False,'Berührt-geführt: Die gebundene Figur muss ziehen.')
        target=self._normalize_castle_gesture(source,target)
        if self.pending_promotion and (source,target,self.revision)!=self.pending_promotion:
            return Attempt(False,'Zuerst die offene Umwandlung abschließen oder abbrechen.')
        candidates=[move for move in self.board.legal_moves if move.from_square==source and move.to_square==target]
        choices=tuple(kind for kind in PROMOTIONS if any(move.promotion==kind for move in candidates))
        if choices and promotion is None:
            self.pending_promotion=(source,target,self.revision)
            return Attempt(False,'Umwandlungsfigur auswählen. Die Uhr läuft weiter.',promotion_choices=choices)
        move=chess.Move(source,target,promotion=promotion)
        if move not in candidates:return Attempt(False,'Ungültiger Zug. Die Auswahl bleibt verbindlich.')
        if self.bound_castle is not None and move!=self.bound_castle:return Attempt(False,'König und Turm berührt: Die legale Rochade ist verbindlich.')
        return self._commit(move)

    def cancel_promotion(self):
        self.pending_promotion=None
        self.tick()  # Binding and elapsed time remain intact.

    def _commit(self,move):
        self.tick()
        if not self.running or move not in self.board.legal_moves:return Attempt(False,'Zug nicht mehr verfügbar.')
        mover=self.board.turn;number=self.board.fullmove_number
        san=self.board.san(move)
        captured=self.board.piece_at(move.to_square)
        if self.board.is_en_passant(move):
            captured=self.board.piece_at(chess.square(chess.square_file(move.to_square),chess.square_rank(move.from_square)))
        rook_shift=None
        if self.board.is_castling(move):
            before=self.board.pieces(chess.ROOK,mover)
            future=self.board.copy(stack=False);future.push(move)
            after=future.pieces(chess.ROOK,mover)
            rook_shift=(next(iter(before-after)),next(iter(after-before)))
        # All parsing/notation is finished; enforce the deadline once more.
        at=self.clock.now();self.tick(at)
        if not self.running:return Attempt(False,'Zeit abgelaufen; der Zug wird nicht angenommen.')
        if not self.clock.complete_move(mover,self.revision+1,at):
            self.tick();return Attempt(False,'Uhrwechsel verweigert.')
        self.board.push(move);self.revision+=1
        record=MoveRecord(self.revision,number,mover,move,san,captured,rook_shift)
        self.records.append(record)
        if captured:self.captured_by[mover].append(captured)
        self.bound_source=None;self.bound_castle=None;self.draw_claim_barred=False;self.pending_promotion=None
        self._event('move',san)
        result=automatic_result(self.board)
        if result:self.finish(result)
        return Attempt(True,san,record=record)

    def claim_draw(self,intended_move=None):
        self.tick()
        if not self.running:return ClaimDecision(False,False,'Die Partie ist bereits beendet.')
        if not self.human_turn:return ClaimDecision(False,False,'Remisanträge sind nur im eigenen Zug möglich.')
        if self.draw_claim_barred:return ClaimDecision(False,False,'Nach dem Berühren einer Figur ist in diesem Zug kein Remisantrag zulässig.')
        if intended_move is not None and intended_move not in self.board.legal_moves:
            return ClaimDecision(False,False,'Der angegebene beabsichtigte Zug ist nicht legal; kein Antrag gestellt.')
        # The preparation dialog never pauses time. Only synchronous adjudication
        # of a submitted, irrevocable claim pauses the clock under FIDE 9.5.1.
        if not self.clock.pause_for_adjudication():
            self.tick();return ClaimDecision(False,False,'Zeit abgelaufen.')
        probe=self.board.copy(stack=True)
        if intended_move is not None:probe.push(intended_move)
        repetition=probe.is_repetition(3);fifty=probe.is_fifty_moves()
        if repetition or fifty:
            reason='Dreifache Stellungswiederholung (Antrag)' if repetition else '50-Züge-Regel (Antrag)'
            self.draw_claim_basis={'intended_uci':intended_move.uci() if intended_move else None}
            self.finish(GameResult(reason,None))
            return ClaimDecision(True,True,reason)
        opponent=not self.board.turn
        self.clock.add_time(opponent,RAPID_CLAIM_PENALTY);self.clock.resume()
        self._event('claim_rejected','Remisantrag abgelehnt: Gegner erhält 60 Sekunden.')
        forced=None
        if intended_move is not None:
            # FIDE 9.5.3: an indicated legal move must be made. This is one real
            # completed move, so its ordinary increment is applied exactly once.
            forced=self._commit(intended_move).record
        return ClaimDecision(True,False,'Unberechtigter Remisantrag: Gegner erhält 60 Sekunden.'+(' Der beabsichtigte Zug wurde ausgeführt.' if forced else ''),RAPID_CLAIM_PENALTY,forced)

    @property
    def ai_name(self):
        return {'grandmaster_ai':'Großmeister-KI', 'adaptive_ai':'Adaptive Grandmaster AI'}.get(self.play_kind, 'Amateur-KI')

    @property
    def human_turn(self):return self.play_kind=='rule_test' or self.board.turn==self.human_color

    def try_engine_move(self,move,*,expected_revision):
        self.tick()
        if self.play_kind not in AI_KINDS or self.human_turn or expected_revision!=self.revision or not self.running:
            return Attempt(False,'Veraltetes oder unzulässiges KI-Ergebnis verworfen.')
        return self._commit(move)

    def resign(self,color=None):
        self.tick()
        if not self.running:return False
        loser=(self.human_color if self.play_kind in AI_KINDS else self.board.turn) if color is None else color
        if self.play_kind in AI_KINDS and loser!=self.human_color:return False
        self.resigned_color=loser
        self.finish(loss_or_material_draw(self.board,loser,'Aufgabe'))
        return True

    def abandon(self):
        if self.closed:return
        self.tick()  # A flag that already fell takes precedence over leaving.
        self.clock.stop();self.closed=True;self.bound_source=None;self.bound_castle=None;self.pending_promotion=None
        self._event('left','Regeltest verlassen; nicht gespeichert.')

    def suspend(self):
        """Freeze for a controlled checkpoint; preserve all selection obligations."""
        if self.suspended:return self.result is None and not self.closed
        self.tick()
        if not self.running:return False
        if not self.clock.pause_for_adjudication():
            self.tick();return False
        self.suspended=True
        return True

    def resume(self):
        """Start a fresh monotonic interval, never an increment or a new move."""
        if self.closed or self.result is not None or not self.suspended:return False
        if not self.clock.resume():return False
        self.suspended=False
        return True
