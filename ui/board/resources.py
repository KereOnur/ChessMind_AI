"""Local piece renderers and cached, shaded scene icons."""
from PySide6.QtCore import QObject, QRectF, QSize, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QGraphicsObject
from ui.widgets import ASSETS
from ui.board.demo import PieceSpec


class PieceResources(QObject):
    def __init__(self,parent=None):
        super().__init__(parent)
        self._renderers={}
        self._textures={}

    def renderer(self, theme, piece):
        key=(theme.key,piece.color,piece.kind)
        if key not in self._renderers:
            path=ASSETS/'board'/theme.key/f'{piece.color}-{piece.kind}.svg'
            renderer=QSvgRenderer(str(path),self)
            if not renderer.isValid(): raise ValueError(f'Ungültige Grafik: {path}')
            self._renderers[key]=renderer
        return self._renderers[key]

    def icon(self,theme,piece,size=26):
        pixmap=QPixmap(size,size);pixmap.fill(Qt.GlobalColor.transparent)
        p=QPainter(pixmap)
        self.paint_piece(p,QRectF(0,0,size,size),theme,piece)
        p.end()
        return pixmap

    def paint_piece(self,painter,rect,theme,piece):
        renderer=self.renderer(theme,piece)
        size=renderer.defaultSize();size.scale(rect.size().toSize(),Qt.AspectRatioMode.KeepAspectRatio)
        target=QRectF(0,0,size.width(),size.height());target.moveCenter(rect.center())
        renderer.render(painter,target)

    def wood_texture(self,light):
        if light not in self._textures:
            renderer=QSvgRenderer(str(ASSETS/'board'/f'wood-{"light" if light else "dark"}.svg'))
            if not renderer.isValid(): raise ValueError('Ungültige Holztextur')
            pixmap=QPixmap(160,160);pixmap.fill(Qt.GlobalColor.transparent)
            painter=QPainter(pixmap);renderer.render(painter);painter.end()
            self._textures[light]=pixmap
        return self._textures[light]


class PieceItem(QGraphicsObject):
    def __init__(self,piece,theme,resources):
        super().__init__()
        self.piece=piece;self.theme=theme;self.resources=resources
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setZValue(2)

    def boundingRect(self):
        return QRectF(-39,-39,78,78)

    def paint(self,painter,option,widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.resources.paint_piece(painter,QRectF(-38,-38,76,76),self.theme,self.piece)
