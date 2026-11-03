"""Live clocks, actual capture events and SAN history; no demonstration data."""
from collections import Counter
import chess
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QFrame, QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout
from ui.board.demo import PieceSpec
from ui.board.panels import PlayerBar
from ui.widgets import label


class LivePlayerBar(PlayerBar):
    def __init__(self):
        super().__init__()
        self.captured_title.setText('Geschlagen:')
        for icon in self.captured_icons:icon.hide()
        self.groups={}
        for kind in (chess.QUEEN,chess.ROOK,chess.BISHOP,chess.KNIGHT,chess.PAWN):
            icon=QLabel();icon.setFixedSize(16,21)
            count=label('','captureCaption');count.setWordWrap(False)
            self.captured_layout.insertWidget(self.captured_layout.count()-1,icon)
            self.captured_layout.insertWidget(self.captured_layout.count()-1,count)
            self.groups[kind]=(icon,count)
        self.empty=label('—','captureCaption')
        self.captured_layout.insertWidget(1,self.empty)

    def update_live(self,name,color,session,theme,resources):
        active=session.running and session.board.turn==color
        self.full_name=name+(' · Am Zug' if active else '')
        self.name.setToolTip(self.full_name);self.name.setAccessibleName(self.full_name);self._fit_name()
        captured=session.captured_by[color]
        self.captured_pieces=tuple(PieceSpec('white' if p.color else 'black',chess.piece_name(p.piece_type)) for p in captured)
        counts=Counter(p.piece_type for p in captured)
        self.empty.setVisible(not captured)
        for kind,(icon,count) in self.groups.items():
            visible=bool(counts[kind]);icon.setVisible(visible);count.setVisible(visible)
            if visible:
                piece=PieceSpec('black' if color else 'white',chess.piece_name(kind))
                icon.setPixmap(resources.icon(theme,piece,21));count.setText('×'+str(counts[kind]))
                icon.setToolTip(chess.piece_name(kind)+' ×'+str(counts[kind]))
        self.clock.setText(session.clock.display(color))
        self.clock.setAccessibleName(('Weiß' if color else 'Schwarz')+' '+self.clock.text()+(' läuft' if active else ' steht'))


class SanMoveList(QFrame):
    def __init__(self):
        super().__init__();self.setObjectName('summaryPanel')
        layout=QVBoxLayout(self);layout.setContentsMargins(12,12,12,12)
        layout.addWidget(label('ZUGLISTE · SAN','eyebrow'))
        self.table=QTableWidget(0,3)
        self.table.setHorizontalHeaderLabels(['Nr.','Weiß','Schwarz'])
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setMinimumWidth(0);self.table.setFixedHeight(165)
        header=self.table.horizontalHeader();header.setMinimumSectionSize(28)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0,QHeaderView.ResizeMode.Fixed);self.table.setColumnWidth(0,32)
        self.table.setStyleSheet('QTableWidget {background:#0d192a;color:#edf3ff;border:0;font-size:12px;gridline-color:#243951;} QHeaderView::section {background:#15263c;color:#adc6e6;border:0;padding:4px;}')
        layout.addWidget(self.table);self.rows=()

    def update_records(self,records):
        rows={}
        for record in records:
            row=rows.setdefault(record.number,['',''])
            row[0 if record.color else 1]=record.san
        self.rows=tuple((number,*moves) for number,moves in rows.items())
        self.table.setRowCount(len(self.rows))
        for i,row in enumerate(self.rows):
            for j,value in enumerate(row):self.table.setItem(i,j,QTableWidgetItem(str(value)))
        self.table.scrollToBottom()
