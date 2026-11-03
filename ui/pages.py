"""German setup pages. User actions are emitted; state lives in navigation.py."""
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QBoxLayout, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from ui.navigation import OPPONENTS, GameSetup, Opponent, PlayerColor
from ui.theme import set_selected
from ui.widgets import Artwork, NavigationButton, ScrollablePage, back_button, label


def header(page, title, subtitle, step):
    row = QHBoxLayout()
    back = back_button()
    row.addWidget(back)
    row.addStretch()
    step_label = label(step, 'eyebrow')
    step_label.setWordWrap(False)
    row.addWidget(step_label)
    page.layout_body.addLayout(row)
    titles = QVBoxLayout()
    titles.setSpacing(9)
    titles.addWidget(label(title, 'pageTitle'))
    titles.addWidget(label(subtitle, 'subtitle'))
    page.layout_body.addLayout(titles)
    return back


class MainMenuPage(ScrollablePage):
    new_game_requested = Signal()
    resume_requested = Signal()
    statistics_requested = Signal()
    review_requested = Signal()
    quit_requested = Signal()

    def __init__(self, parent=None, *, enable_storage=False):
        super().__init__(parent)
        self.columns = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.columns.setSpacing(42)
        self.left = QWidget()
        left = QVBoxLayout(self.left)
        left.setContentsMargins(0, 8, 0, 0)
        left.setSpacing(10)
        left.addWidget(label('SCHACH. NEU GEDACHT.', 'eyebrow'))
        self.title_label = label('NeuroChess', 'brand')
        left.addWidget(self.title_label)
        tagline = label('Dein nächster Zug beginnt hier.', 'subtitle')
        tagline.setContentsMargins(0, 0, 0, 20)
        left.addWidget(tagline)
        self.menu_buttons = {}
        items = [
            ('Neues Spiel', 'Gegner und Spielerfarbe wählen', 'new'),
            ('Spiel fortsetzen', 'Noch nicht verfügbar', 'resume'),
            ('Statistiken', 'Menschliche Partien und Lernverlauf' if enable_storage else 'Noch nicht verfügbar', 'stats'),
            ('KI-Testzentrum', 'Lokaler Modellvergleich' if enable_storage else 'Noch nicht verfügbar', 'lab'),
            ('Beenden', 'NeuroChess schließen', 'quit'),
        ]
        for title, subtitle, icon in items:
            button = NavigationButton(title, subtitle, icon, title == 'Neues Spiel')
            self.menu_buttons[title] = button
            left.addWidget(button)
            if title == 'Neues Spiel':
                button.clicked.connect(self.new_game_requested.emit)
            elif title == 'Spiel fortsetzen':
                button.clicked.connect(self.resume_requested.emit)
            elif enable_storage and title == 'Statistiken':
                button.clicked.connect(self.statistics_requested.emit)
            elif enable_storage and title == 'KI-Testzentrum':
                button.clicked.connect(self.review_requested.emit)
            elif title == 'Beenden':
                button.clicked.connect(self.quit_requested.emit)
            else:
                button.clicked.connect(lambda checked=False, name=title: self.show_unavailable(name))
        self.notice = label('Wähle einen Gegner und bereite deinen Spielmodus vor.', 'smallText')
        self.notice.setMinimumHeight(46)
        left.addWidget(self.notice)
        left.addStretch(1)
        left.addWidget(label('NEUROCHESS  /  DESKTOP EDITION', 'eyebrow'))

        self.hero = QFrame()
        self.hero.setObjectName('heroPanel')
        hero = QVBoxLayout(self.hero)
        hero.setContentsMargins(26, 28, 26, 24)
        hero.setSpacing(14)
        hero.addWidget(label('PRÄZISION TRIFFT STRATEGIE', 'eyebrow'))
        hero.addWidget(label('Ein Spiel. Neue Perspektiven.', 'heroTitle'))
        self.hero_art = Artwork('menu-chess.svg')
        self.hero_art.setMinimumHeight(365)
        hero.addWidget(self.hero_art, 1)
        hero.addWidget(label('Drei Charaktere. Dein eigener Spielstil.', 'subtitle'))
        hero.addWidget(label('Gegnerwahl und Spielvorbereitung', 'smallText'))
        self.columns.addWidget(self.left, 4)
        self.columns.addWidget(self.hero, 7)
        self.layout_body.addLayout(self.columns)
        self.width_changed.connect(self.adapt_layout)

    def adapt_layout(self, width):
        wide = width >= 850
        self.columns.setDirection(QBoxLayout.Direction.LeftToRight if wide else QBoxLayout.Direction.TopToBottom)
        self.left.setMaximumWidth(430 if wide else 16777215)
        self.hero_art.setMinimumHeight(365 if wide else 260)

    def show_unavailable(self, feature):
        self.notice.setObjectName('notice')
        self.notice.setText(f'{feature}: Noch nicht verfügbar.')
        self.notice.style().unpolish(self.notice)
        self.notice.style().polish(self.notice)


class OpponentCard(QPushButton):
    def __init__(self, opponent: Opponent, parent=None):
        super().__init__(parent)
        info = OPPONENTS[opponent]
        self.opponent = opponent
        self.setObjectName('opponentCard')
        self.setAccessibleName(info.title)
        self.setAccessibleDescription(info.description)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)
        layout.addWidget(label(info.category, 'eyebrow'))
        art = Artwork(info.artwork)
        art.setMinimumHeight(190)
        art.setMaximumHeight(260)
        layout.addWidget(art)
        title = label(info.title, 'cardTitle')
        title.setMinimumHeight(62)
        layout.addWidget(title)
        description = label(info.description, 'cardDescription')
        description.setMinimumHeight(65)
        layout.addWidget(description)
        layout.addStretch(1)
        self.action_label = label('Auswählen  →', 'cardAction')
        layout.addWidget(self.action_label)
        for child in self.findChildren(QWidget):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def sizeHint(self):
        return QSize(330, self.layout().sizeHint().height())

    def minimumSizeHint(self):
        return QSize(0, self.layout().minimumSize().height())

    def select(self, selected):
        set_selected(self, selected)
        self.action_label.setText('✓  Ausgewählt' if selected else 'Auswählen  →')


class OpponentPage(ScrollablePage):
    back_requested = Signal()
    opponent_chosen = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.back_button = header(self, 'Wähle deinen Gegner', 'Drei Spielstile. Welcher passt zu dir?', '01  /  GEGNER')
        self.back_button.clicked.connect(self.back_requested.emit)
        self.cards_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.cards_layout.setSpacing(20)
        self.opponent_cards = {}
        for opponent in Opponent:
            card = OpponentCard(opponent)
            card.clicked.connect(lambda checked=False, value=opponent: self.opponent_chosen.emit(value))
            self.opponent_cards[opponent] = card
            self.cards_layout.addWidget(card, 1)
        self.layout_body.addLayout(self.cards_layout)
        self.layout_body.addWidget(label('Du wählst hier deinen Spielmodus. Die Schachpartie und die KI-Funktionen sind noch nicht verfügbar.', 'notice'))
        self.width_changed.connect(lambda width: self.cards_layout.setDirection(
            QBoxLayout.Direction.LeftToRight if width >= 980 else QBoxLayout.Direction.TopToBottom))

    def refresh(self, setup: GameSetup):
        for opponent, card in self.opponent_cards.items():
            card.select(opponent == setup.opponent)


class ColorCard(QPushButton):
    def __init__(self, color: PlayerColor, parent=None):
        super().__init__(parent)
        self.setObjectName('colorCard')
        self.setAccessibleName(color.value)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 22)
        layout.setSpacing(12)
        art = Artwork('color-white.svg' if color == PlayerColor.WHITE else 'color-black.svg')
        art.setMinimumHeight(160)
        art.setMaximumHeight(195)
        layout.addWidget(art)
        title = label(color.value, 'cardTitle')
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        text = label('Du ziehst zuerst.' if color == PlayerColor.WHITE else 'Dein Gegner zieht zuerst.', 'subtitle')
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(text)
        self.indicator = label('Farbe wählen', 'cardAction')
        self.indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.indicator)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        for child in self.findChildren(QWidget):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def sizeHint(self):
        return QSize(330, self.layout().sizeHint().height())

    def minimumSizeHint(self):
        return QSize(0, self.layout().minimumSize().height())

    def select(self, selected):
        set_selected(self, selected)
        self.indicator.setText('✓  Ausgewählt' if selected else 'Farbe wählen')


class ColorPage(ScrollablePage):
    back_requested = Signal()
    color_chosen = Signal(object)
    continue_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.back_button = header(self, 'Mit welcher Farbe spielst du?', 'Wähle deine Seite für den ausgewählten Spielmodus.', '02  /  SPIELERFARBE')
        self.back_button.clicked.connect(self.back_requested.emit)
        self.opponent_label = label('', 'chip')
        self.layout_body.addWidget(self.opponent_label)
        self.colors_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.colors_layout.setSpacing(20)
        self.color_cards = {}
        for color in PlayerColor:
            card = ColorCard(color)
            card.clicked.connect(lambda checked=False, value=color: self.color_chosen.emit(value))
            self.color_cards[color] = card
            self.colors_layout.addWidget(card, 1)
        self.layout_body.addLayout(self.colors_layout)
        self.continue_button = QPushButton('Zur Zusammenfassung  →')
        self.continue_button.setObjectName('primaryButton')
        self.continue_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.continue_button.clicked.connect(self.continue_requested.emit)
        self.continue_button.setEnabled(False)
        self.layout_body.addWidget(self.continue_button)
        self.layout_body.addWidget(label('Zeitkontrolle: Rapid 15+10', 'smallText'))
        self.width_changed.connect(lambda width: self.colors_layout.setDirection(
            QBoxLayout.Direction.LeftToRight if width >= 620 else QBoxLayout.Direction.TopToBottom))

    def refresh(self, setup: GameSetup):
        self.opponent_label.setText('Dein Gegner: ' + OPPONENTS[setup.opponent].title if setup.opponent else 'Noch kein Gegner ausgewählt')
        for color, card in self.color_cards.items():
            card.select(color == setup.player_color)
        self.continue_button.setEnabled(setup.opponent is not None and setup.player_color is not None)


class SummaryPage(ScrollablePage):
    amateur_requested = Signal()
    grandmaster_requested = Signal()
    adaptive_requested = Signal()
    rule_test_requested = Signal()
    preview_requested = Signal()
    back_requested = Signal()
    home_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.back_button = header(self, 'Deine Spielauswahl', 'Alles im Blick. Deine Auswahl bleibt beim Zurückgehen erhalten.', '03  /  ÜBERSICHT')
        self.back_button.clicked.connect(self.back_requested.emit)
        panel = QFrame()
        panel.setObjectName('summaryPanel')
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(28, 26, 28, 28)
        layout.setSpacing(12)
        self.values = {}
        for key in ('Gegner', 'Spielerfarbe', 'Zeitkontrolle'):
            layout.addWidget(label(key.upper(), 'eyebrow'))
            value = label('', 'summaryValue')
            self.values[key] = value
            layout.addWidget(value)
            layout.addSpacing(16)
        self.layout_body.addWidget(panel)
        self.availability_text='Alle drei KI-Gegner sind spielbar. Der lokale Regeltest bleibt erhalten.'
        self.availability=label(self.availability_text, 'notice')
        self.layout_body.addWidget(self.availability)
        self.play_button=QPushButton('Partie gegen Amateur starten')
        self.play_button.setObjectName('primaryButton')
        self.play_button.clicked.connect(self.request_game)
        self.layout_body.addWidget(self.play_button)
        self.preview_button = QPushButton('Schachbrett-Vorschau öffnen')
        self.preview_button.setObjectName('primaryButton')
        self.preview_button.clicked.connect(self.preview_requested.emit)
        self.layout_body.addWidget(self.preview_button)
        self.rule_test_button = QPushButton('Regeltest-Partie starten')
        self.rule_test_button.setObjectName('primaryButton')
        self.rule_test_button.clicked.connect(self.rule_test_requested.emit)
        self.layout_body.addWidget(self.rule_test_button)
        home = QPushButton('Zum Hauptmenü')
        home.setObjectName('primaryButton')
        home.setCursor(Qt.CursorShape.PointingHandCursor)
        home.clicked.connect(self.home_requested.emit)
        self.home_button = home
        self.layout_body.addWidget(home)

    def refresh(self, setup: GameSetup):
        self.values['Gegner'].setText(OPPONENTS[setup.opponent].title if setup.opponent else '–')
        self.values['Spielerfarbe'].setText(setup.player_color.value if setup.player_color else '–')
        self.values['Zeitkontrolle'].setText(setup.time_control)
        self.availability.setText(self.availability_text)
        self.selected_opponent=setup.opponent
        self.play_button.setText('Partie gegen '+OPPONENTS[setup.opponent].title+' starten' if setup.opponent is not None else 'Partie starten')

    def request_game(self):
        if self.selected_opponent==Opponent.AMATEUR:self.amateur_requested.emit()
        elif self.selected_opponent==Opponent.GRANDMASTER:self.grandmaster_requested.emit()
        elif self.selected_opponent==Opponent.ADAPTIVE:self.adaptive_requested.emit()
