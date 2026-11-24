"""整页缩放容器。

把整个 Root 界面放进 QGraphicsScene，通过 QGraphicsView 的 transform 做
页面缩放：字体、间距、自绘控件、文档侧板一起缩放，布局在逻辑尺寸内重新排布。
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QWheelEvent
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsScene,
    QGraphicsView,
    QWidget,
)

from ..theme import Theme


class ZoomView(QGraphicsView):
    zoom_changed = Signal(int)  # 百分比，例如 115

    MIN_ZOOM = 0.85
    MAX_ZOOM = 1.50
    STEP = 0.05
    MIN_LOGICAL = QSize(1180, 680)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ZoomView")
        self.setFrameShape(QFrame.NoFrame)
        self.setAlignment(Qt.AlignCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setFocusPolicy(Qt.StrongFocus)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._widget: QWidget | None = None
        self._zoom = 1.0
        self._syncing = False

    # ---------- 装配 ----------
    def set_widget(self, widget: QWidget) -> None:
        self._widget = widget
        widget.setMinimumSize(0, 0)
        self._scene.addWidget(widget)
        self._sync_size()

    def set_theme(self, theme: Theme) -> None:
        self.setBackgroundBrush(QColor(theme.bg))
        self.viewport().update()

    def zoom_percent(self) -> int:
        return round(self._zoom * 100)

    # ---------- 缩放 ----------
    def set_zoom(self, zoom: float) -> None:
        zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, zoom))
        self._zoom = round(zoom, 2)
        self.resetTransform()
        self.scale(self._zoom, self._zoom)
        self._sync_size()
        self.zoom_changed.emit(self.zoom_percent())

    def step_zoom(self, direction: int) -> None:
        target = round(self._zoom + direction * self.STEP, 2)
        self.set_zoom(target)

    def reset_zoom(self) -> None:
        self.set_zoom(1.0)

    def scroll_home(self) -> None:
        self.horizontalScrollBar().setValue(0)
        self.verticalScrollBar().setValue(0)

    # ---------- 尺寸同步 ----------
    def _sync_size(self) -> None:
        """逻辑尺寸 = 视口 / 缩放；但不低于界面最小设计尺寸。

        这样 100% 左右时内容始终填满窗口；放大超过窗口时出现滚动条，
        不会把固定宽度的面板压坏。
        """
        if self._widget is None or self._syncing:
            return
        self._syncing = True
        try:
            viewport = self.viewport().size()
            logical_w = max(self.MIN_LOGICAL.width(), int(viewport.width() / self._zoom))
            logical_h = max(self.MIN_LOGICAL.height(), int(viewport.height() / self._zoom))
            self._widget.resize(logical_w, logical_h)
            self._scene.setSceneRect(0, 0, logical_w, logical_h)
        finally:
            self._syncing = False

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_size()

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta:
                self.step_zoom(1 if delta > 0 else -1)
            event.accept()
            return
        super().wheelEvent(event)
