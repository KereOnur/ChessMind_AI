"""Single-current-game repository; every connection is short-lived and closed."""
from contextlib import contextmanager
from datetime import datetime,timezone
from pathlib import Path
import sqlite3
from learning import repository as learning
from evaluation import schema as review_schema, training_schema
from game.checkpoint import Checkpoint,InvalidCheckpoint,pack,restore_checkpoint

PROJECT_ROOT=Path(__file__).resolve().parents[1]
DEFAULT_PATH=PROJECT_ROOT/'database'/'neurochess.sqlite3'
SCHEMA_VERSION=1
APPLICATION_ID=0x4E434835


class StorageError(RuntimeError):pass
class ConflictError(StorageError):pass
class UnsupportedSchema(StorageError):pass
class DamagedSave(StorageError):pass

SCHEMA=(
'''CREATE TABLE schema_info (singleton INTEGER PRIMARY KEY CHECK(singleton=1), version INTEGER NOT NULL, application TEXT NOT NULL)''',
'''CREATE TABLE games (
 id TEXT PRIMARY KEY, sequence INTEGER NOT NULL CHECK(sequence>=0), format_version INTEGER NOT NULL,
 mode TEXT NOT NULL, player_color TEXT NOT NULL, theme TEXT NOT NULL, ai_model_version TEXT,
 root_fen TEXT NOT NULL, current_fen TEXT NOT NULL, turn INTEGER NOT NULL CHECK(turn IN(0,1)),
 castling_rights TEXT NOT NULL, ep_square INTEGER, halfmove_clock INTEGER NOT NULL, fullmove_number INTEGER NOT NULL,
 white_seconds REAL NOT NULL CHECK(white_seconds>=0), black_seconds REAL NOT NULL CHECK(black_seconds>=0),
 initial_seconds REAL NOT NULL, increment_seconds REAL NOT NULL, time_control TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN('running','suspended','finished','discarded')),
 result_json TEXT, captured_at TEXT NOT NULL, saved_at TEXT NOT NULL, payload_json TEXT NOT NULL, sha256 TEXT NOT NULL)''',
'''CREATE TABLE moves (game_id TEXT NOT NULL REFERENCES games(id), ply INTEGER NOT NULL CHECK(ply>0), uci TEXT NOT NULL, san TEXT NOT NULL, PRIMARY KEY(game_id,ply))''',
'''CREATE TABLE active_game (slot INTEGER PRIMARY KEY CHECK(slot=1), game_id TEXT NOT NULL UNIQUE REFERENCES games(id))''',
'''CREATE UNIQUE INDEX exactly_one_resumable ON games((1)) WHERE status IN('running','suspended')''',
)
FIELDS=('id','sequence','format_version','mode','player_color','theme','ai_model_version','root_fen','current_fen','turn','castling_rights','ep_square','halfmove_clock','fullmove_number','white_seconds','black_seconds','initial_seconds','increment_seconds','time_control','status','result_json','captured_at','saved_at','payload_json','sha256')


class GameStore:
    def __init__(self,path=DEFAULT_PATH,*,fault=None):
        self.path=Path(path).resolve()
        if not self.path.is_relative_to(PROJECT_ROOT):raise StorageError('Datenbankpfad liegt außerhalb von ChessMind_AI.')
        self.fault=fault

    @contextmanager
    def connection(self,*,create=False):
        connection=None
        try:
            if create:self.path.parent.mkdir(parents=True,exist_ok=True)
            uri=self.path.as_uri()+('?mode=rwc' if create else '?mode=rw')
            connection=sqlite3.connect(uri,uri=True,timeout=.25,isolation_level=None)
            connection.row_factory=sqlite3.Row
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA busy_timeout=250')
            connection.execute('PRAGMA synchronous=FULL')
            connection.execute('PRAGMA fullfsync=ON')
            if connection.execute('PRAGMA journal_mode').fetchone()[0]!='delete':raise UnsupportedSchema('Nicht unterstützter Journalmodus. Vorhandene Daten bleiben unverändert.')
            yield connection
        except sqlite3.Error as exc:
            raise StorageError('SQLite-Zugriff fehlgeschlagen: '+str(exc)) from exc
        finally:
            if connection is not None:connection.close()

    @contextmanager
    def transaction(self,connection):
        connection.execute('BEGIN IMMEDIATE')
        try:
            yield
            if self.fault:self.fault('before_commit',connection)
            connection.commit()
        except BaseException:
            connection.rollback();raise

    def initialize(self):
        was_new=not self.path.exists()
        if not was_new and self.path.stat().st_size==0:raise DamagedSave('Datenbankdatei ist leer oder abgeschnitten; sie wird nicht überschrieben.')
        with self.connection(create=True) as con:
            tables={row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            if tables:
                if 'schema_info' not in tables or con.execute('PRAGMA application_id').fetchone()[0]!=APPLICATION_ID:
                    raise UnsupportedSchema('Unbekannte Datenbank; vorhandene Daten bleiben unverändert.')
                row=con.execute('SELECT version,application FROM schema_info WHERE singleton=1').fetchone()
                if row is None or row['version']!=SCHEMA_VERSION or row['application']!='NeuroChess' or con.execute('PRAGMA user_version').fetchone()[0]!=SCHEMA_VERSION:
                    raise UnsupportedSchema('Nicht unterstützte Datenbankversion; keine automatische Überschreibung.')
                core={'schema_info','games','moves','active_game'}
                learned=core | learning.SCHEMA.keys()
                allowed=(core, *(learned | review | training for review in (set(),review_schema.SCHEMA.keys())
                                  for training in (set(),training_schema.SCHEMA.keys())))
                if tables not in allowed:raise UnsupportedSchema('Unerwartetes Datenbankschema.')
                if 'review_schema' in tables:review_schema.validate(con)
                if 'training_schema' in tables:training_schema.validate(con)
                if tuple(r[1] for r in con.execute('PRAGMA table_info(games)'))!=FIELDS:raise UnsupportedSchema('Unvollständiges Datenbankschema.')
                self._integrity(con)
            else:
                if not was_new:raise UnsupportedSchema('Leere oder unvollständige vorhandene Datenbank; keine automatische Überschreibung.')
                # Rollback journal + FULL avoids dependence on newer WAL fixes
                # in the existing Python 3.11.0 / SQLite 3.38.4 runtime.
                if con.execute('PRAGMA user_version').fetchone()[0]!=0:raise UnsupportedSchema('Unvollständige fremde Datenbank.')
                con.execute('PRAGMA journal_mode=DELETE')
                with self.transaction(con):
                    for statement in SCHEMA:con.execute(statement)
                    con.execute('INSERT INTO schema_info VALUES(1,?,?)',(SCHEMA_VERSION,'NeuroChess'))
                    con.execute(f'PRAGMA application_id={APPLICATION_ID}')
                    con.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
            return True

    def _integrity(self,con):
        messages=[row[0] for row in con.execute('PRAGMA quick_check')]
        if messages!=['ok'] or list(con.execute('PRAGMA foreign_key_check')):raise DamagedSave('Die Datenbank-Integritätsprüfung ist fehlgeschlagen.')

    def _decode(self,con,row):
        try:
            checkpoint=Checkpoint(row['payload_json'],row['sha256']);restored=restore_checkpoint(checkpoint);d=checkpoint.data
            checks={'id':d['game_id'],'sequence':d['sequence'],'format_version':d['format_version'],'mode':d['mode'],'player_color':d['player_color'],'theme':d['theme'],'ai_model_version':d['ai_model_version'],'root_fen':d['root_fen'],'current_fen':d['fen'],'turn':int(d['turn']),'castling_rights':d['castling_rights'],'ep_square':d['ep_square'],'halfmove_clock':d['halfmove_clock'],'fullmove_number':d['fullmove_number'],'white_seconds':d['white_seconds'],'black_seconds':d['black_seconds'],'initial_seconds':d['initial_seconds'],'increment_seconds':d['increment_seconds'],'time_control':d['time_control'],'status':d['status'],'captured_at':d['captured_at'],'saved_at':d['saved_at']}
            if any(row[key]!=value for key,value in checks.items()):raise InvalidCheckpoint('Tabellenspalten und Checkpoint widersprechen sich.')
            import json
            if (json.loads(row['result_json']) if row['result_json'] else None)!=d['result']:raise InvalidCheckpoint('Ergebnisdaten widersprechen sich.')
            moves=list(con.execute('SELECT ply,uci,san FROM moves WHERE game_id=? ORDER BY ply',(row['id'],)))
            expected=[(r.revision,r.move.uci(),r.san) for r in restored.session.records]
            if [tuple(r) for r in moves]!=expected:raise InvalidCheckpoint('Zugtabelle ist unvollständig oder widersprüchlich.')
            return restored,checkpoint
        except (InvalidCheckpoint,ValueError,TypeError,KeyError) as exc:raise DamagedSave('Spielstand kann nicht sicher wiederhergestellt werden: '+str(exc)) from exc

    def load_active(self):
        with self.connection() as con:
            con.execute('BEGIN')
            self._integrity(con)
            slots=list(con.execute('SELECT game_id FROM active_game'))
            resumable=list(con.execute("SELECT id FROM games WHERE status IN('running','suspended')"))
            if len(slots)!=len(resumable) or len(slots)>1 or (slots and slots[0][0]!=resumable[0][0]):raise DamagedSave('Aktiver Spielstand-Slot ist widersprüchlich.')
            if not slots:return None
            row=con.execute('SELECT * FROM games WHERE id=?',(slots[0][0],)).fetchone()
            restored = self._decode(con,row)[0]
            restored.learning = learning.snapshot(con, restored)
            return restored

    def read_owned(self,game_id):
        """Internal retry lookup; no history chooser is exposed in the UI."""
        with self.connection() as con:
            con.execute('BEGIN')
            row=con.execute('SELECT * FROM games WHERE id=?',(game_id,)).fetchone()
            if row is None:
                return None
            restored = self._decode(con,row)[0]
            restored.learning = learning.snapshot(con, restored)
            return restored

    def _values(self,checkpoint):
        import json
        d=checkpoint.data
        return (d['game_id'],d['sequence'],d['format_version'],d['mode'],d['player_color'],d['theme'],d['ai_model_version'],d['root_fen'],d['fen'],int(d['turn']),d['castling_rights'],d['ep_square'],d['halfmove_clock'],d['fullmove_number'],d['white_seconds'],d['black_seconds'],d['initial_seconds'],d['increment_seconds'],d['time_control'],d['status'],json.dumps(d['result'],ensure_ascii=False) if d['result'] else None,d['captured_at'],d['saved_at'],checkpoint.text,checkpoint.digest)

    def _stamp(self,checkpoint):
        d=checkpoint.data;d['saved_at']=datetime.now(timezone.utc).isoformat(timespec='microseconds');return pack(d)

    def create(self,checkpoint):
        restored=restore_checkpoint(checkpoint);d=checkpoint.data
        if d['status']=='discarded':raise ConflictError('Verwerfen ist nur über die bestätigte Aktion zulässig.')
        if d['sequence']!=0:raise ConflictError('Eine neue Partie muss mit Speichersequenz 0 beginnen.')
        with self.connection() as con:
            with self.transaction(con):
                if con.execute('SELECT 1 FROM active_game').fetchone():raise ConflictError('Eine fortsetzbare Partie existiert bereits.')
                checkpoint=self._stamp(checkpoint)
                con.execute('INSERT INTO games ('+','.join(FIELDS)+') VALUES('+','.join('?' for _ in FIELDS)+')',self._values(checkpoint))
                for record in restored.session.records:con.execute('INSERT INTO moves VALUES(?,?,?,?)',(restored.game_id,record.revision,record.move.uci(),record.san))
                restored.learning = learning.sync(con, restored)
                if d['status'] in ('running','suspended'):con.execute('INSERT INTO active_game VALUES(1,?)',(restored.game_id,))
            restored.saved_at=checkpoint.data['saved_at'];return restored

    def save(self,checkpoint):
        restored=restore_checkpoint(checkpoint);new=checkpoint.data
        if new['status']=='discarded':raise ConflictError('Verwerfen ist nur über die bestätigte Aktion zulässig.')
        with self.connection() as con:
            with self.transaction(con):
                row=con.execute('SELECT * FROM games WHERE id=?',(restored.game_id,)).fetchone()
                if row is None:raise ConflictError('Partie wurde nicht angelegt oder bereits entfernt.')
                old_restored,old_checkpoint=self._decode(con,row);old=old_checkpoint.data
                if new['sequence']==old['sequence']:
                    a=dict(new);b=dict(old);a.pop('saved_at');b.pop('saved_at')
                    if a==b:
                        old_restored.learning = learning.sync(con, old_restored, old_restored.session.revision)
                        return old_restored
                    raise ConflictError('Dieselbe Speichersequenz enthält andere Daten.')
                if new['sequence']!=old['sequence']+1:raise ConflictError('Veralteter oder überholter Speichervorgang wurde verworfen.')
                if old['status']=='discarded' or (old['status']=='finished' and (new['status']!='finished' or new['result']!=old['result'] or any(new[k]!=old[k] for k in ('white_seconds','black_seconds')))):
                    raise ConflictError('Ein beendeter/verwerfener Spielstand darf nicht wieder laufen.')
                if any(new[k]!=old[k] for k in ('root_fen','mode','player_color','theme','ai_model_version')):raise ConflictError('Partieidentität oder Konfiguration hat sich geändert.')
                if new.get('play_kind','rule_test')!=old.get('play_kind','rule_test') or new.get('human_color')!=old.get('human_color') or new['format_version']!=old['format_version']:raise ConflictError('Spieltyp und menschliche Spielfarbe dürfen nicht geändert werden.')
                if len(new['uci_moves'])<len(old['uci_moves']) or new['uci_moves'][:len(old['uci_moves'])]!=old['uci_moves']:raise ConflictError('Zugrücknahme oder abweichende Historie verweigert.')
                # CAS alone does not detect an older in-memory state rebased
                # after another writer: history/events must extend, and clocks
                # may rise only by proven new increments / rapid penalties.
                if new['events'][:len(old['events'])]!=old['events']:raise ConflictError('Ältere oder unvollständige Ereignisliste verweigert.')
                gains={True:0,False:0}
                for record in restored.session.records[len(old['uci_moves']):]:gains[record.color]+=10
                turns=[restored.session.board.root().turn]+[not record.color for record in restored.session.records]
                for event in new['events'][len(old['events']):]:
                    if event['kind']=='claim_rejected':gains[not turns[event['ply']]]+=60
                for color,key in ((True,'white_seconds'),(False,'black_seconds')):
                    if new[key]>old[key]+gains[color]+1e-6:raise ConflictError('Ein älterer Uhrstand darf keine Bedenkzeit zurückgeben.')
                if len(new['uci_moves'])==len(old['uci_moves']) and new['result'] is None:
                    if (old['bound_source'] is not None and new['bound_source']!=old['bound_source']) or (old['bound_castle'] is not None and new['bound_castle']!=old['bound_castle']) or (old['draw_claim_barred'] and not new['draw_claim_barred']):raise ConflictError('Eine bestehende Auswahlverpflichtung darf nicht zurückgesetzt werden.')
                checkpoint=self._stamp(checkpoint);values=self._values(checkpoint)
                assignments=','.join(name+'=?' for name in FIELDS[1:])
                updated=con.execute('UPDATE games SET '+assignments+' WHERE id=? AND sequence=?',values[1:]+(restored.game_id,old['sequence']))
                if updated.rowcount!=1:raise ConflictError('Spielstand wurde zwischenzeitlich geändert.')
                for record in restored.session.records[len(old['uci_moves']):]:con.execute('INSERT INTO moves VALUES(?,?,?,?)',(restored.game_id,record.revision,record.move.uci(),record.san))
                restored.learning = learning.sync(con, restored, old_restored.session.revision)
                if new['status']=='finished':con.execute('DELETE FROM active_game WHERE game_id=?',(restored.game_id,))
                elif con.execute('SELECT game_id FROM active_game WHERE slot=1').fetchone()[0]!=restored.game_id:raise ConflictError('Diese Partie ist nicht mehr die aktuelle.')
            restored.saved_at=checkpoint.data['saved_at'];return restored

    def discard(self,game_id,sequence):
        with self.connection() as con:
            with self.transaction(con):
                row=con.execute('SELECT * FROM games WHERE id=?',(game_id,)).fetchone()
                if row is None:raise ConflictError('Partie existiert nicht mehr.')
                _,checkpoint=self._decode(con,row);d=checkpoint.data
                slot=con.execute('SELECT game_id FROM active_game WHERE slot=1').fetchone()
                if d['sequence']!=sequence or slot is None or slot[0]!=game_id:raise ConflictError('Spielstand hat sich seit der Rückfrage geändert.')
                d['status']='discarded';d['sequence']+=1;checkpoint=self._stamp(pack(d))
                con.execute('UPDATE games SET sequence=?,status=?,saved_at=?,payload_json=?,sha256=? WHERE id=?',(d['sequence'],'discarded',checkpoint.data['saved_at'],checkpoint.text,checkpoint.digest,game_id))
                con.execute('DELETE FROM active_game WHERE game_id=?',(game_id,))

    def next_learning_notice(self):
        with self.connection() as con:
            return learning.next_notice(con)

    def acknowledge_learning_notice(self, milestone):
        with self.connection() as con, self.transaction(con):
            learning.acknowledge_notice(con, milestone)

    def restore_stable_learning_model(self):
        with self.connection() as con, self.transaction(con):
            return learning.restore_stable(con)
