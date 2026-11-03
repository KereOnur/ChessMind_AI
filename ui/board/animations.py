"""Cancellable visual motion. Completion never commits a game move or clock."""
from PySide6.QtCore import QObject, QPointF, QParallelAnimationGroup, QPropertyAnimation, QRectF, Signal
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QGraphicsObject


class NeonPulse(QGraphicsObject):
    def __init__(self,color):
        super().__init__()
        self.color=QColor(color);self.setZValue(4)

    def boundingRect(self): return QRectF(-39,-39,78,78)

    def paint(self,painter,option,widget=None):
        for width,alpha in ((12,30),(7,75),(2,230)):
            color=QColor(self.color);color.setAlpha(alpha)
            painter.setPen(QPen(color,width))
            painter.drawEllipse(QRectF(-29,-29,58,58))


class MoveAnimator(QObject):
    active_changed=Signal(bool)

    def __init__(self,scene,parent=None):
        super().__init__(parent)
        self.scene=scene;self.group=None;self.item=None;self.target=None;self.glow=None;self.motions=[]

    @property
    def busy(self): return self.group is not None

    def animate(self,item,target,theme):
        self.animate_many([(item,target)],theme)

    def animate_many(self,motions,theme):
        self.cancel()
        if not motions:return
        self.motions=[(item,QPointF(target)) for item,target in motions]
        self.item,self.target=self.motions[0]
        group=QParallelAnimationGroup(self);self.group=group
        primary_motion=None
        for item,target in self.motions:
            item.setZValue(8)
            motion=QPropertyAnimation(item,b'pos',group)
            motion.setDuration(theme.duration_ms)
            motion.setStartValue(item.pos());motion.setEndValue(target)
            motion.setEasingCurve(theme.easing);group.addAnimation(motion)
            if primary_motion is None:primary_motion=motion
        if theme.neon:
            self.glow=NeonPulse(theme.accent);self.scene.addItem(self.glow)
            self.glow.setPos(self.item.pos())
            primary_motion.valueChanged.connect(self._move_glow)
            fade=QPropertyAnimation(self.glow,b'opacity',group)
            fade.setDuration(theme.duration_ms);fade.setStartValue(.95);fade.setEndValue(0.)
            group.addAnimation(fade)
        group.finished.connect(self._finish)
        self.active_changed.emit(True);group.start()

    def _move_glow(self,value):
        if self.glow is not None: self.glow.setPos(value)

    def _finish(self):
        group=self.group
        if group is None: return
        group.stop()
        for item,target in self.motions:
            item.setPos(target);item.setZValue(2)
        if self.glow is not None:
            self.scene.removeItem(self.glow);self.glow=None
        self.group=None;self.item=None;self.target=None;self.motions=[]
        group.deleteLater()
        self.active_changed.emit(False)

    def cancel(self):
        """Stop immediately, snapping to the already committed presentation position."""
        self._finish()
