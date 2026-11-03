"""Responsive preview surface. Owns disposable demo data, never a real game."""
from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import QBoxLayout, QFrame, QHBoxLayout, QPushButton, QScrollArea, QVBoxLayout, QWidget
from ui.navigation import OPPONENTS, PlayerColor
from ui.widgets import ScrollablePage, label
from ui.board.demo import initial_preview
from ui.board.input import DemoInput
from ui.board.panels import DemoMoveList, PlayerBar
from ui.board.themes import THEMES
from ui.board.view import BoardView


class BoardPreviewPage(ScrollablePage):
    back_requested=Signal()
    home_requested=Signal()

    def __init__(self,parent=None):
        super().__init__(parent)
        self.layout_body.setSpacing(10)
        self.nav=QHBoxLayout();self.nav.setSpacing(8)
        self.back_button=QPushButton('‹  Zur Zusammenfassung');self.back_button.setObjectName('backButton')
        self.back_button.clicked.connect(self.back_requested.emit)
        self.home_button=QPushButton('Hauptmenü');self.home_button.setObjectName('backButton')
        self.home_button.clicked.connect(self.home_requested.emit)
        self.nav.addWidget(self.back_button);self.nav.addStretch();self.nav.addWidget(self.home_button)
        self.layout_body.addLayout(self.nav)
        self.banner=label('Vorschau – Schachregeln und KI noch nicht verfügbar','previewBanner')
        self.layout_body.addWidget(self.banner)
        self.columns=QBoxLayout(QBoxLayout.Direction.LeftToRight);self.columns.setSpacing(20)
        self.board_panel=QWidget();board_layout=QVBoxLayout(self.board_panel)
        board_layout.setContentsMargins(0,0,0,0);board_layout.setSpacing(6)
        self.top_player=self.create_player_bar();self.bottom_player=self.create_player_bar()
        self.board=BoardView()
        board_layout.addWidget(self.top_player);board_layout.addWidget(self.board);board_layout.addWidget(self.bottom_player)
        self.columns.addWidget(self.board_panel,1)

        self.sidebar=QWidget();self.sidebar.setObjectName('pageCanvas');side=QVBoxLayout(self.sidebar)
        side.setContentsMargins(0,0,0,0);side.setSpacing(16)
        self.sidebar_layout=side
        self.sidebar_title=label('SPIELMODUS · VORSCHAU','eyebrow');side.addWidget(self.sidebar_title)
        self.mode_label=label('','previewTitle');side.addWidget(self.mode_label)
        self.theme_label=label('','chip');side.addWidget(self.theme_label)
        self.player_label=label('','subtitle');side.addWidget(self.player_label)
        self.context_label=label('Am Zug: Weiß · Beispielanzeige\nBeide Uhren: 15:00 · nicht laufend','smallText');side.addWidget(self.context_label)
        self.move_list=self.create_move_list();side.addWidget(self.move_list)
        self.input_hint=label('Visueller Demomodus: Figur anklicken und freies Zielfeld anklicken oder per Drag & Drop verschieben. Keine Schachzüge.','notice')
        side.addWidget(self.input_hint)
        self.save_button=QPushButton('Speichern && verlassen');self.save_button.setObjectName('primaryButton')
        self.resign_button=QPushButton('Aufgeben')
        self.save_button.clicked.connect(self.show_save_notice)
        self.resign_button.clicked.connect(self.show_resign_notice)
        side.addWidget(self.save_button);side.addWidget(self.resign_button)
        self.action_notice=label('','notice');self.action_notice.hide();side.addWidget(self.action_notice)
        self.exit_button=QPushButton('Jetzt zum Hauptmenü');self.exit_button.hide()
        self.exit_button.clicked.connect(self.home_requested.emit);side.addWidget(self.exit_button)
        side.addStretch()
        self.side_scroll=QScrollArea()
        self.side_scroll.setWidgetResizable(True)
        self.side_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.side_scroll.setWidget(self.sidebar)
        self.columns.addWidget(self.side_scroll)
        self.layout_body.addLayout(self.columns)
        self.board.input_feedback.connect(self.input_hint.setText)
        self.position={};self.theme=None;self.active=False
        self.width_changed.connect(self.adapt_layout)

    def configure(self,setup):
        self.leave()
        self.active=True
        self.theme=THEMES[setup.opponent]
        color='white' if setup.player_color==PlayerColor.WHITE else 'black'
        opponent_color='black' if color=='white' else 'white'
        self.position=initial_preview()
        self.board.configure(self.theme,color,self.position,DemoInput(self.position))
        self.top_player.configure(OPPONENTS[setup.opponent].title,opponent_color,self.theme,self.board.resources)
        self.bottom_player.configure('Du · '+setup.player_color.value,color,self.theme,self.board.resources)
        self.mode_label.setText(OPPONENTS[setup.opponent].title)
        self.theme_label.setText(self.theme.title+'  ·  Rapid 15+10')
        self.player_label.setText('Deine Spielerfarbe: '+setup.player_color.value)
        self.action_notice.hide();self.exit_button.hide()
        self.input_hint.setText('Visueller Demomodus: Figuren auf freie Felder bewegen. Keine Schachzüge; keine Spiellogik.')
        self.verticalScrollBar().setValue(0)
        QTimer.singleShot(0,self.fit_preview)

    def adapt_layout(self,width):
        wide=width>=900
        self.columns.setDirection(QBoxLayout.Direction.LeftToRight if wide else QBoxLayout.Direction.TopToBottom)
        self._wide=wide
        self.side_scroll.setFixedWidth(310 if wide else width)
        QTimer.singleShot(0,self.fit_preview)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        margin=12 if self.viewport().width()<800 else 20
        self.outer.setContentsMargins(margin,margin,margin,margin)
        width=max(1,min(1400,self.viewport().width()-2*margin))
        self.body.setFixedWidth(width)
        self.adapt_layout(width)

    def fit_preview(self):
        if not self.active: return
        # Leave both player bars and the entire square board above the fold.
        margins=self.outer.contentsMargins()
        banner_height=self.banner.heightForWidth(self.body.width())
        budget=self.viewport().height()-margins.top()-margins.bottom()-self.nav.sizeHint().height()-banner_height-20-108-12-8
        height=max(24,budget)
        self.board.setFixedHeight(height)
        self.side_scroll.setFixedHeight(height+120 if getattr(self,'_wide',False) else self.sidebar.sizeHint().height()+4)
        self.board.fit_board()

    def leave(self):
        self.active=False
        self.board.stop()

    def hideEvent(self,event):
        self.leave();super().hideEvent(event)

    def show_save_notice(self):
        self.action_notice.setText('Die Vorschau wird nicht gespeichert. Speichern ist nur in einer Regeltest-Partie verfügbar.')
        self.action_notice.show();self.exit_button.show()
        self.fit_preview()
        QTimer.singleShot(0,self.reveal_notice)

    def show_resign_notice(self):
        self.action_notice.setText('Die Aufgabe-Funktion ist erst mit einer echten Schachpartie verfügbar.')
        self.action_notice.show()
        self.fit_preview()
        QTimer.singleShot(0,self.reveal_notice)

    def reveal_notice(self):
        if not self.active: return
        self.side_scroll.ensureWidgetVisible(self.exit_button if self.exit_button.isVisible() else self.action_notice)
        if not getattr(self,'_wide',False):
            self.ensureWidgetVisible(self.exit_button if self.exit_button.isVisible() else self.action_notice)

    def create_player_bar(self): return PlayerBar()

    def create_move_list(self): return DemoMoveList()
