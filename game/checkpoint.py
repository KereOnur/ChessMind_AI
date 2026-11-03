"""Versioned, untrusted save codec. Full legal replay, never FEN-only loading."""
from dataclasses import dataclass
from datetime import datetime,timezone
import hashlib,json,math,time,uuid
import chess
from game.session import GameSession,AI_KINDS
from game.events import GameEvent,MoveRecord
from game.ending import GameResult,automatic_result,loss_or_material_draw

FORMAT_VERSION=1
MODES={'amateur':'classic','grandmaster':'wood','adaptive':'cyber'}
MAX_MOVES=20000
MAX_BYTES=8_000_000


class InvalidCheckpoint(ValueError):pass


@dataclass(frozen=True)
class Checkpoint:
    text:str
    digest:str

    @property
    def data(self):return json.loads(self.text)


@dataclass
class RestoredGame:
    session:GameSession
    game_id:str
    sequence:int
    mode:str
    player_color:str
    theme:str
    saved_at:str
    learning:object=None


def canonical(data):return json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)


def pack(data):
    text=canonical(data)
    return Checkpoint(text,hashlib.sha256(text.encode()).hexdigest())


def export_checkpoint(session,mode,player_color,theme,game_id,sequence,*,status=None):
    """Called on the UI thread: copy primitives only; replay happens in the worker."""
    session.tick()
    root=session.board.root()
    moves=[move.uci() for move in session.board.move_stack]
    offset=len(moves)-session.revision
    events=[{'kind':e.kind,'message':e.message,'ply':e.revision+offset} for e in session.events if e.kind!='left']
    result={'reason':session.result.reason,'winner':session.result.winner,'score':session.result.score} if session.result else None
    data={
      'format_version':{'amateur_ai':2,'grandmaster_ai':3,'adaptive_ai':4}.get(session.play_kind,FORMAT_VERSION),'game_id':game_id,'sequence':sequence,
      'mode':mode,'player_color':player_color,'theme':theme,'ai_model_version':None,
      'root_fen':root.fen(en_passant='fen'),'uci_moves':moves,
      'fen':session.board.fen(en_passant='fen'),'turn':session.board.turn,
      'castling_rights':str(session.board.castling_rights),'ep_square':session.board.ep_square,
      'halfmove_clock':session.board.halfmove_clock,'fullmove_number':session.board.fullmove_number,
      'initial_seconds':session.clock.initial_seconds,'increment_seconds':session.clock.increment,
      'white_seconds':session.clock.remaining[True],'black_seconds':session.clock.remaining[False],
      'time_control':'Rapid 15+10','revision':len(moves),
      'status':'finished' if result else (status or ('suspended' if session.suspended else 'running')),
      'result':result,'events':events,'draw_claim_basis':session.draw_claim_basis,
      'bound_source':session.bound_source,'bound_castle':session.bound_castle.uci() if session.bound_castle else None,
      'draw_claim_barred':session.draw_claim_barred,
      'pending_promotion':list(session.pending_promotion[:2]) if session.pending_promotion else None,
      'captured_at':datetime.now(timezone.utc).isoformat(timespec='microseconds'),
      'saved_at':datetime.now(timezone.utc).isoformat(timespec='microseconds'),
    }
    if session.play_kind in AI_KINDS:
        data.update(play_kind=session.play_kind,human_color=session.human_color,ai_model_version={'grandmaster_ai':'grandmaster-v1','adaptive_ai':'adaptive-v1'}.get(session.play_kind,'amateur-v1'),resigned_color=session.resigned_color)
    return pack(data)


def _require(condition,message):
    if not condition:raise InvalidCheckpoint(message)


def _number(value):return type(value) in (float,int) and math.isfinite(value) and 0<=value<=1_000_000_000


def restore_checkpoint(checkpoint,*,now=time.monotonic):
    try:return _restore(checkpoint,now)
    except InvalidCheckpoint:raise
    except (ValueError,TypeError,KeyError,IndexError,AttributeError,OverflowError) as exc:
        raise InvalidCheckpoint('Unvollständiger oder ungültiger Spielstand: '+str(exc)) from exc


def _restore(checkpoint,now):
    _require(len(checkpoint.text.encode())<=MAX_BYTES,'Spielstand ist zu groß.')
    _require(hashlib.sha256(checkpoint.text.encode()).hexdigest()==checkpoint.digest,'Prüfsumme des Spielstands stimmt nicht.')
    d=json.loads(checkpoint.text)
    _require(type(d)==dict and type(d['format_version'])==int and d['format_version'] in (1,2,3,4),'Unbekannte Spielstandversion.')
    _require(str(uuid.UUID(d['game_id']))==d['game_id'],'Ungültige Partie-ID.')
    _require(type(d['sequence'])==int and d['sequence']>=0,'Ungültige Speichersequenz.')
    _require(d['mode'] in MODES and d['theme']==MODES[d['mode']],'Modus und Brettdesign passen nicht zusammen.')
    _require(d['player_color'] in ('Weiß','Schwarz'),'Ungültige Spielerfarbe.')
    _require(d['ai_model_version'] is None or type(d['ai_model_version'])==str,'Ungültige Modell-Metadaten.')
    play_kind=d.get('play_kind','rule_test');human_color=d.get('human_color')
    if d['format_version'] in (2,3,4):
        kind,mode,theme,model={2:('amateur_ai','amateur','classic','amateur-v1'), 3:('grandmaster_ai','grandmaster','wood','grandmaster-v1'), 4:('adaptive_ai','adaptive','cyber','adaptive-v1')}[d['format_version']]
        _require(play_kind==kind and type(human_color)==bool and human_color==(d['player_color']=='Weiß') and d['mode']==mode and d['theme']==theme and d['ai_model_version']==model,'Ungültige KI-Konfiguration.')
        _require(d.get('resigned_color') is None or d['resigned_color']==human_color,'Ungültige Aufgabe-Farbe.')
    else:_require(play_kind=='rule_test' and human_color is None,'Alte Regeltest-Partie darf nicht als KI-Partie interpretiert werden.')
    for key in ('captured_at','saved_at'):
        saved=datetime.fromisoformat(d[key]);_require(saved.tzinfo is not None,'Speicherzeit ohne Zeitzone.')
    _require(type(d['uci_moves'])==list and len(d['uci_moves'])<=MAX_MOVES,'Ungültiger Zugverlauf.')
    board=chess.Board(d['root_fen']);_require(board.is_valid() and not board.chess960,'Ungültige Ausgangsstellung.')
    _require(board.fen(en_passant='fen')==d['root_fen'],'Nicht kanonische Ausgangsstellung.')
    records=[];captured_by={True:[],False:[]};turns=[board.turn]
    for ply,token in enumerate(d['uci_moves'],1):
        _require(automatic_result(board) is None,'Zug nach automatischem Spielende.')
        _require(type(token)==str,'Ungültiger UCI-Eintrag.')
        move=chess.Move.from_uci(token)
        _require(move.uci()==token and move in board.legal_moves,'Illegaler gespeicherter Zug: '+token)
        mover=board.turn;san=board.san(move);number=board.fullmove_number
        captured=board.piece_at(move.to_square)
        if board.is_en_passant(move):captured=board.piece_at(chess.square(chess.square_file(move.to_square),chess.square_rank(move.from_square)))
        rook_shift=None
        if board.is_castling(move):
            before=board.pieces(chess.ROOK,mover);copy=board.copy(stack=False);copy.push(move)
            after=copy.pieces(chess.ROOK,mover);rook_shift=(next(iter(before-after)),next(iter(after-before)))
        records.append(MoveRecord(ply,number,mover,move,san,captured,rook_shift))
        if captured:captured_by[mover].append(captured)
        board.push(move);turns.append(board.turn)
    _require(board.fen(en_passant='fen')==d['fen'],'FEN und vollständiger Zugverlauf widersprechen sich.')
    _require(type(d['turn'])==bool and board.turn==d['turn'],'Falsche Spielfarbe am Zug.')
    _require(str(board.castling_rights)==d['castling_rights'] and board.ep_square==d['ep_square'],'Rochade-/En-passant-Daten widersprechen dem Verlauf.')
    _require(board.halfmove_clock==d['halfmove_clock'] and board.fullmove_number==d['fullmove_number'],'Falsche Zugzähler.')
    _require(type(d['revision'])==int and d['revision']==len(records),'Unvollständige Zugrevision.')
    _require(d['time_control']=='Rapid 15+10' and d['initial_seconds']==900 and d['increment_seconds']==10,'Nicht unterstützte Zeitkontrolle.')
    _require(_number(d['white_seconds']) and _number(d['black_seconds']),'Ungültige Restzeit.')
    _require(type(d['events'])==list and len(d['events'])<=100000,'Ungültige Ereignisliste.')
    penalties={True:0,False:0};events=[]
    for e in d['events']:
        _require(type(e)==dict and e['kind'] in ('touch','move','claim_rejected','ended'),'Ungültiges Ereignis.')
        _require(type(e['ply'])==int and 0<=e['ply']<=len(records) and type(e['message'])==str and len(e['message'])<=2048,'Ungültige Ereignisdaten.')
        if e['kind']=='claim_rejected':penalties[not turns[e['ply']]]+=60
        events.append(GameEvent(e['kind'],e['message'],e['ply']))
    for color,key in ((True,'white_seconds'),(False,'black_seconds')):
        upper=900+10*sum(r.color==color for r in records)+penalties[color]
        _require(d[key]<=upper+1e-6,'Zeitgutschrift ist nicht durch Züge/Strafen erklärbar.')
    _require(d['status'] in ('running','suspended','finished','discarded'),'Unbekannter Spielstatus.')
    auto=automatic_result(board);result=None
    if d['result'] is not None:
        r=d['result'];_require(type(r)==dict and (type(r['winner'])==bool or r['winner'] is None),'Ungültiges Ergebnis.')
        result=GameResult(r['reason'],r['winner']);_require(result.score==r['score'],'Ergebniscode widerspricht Gewinner.')
        if auto:_require(result==auto,'Automatisches Spielende widerspricht Ergebnis.')
        elif result.reason.startswith(('Zeitüberschreitung','Aufgabe')):
            reason='Zeitüberschreitung' if result.reason.startswith('Zeit') else 'Aufgabe'
            loser=d.get('resigned_color') if reason=='Aufgabe' and play_kind in AI_KINDS else board.turn
            _require(type(loser)==bool and result==loss_or_material_draw(board,loser,reason),'Unplausibles Zeit-/Aufgabeergebnis.')
            if reason.startswith('Zeit'):_require(d['white_seconds' if board.turn else 'black_seconds']==0,'Zeitverlust ohne abgelaufene Uhr.')
        else:
            basis=d['draw_claim_basis'];_require(type(basis)==dict,'Nachweis des Remisantrags fehlt.')
            probe=board.copy(stack=True)
            if basis['intended_uci'] is not None:
                move=chess.Move.from_uci(basis['intended_uci']);_require(move in probe.legal_moves,'Illegaler beabsichtigter Remiszug.');probe.push(move)
            expected='Dreifache Stellungswiederholung (Antrag)' if probe.is_repetition(3) else ('50-Züge-Regel (Antrag)' if probe.is_fifty_moves() else None)
            _require(result==GameResult(expected,None) and expected is not None,'Remisergebnis ist nicht belegbar.')
        _require(d['status']=='finished','Beendete Partie ist als laufend markiert.')
    else:
        _require(auto is None and d['status']!='finished','Spielende fehlt oder Status widerspricht.')
        _require(d['white_seconds']>0 and d['black_seconds']>0,'Laufende Partie mit abgelaufener Uhr.')
    _require(type(d['draw_claim_barred'])==bool,'Ungültige Auswahlbindung.')
    source=d['bound_source'];castle=None;pending=None
    if source is not None:
        _require(type(source)==int and source in chess.SQUARES and board.color_at(source)==board.turn,'Gebundene Figur fehlt.')
        _require(d['draw_claim_barred'] and any(m.from_square==source for m in board.legal_moves),'Unplausible Berührt-geführt-Bindung.')
    if d['bound_castle'] is not None:
        castle=chess.Move.from_uci(d['bound_castle'])
        _require(castle in board.legal_moves and board.is_castling(castle) and castle.from_square==source,'Ungültige Rochadebindung.')
    if d['pending_promotion'] is not None:
        p=d['pending_promotion'];_require(type(p)==list and len(p)==2 and p[0]==source,'Ungültige offene Umwandlung.')
        _require(any(m.from_square==p[0] and m.to_square==p[1] and m.promotion for m in board.legal_moves),'Offene Umwandlung ist nicht legal.')
        pending=(*p,len(records))
    _require(result is None or (source is None and castle is None and pending is None),'Auswahlbindung nach Spielende.')
    if play_kind in AI_KINDS and board.turn!=human_color:_require(source is None and pending is None and not d['draw_claim_barred'],'Menschliche Auswahlbindung im KI-Zug.')
    session=GameSession(board.root(),now=now,start_clock=False,play_kind=play_kind,human_color=human_color)
    session.resigned_color=d.get('resigned_color')
    session.board=board;session.records=records;session.captured_by=captured_by;session.events=events
    session.revision=len(records);session.result=result;session.closed=d['status']=='discarded';session.suspended=True
    session.bound_source=source;session.bound_castle=castle;session.draw_claim_barred=d['draw_claim_barred'];session.pending_promotion=pending
    session.draw_claim_basis=d['draw_claim_basis']
    session.clock.remaining={True:float(d['white_seconds']),False:float(d['black_seconds'])}
    session.clock.completed_moves=len(records);session.clock.started=True;session.clock.active=None;session.clock.anchor=None
    session.clock.finished=result is not None or session.closed;session.clock.paused_color=None if session.clock.finished else board.turn
    session.clock.expired_color=board.turn if result and result.reason.startswith('Zeit') else None
    return RestoredGame(session,d['game_id'],d['sequence'],d['mode'],d['player_color'],d['theme'],d['saved_at'])
