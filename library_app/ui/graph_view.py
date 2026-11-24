"""两跳关系图：纯 QPainter 绘制，不做力导向。

节点坐标由 GUI 按跳数安排；后端只给 nodes / edges。
"""
from __future__ import annotations

import math

from PySide6.QtCore import Property, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from ..models import GraphView
from ..theme import Theme


class GraphViewWidget(QWidget):
    node_clicked = Signal(int)
    LEGEND_H = 44

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._graph: GraphView | None = None
        self._theme: Theme | None = None
        self._center_title = ""
        self._preset_label = ""
        self._paths: dict[int, str] = {}
        self._positions: dict[int, QPointF] = {}
        self._node_radius = 18.0
        self._hover_id: int | None = None
        self._right_inset = 0
        self.setMouseTracking(True)
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    # ---------- 属性 ----------
    def get_right_inset(self) -> int:
        return self._right_inset

    def set_right_inset(self, value: int) -> None:
        self._right_inset = int(value)
        self.update()

    rightInset = Property(int, get_right_inset, set_right_inset)

    # ---------- 数据 ----------
    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def set_graph(self, graph: GraphView, center_title: str, preset_label: str) -> None:
        self._graph = graph
        self._center_title = center_title
        self._preset_label = preset_label
        self._hover_id = None
        self.update()

    def set_paths(self, paths: dict[int, str]) -> None:
        self._paths = paths

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(860, 620)

    # ---------- 布局 ----------
    def _available(self) -> QRectF:
        return QRectF(self.rect()).adjusted(24, 14, -24 - self._right_inset, -34)

    def _layout(self) -> tuple[dict[int, QPointF], float, float, QPointF]:
        graph = self._graph
        avail = self._available()
        if avail.width() < 80 or avail.height() < 80:
            return {}, 0.0, 0.0, avail.center()
        center = QPointF(avail.center().x(), avail.top() + avail.height() * 0.54)
        r2 = max(70.0, min(avail.width() * 0.46, avail.height() * 0.47))
        r1 = r2 * 0.55
        pos: dict[int, QPointF] = {}
        if graph is None:
            return pos, r1, r2, center
        groups = {0: [], 1: [], 2: []}
        for node in graph.nodes:
            groups.setdefault(node.hop, []).append(node.doc_id)
        if 0 in groups:
            for nid in groups[0]:
                pos[nid] = center
        for hop, radius in ((1, r1), (2, r2)):
            arr = groups.get(hop, [])
            for i, nid in enumerate(arr):
                angle = math.radians(-90 + i * 360 / max(1, len(arr)))
                pos[nid] = QPointF(center.x() + math.cos(angle) * radius,
                                   center.y() + math.sin(angle) * radius)
        return pos, r1, r2, center

    # ---------- 绘制 ----------
    def paintEvent(self, event) -> None:  # noqa: N802
        t = self._theme
        if t is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(t.canvas))
        self._draw_grid(p, t)

        pos, r1, r2, center = self._layout()
        self._positions = pos
        self._node_radius = 18.0 if self.width() > 560 else 16.0

        self._draw_crop_marks(p, t)
        self._draw_axes(p, t, center)
        self._draw_rings(p, t, center, r1, r2)
        if self._graph is not None:
            self._draw_edges(p, t, pos)
            self._draw_nodes(p, t, pos)
        else:
            self._draw_empty(p, t)
        self._draw_legend(p, t)
        self._draw_scale(p, t)
        self._draw_truncated(p, t)
        p.end()

    def _draw_grid(self, p: QPainter, t: Theme) -> None:
        minor = QColor(t.grid)
        minor.setAlpha(50 if not t.is_dark else 70)
        major = QColor(t.grid)
        major.setAlpha(90 if not t.is_dark else 115)
        w, h = self.width(), self.height()
        p.setPen(QPen(minor, 1))
        for x in range(0, w, 26):
            p.drawLine(x, 0, x, h)
        for y in range(0, h, 26):
            p.drawLine(0, y, w, y)
        p.setPen(QPen(major, 1))
        for x in range(0, w, 130):
            p.drawLine(x, 0, x, h)
        for y in range(0, h, 130):
            p.drawLine(0, y, w, y)

    def _draw_crop_marks(self, p: QPainter, t: Theme) -> None:
        color = QColor(t.accent)
        color.setAlpha(70)
        p.setPen(QPen(color, 1))
        r = QRectF(self.rect()).adjusted(14.5, 14.5, -14.5, -14.5)
        p.drawRect(r)
        color.setAlpha(110)
        p.setPen(QPen(color, 1))
        arm = 18
        for x, y, dx, dy in (
            (r.left(), r.top(), 1, 1),
            (r.right(), r.top(), -1, 1),
            (r.left(), r.bottom(), 1, -1),
            (r.right(), r.bottom(), -1, -1),
        ):
            p.drawLine(QPointF(x, y), QPointF(x + dx * arm, y))
            p.drawLine(QPointF(x, y), QPointF(x, y + dy * arm))

    def _draw_axes(self, p: QPainter, t: Theme, center: QPointF) -> None:
        pen = QPen(QColor(t.axis), 1, Qt.DashLine)
        pen.setDashPattern([1, 4])
        p.setPen(pen)
        avail = self._available()
        p.drawLine(QPointF(avail.left(), center.y()), QPointF(avail.right(), center.y()))
        p.drawLine(QPointF(center.x(), avail.top()), QPointF(center.x(), avail.bottom()))

    def _draw_rings(self, p: QPainter, t: Theme, center: QPointF, r1: float, r2: float) -> None:
        pen = QPen(QColor(t.ring), 1, Qt.DashLine)
        pen.setDashPattern([2, 6])
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(center, r1, r1)
        p.drawEllipse(center, r2, r2)

    def _draw_edges(self, p: QPainter, t: Theme, pos: dict[int, QPointF]) -> None:
        assert self._graph is not None
        for edge in self._graph.edges:
            a, b = pos.get(edge.low_id), pos.get(edge.high_id)
            if a is None or b is None:
                continue
            radius = self._node_radius + 5
            pa, pb = self._trim(a, b, radius), self._trim(b, a, radius)
            line_color = QColor(t.edge_struct if edge.has_structure else t.edge_rec)
            if not edge.has_structure:
                line_color.setAlpha(165)
            p.setPen(QPen(line_color, 1.15))
            p.drawLine(pa, pb)
            arrow_color = QColor(t.edge_rec)
            if edge.low_to_high:
                self._arrow(p, pa, pb, arrow_color)
            if edge.high_to_low:
                self._arrow(p, pb, pa, arrow_color)

    @staticmethod
    def _trim(a: QPointF, b: QPointF, pad: float) -> QPointF:
        dx, dy = b.x() - a.x(), b.y() - a.y()
        length = math.hypot(dx, dy) or 1.0
        return QPointF(a.x() + dx / length * pad, a.y() + dy / length * pad)

    @staticmethod
    def _arrow(p: QPainter, tail: QPointF, tip: QPointF, color: QColor) -> None:
        dx, dy = tip.x() - tail.x(), tip.y() - tail.y()
        length = math.hypot(dx, dy) or 1.0
        ux, uy = dx / length, dy / length
        base = QPointF(tip.x() - ux * 8, tip.y() - uy * 8)
        perp = (-uy * 3.8, ux * 3.8)
        poly = QPolygonF([
            tip,
            QPointF(base.x() + perp[0], base.y() + perp[1]),
            QPointF(base.x() - perp[0], base.y() - perp[1]),
        ])
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawPolygon(poly)

    def _draw_nodes(self, p: QPainter, t: Theme, pos: dict[int, QPointF]) -> None:
        assert self._graph is not None
        label_font = QFont(t.serif)
        label_font.setPixelSize(12)
        center_font = QFont(t.serif)
        center_font.setPixelSize(13)
        center_font.setBold(True)
        id_font = QFont(t.mono)
        id_font.setPixelSize(11)

        for node in self._graph.nodes:
            ppos = pos.get(node.doc_id)
            if ppos is None:
                continue
            is_center = node.hop == 0
            radius = 25.0 if is_center else self._node_radius
            hover = self._hover_id == node.doc_id
            fill = QColor(t.center_fill if is_center else t.node_fill)
            stroke = QColor(t.center_fill if is_center else t.node_stroke)
            if hover:
                stroke = QColor(t.signal)
            p.setBrush(fill)
            p.setPen(QPen(stroke, 2.0 if hover else 1.1))
            p.drawEllipse(ppos, radius, radius)

            p.setFont(id_font)
            p.setPen(QColor(t.center_id if is_center else t.node_id))
            p.drawText(QRectF(ppos.x() - radius, ppos.y() - radius, radius * 2, radius * 2),
                       Qt.AlignCenter, str(node.doc_id).zfill(2))

            if self._right_inset == 0 or is_center:
                self._draw_node_label(p, t, node, ppos, is_center, label_font, center_font)

    def _draw_node_label(self, p: QPainter, t: Theme, node, ppos: QPointF,
                         is_center: bool, label_font: QFont, center_font: QFont) -> None:
        title = node.title
        if len(title) > 8:
            title = title[:7] + "…"
        font = center_font if is_center else label_font
        metrics = QFontMetrics(font)
        width = metrics.horizontalAdvance(title)

        if is_center:
            x = ppos.x() - width / 2
            y = ppos.y() + 25 + 16
            color = QColor(t.center_label)
        else:
            center = self._layout()[3]
            dx, dy = ppos.x() - center.x(), ppos.y() - center.y()
            dist = math.hypot(dx, dy) or 1.0
            ux, uy = dx / dist, dy / dist
            if ux > 0.32:
                x = ppos.x() + 30
            elif ux < -0.32:
                x = ppos.x() - 30 - width
            else:
                x = ppos.x() - width / 2
            if uy < -0.72:
                y = ppos.y() - 28
            elif uy > 0.72:
                y = ppos.y() + 38
                if y > self._available().bottom() - 28:
                    y = ppos.y() - 28
            else:
                y = ppos.y() + 4
            color = QColor(t.node_label)

        path = QPainterPath()
        path.addText(x, y, font, title)
        halo = QPen(QColor(t.canvas), 3)
        halo.setJoinStyle(Qt.RoundJoin)
        p.setPen(halo)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawPath(path)

    def _draw_empty(self, p: QPainter, t: Theme) -> None:
        p.setPen(QColor(t.muted))
        font = QFont(t.serif)
        font.setPixelSize(13)
        p.setFont(font)
        p.drawText(self.rect(), Qt.AlignCenter, "没有可显示的关系")

    def _draw_legend(self, p: QPainter, t: Theme) -> None:
        avail = self._available()
        bar_h = self.LEGEND_H
        bar = QRectF(avail.left() + 2, avail.bottom() - bar_h, avail.width() - 4, bar_h)
        p.setPen(QPen(QColor(t.line), 1))
        p.setBrush(QColor(t.panel))
        p.drawRect(bar)
        p.setBrush(Qt.NoBrush)

        font = QFont(t.mono)
        font.setPixelSize(10)
        p.setFont(font)
        metrics = QFontMetrics(font)
        text_color = QColor(t.muted)
        right = bar.right() - 10
        x = bar.left() + 10
        y = bar.top() + 14

        def draw_chip(icon, label: str) -> None:
            nonlocal x
            need = 24 + metrics.horizontalAdvance(label)
            if x + need > right:
                return
            icon(x, y)
            p.setPen(text_color)
            p.drawText(QPointF(x + 24, y + 3), label)
            x += need + 16

        def icon_struct(px: float, py: float) -> None:
            p.setPen(QPen(QColor(t.edge_struct), 1.2))
            p.drawLine(QPointF(px, py), QPointF(px + 16, py))

        def icon_rec(px: float, py: float) -> None:
            p.setPen(QPen(QColor(t.edge_rec), 1.2))
            p.drawLine(QPointF(px, py), QPointF(px + 15, py))
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(t.edge_rec))
            p.drawPolygon(QPolygonF([
                QPointF(px + 20, py),
                QPointF(px + 14, py - 4),
                QPointF(px + 14, py + 4),
            ]))
            p.setBrush(Qt.NoBrush)

        def icon_ring(px: float, py: float) -> None:
            pen = QPen(QColor(t.ring), 1, Qt.DashLine)
            pen.setDashPattern([1, 2])
            p.setPen(pen)
            p.drawEllipse(QRectF(px, py - 6, 12, 12))

        def icon_center(px: float, py: float) -> None:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(t.center_fill))
            p.drawEllipse(QPointF(px + 4, py), 3.5, 3.5)
            p.setBrush(Qt.NoBrush)

        draw_chip(icon_struct, "结构边：同目录，双向")
        draw_chip(icon_rec, "推荐箭头：单向")
        draw_chip(icon_ring, "R1 / R2 两跳")
        draw_chip(icon_center, "CENTER")

        # 箭头指代说明
        p.setPen(QColor(t.text_dim))
        p.drawText(QPointF(bar.left() + 10, bar.top() + 34),
                   "箭头 = 推荐方向（来源 → 被推荐文档）；灰线 = 同目录结构")

    def _draw_scale(self, p: QPainter, t: Theme) -> None:
        avail = self._available()
        font = QFont(t.mono)
        font.setPixelSize(10)
        p.setFont(font)
        p.setPen(QColor(t.faint))
        text = "GRID 26 PX · 1:1"
        width = QFontMetrics(font).horizontalAdvance(text)
        x = avail.right() - width
        y = avail.bottom() - self.LEGEND_H - 8
        p.drawText(QPointF(x, y), text)
        p.setPen(QPen(QColor(t.ring), 1))
        tx = avail.right() - 6 * 14
        ty = avail.bottom() - self.LEGEND_H - 16
        for i in range(6):
            h = 3 if i % 2 == 0 else 6
            p.drawLine(QPointF(tx + i * 14, ty), QPointF(tx + i * 14, ty + h))

    def _draw_truncated(self, p: QPainter, t: Theme) -> None:
        if self._graph is None:
            return
        truncated = int(getattr(self._graph, "truncated", 0) or 0)
        if truncated <= 0:
            return
        avail = self._available()
        text = f"{truncated} 个节点因该圈满 10 个被截去"
        font = QFont(t.mono)
        font.setPixelSize(10)
        p.setFont(font)
        width = QFontMetrics(font).horizontalAdvance(text) + 14
        rect = QRectF(avail.right() - width - 2, avail.top() + 6, width, 20)
        p.setBrush(QColor(t.panel))
        p.setPen(QPen(QColor(t.danger), 1))
        p.drawRect(rect)
        p.setPen(QColor(t.danger))
        p.drawText(rect, Qt.AlignCenter, text)

    # ---------- 交互 ----------
    def _node_at(self, pos: QPointF) -> int | None:
        for nid, ppos in self._positions.items():
            radius = 26 if self._is_center(nid) else self._node_radius + 2
            dx, dy = pos.x() - ppos.x(), pos.y() - ppos.y()
            if dx * dx + dy * dy <= radius * radius:
                return nid
        return None

    def _is_center(self, doc_id: int) -> bool:
        if self._graph is None:
            return False
        return any(n.doc_id == doc_id and n.hop == 0 for n in self._graph.nodes)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        nid = self._node_at(event.position())
        if nid != self._hover_id:
            self._hover_id = nid
            self.setCursor(Qt.PointingHandCursor if nid is not None else Qt.ArrowCursor)
            self.update()
        if nid is not None and self._graph is not None:
            node = next((n for n in self._graph.nodes if n.doc_id == nid), None)
            if node is not None:
                path = self._paths.get(nid, "")
                tip = f"{node.title}\n#{node.doc_id:02d} · 第 {node.hop} 跳"
                if path:
                    tip += f"\n{path}"
                QToolTip.showText(event.globalPosition().toPoint(), tip, self)
        else:
            QToolTip.hideText()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover_id = None
        self.setCursor(Qt.ArrowCursor)
        QToolTip.hideText()
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        # 在 QGraphicsProxyWidget 里，只有 accept 过 press 的控件才能收到 release，
        # 不接住左键的话点节点没有任何反应。
        if event.button() == Qt.LeftButton:
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            nid = self._node_at(event.position())
            if nid is not None:
                self.node_clicked.emit(nid)
        super().mouseReleaseEvent(event)
