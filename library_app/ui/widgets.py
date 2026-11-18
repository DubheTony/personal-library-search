"""自绘小部件与通用控件。"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QAbstractButton, QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget

from ..theme import THEME_ORDER, THEMES, Theme


def clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        child = item.layout()
        if widget is not None:
            widget.deleteLater()
        elif child is not None:
            clear_layout(child)


def vline(height: int = 14) -> QFrame:
    line = QFrame()
    line.setObjectName("VLine")
    line.setFixedSize(1, height)
    return line


def elide(text: str, font: QFont, width: int) -> str:
    return QFontMetrics(font).elidedText(text, Qt.ElideRight, max(10, width))


class ClickableCard(QFrame):
    clicked = Signal()

    def __init__(self, object_name: str = "ResultCard", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
        self.setAttribute(Qt.WA_Hover, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setProperty("hovered", False)
        self.setProperty("active", False)

    def _repolish(self) -> None:
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def set_active(self, active: bool) -> None:
        if bool(self.property("active")) != bool(active):
            self.setProperty("active", bool(active))
            self._repolish()

    def enterEvent(self, event) -> None:  # noqa: N802
        self.setProperty("hovered", True)
        self._repolish()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.setProperty("hovered", False)
        self._repolish()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def make_children_transparent(self) -> None:
        for child in self.findChildren(QWidget):
            child.setAttribute(Qt.WA_TransparentForMouseEvents, True)


class RailButton(QAbstractButton):
    def __init__(self, mode: str, text: str, index: str, parent=None) -> None:
        super().__init__(parent)
        self.mode = mode
        self.text_label = text
        self.index = index
        self._theme = THEMES["drafting"]
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(64, 76)
        self.setAttribute(Qt.WA_Hover, True)
        self.setToolTip(text)
        self._hover = False

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        t = self._theme
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        if self.isChecked():
            p.fillRect(rect, QColor(t.accent))
            p.fillRect(QRect(0, 0, 2, rect.height()), QColor(t.signal))
        elif self._hover:
            p.fillRect(rect, QColor(t.accent_soft))

        checked = self.isChecked()
        glyph_color = QColor(t.on_accent if checked else t.text_dim)
        text_color = QColor(t.on_accent if checked else t.muted)
        index_color = QColor(t.on_accent if checked else t.faint)
        if checked:
            index_color.setAlpha(150)

        self._draw_icon(p, glyph_color)

        label_font = QFont(t.sans)
        label_font.setPixelSize(9)
        p.setFont(label_font)
        p.setPen(text_color)
        p.drawText(QRect(0, 37, rect.width(), 16), Qt.AlignCenter, self.text_label)

        idx_font = QFont(t.mono)
        idx_font.setPixelSize(6)
        p.setFont(idx_font)
        p.setPen(index_color)
        p.drawText(QRect(0, 55, rect.width(), 10), Qt.AlignCenter, self.index)
        p.end()

    def _draw_icon(self, p: QPainter, color: QColor) -> None:
        cx, cy = self.width() / 2, 23
        pen = QPen(color, 1.5)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        if self.mode == "folder":
            path = QPainterPath()
            path.moveTo(cx - 7, cy - 3)
            path.lineTo(cx - 2.5, cy - 3)
            path.lineTo(cx - 0.5, cy - 1)
            path.lineTo(cx + 7, cy - 1)
            path.lineTo(cx + 7, cy + 6)
            path.lineTo(cx - 7, cy + 6)
            path.closeSubpath()
            p.drawPath(path)
        elif self.mode == "search":
            p.drawEllipse(QPointF(cx - 1.5, cy - 1.5), 4.2, 4.2)
            p.drawLine(QPointF(cx + 1.7, cy + 1.7), QPointF(cx + 6, cy + 6))
        elif self.mode == "frequency":
            p.setPen(QPen(color, 2))
            p.drawLine(QPointF(cx - 5, cy + 6), QPointF(cx - 5, cy + 1))
            p.drawLine(QPointF(cx, cy + 6), QPointF(cx, cy - 4))
            p.drawLine(QPointF(cx + 5, cy + 6), QPointF(cx + 5, cy - 1))
        else:
            p.drawEllipse(QPointF(cx, cy), 6.5, 6.5)
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawEllipse(QPointF(cx, cy), 2.2, 2.2)
            p.setBrush(Qt.NoBrush)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(64, 76)


class LogoMark(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._theme = THEMES["drafting"]
        self.setFixedSize(30, 30)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        t = self._theme
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(t.accent))
        font = QFont(t.mono)
        font.setPixelSize(12)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor(t.on_accent))
        p.drawText(self.rect(), Qt.AlignCenter, "AT")
        p.fillRect(QRect(self.width() - 7, self.height() - 7, 7, 7), QColor(t.signal))
        p.end()


class ZoomControl(QFrame):
    """顶部 − / 百分比 / + 控件；点百分比恢复 100%。"""

    zoom_out = Signal()
    zoom_in = Signal()
    reset = Signal()

    def __init__(self, percent: int = 120, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ZoomBar")
        self.setFixedSize(94, 30)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(1, 0, 1, 0)
        lay.setSpacing(0)

        minus = QPushButton("−")
        minus.setObjectName("ZoomButton")
        minus.setFixedSize(22, 28)
        minus.setCursor(Qt.PointingHandCursor)
        minus.setToolTip("缩小页面")
        minus.clicked.connect(self.zoom_out)

        self.value = QPushButton(f"{percent}%")
        self.value.setObjectName("ZoomValue")
        self.value.setFixedSize(46, 28)
        self.value.setCursor(Qt.PointingHandCursor)
        self.value.setToolTip("点击恢复 100%")
        self.value.clicked.connect(self.reset)

        plus = QPushButton("+")
        plus.setObjectName("ZoomButton")
        plus.setFixedSize(22, 28)
        plus.setCursor(Qt.PointingHandCursor)
        plus.setToolTip("放大页面")
        plus.clicked.connect(self.zoom_in)

        lay.addWidget(minus)
        lay.addWidget(self.value)
        lay.addWidget(plus)

    def set_value(self, percent: int) -> None:
        self.value.setText(f"{percent}%")


class ThemeSwitcher(QWidget):
    theme_selected = Signal(str)

    def __init__(self, current: str = "drafting", parent=None) -> None:
        super().__init__(parent)
        self.current = current
        self._theme = THEMES[current]
        self.setFixedSize(118, 30)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("切换皮肤：纸质档案 / 观察台 / 制图台")

    def set_current(self, key: str, theme: Theme) -> None:
        self.current = key
        self._theme = theme
        self.update()

    def _circles(self) -> list[QPointF]:
        return [QPointF(46 + i * 29, 15) for i in range(3)]

    def paintEvent(self, event) -> None:  # noqa: N802
        t = self._theme
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        font = QFont(t.mono)
        font.setPixelSize(6)
        p.setFont(font)
        p.setPen(QColor(t.faint))
        p.drawText(QRect(0, 5, 30, 20), Qt.AlignRight | Qt.AlignVCenter, "SKIN")
        for i, key in enumerate(THEME_ORDER):
            th = THEMES[key]
            center = self._circles()[i]
            active = i == THEME_ORDER.index(self.current)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(th.accent))
            p.drawEllipse(center, 8, 8)
            if active:
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(QColor(t.text), 1.6))
                p.drawEllipse(center, 11.5, 11.5)
            label_font = QFont(th.sans)
            label_font.setPixelSize(7)
            p.setFont(label_font)
            p.setPen(QColor(th.on_accent))
            p.drawText(QRectF(center.x() - 8, center.y() - 8, 16, 16),
                       Qt.AlignCenter, ["纸", "仪", "图"][i])
            p.setFont(font)
        p.end()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        pos = event.position()
        for i, center in enumerate(self._circles()):
            if (pos.x() - center.x()) ** 2 + (pos.y() - center.y()) ** 2 <= 13 ** 2:
                key = THEME_ORDER[i]
                if key != self.current:
                    self.theme_selected.emit(key)
                return
        super().mouseReleaseEvent(event)


class Toast(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._theme = THEMES["drafting"]
        self._text = ""
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setFixedHeight(32)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def show_message(self, text: str, msec: int = 1900) -> None:
        self._text = text
        font = QFont(self._theme.sans)
        font.setPixelSize(10)
        width = QFontMetrics(font).horizontalAdvance(text) + 34
        self.setFixedWidth(max(160, width))
        self._position()
        self.show()
        self.raise_()
        self._timer.start(msec)
        self.update()

    def _position(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.move((parent.width() - self.width()) // 2, parent.height() - 48)

    def paintEvent(self, event) -> None:  # noqa: N802
        t = self._theme
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setBrush(QColor(t.panel))
        p.setPen(QPen(QColor(t.line), 1))
        p.drawRoundedRect(rect, t.radius + 1, t.radius + 1)
        p.fillRect(QRectF(1, 1, 2, self.height() - 2), QColor(t.accent))
        font = QFont(t.sans)
        font.setPixelSize(10)
        p.setFont(font)
        p.setPen(QColor(t.text))
        p.drawText(self.rect().adjusted(12, 0, -10, 0), Qt.AlignVCenter | Qt.AlignLeft, self._text)
        p.end()


class HoverLabel(QLabel):
    """给树行等位置用的紧凑标签。"""

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)


def fixed_spacer(width: int = 0, height: int = 0) -> QWidget:
    w = QWidget()
    w.setFixedSize(width, height)
    w.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    return w
