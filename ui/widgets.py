"""Reusable presentation widgets; no game state or navigation decisions."""
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

ASSETS = Path(__file__).resolve().parents[1] / 'assets'


def label(text: str, role: str, parent=None) -> QLabel:
    widget = QLabel(text, parent)
    widget.setObjectName(role)
    widget.setWordWrap(True)
    return widget


class Artwork(QWidget):
    """Render a local SVG only on paint/resize; no animation or timer."""
    def __init__(self, filename: str, parent=None):
        super().__init__(parent)
        self.renderer = QSvgRenderer(str(ASSETS / filename), self)
        if not self.renderer.isValid():
            raise ValueError(f'Ungültige lokale Grafik: {filename}')
        self.setAccessibleName('Schachillustration')
        self.setMinimumSize(0, 140)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def sizeHint(self):
        return QSize(520, 370)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Keep the complete composition visible, including on narrow windows.
        size = self.renderer.defaultSize()
        target = QSize(size)
        target.scale(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        x, y = (self.width()-target.width())/2, (self.height()-target.height())/2
        self.renderer.render(painter, QRectF(x, y, target.width(), target.height()))


class LineIcon(QWidget):
    """Small original line icons, painted locally rather than from a font."""
    def __init__(self, kind, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setFixedSize(24, 26)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor('#cce4ff'), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        if self.kind == 'new':
            p.drawRoundedRect(4, 5, 16, 16, 4, 4)
            p.drawLine(12, 9, 12, 17)
            p.drawLine(8, 13, 16, 13)
        elif self.kind == 'resume':
            p.drawEllipse(3, 4, 18, 18)
            p.drawLine(10, 9, 16, 13)
            p.drawLine(16, 13, 10, 17)
            p.drawLine(10, 17, 10, 9)
        elif self.kind == 'stats':
            p.drawLine(4, 21, 4, 13)
            p.drawLine(11, 21, 11, 6)
            p.drawLine(18, 21, 18, 10)
        elif self.kind == 'lab':
            p.drawRoundedRect(6, 7, 13, 13, 3, 3)
            p.drawRect(10, 11, 5, 5)
            for x in (9, 16):
                p.drawLine(x, 3, x, 6)
                p.drawLine(x, 21, x, 24)
        else:
            p.drawArc(4, 6, 17, 17, 45*16, 270*16)
            p.drawLine(12, 3, 12, 12)


class NavigationButton(QPushButton):
    def __init__(self, title, subtitle, icon, primary=False, parent=None):
        super().__init__(parent)
        self.setObjectName('navButton')
        self.setProperty('primary', primary)
        self.setAccessibleName(title)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 13, 18, 13)
        layout.setSpacing(15)
        layout.addWidget(LineIcon(icon))
        texts = QVBoxLayout()
        texts.setSpacing(4)
        texts.setContentsMargins(0, 0, 0, 0)
        for text, role in ((title, 'navTitle'), (subtitle, 'navSubtitle')):
            child = label(text, role)
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            texts.addWidget(child)
        layout.addLayout(texts, 1)
        self.setMinimumHeight(76)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def sizeHint(self):
        return self.layout().sizeHint()


class ScrollablePage(QScrollArea):
    """Constrain reading width; allow vertical scrolling at every window size."""
    width_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        canvas = QWidget()
        canvas.setObjectName('pageCanvas')
        self.outer = QVBoxLayout(canvas)
        self.outer.setContentsMargins(32, 32, 32, 32)
        self.body = QWidget()
        self.body.setMinimumWidth(0)
        self.layout_body = QVBoxLayout(self.body)
        self.layout_body.setContentsMargins(0, 0, 0, 0)
        self.layout_body.setSpacing(24)
        self.outer.addWidget(self.body, 0, Qt.AlignmentFlag.AlignHCenter)
        self.outer.addStretch(1)
        self.setWidget(canvas)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        width = self.viewport().width()
        margin = 24 if width < 800 else 42
        self.outer.setContentsMargins(margin, margin, margin, margin)
        available = max(1, min(1400, width - 2*margin))
        self.body.setFixedWidth(available)
        self.width_changed.emit(available)


def back_button():
    button = QPushButton('‹  Zurück')
    button.setObjectName('backButton')
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button
