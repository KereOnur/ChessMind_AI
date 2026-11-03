"""Static clocks, captured-piece examples, and a clearly labeled demo move list."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout
from ui.board.demo import CAPTURED_BY, DEMO_ROWS
from ui.widgets import label


class PlayerBar(QFrame):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setObjectName('playerBar')
        self.setFixedHeight(54)
        layout=QHBoxLayout(self);layout.setContentsMargins(10,4,10,4);layout.setSpacing(8)
        texts=QVBoxLayout();texts.setSpacing(1)
        self.name=label('','playerName');self.name.setWordWrap(False)
        self.full_name=''
        self.name.setMinimumWidth(0)
        self.name.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        texts.addWidget(self.name)
        self.captured_layout=QHBoxLayout();self.captured_layout.setSpacing(2)
        self.captured_title=label('Demo: geschlagen','captureCaption')
        self.captured_title.setWordWrap(False)
        self.captured_layout.addWidget(self.captured_title)
        self.captured_icons=[]
        for _ in range(2):
            icon=QLabel();icon.setFixedSize(22,22);self.captured_icons.append(icon)
            self.captured_layout.addWidget(icon)
        self.captured_layout.addStretch()
        texts.addLayout(self.captured_layout)
        layout.addLayout(texts,1)
        self.clock=QLabel('15:00');self.clock.setObjectName('staticClock')
        self.clock.setAccessibleName('Schachuhr: 15 Minuten, reine Anzeige')
        layout.addWidget(self.clock)
        self.captured_pieces=()

    def configure(self,name,color,theme,resources):
        self.full_name=name + (' · Am Zug (Demo)' if color=='white' else '')
        self.name.setToolTip(self.full_name)
        self.name.setAccessibleName(self.full_name)
        self._fit_name()
        self.captured_pieces=CAPTURED_BY[color]
        for index,icon in enumerate(self.captured_icons):
            if index<len(self.captured_pieces):
                piece=self.captured_pieces[index]
                icon.setPixmap(resources.icon(theme,piece,22))
                icon.setToolTip(f'Demonstrationsdaten: {piece.color} {piece.kind}')
                icon.show()
            else: icon.hide()
        self.clock.setText('15:00')

    def _fit_name(self):
        self.name.setText(self.name.fontMetrics().elidedText(self.full_name,Qt.TextElideMode.ElideRight,max(1,self.name.width())))

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self._fit_name()


class DemoMoveList(QFrame):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setObjectName('summaryPanel')
        layout=QVBoxLayout(self);layout.setContentsMargins(16,16,16,16)
        layout.addWidget(label('ZUGLISTE · DEMONSTRATION','eyebrow'))
        grid=QGridLayout();grid.setHorizontalSpacing(12);grid.setVerticalSpacing(12)
        for col,text in enumerate(('Nr.','Weiß (Demo)','Schwarz (Demo)')):
            grid.addWidget(label(text,'captureCaption'),0,col)
        self.rows=DEMO_ROWS
        for row,data in enumerate(self.rows,1):
            for col,text in enumerate(data): grid.addWidget(label(str(text),'moveExample'),row,col)
        layout.addLayout(grid)
        layout.addWidget(label('Beispielbewegungen – kein Partieverlauf. Unabhängig von den Figuren auf dem Vorschaubrett.','smallText'))
