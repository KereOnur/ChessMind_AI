"""One orthographic 8×8 scene for every theme and player orientation."""
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QApplication, QFrame, QGraphicsRectItem, QGraphicsScene, QGraphicsView

from ui.board.animations import MoveAnimator
from ui.board.demo import square_name
from ui.board.input import MoveIntent
from ui.board.resources import PieceItem, PieceResources

CELL=80
GUTTER=28
BOARD_SIZE=8*CELL+2*GUTTER


class SquareItem(QGraphicsRectItem):
    def __init__(self,square,rect,theme,resources):
        super().__init__(rect)
        self.square=square;self.theme=theme;self.resources=resources
        self.light=(sum(square)%2)==1  # A1 is dark in either orientation.
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def paint(self,painter,option,widget=None):
        rect=self.rect()
        if self.theme.key=='wood':
            painter.drawPixmap(rect.toRect(),self.resources.wood_texture(self.light))
        else:
            painter.fillRect(rect,QColor(self.theme.light if self.light else self.theme.dark))
        if self.theme.neon:
            color=QColor(self.theme.accent);color.setAlpha(25)
            painter.setPen(QPen(color,.7));painter.drawRect(rect.adjusted(.4,.4,-.4,-.4))


class BoardView(QGraphicsView):
    input_feedback=Signal(str)

    def __init__(self,parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setBackgroundBrush(QColor('#080f1d'))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setRenderHints(QPainter.RenderHint.Antialiasing|QPainter.RenderHint.SmoothPixmapTransform)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMouseTracking(True)
        self.setAccessibleName('Schachbrett-Vorschau – freie Demo-Bewegungen')
        self.setMinimumSize(1,1)
        self.board_scene=QGraphicsScene(self)
        self.board_scene.setSceneRect(0,0,BOARD_SIZE,BOARD_SIZE)
        self.setScene(self.board_scene)
        self.resources=PieceResources(self)
        self.animator=MoveAnimator(self.board_scene,self)
        self.pieces={};self.squares=[];self.selected=None;self.selection=None
        self.position={};self.input_handler=None;self.orientation='white'
        self._drag_source=None;self._dragging=False;self._press_point=None
        self.coordinate_files=[];self.coordinate_ranks=[];self.status_marks=[]

    def configure(self,theme,orientation,position,input_handler):
        self.stop()
        self.board_scene.clear()
        self.theme=theme;self.orientation=orientation
        self.position=position;self.input_handler=input_handler
        self.pieces={};self.squares=[];self.selection=None;self.status_marks=[]
        border=self.board_scene.addRect(self.sceneRect(),QPen(QColor(theme.accent),1.4),QBrush(QColor(theme.border)))
        border.setZValue(-1)
        for file in range(8):
            for rank in range(8):
                square=(file,rank)
                center=self.square_center(square)
                item=SquareItem(square,QRectF(center.x()-CELL/2,center.y()-CELL/2,CELL,CELL),theme,self.resources)
                self.board_scene.addItem(item);self.squares.append(item)
        self._add_coordinates()
        for square,piece in position.items():
            item=PieceItem(piece,theme,self.resources)
            item.setPos(self.square_center(square));self.board_scene.addItem(item)
            self.pieces[square]=item
        self.selection=self.board_scene.addRect(0,0,CELL-6,CELL-6,QPen(QColor(theme.accent),3),QBrush(QColor(70,160,255,24)))
        self.selection.setZValue(1);self.selection.hide()
        self.fit_board()

    def square_center(self,square):
        file,rank=square
        column,row=(file,7-rank) if self.orientation=='white' else (7-file,rank)
        return QPointF(GUTTER+(column+.5)*CELL,GUTTER+(row+.5)*CELL)

    def square_at(self,point):
        column=int((point.x()-GUTTER)//CELL);row=int((point.y()-GUTTER)//CELL)
        if not(0<=column<8 and 0<=row<8): return None
        return (column,7-row) if self.orientation=='white' else (7-column,row)

    def _add_coordinates(self):
        self.coordinate_files=list('ABCDEFGH' if self.orientation=='white' else 'HGFEDCBA')
        self.coordinate_ranks=list('87654321' if self.orientation=='white' else '12345678')
        font=QFont(self.font());font.setPointSize(12);font.setBold(True)
        for index in range(8):
            for text,x,y in ((self.coordinate_files[index],GUTTER+(index+.5)*CELL,14),
                             (self.coordinate_files[index],GUTTER+(index+.5)*CELL,BOARD_SIZE-14),
                             (self.coordinate_ranks[index],14,GUTTER+(index+.5)*CELL),
                             (self.coordinate_ranks[index],BOARD_SIZE-14,GUTTER+(index+.5)*CELL)):
                item=self.board_scene.addSimpleText(text,font)
                item.setBrush(QBrush(QColor(self.theme.coordinates)))
                bounds=item.boundingRect();item.setPos(x-bounds.width()/2,y-bounds.height()/2)

    def select(self,square):
        self.selected=square
        if self.selection is None: return
        if square is None: self.selection.hide()
        else:
            center=self.square_center(square)
            self.selection.setPos(center-QPointF(CELL/2-3,CELL/2-3));self.selection.show()

    def mousePressEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton or self.animator.busy: return
        square=self.square_at(self.mapToScene(event.position().toPoint()))
        self._press_point=event.position().toPoint();self._dragging=False
        if getattr(self.input_handler,'managed_rendering',False):
            self.input_handler.press(square)
            chosen=self.input_handler.selected_square
            self.select(chosen)
            self._drag_source=square if square==chosen and square in self.pieces and self.input_handler.allows_input else None
        else:
            self._drag_source=square if square in self.pieces else None
            if self._drag_source is not None:self.select(square)
            elif square is None:self.select(None)
        event.accept()

    def mouseMoveEvent(self,event):
        if self.animator.busy or self._drag_source is None or self._press_point is None: return
        if not self._dragging and (event.position().toPoint()-self._press_point).manhattanLength()>=QApplication.startDragDistance():
            self._dragging=True
            self.pieces[self._drag_source].setZValue(8)
        if self._dragging:
            self.pieces[self._drag_source].setPos(self.mapToScene(event.position().toPoint()))
        event.accept()

    def mouseReleaseEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton or self.animator.busy: return
        square=self.square_at(self.mapToScene(event.position().toPoint()))
        source=self._drag_source if self._dragging else self.selected
        dragging=self._dragging
        self._drag_source=None;self._press_point=None;self._dragging=False
        if source is not None and (dragging or square!=source):
            self.request_move(MoveIntent(source,square,'drag' if dragging else 'click'))
        event.accept()

    def request_move(self,intent):
        if self.animator.busy or self.input_handler is None: return
        if getattr(self.input_handler,'managed_rendering',False):
            self.input_handler.request(intent)
            self.select(self.input_handler.selected_square)
            return
        item=self.pieces.get(intent.source)
        if item is None: return
        decision=self.input_handler.request(intent)
        if decision.accepted:
            self.pieces[intent.target]=self.pieces.pop(intent.source)
            # The demo placement is already committed. Animation is visual only.
            self.animator.animate(item,self.square_center(intent.target),self.theme)
            self.input_feedback.emit(f'{decision.message} {square_name(intent.source)} → {square_name(intent.target)}')
            self.select(None)
        else:
            if item.pos()!=self.square_center(intent.source):
                self.animator.animate(item,self.square_center(intent.source),self.theme)
            self.input_feedback.emit(decision.message)

    def apply_position(self,position,movements=()):
        """Render an already committed snapshot, including captures/promotions.

        No move legality is evaluated here. Secondary motion (e.g. rook) is
        supplied by the rule controller, not inferred by this scene.
        """
        self.animator.cancel()
        moving=[]
        for source,target in movements:
            item=self.pieces.pop(source,None)
            if item is not None:moving.append((item,target))
        for square,item in list(self.pieces.items()):
            if square not in position or item.piece!=position[square]:
                self.scene().removeItem(item);del self.pieces[square]
        for item,target in moving:
            old=self.pieces.pop(target,None)
            if old is not None:self.scene().removeItem(old)
            item.piece=position[target];item.update();self.pieces[target]=item
        for square,piece in position.items():
            if square not in self.pieces:
                item=PieceItem(piece,self.theme,self.resources)
                item.setPos(self.square_center(square));self.scene().addItem(item);self.pieces[square]=item
        self.position=dict(position)
        self.select(None)
        self.animator.animate_many([(item,self.square_center(target)) for item,target in moving],self.theme)

    def mark_status(self,last_move=None,check_square=None):
        for item in self.status_marks:self.scene().removeItem(item)
        self.status_marks=[]
        for square in (last_move or ()):
            center=self.square_center(square)
            item=self.scene().addRect(QRectF(center.x()-40,center.y()-40,80,80),QPen(Qt.PenStyle.NoPen),QBrush(QColor(240,198,69,65)))
            item.setZValue(.5);self.status_marks.append(item)
        if check_square is not None:
            center=self.square_center(check_square)
            item=self.scene().addRect(QRectF(center.x()-37,center.y()-37,74,74),QPen(QColor('#ff667e'),3),QBrush(QColor(245,60,80,35)))
            item.setZValue(1);self.status_marks.append(item)

    def cancel_input(self):
        if self._drag_source in self.pieces:
            self.pieces[self._drag_source].setPos(self.square_center(self._drag_source))
            self.pieces[self._drag_source].setZValue(2)
        self._drag_source=None;self._dragging=False;self._press_point=None
        self.select(self.input_handler.selected_square if getattr(self.input_handler,'managed_rendering',False) else None)

    def stop(self):
        self.animator.cancel();self.cancel_input()

    def fit_board(self):
        self.resetTransform()
        self.fitInView(self.sceneRect(),Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.cancel_input();self.fit_board()

    def hideEvent(self,event):
        self.stop();super().hideEvent(event)

    def focusOutEvent(self,event):
        self.cancel_input();super().focusOutEvent(event)

    def wheelEvent(self,event):
        event.ignore()  # No zoom/rotation controls; let the containing page scroll.
