"""Interchangeable visual themes; no position, input, or chess rules."""
from dataclasses import dataclass
from PySide6.QtCore import QEasingCurve
from ui.navigation import Opponent


@dataclass(frozen=True)
class BoardTheme:
    key: str
    title: str
    light: str
    dark: str
    border: str
    accent: str
    coordinates: str
    duration_ms: int
    easing: QEasingCurve.Type
    neon: bool = False


THEMES = {
    Opponent.AMATEUR: BoardTheme('classic','Classic Green','#e5ddc4','#678474','#1c332c','#c7e8a9','#e4e8db',260,QEasingCurve.Type.InOutQuad),
    Opponent.GRANDMASTER: BoardTheme('wood','Premium Wood','#d7b080','#735039','#302018','#e6bb76','#eed6b0',320,QEasingCurve.Type.InOutCubic),
    Opponent.ADAPTIVE: BoardTheme('cyber','Cyber Blue','#1a3b57','#081725','#071323','#38d9ff','#a7eaff',300,QEasingCurve.Type.OutCubic,True),
}
