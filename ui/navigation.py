"""In-memory setup and navigation; independent of any future chess engine."""
from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import QObject, Signal


class Page(str, Enum):
    MENU = 'menu'
    OPPONENTS = 'opponents'
    COLOR = 'color'
    SUMMARY = 'summary'
    PREVIEW = 'preview'
    RULE_TEST = 'rule_test'


class Opponent(str, Enum):
    AMATEUR = 'amateur'
    GRANDMASTER = 'grandmaster'
    ADAPTIVE = 'adaptive'


class PlayerColor(str, Enum):
    WHITE = 'Weiß'
    BLACK = 'Schwarz'


@dataclass(frozen=True)
class OpponentInfo:
    title: str
    description: str
    artwork: str
    category: str


OPPONENTS = {
    Opponent.AMATEUR: OpponentInfo('Amateur', 'Für Einsteiger – ausgewogene, gelegentlich schwächere Züge.', 'amateur.svg', 'KLASSISCH'),
    Opponent.GRANDMASTER: OpponentInfo('Großmeister', 'Anspruchsvoller Gegner mit starker taktischer Spielweise.', 'grandmaster.svg', 'STRATEGISCH'),
    Opponent.ADAPTIVE: OpponentInfo('Adaptive Grandmaster AI', 'Eine lernfähige KI, die sich anhand deiner Partien weiterentwickelt.', 'adaptive.svg', 'ADAPTIV'),
}


@dataclass
class GameSetup:
    opponent: Opponent | None = None
    player_color: PlayerColor | None = None

    @property
    def time_control(self) -> str:
        return 'Rapid 15+10'


class NavigationController(QObject):
    """Keep one setup while navigating; never start a game or persist data."""
    page_changed = Signal(object)
    selection_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup = GameSetup()
        self.page = Page.MENU

    def _go(self, page: Page) -> None:
        self.page = page
        self.page_changed.emit(page)

    def new_game(self) -> None:
        self._go(Page.OPPONENTS)

    def choose_opponent(self, opponent: Opponent) -> None:
        self.setup.opponent = Opponent(opponent)
        self.selection_changed.emit()
        self._go(Page.COLOR)

    def choose_color(self, color: PlayerColor) -> None:
        if self.setup.opponent is None:
            raise ValueError('Zuerst einen Gegner auswählen.')
        self.setup.player_color = PlayerColor(color)
        self.selection_changed.emit()

    def show_summary(self) -> None:
        if self.setup.opponent is None or self.setup.player_color is None:
            raise ValueError('Gegner und Spielerfarbe müssen ausgewählt sein.')
        self._go(Page.SUMMARY)

    def open_preview(self) -> None:
        if self.setup.opponent is None or self.setup.player_color is None:
            raise ValueError('Gegner und Spielerfarbe müssen ausgewählt sein.')
        self._go(Page.PREVIEW)

    def open_rule_test(self) -> None:
        if self.setup.opponent is None or self.setup.player_color is None:
            raise ValueError('Gegner und Spielerfarbe müssen ausgewählt sein.')
        self._go(Page.RULE_TEST)

    def back(self) -> None:
        self._go({Page.RULE_TEST: Page.SUMMARY, Page.PREVIEW: Page.SUMMARY, Page.SUMMARY: Page.COLOR, Page.COLOR: Page.OPPONENTS,
                  Page.OPPONENTS: Page.MENU, Page.MENU: Page.MENU}[self.page])

    def home(self) -> None:
        self._go(Page.MENU)
