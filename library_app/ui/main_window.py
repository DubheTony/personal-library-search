"""主窗口：C 制图台布局 + 三套可切换皮肤。"""
from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Optional

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QEvent,
    QPoint,
    Property,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QKeyEvent,
    QKeySequence,
    QPalette,
    QShortcut,
    QTextBlockFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..models import (
    DocumentView,
    FrequencyReport,
    GraphView,
    LoadSummary,
    RecommendationView,
    SearchResult,
    TreeItem,
)
from ..theme import Theme, build_qss, THEMES
from .graph_view import GraphViewWidget
from .widgets import (
    ClickableCard,
    LogoMark,
    RailButton,
    ThemeSwitcher,
    Toast,
    ZoomControl,
    clear_layout,
    elide,
    vline,
)
from .zoom_view import ZoomView

PRESET_CN = {"balanced": "均衡", "structure": "结构优先", "content": "内容优先"}
PRESET_WEIGHTS = {
    "balanced": (0.3, 0.5, 0.2),
    "structure": (0.6, 0.3, 0.1),
    "content": (0.1, 0.7, 0.2),
}
TOOL_META = {
    "folder": ("目录 / DIRECTORY", "MULTI-WAY TREE"),
    "search": ("检索 / SEARCH", "INVERTED INDEX"),
    "frequency": ("词频 / FREQUENCY", "HASH · HEAP · SORT"),
    "recommend": ("推荐 / RECOMMEND", "3-WAY SCORE"),
}
RAIL_ITEMS = [
    ("folder", "目录", "00"),
    ("search", "检索", "01"),
    ("frequency", "词频", "02"),
    ("recommend", "推荐", "03"),
]


def esc(text: str) -> str:
    return html.escape(str(text), quote=True)


def html_with_spans(text: str, spans, theme: Theme) -> str:
    if not spans:
        return esc(text)
    out: list[str] = []
    pos = 0
    for span in sorted(spans, key=lambda s: s.start):
        start, end = max(pos, span.start), min(len(text), span.end)
        if start >= end:
            continue
        out.append(esc(text[pos:start]))
        out.append(
            f'<span style="background-color:{theme.mark_bg};color:{theme.mark_text};">'
            f"{esc(text[start:end])}</span>"
        )
        pos = end
    out.append(esc(text[pos:]))
    return "".join(out)


def elide_path(path: str, width: int = 360) -> str:
    if len(path) <= 46:
        return path
    return "…/" + path[-42:]


def doc_html(doc: DocumentView, terms: list[str] | None, theme: Theme,
             title_spans=None, body_spans=None) -> str:
    """把 DocumentView 转成 QTextBrowser 的富文本。"""
    title_html = html_with_spans(doc.title, title_spans or [], theme)
    paragraphs = [(m.start(), m.group()) for m in re.finditer(r"[^\n]+", doc.body)]
    body_html: list[str] = []

    # 用真实起始偏移分割段落，避免多个换行时 span 错位。
    for i, (offset, p) in enumerate(paragraphs):
        local_spans = []
        if body_spans:
            from ..models import Span

            for s in body_spans:
                if s.start >= offset and s.end <= offset + len(p):
                    local_spans.append(Span(s.start - offset, s.end - offset))
        content = html_with_spans(p, local_spans, theme)
        if i == 0 and not local_spans and content:
            first = esc(p[0])
            rest = html_with_spans(p[1:], [], theme)
            content = (
                f'<span style="font-family:{theme.serif};font-size:30px;'
                f'color:{theme.signal};">{first}</span>{rest}'
            )
        body_html.append(f'<p style="margin:0 0 13px 0;text-align:justify;">{content}</p>')

    meta = f"UTF-8 · {len(doc.body)} 字符"
    if terms:
        meta = "命中词已高亮 · " + " / ".join(terms)
    return f"""
    <html><body style="font-family:{theme.serif};color:{theme.text};">
      <div style="font-family:{theme.mono};font-size:7px;color:{theme.faint};">
        DOC #{doc.doc_id:02d} &nbsp;·&nbsp; {esc(doc.relative_path.rsplit('/', 1)[0] if '/' in doc.relative_path else '根目录')}
      </div>
      <h1 style="font-family:{theme.serif};font-size:24px;font-weight:600;
                 color:{theme.text};margin:10px 0 7px 0;">{title_html}</h1>
      <div style="font-family:{theme.mono};font-size:7px;color:{theme.faint};">
        {esc(doc.relative_path)} &nbsp;·&nbsp; {esc(meta)}
      </div>
      <div style="height:14px;"></div>
      <div style="font-family:{theme.serif};font-size:14px;color:{theme.text};">
        {''.join(body_html)}
      </div>
      <div style="font-family:{theme.mono};font-size:6.5px;color:{theme.faint};
                  margin-top:22px;padding-top:10px;border-top:1px solid {theme.line_soft};">
        SAMPLE LIBRARY · READ ONLY &nbsp;&nbsp; SPAN [start, end)
      </div>
    </body></html>
    """


class DocPanel(QFrame):
    close_requested = Signal()
    center_requested = Signal()
    freq_requested = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("DocPanel")
        self.setFixedWidth(448)
        self._theme = THEMES["drafting"]
        self._open = False
        self._anim = QPropertyAnimation(self, b"pos", self)
        self._anim.setDuration(270)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        head = QFrame()
        head.setObjectName("DocHead")
        head.setFixedHeight(46)
        hl = QHBoxLayout(head)
        hl.setContentsMargins(16, 0, 8, 0)
        hl.setSpacing(8)
        self.title_label = QLabel("DOCUMENT")
        self.title_label.setObjectName("DocLabel")
        self.path_label = QLabel("")
        self.path_label.setObjectName("DocLabel")
        self.path_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.actions = QWidget()
        self.actions.setObjectName("DocActions")
        self.actions_lay = QHBoxLayout(self.actions)
        self.actions_lay.setContentsMargins(0, 0, 0, 0)
        self.actions_lay.setSpacing(8)
        close = QPushButton("×")
        close.setObjectName("CloseButton")
        close.setFixedSize(26, 26)
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(self.close_requested)
        hl.addWidget(self.title_label)
        hl.addWidget(self.path_label, 1)
        hl.addWidget(self.actions)
        hl.addWidget(close)
        lay.addWidget(head)

        self.text = QTextBrowser()
        self.text.setObjectName("DocText")
        self.text.setFrameShape(QFrame.NoFrame)
        self.text.setOpenExternalLinks(False)
        self.text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.text.document().setDocumentMargin(0)
        body_wrap = QWidget()
        bl = QVBoxLayout(body_wrap)
        bl.setContentsMargins(28, 22, 28, 40)
        bl.setSpacing(0)
        bl.addWidget(self.text)
        lay.addWidget(body_wrap, 1)

        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(46)
        self.shadow.setOffset(-18, 0)
        self.setGraphicsEffect(self.shadow)
        self.hide()

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        color = QColor(theme.shadow)
        color.setAlpha(80 if not theme.is_dark else 150)
        self.shadow.setColor(color)

    def set_content(self, doc: DocumentView, terms: list[str] | None, is_center: bool,
                    hits=None) -> None:
        title_spans = [h.span for h in (hits or []) if getattr(h, "field", "") == "title"]
        body_spans = [h.span for h in (hits or []) if getattr(h, "field", "") == "body"]
        self.path_label.setText(elide_path(doc.relative_path, 250))
        self.path_label.setToolTip(doc.relative_path)

        clear_layout(self.actions_lay)
        if is_center:
            badge = QLabel("● CENTER")
            badge.setObjectName("CenterBadge")
            self.actions_lay.addWidget(badge)
        else:
            btn = QPushButton("设为中心")
            btn.setObjectName("Primary")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(self.center_requested)
            self.actions_lay.addWidget(btn)
        freq = QPushButton("本文词频")
        freq.setObjectName("Ghost")
        freq.setCursor(Qt.PointingHandCursor)
        freq.clicked.connect(self.freq_requested)
        self.actions_lay.addWidget(freq)

        self.text.setHtml(doc_html(doc, terms, self._theme, title_spans, body_spans))
        # QTextDocument 的行距设置比 HTML line-height 更可靠。
        cursor = QTextCursor(self.text.document())
        cursor.select(QTextCursor.Document)
        fmt = QTextBlockFormat()
        fmt.setLineHeight(178.0, QTextBlockFormat.ProportionalHeight.value)
        cursor.mergeBlockFormat(fmt)
        cursor.clearSelection()
        cursor.setPosition(0)
        self.text.setTextCursor(cursor)
        self.text.verticalScrollBar().setValue(0)

    def fit(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        height = parent.height()
        x = parent.width() - self.width() if self._open else parent.width()
        if self._anim.state() == QAbstractAnimation.Running:
            return
        self.setGeometry(x, 0, self.width(), height)

    def slide_in(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        if self._open and self.isVisible():
            self.fit()
            return
        self._open = True
        self.setGeometry(parent.width(), 0, self.width(), parent.height())
        self.show()
        self.raise_()
        self._anim.stop()
        self._anim.setStartValue(QPoint(parent.width(), 0))
        self._anim.setEndValue(QPoint(parent.width() - self.width(), 0))
        self._anim.start()

    def slide_out(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self._open = False
        self._anim.stop()
        self._anim.setStartValue(self.pos())
        self._anim.setEndValue(QPoint(parent.width(), 0))
        self._anim.start()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.fit()


class CanvasArea(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("CanvasArea")
        self._theme = THEMES["drafting"]
        self._doc_open = False
        self._graph_data: GraphView | None = None
        self._inset_value = 0
        self._inset_anim = QPropertyAnimation(self, b"insetTarget", self)
        self._inset_anim.setDuration(270)
        self._inset_anim.setEasingCurve(QEasingCurve.OutCubic)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        head = QFrame()
        head.setObjectName("MapHead")
        head.setFixedHeight(86)
        hl = QHBoxLayout(head)
        hl.setContentsMargins(28, 12, 26, 8)
        hl.setSpacing(20)

        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(2)
        kick_row = QHBoxLayout()
        kick_row.setContentsMargins(0, 0, 0, 0)
        kick_row.setSpacing(8)
        kick = QFrame()
        kick.setObjectName("KickLine")
        kick.setFixedSize(18, 1)
        self.map_kicker = QLabel("RELATION MAP · BFS 2 HOPS")
        self.map_kicker.setObjectName("MapKicker")
        kick_row.addWidget(kick, 0, Qt.AlignVCenter)
        kick_row.addWidget(self.map_kicker)
        kick_row.addStretch()
        left.addLayout(kick_row)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(9)
        self.map_title = QLabel("两跳关系图")
        self.map_title.setObjectName("MapTitle")
        self.map_title_en = QLabel("邻接表 + 队列")
        self.map_title_en.setObjectName("MapTitleEn")
        title_row.addWidget(self.map_title, 0, Qt.AlignBottom)
        title_row.addWidget(self.map_title_en, 0, Qt.AlignBottom)
        title_row.addStretch()
        left.addLayout(title_row)

        self.center_line = QLabel("")
        self.center_line.setObjectName("MapCenter")
        self.center_line.setTextFormat(Qt.RichText)
        left.addWidget(self.center_line)
        left.addStretch()
        hl.addLayout(left, 1)

        self.stats_box = QFrame()
        self.stats_box.setObjectName("StatsBox")
        sl = QHBoxLayout(self.stats_box)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)
        self.stat_values: dict[str, QLabel] = {}
        for label, key in (("NODES", "nodes"), ("EDGES", "edges"), ("H1 / H2", "hops"), ("TRUNC", "trunc")):
            cell = QFrame()
            cell.setObjectName("StatCell")
            cl = QVBoxLayout(cell)
            cl.setContentsMargins(9, 6, 9, 5)
            cl.setSpacing(1)
            cap = QLabel(label)
            cap.setObjectName("StatLabel")
            val = QLabel("0")
            val.setObjectName("StatValueHot" if key == "trunc" else "StatValue")
            cl.addWidget(cap)
            cl.addWidget(val)
            sl.addWidget(cell)
            self.stat_values[key] = val
        hl.addWidget(self.stats_box, 0, Qt.AlignTop)
        root.addWidget(head)

        self.graph = GraphViewWidget()
        root.addWidget(self.graph, 1)

        self.doc_panel = DocPanel(self)
        self.doc_panel.raise_()

    # ---------- 动画属性 ----------
    def get_inset_target(self) -> int:
        return self._inset_value

    def set_inset_target(self, value: int) -> None:
        self._inset_value = int(value)
        self.graph.set_right_inset(self._inset_value)

    insetTarget = Property(int, get_inset_target, set_inset_target)

    # ---------- 接口 ----------
    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.graph.set_theme(theme)
        self.doc_panel.set_theme(theme)

    def set_graph(self, graph: GraphView, center_title: str, preset_label: str,
                  paths: dict[int, str]) -> None:
        self._graph_data = graph
        self.graph.set_graph(graph, center_title, preset_label)
        self.graph.set_paths(paths)
        hops = {0: 0, 1: 0, 2: 0}
        for node in graph.nodes:
            hops[node.hop] = hops.get(node.hop, 0) + 1
        self.stat_values["nodes"].setText(str(len(graph.nodes)))
        self.stat_values["edges"].setText(str(len(graph.edges)))
        self.stat_values["hops"].setText(f"{hops.get(1, 0)}/{hops.get(2, 0)}")
        trunc = int(getattr(graph, "truncated", 0) or 0)
        self.stat_values["trunc"].setText(str(trunc))
        self.center_line.setText(
            f'<span style="color:{self._theme.muted};">CENTER</span> '
            f'<b style="font-family:{self._theme.serif};font-size:11px;color:{self._theme.text};">'
            f"{esc(center_title)}</b>"
            f'<span style="color:{self._theme.muted};"> · 预设 {esc(preset_label)} · 每圈最多 10 个节点</span>'
        )

    def set_doc_open(self, open_: bool) -> None:
        if self._doc_open == open_:
            if open_:
                self.doc_panel.raise_()
            return
        self._doc_open = open_
        self.stats_box.setVisible(not open_)
        target = self.doc_panel.width() if open_ else 0
        self._inset_anim.stop()
        self._inset_anim.setStartValue(self._inset_value)
        self._inset_anim.setEndValue(target)
        self._inset_anim.start()
        if open_:
            self.doc_panel.slide_in()
        else:
            self.doc_panel.slide_out()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.doc_panel.fit()


class MainWindow(QMainWindow):
    def __init__(self, service) -> None:
        super().__init__()
        self.service = service
        self.summary: LoadSummary = service.load()
        self.tree_root: TreeItem = service.get_tree()
        self.all_docs: list[DocumentView] = service.list_folder("")
        self.docs_by_id = {d.doc_id: d for d in self.all_docs}
        self.paths = {d.doc_id: d.relative_path for d in self.all_docs}

        self.theme_key = "drafting"
        self.theme = THEMES[self.theme_key]
        self.zoom = 1.20
        self._zoom_initialized = False
        self.mode = "recommend"
        self.preset = "balanced"
        self.folder = ""
        self.doc_id: Optional[int] = 5 if 5 in self.docs_by_id else (self.all_docs[0].doc_id if self.all_docs else None)
        self.center_id = self.doc_id
        self.query = ""
        self.results: list[SearchResult] = []
        self.selected_result_id: Optional[int] = None
        self.highlight_terms: Optional[list[str]] = None
        self.freq_scope = "doc"
        self.freq_algo = "top"
        self.doc_open = False
        self.expanded = self._all_folder_paths()
        self._rec_view: Optional[RecommendationView] = None
        self._freq_report: Optional[FrequencyReport] = None
        self._freq_key = None
        self._all_report = self.service.analyze_frequency(folder_path="", k=10)
        self._issue_popup: Optional[QFrame] = None
        self._tree_scroll: Optional[QScrollArea] = None

        self.setWindowTitle("ATLAS · 个人资料库")
        self.setMinimumSize(1180, 680)
        screen = QApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            # 大屏默认 120%，小屏默认 100%，避免一启动就出现滚动条。
            if avail.width() < 1400 or avail.height() < 780:
                self.zoom = 1.0
            else:
                self.zoom = 1.2
            self.resize(
                min(1560, max(1180, avail.width() - 20)),
                min(960, max(680, avail.height() - 40)),
            )
        else:
            self.zoom = 1.2
            self.resize(1440, 900)
        self._build()
        self._apply_theme(self.theme_key, first=True)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    # ============================================================
    # 构建
    # ============================================================
    def _build(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        self.root = root
        lay = QVBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        lay.addWidget(self._build_topbar())

        body = QWidget()
        body_lay = QHBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(0)
        body_lay.addWidget(self._build_rail())

        self.panel = QFrame()
        self.panel.setObjectName("Panel")
        self.panel.setFixedWidth(318)
        pl = QVBoxLayout(self.panel)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(0)
        self.panel_head = QFrame()
        self.panel_head.setObjectName("PanelHead")
        self.panel_head.setFixedHeight(44)
        ph = QHBoxLayout(self.panel_head)
        ph.setContentsMargins(16, 0, 16, 0)
        ph.setSpacing(8)
        self.panel_title = QLabel("推荐 / RECOMMEND")
        self.panel_title.setObjectName("PanelTitle")
        self.panel_hint = QLabel("3-WAY SCORE")
        self.panel_hint.setObjectName("PanelHint")
        ph.addWidget(self.panel_title)
        ph.addStretch()
        ph.addWidget(self.panel_hint)
        pl.addWidget(self.panel_head)

        self.panel_scroll = QScrollArea()
        self.panel_scroll.setWidgetResizable(True)
        self.panel_scroll.setFrameShape(QFrame.NoFrame)
        self.panel_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.panel_body = QWidget()
        self.panel_body.setObjectName("PanelBody")
        self.panel_body_lay = QVBoxLayout(self.panel_body)
        self.panel_body_lay.setContentsMargins(16, 14, 16, 24)
        self.panel_body_lay.setSpacing(0)
        self.panel_scroll.setWidget(self.panel_body)
        pl.addWidget(self.panel_scroll, 1)
        body_lay.addWidget(self.panel)

        self.canvas = CanvasArea()
        self.canvas.graph.node_clicked.connect(self._on_graph_node)
        self.canvas.doc_panel.close_requested.connect(self.close_doc)
        self.canvas.doc_panel.center_requested.connect(self.recenter)
        self.canvas.doc_panel.freq_requested.connect(self.open_freq_for_doc)
        body_lay.addWidget(self.canvas, 1)
        lay.addWidget(body, 1)

        lay.addWidget(self._build_status())

        self.toast = Toast(root)
        self.toast.set_theme(self.theme)

        # 整页缩放容器：Root 作为 proxy widget 放进 QGraphicsScene。
        self.view = ZoomView(self)
        self.view.set_widget(root)
        self.setCentralWidget(self.view)
        self.view.zoom_changed.connect(self._on_zoom_changed)
        self.view.set_zoom(self.zoom)
        self._zoom_initialized = True

        # 快捷键
        self.search_input.returnPressed.connect(self.perform_search)
        self.search_btn.clicked.connect(self.perform_search)
        self._build_shortcuts()

    def _build_topbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(58)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(16)

        self.logo = LogoMark()
        lay.addWidget(self.logo)

        brand = QWidget()
        bl = QVBoxLayout(brand)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(1)
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(9)
        en = QLabel("ATLAS")
        en.setObjectName("BrandTitle")
        cn = QLabel("个人资料库")
        cn.setObjectName("BrandCn")
        title_row.addWidget(en)
        title_row.addWidget(cn)
        title_row.addStretch()
        bl.addLayout(title_row)
        sub = QLabel("PERSONAL ARCHIVE · SHEET 01 · OFFLINE")
        sub.setObjectName("BrandSub")
        bl.addWidget(sub)
        brand.setFixedWidth(280)
        lay.addWidget(brand)

        self.zoom_control = ZoomControl(round(self.zoom * 100))
        self.zoom_control.zoom_out.connect(self.zoom_out)
        self.zoom_control.zoom_in.connect(self.zoom_in)
        self.zoom_control.reset.connect(self.reset_zoom)
        lay.addWidget(self.zoom_control)

        search = QFrame()
        search.setObjectName("TopSearch")
        search.setFixedHeight(34)
        search.setMinimumWidth(300)
        search.setMaximumWidth(600)
        search.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        sl = QHBoxLayout(search)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)
        prefix = QLabel("检索 / FIND")
        prefix.setObjectName("SearchPrefix")
        prefix.setFixedHeight(32)
        self.search_input = QLineEdit()
        self.search_input.setObjectName("SearchInput")
        self.search_input.setPlaceholderText("关键词，空格分隔")
        self.search_input.setToolTip("例如：检索 索引")
        self.search_input.setClearButtonEnabled(False)
        self.search_btn = QPushButton("查询")
        self.search_btn.setObjectName("SearchButton")
        self.search_btn.setFixedSize(58, 32)
        self.search_btn.setCursor(Qt.PointingHandCursor)
        sl.addWidget(prefix)
        sl.addWidget(self.search_input, 1)
        sl.addWidget(self.search_btn)
        lay.addWidget(search, 2)
        lay.addStretch(1)

        stats = QWidget()
        stats.setFixedWidth(200)
        st = QHBoxLayout(stats)
        st.setContentsMargins(0, 0, 0, 0)
        st.setSpacing(9)
        roots = sum(1 for c in self.tree_root.children if c.kind == "folder")
        self.doc_stat = QLabel(f"{self.summary.document_count} DOCS")
        self.doc_stat.setObjectName("TopStat")
        self.root_stat = QLabel(f"{roots} ROOTS")
        self.root_stat.setObjectName("TopStat")
        self.issue_btn = QPushButton(f"{len(self.summary.issues)} ISSUE")
        self.issue_btn.setObjectName("IssueButton")
        self.issue_btn.setFixedHeight(20)
        self.issue_btn.setCursor(Qt.PointingHandCursor)
        self.issue_btn.clicked.connect(self.show_issues)
        st.addWidget(self.doc_stat, 0, Qt.AlignVCenter)
        st.addWidget(vline(), 0, Qt.AlignVCenter)
        st.addWidget(self.root_stat, 0, Qt.AlignVCenter)
        st.addWidget(vline(), 0, Qt.AlignVCenter)
        st.addWidget(self.issue_btn, 0, Qt.AlignVCenter)
        st.addStretch()
        lay.addWidget(stats)

        self.theme_switcher = ThemeSwitcher(self.theme_key)
        self.theme_switcher.theme_selected.connect(self._apply_theme)
        lay.addWidget(self.theme_switcher)
        return bar

    def _build_rail(self) -> QFrame:
        rail = QFrame()
        rail.setObjectName("Rail")
        rail.setFixedWidth(64)
        rl = QVBoxLayout(rail)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        self.rail_group = QButtonGroup(self)
        self.rail_group.setExclusive(True)
        self.rail_buttons: dict[str, RailButton] = {}
        for mode, text, idx in RAIL_ITEMS:
            btn = RailButton(mode, text, idx)
            btn.set_theme(self.theme)
            btn.clicked.connect(lambda checked=False, m=mode: self.set_mode(m))
            rl.addWidget(btn)
            self.rail_group.addButton(btn)
            self.rail_buttons[mode] = btn
        rl.addStretch(1)
        foot = QLabel("OFFLINE\nv0.9")
        foot.setObjectName("RailFoot")
        foot.setAlignment(Qt.AlignCenter)
        rl.addWidget(foot)
        rl.addSpacing(10)
        return rail

    def _build_status(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("StatusBar")
        bar.setFixedHeight(28)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(16)
        self.status_left = QLabel("")
        self.status_left.setObjectName("StatusText")
        self.status_left.setTextFormat(Qt.RichText)
        self.status_right = QLabel("")
        self.status_right.setObjectName("StatusText")
        self.status_right.setTextFormat(Qt.RichText)
        lay.addWidget(self.status_left, 1)
        lay.addWidget(self.status_right)
        return bar

    # ============================================================
    # 主题
    # ============================================================
    def _apply_theme(self, key: str, first: bool = False) -> None:
        self.theme_key = key
        self.theme = THEMES[key]
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(build_qss(self.theme))
        self.logo.set_theme(self.theme)
        for btn in self.rail_buttons.values():
            btn.set_theme(self.theme)
        self.theme_switcher.set_current(key, self.theme)
        self.canvas.set_theme(self.theme)
        self.view.set_theme(self.theme)
        self.toast.set_theme(self.theme)
        pal = self.search_input.palette()
        pal.setColor(QPalette.PlaceholderText, QColor(self.theme.faint))
        self.search_input.setPalette(pal)
        if self._issue_popup is not None:
            self._issue_popup.close()
            self._issue_popup.deleteLater()
            self._issue_popup = None
        self._refresh_all(preserve_panel_scroll=True)
        if not first:
            self.toast.show_message(f"皮肤 · {self.theme.cn}")

    # ============================================================
    # 数据刷新
    # ============================================================
    def _refresh_all(self, preserve_panel_scroll: bool = True) -> None:
        if self.center_id is None and self.doc_id is not None:
            self.center_id = self.doc_id
        if self.center_id is not None:
            self._rec_view = self.service.recommend(self.center_id, self.preset)
            self.canvas.set_graph(
                self._rec_view.graph,
                self.docs_by_id[self.center_id].title,
                PRESET_CN[self.preset],
                self.paths,
            )
        self._sync_rail()
        self.panel_title.setText(TOOL_META[self.mode][0])
        self.panel_hint.setText(TOOL_META[self.mode][1])
        self._refresh_panel(preserve_scroll=preserve_panel_scroll)
        if self.doc_open and self.doc_id is not None:
            self._update_doc_panel()
        self.canvas.set_doc_open(self.doc_open)
        self._update_status()
        self.doc_stat.setText(f"{self.summary.document_count} DOCS")

    def _sync_rail(self) -> None:
        btn = self.rail_buttons.get(self.mode)
        if btn is not None and not btn.isChecked():
            btn.setChecked(True)
            btn.update()

    def _update_doc_panel(self) -> None:
        if self.doc_id is None:
            return
        doc = self.service.get_document(self.doc_id)
        hits = None
        if self.highlight_terms:
            results = self.service.search(self.query)
            hit_doc = next((r for r in results if r.doc_id == self.doc_id), None)
            hits = hit_doc.hits if hit_doc else None
        self.canvas.doc_panel.set_content(
            doc,
            self.highlight_terms,
            self.doc_id == self.center_id,
            hits=hits,
        )

    def _update_status(self) -> None:
        t = self.theme
        issues = len(self.summary.issues)
        current = ""
        if self.doc_id is not None:
            current = f'CURRENT <b style="color:{t.text_dim};">#{self.doc_id:02d} {esc(self.docs_by_id[self.doc_id].title)}</b>'
        self.status_left.setText(
            f'<span style="color:{t.faint};">ROOT</span> '
            f'{"样例库（演示）" if getattr(self.service, "is_demo", False) else "样例库"} '
            f'<span style="color:{t.faint};">/</span> DOCS <b style="color:{t.text_dim};">{self.summary.document_count}</b> '
            f'<span style="color:{t.faint};">/</span> ROOTS <b style="color:{t.text_dim};">'
            f'{sum(1 for c in self.tree_root.children if c.kind == "folder")}</b> '
            f'<span style="color:{t.faint};">/</span> <span style="color:{t.danger};">ISSUES {issues}</span> '
            f'<span style="color:{t.faint};">/</span> {current}'
        )
        self.status_left.setToolTip(self.summary.root_path)
        self.status_right.setText(
            f'Q <b style="color:{t.accent};">{self._all_report.quick_ms:.2f}ms</b> / '
            f'M <b style="color:{t.accent};">{self._all_report.merge_ms:.2f}ms</b> '
            f'<span style="color:{t.faint};">·</span> jieba 精确模式 '
            f'<span style="color:{t.faint};">·</span> 停用词 128 '
            f'<span style="color:{t.faint};">·</span> 哈希桶 64'
        )

    # ============================================================
    # 面板内容
    # ============================================================
    def _refresh_panel(self, preserve_scroll: bool = True) -> None:
        panel_value = self.panel_scroll.verticalScrollBar().value() if preserve_scroll else 0
        tree_value = 0
        try:
            if self._tree_scroll is not None:
                tree_value = self._tree_scroll.verticalScrollBar().value()
        except RuntimeError:
            self._tree_scroll = None
        clear_layout(self.panel_body_lay)
        self._tree_scroll = None
        if self.mode == "folder":
            self._build_folder_panel()
        elif self.mode == "search":
            self._build_search_panel()
        elif self.mode == "frequency":
            self._build_frequency_panel()
        else:
            self._build_recommend_panel()
        self.panel_body_lay.addStretch(1)

        new_tree_scroll = self._tree_scroll

        def restore():
            try:
                if preserve_scroll:
                    self.panel_scroll.verticalScrollBar().setValue(panel_value)
                if new_tree_scroll is not None:
                    new_tree_scroll.verticalScrollBar().setValue(tree_value)
            except RuntimeError:
                pass

        QTimer.singleShot(0, restore)

    @staticmethod
    def _section_title(text: str, en: str) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 9)
        lay.setSpacing(8)
        title = QLabel(text)
        title.setObjectName("SectionTitle")
        hint = QLabel(en)
        hint.setObjectName("Kicker")
        lay.addWidget(title)
        lay.addStretch()
        lay.addWidget(hint)
        return w

    @staticmethod
    def _note(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("Note")
        label.setWordWrap(True)
        return label

    def _empty_state(self, glyph: str, title: str, hint: str) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 40, 0, 30)
        lay.setSpacing(6)
        g = QLabel(glyph)
        g.setObjectName("EmptyGlyph")
        g.setAlignment(Qt.AlignCenter)
        t = QLabel(title)
        t.setObjectName("EmptyTitle")
        t.setAlignment(Qt.AlignCenter)
        h = QLabel(hint)
        h.setObjectName("EmptyHint")
        h.setAlignment(Qt.AlignCenter)
        h.setWordWrap(True)
        lay.addWidget(g)
        lay.addWidget(t)
        lay.addWidget(h)
        return w

    # ---------- 目录 ----------
    def _build_folder_panel(self) -> None:
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.panel_body_lay.addWidget(box)

        tree_head = QHBoxLayout()
        tree_head.setContentsMargins(0, 0, 0, 6)
        tree_head.setSpacing(8)
        th = QLabel("TREE / 目录树")
        th.setObjectName("Kicker")
        td = QLabel("DFS")
        td.setObjectName("MonoFaint")
        tree_head.addWidget(th)
        tree_head.addStretch()
        tree_head.addWidget(td)
        lay.addLayout(tree_head)

        self._tree_scroll = QScrollArea()
        self._tree_scroll.setObjectName("TreeScroll")
        self._tree_scroll.setWidgetResizable(True)
        self._tree_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._tree_scroll.setFrameShape(QFrame.NoFrame)
        self._tree_scroll.setFixedHeight(300)
        tree_host = QWidget()
        tree_lay = QVBoxLayout(tree_host)
        tree_lay.setContentsMargins(0, 0, 0, 4)
        tree_lay.setSpacing(0)
        self._tree_host_lay = tree_lay
        self._fill_tree(tree_lay)
        tree_lay.addStretch(1)
        self._tree_scroll.setWidget(tree_host)
        lay.addWidget(self._tree_scroll)

        docs = self.service.list_folder(self.folder)
        name = "全部文档" if self.folder == "" else self.folder.rsplit("/", 1)[-1]
        head = QHBoxLayout()
        head.setContentsMargins(0, 12, 0, 4)
        head.setSpacing(8)
        title = QLabel(f"{name}")
        title.setObjectName("SectionTitle")
        count = QLabel(f"{len(docs)} DOCS")
        count.setObjectName("MonoMuted")
        head.addWidget(title)
        head.addStretch()
        head.addWidget(count)
        lay.addLayout(head)

        note = QLabel(
            "全库共 %d 篇，按 doc_id 升序。" % len(docs)
            if self.folder == ""
            else "该目录及子目录共 %d 篇。目录只改变列表范围，不改变推荐候选集。" % len(docs)
        )
        note.setObjectName("Note")
        note.setWordWrap(True)
        lay.addWidget(note)
        lay.addSpacing(4)

        if not docs:
            lay.addWidget(self._empty_state("空", "该目录没有文档", "换一个目录，或查看全库。"))
            return

        for doc in docs:
            card = ClickableCard("DocRow")
            cl = QHBoxLayout(card)
            cl.setContentsMargins(4, 8, 6, 8)
            cl.setSpacing(8)
            num = QLabel(f"{doc.doc_id:02d}")
            num.setObjectName("MonoFaint")
            num.setFixedWidth(18)
            mid = QVBoxLayout()
            mid.setContentsMargins(0, 0, 0, 0)
            mid.setSpacing(2)
            title = QLabel(doc.title)
            title.setObjectName("RowTitle")
            path = QLabel(doc.relative_path)
            path.setObjectName("RowPath")
            mid.addWidget(title)
            mid.addWidget(path)
            go = QLabel("›")
            go.setObjectName("MonoFaint")
            cl.addWidget(num)
            cl.addLayout(mid, 1)
            cl.addWidget(go)
            card.set_active(doc.doc_id == self.doc_id)
            card.clicked.connect(lambda d=doc.doc_id: self.open_doc(d))
            card.make_children_transparent()
            lay.addWidget(card)

    def _fill_tree(self, layout: QVBoxLayout) -> None:
        def walk(node: TreeItem, depth: int) -> None:
            for child in node.children:
                if child.kind == "folder":
                    expanded = child.relative_path in self.expanded
                    row = ClickableCard("TreeRow")
                    row.setProperty("kind", "folder")
                    row.set_active(child.relative_path == self.folder)
                    rl = QHBoxLayout(row)
                    rl.setContentsMargins(6 + depth * 12, 0, 6, 0)
                    rl.setSpacing(5)
                    caret = QToolButton()
                    caret.setObjectName("Caret")
                    caret.setText("▾" if expanded else "▸")
                    caret.setFixedWidth(13)
                    caret.setCursor(Qt.PointingHandCursor)
                    caret.clicked.connect(lambda checked=False, p=child.relative_path: self.toggle_folder(p))
                    name = QLabel(child.name)
                    name.setObjectName("TreeName")
                    name.setToolTip(child.relative_path)
                    count = QLabel(str(self._folder_count(child)))
                    count.setObjectName("TreeCount")
                    rl.addWidget(caret)
                    rl.addWidget(name, 1)
                    rl.addWidget(count)
                    row.setFixedHeight(25)
                    row.clicked.connect(lambda p=child.relative_path: self.select_folder(p))
                    # 只让标签透明，caret 仍可点。
                    name.setAttribute(Qt.WA_TransparentForMouseEvents, True)
                    count.setAttribute(Qt.WA_TransparentForMouseEvents, True)
                    layout.addWidget(row)
                    if expanded:
                        walk(child, depth + 1)
                else:
                    row = ClickableCard("TreeRow")
                    row.setProperty("kind", "doc")
                    row.set_active(child.doc_id == self.doc_id)
                    rl = QHBoxLayout(row)
                    rl.setContentsMargins(6 + depth * 12 + 13, 0, 6, 0)
                    rl.setSpacing(5)
                    dot = QLabel("•")
                    dot.setObjectName("Dot")
                    dot.setFixedWidth(7)
                    name = QLabel(child.name)
                    name.setObjectName("TreeName")
                    name.setToolTip(child.relative_path)
                    rl.addWidget(dot)
                    rl.addWidget(name, 1)
                    row.setFixedHeight(25)
                    row.clicked.connect(lambda d=child.doc_id: self.open_doc(d))
                    dot.setAttribute(Qt.WA_TransparentForMouseEvents, True)
                    name.setAttribute(Qt.WA_TransparentForMouseEvents, True)
                    layout.addWidget(row)

        walk(self.tree_root, 0)

    def _folder_count(self, node: TreeItem) -> int:
        if node.kind == "document":
            return 1
        return sum(self._folder_count(c) for c in node.children)

    def _all_folder_paths(self) -> set[str]:
        paths: set[str] = set()

        def walk(node: TreeItem) -> None:
            for child in node.children:
                if child.kind == "folder":
                    paths.add(child.relative_path)
                    walk(child)

        walk(self.tree_root)
        return paths

    # ---------- 检索 ----------
    def _build_search_panel(self) -> None:
        q = self.query.strip()
        if not q:
            self.panel_body_lay.addWidget(
                self._empty_state("检", "在顶部输入关键词后回车", "多词用空格分隔，例如「检索 索引」。\n所有查询词都命中才算一条结果。")
            )
            return
        if not self.results:
            self.panel_body_lay.addWidget(
                self._empty_state("无", "没有检索结果，请输入或调整关键词", "所有查询词必须同时出现；可减少关键词或去掉停用词。")
            )
            return

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 8)
        head.setSpacing(8)
        qlabel = QLabel(f"「{q}」")
        qlabel.setObjectName("SectionTitle")
        info = QLabel(f"{len(self.results)} RESULTS · DOC_ID ASC")
        info.setObjectName("MonoFaint")
        head.addWidget(qlabel)
        head.addStretch()
        head.addWidget(info)
        self.panel_body_lay.addLayout(head)

        for r in self.results:
            card = ClickableCard("ResultCard")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(8, 10, 6, 10)
            cl.setSpacing(4)
            top = QHBoxLayout()
            top.setContentsMargins(0, 0, 0, 0)
            top.setSpacing(6)
            title = QLabel(self._title_html(r))
            title.setObjectName("RowTitle")
            title.setTextFormat(Qt.RichText)
            title.setWordWrap(True)
            badge = QLabel(f"{r.match_count} HITS")
            badge.setObjectName("HitBadge")
            top.addWidget(title, 1)
            top.addWidget(badge, 0, Qt.AlignTop)
            path = QLabel(f"{r.relative_path} · #{r.doc_id:02d}")
            path.setObjectName("RowPath")
            snippet = QLabel(self._snippet_html(r))
            snippet.setObjectName("Snippet")
            snippet.setTextFormat(Qt.RichText)
            snippet.setWordWrap(True)
            cl.addLayout(top)
            cl.addWidget(path)
            cl.addWidget(snippet)
            card.set_active(r.doc_id == self.selected_result_id)
            terms = list(dict.fromkeys(h.word for h in r.hits))
            card.clicked.connect(
                lambda d=r.doc_id, t=terms: self.open_doc(d, highlight_terms=t, selected=d)
            )
            card.make_children_transparent()
            self.panel_body_lay.addWidget(card)

    def _title_html(self, result: SearchResult) -> str:
        spans = [h.span for h in result.hits if h.field == "title"]
        return html_with_spans(result.title, spans, self.theme)

    def _snippet_html(self, result: SearchResult) -> str:
        return html_with_spans(result.snippet, result.snippet_spans, self.theme)

    # ---------- 词频 ----------
    def _freq_key_value(self):
        if self.freq_scope == "doc":
            return ("doc", self.doc_id)
        if self.freq_scope == "all":
            return ("all", "")
        return ("folder", self.folder)

    def _ensure_freq(self) -> Optional[FrequencyReport]:
        key = self._freq_key_value()
        if self._freq_report is None or self._freq_key != key:
            try:
                if self.freq_scope == "doc":
                    if self.doc_id is None:
                        return None
                    self._freq_report = self.service.analyze_frequency(doc_id=self.doc_id, k=10)
                elif self.freq_scope == "all":
                    self._freq_report = self.service.analyze_frequency(folder_path="", k=10)
                else:
                    self._freq_report = self.service.analyze_frequency(folder_path=self.folder, k=10)
                self._freq_key = key
            except ValueError:
                return None
        return self._freq_report

    def _build_frequency_panel(self) -> None:
        self.panel_body_lay.addWidget(self._section_title("词频分析", "HASH · HEAP · SORT"))

        seg = QHBoxLayout()
        seg.setContentsMargins(0, 0, 0, 8)
        seg.setSpacing(4)
        self._seg_group_freq_scope = QButtonGroup(self)
        self._seg_group_freq_scope.setExclusive(True)
        for key, label in (("doc", "当前文档"), ("folder", "当前目录"), ("all", "全库")):
            btn = QPushButton(label)
            btn.setObjectName("Segment")
            btn.setCheckable(True)
            btn.setChecked(self.freq_scope == key)
            btn.setCursor(Qt.PointingHandCursor)
            if key == "doc" and self.doc_id is None:
                btn.setEnabled(False)
            btn.clicked.connect(lambda checked=False, s=key: self.set_freq_scope(s))
            self._seg_group_freq_scope.addButton(btn)
            seg.addWidget(btn)
        seg.addStretch()
        self.panel_body_lay.addLayout(seg)

        rep = self._ensure_freq()
        if rep is None or not rep.top_k:
            self.panel_body_lay.addWidget(
                self._empty_state("词", "该范围内没有可统计的词", "换一个范围，或打开一篇有正文的文档。")
            )
            return

        scope_name = (
            self.docs_by_id[self.doc_id].title if self.freq_scope == "doc" and self.doc_id is not None
            else "全库" if self.freq_scope == "all" else (self.folder or "全库")
        )
        distinct = len(rep.quick_sorted)
        tokens = sum(w.count for w in rep.quick_sorted)
        scope = QLabel(f"SCOPE {scope_name}  ·  V={distinct}  ·  TOKENS={tokens}")
        scope.setObjectName("ScopeName")
        scope.setWordWrap(True)
        self.panel_body_lay.addWidget(scope)
        self.panel_body_lay.addSpacing(6)

        timing = QHBoxLayout()
        timing.setContentsMargins(0, 0, 0, 8)
        timing.setSpacing(6)
        for key, label, value in (
            ("quick", "QUICK / 快速", rep.quick_ms),
            ("merge", "MERGE / 归并", rep.merge_ms),
        ):
            cell = QFrame()
            cell.setObjectName("TimingCell")
            cell.setProperty("active", self.freq_algo == key)
            cl = QVBoxLayout(cell)
            cl.setContentsMargins(8, 6, 8, 6)
            cl.setSpacing(1)
            cap = QLabel(label)
            cap.setObjectName("TimingLabel")
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(2)
            val = QLabel(f"{value:.2f}")
            val.setObjectName("TimingValue")
            unit = QLabel("ms")
            unit.setObjectName("TimingUnit")
            row.addWidget(val)
            row.addWidget(unit)
            row.addStretch()
            cl.addWidget(cap)
            cl.addLayout(row)
            timing.addWidget(cell, 1)
        self.panel_body_lay.addLayout(timing)

        algo_row = QHBoxLayout()
        algo_row.setContentsMargins(0, 0, 0, 6)
        algo_row.setSpacing(4)
        self._seg_group_algo = QButtonGroup(self)
        self._seg_group_algo.setExclusive(True)
        for key, label in (("top", "Top-K 堆"), ("quick", "快速排序"), ("merge", "归并排序")):
            btn = QPushButton(label)
            btn.setObjectName("Segment")
            btn.setCheckable(True)
            btn.setChecked(self.freq_algo == key)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, a=key: self.set_freq_algo(a))
            self._seg_group_algo.addButton(btn)
            algo_row.addWidget(btn)
        algo_row.addStretch()
        self.panel_body_lay.addLayout(algo_row)

        line = QHBoxLayout()
        line.setContentsMargins(0, 0, 0, 8)
        line.setSpacing(6)
        algo_name = {
            "top": "MIN HEAP · TOP-K",
            "quick": "QUICK SORT · FULL",
            "merge": "MERGE SORT · FULL",
        }[self.freq_algo]
        an = QLabel(algo_name)
        an.setObjectName("AlgoName")
        ok = QLabel("结果逐项一致 ✓")
        ok.setObjectName("FreqOK")
        line.addWidget(an)
        line.addStretch()
        line.addWidget(ok)
        self.panel_body_lay.addLayout(line)

        max_count = max(w.count for w in rep.top_k) or 1
        for i, w in enumerate(rep.top_k):
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(6)
            rank = QLabel(f"{i + 1:02d}")
            rank.setObjectName("MonoFaint")
            rank.setFixedWidth(18)
            rank.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            word = QLabel(w.word)
            word.setObjectName("RowTitle")
            word.setFixedWidth(50)
            bar = QProgressBar()
            bar.setObjectName("BarHot" if i < 3 else "Bar")
            bar.setRange(0, max_count)
            bar.setValue(w.count)
            bar.setTextVisible(False)
            bar.setFixedHeight(4)
            bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            count = QLabel(str(w.count))
            count.setObjectName("MonoMuted")
            count.setFixedWidth(26)
            count.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            rl.addWidget(rank)
            rl.addWidget(word)
            rl.addWidget(bar, 1)
            rl.addWidget(count)
            row.setFixedHeight(24)
            self.panel_body_lay.addWidget(row)

        self.panel_body_lay.addSpacing(10)
        foot = QLabel(
            "Top-K 由容量 K 的最小堆维护；全量排序在独立副本上分别运行。\n"
            "耗时为本次计算的参考值，不作为严谨性能结论。"
        )
        foot.setObjectName("FreqFoot")
        foot.setWordWrap(True)
        self.panel_body_lay.addWidget(foot)

        note_card = QFrame()
        note_card.setObjectName("Card")
        ncl = QVBoxLayout(note_card)
        ncl.setContentsMargins(10, 8, 10, 8)
        ncl.setSpacing(4)
        nk = QLabel("ALGORITHM NOTE / 算法注记")
        nk.setObjectName("Kicker")
        nt = QLabel(
            "Top-K 使用容量 K 的最小堆，堆顶是当前第 K 名。"
            "快速排序与归并排序在同一份计数副本上分别运行，结果必须逐项一致；"
            "耗时只作参考，不作为性能结论。"
        )
        nt.setObjectName("Note")
        nt.setWordWrap(True)
        ncl.addWidget(nk)
        ncl.addWidget(nt)
        self.panel_body_lay.addSpacing(10)
        self.panel_body_lay.addWidget(note_card)

    # ---------- 推荐 ----------
    def _build_recommend_panel(self) -> None:
        if self.doc_id is None or self.center_id is None:
            self.panel_body_lay.addWidget(
                self._empty_state("荐", "还没有打开文档", "从目录或检索结果中选择一篇文档，再生成推荐。")
            )
            return
        assert self._rec_view is not None
        center = self.docs_by_id[self.center_id]

        self.panel_body_lay.addWidget(self._section_title("文档推荐", "3-WAY SCORE"))

        card = QFrame()
        card.setObjectName("CenterCard")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(10, 8, 10, 8)
        cl.setSpacing(3)
        small = QLabel(f"CENTER DOC · #{center.doc_id:02d}")
        small.setObjectName("MonoFaint")
        title = QLabel(center.title)
        title.setObjectName("RowTitle")
        title.setWordWrap(True)
        wd, wc, wk = PRESET_WEIGHTS[self.preset]
        weights = QLabel(
            f'<span style="color:{self.theme.muted};">D 目录 · C 正文 · K 关键词</span><br>'
            f'wD {wd:.1f} · wC {wc:.1f} · wK {wk:.1f}'
        )
        weights.setObjectName("ScoreKey")
        weights.setTextFormat(Qt.RichText)
        cl.addWidget(small)
        cl.addWidget(title)
        cl.addWidget(weights)
        self.panel_body_lay.addWidget(card)

        preset_row = QHBoxLayout()
        preset_row.setContentsMargins(0, 8, 0, 8)
        preset_row.setSpacing(4)
        self._seg_group_preset = QButtonGroup(self)
        self._seg_group_preset.setExclusive(True)
        for key, label in (("balanced", "均衡"), ("structure", "结构优先"), ("content", "内容优先")):
            btn = QPushButton(label)
            btn.setObjectName("Segment")
            btn.setCheckable(True)
            btn.setChecked(self.preset == key)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, p=key: self.set_preset(p))
            self._seg_group_preset.addButton(btn)
            preset_row.addWidget(btn)
        preset_row.addStretch()
        self.panel_body_lay.addLayout(preset_row)

        key = QLabel("分值条：目 = 目录 · 文 = 正文 · 词 = 高频词")
        key.setObjectName("ScoreKey")
        self.panel_body_lay.addWidget(key)

        if self.doc_id != self.center_id:
            notice = QFrame()
            notice.setObjectName("Notice")
            nl = QHBoxLayout(notice)
            nl.setContentsMargins(0, 0, 8, 0)
            nl.setSpacing(6)
            bar = QFrame()
            bar.setObjectName("NoticeBar")
            bar.setFixedWidth(2)
            text = QLabel(
                f"正在阅读《{self.docs_by_id[self.doc_id].title}》。"
                "列表仍以旧中心计算；主动重算才更换中心。"
            )
            text.setObjectName("Note")
            text.setWordWrap(True)
            btn = QPushButton("重算")
            btn.setObjectName("Primary")
            btn.setMinimumWidth(34)
            btn.setFixedHeight(18)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(self.recenter)
            nl.addWidget(bar)
            nl.addSpacing(6)
            nl.addWidget(text, 1)
            nl.addWidget(btn, 0, Qt.AlignTop)
            self.panel_body_lay.addWidget(notice)

        if not self._rec_view.items:
            self.panel_body_lay.addWidget(
                self._empty_state("荐", "没有其他文档可推荐", "样例库中至少需要两篇文档。")
            )
            return

        for i, item in enumerate(self._rec_view.items):
            card = ClickableCard("RecCard")
            cl = QHBoxLayout(card)
            cl.setContentsMargins(0, 9, 4, 9)
            cl.setSpacing(6)
            rank = QLabel(f"{i + 1:02d}")
            rank.setObjectName("MonoFaint")
            rank.setFixedWidth(18)
            rank.setAlignment(Qt.AlignTop | Qt.AlignRight)
            body = QVBoxLayout()
            body.setContentsMargins(0, 0, 0, 0)
            body.setSpacing(3)

            top = QHBoxLayout()
            top.setContentsMargins(0, 0, 0, 0)
            top.setSpacing(6)
            title = QLabel(item.title)
            title.setObjectName("RowTitle")
            title.setWordWrap(True)
            total = QLabel(f"{item.scores.total:.2f}")
            total.setObjectName("RecTotal")
            top.addWidget(title, 1)
            top.addWidget(total, 0, Qt.AlignTop)
            body.addLayout(top)

            path = QLabel(f"{item.relative_path} · #{item.doc_id:02d}")
            path.setObjectName("RowPath")
            body.addWidget(path)

            for label, value, obj in (
                ("D", item.scores.directory, "MeterD"),
                ("C", item.scores.content, "MeterC"),
                ("K", item.scores.keywords, "MeterK"),
            ):
                row = QHBoxLayout()
                row.setContentsMargins(0, 0, 0, 0)
                row.setSpacing(5)
                lab = QLabel(label)
                lab.setObjectName("MonoFaint")
                lab.setFixedWidth(10)
                bar = QProgressBar()
                bar.setObjectName(obj)
                bar.setRange(0, 100)
                bar.setValue(int(round(max(0.0, min(1.0, value)) * 100)))
                bar.setTextVisible(False)
                bar.setFixedHeight(3)
                bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                val = QLabel(f"{value:.2f}")
                val.setObjectName("MonoFaint")
                val.setFixedWidth(23)
                val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                row.addWidget(lab)
                row.addWidget(bar, 1)
                row.addWidget(val)
                body.addLayout(row)

            reason = QLabel(item.reason)
            reason.setObjectName("Reason")
            reason.setWordWrap(True)
            body.addWidget(reason)

            if item.shared_keywords:
                chips = "&nbsp;".join(
                    f'<span style="background-color:{self.theme.accent_soft};color:{self.theme.text_dim};">'
                    f"&nbsp;{esc(w)}&nbsp;</span>"
                    for w in item.shared_keywords[:4]
                )
                chip_label = QLabel(chips)
                chip_label.setObjectName("Chips")
                chip_label.setTextFormat(Qt.RichText)
                chip_label.setWordWrap(True)
                body.addWidget(chip_label)

            cl.addWidget(rank)
            cl.addLayout(body, 1)
            card.clicked.connect(lambda d=item.doc_id: self.open_doc(d))
            card.make_children_transparent()
            self.panel_body_lay.addWidget(card)

        hint = QLabel("关系图与列表使用同一预设；点节点或推荐项只打开正文，不换中心。")
        hint.setObjectName("Note")
        hint.setWordWrap(True)
        self.panel_body_lay.addSpacing(10)
        self.panel_body_lay.addWidget(hint)

    # ============================================================
    # 交互
    # ============================================================
    def set_mode(self, mode: str) -> None:
        if mode == self.mode:
            self._sync_rail()
            return
        self.mode = mode
        self._sync_rail()
        self.panel_title.setText(TOOL_META[mode][0])
        self.panel_hint.setText(TOOL_META[mode][1])
        self._refresh_panel(preserve_scroll=False)

    def perform_search(self) -> None:
        self.query = self.search_input.text()
        self.results = self.service.search(self.query)
        self.mode = "search"
        self.selected_result_id = None
        self.highlight_terms = None
        self.doc_open = False
        self.canvas.set_doc_open(False)
        self._refresh_all(preserve_panel_scroll=False)

    def open_doc(self, doc_id: int, highlight_terms: Optional[list[str]] = None,
                 selected: Optional[int] = None) -> None:
        if doc_id not in self.docs_by_id:
            return
        self.doc_id = doc_id
        self.doc_open = True
        if highlight_terms is not None:
            self.highlight_terms = highlight_terms
            self.selected_result_id = selected
        elif self.mode != "search" or selected is None:
            self.highlight_terms = None
            self.selected_result_id = None
        self._refresh_all(preserve_panel_scroll=True)
        self.canvas.set_doc_open(True)
        self.canvas.doc_panel.raise_()

    def close_doc(self) -> None:
        self.doc_open = False
        self.canvas.set_doc_open(False)

    def recenter(self) -> None:
        if self.doc_id is None:
            return
        self.center_id = self.doc_id
        self.mode = "recommend"
        self.doc_open = False
        self.highlight_terms = None
        self.selected_result_id = None
        self.canvas.set_doc_open(False)
        self._sync_rail()
        self._refresh_all(preserve_panel_scroll=False)
        self.toast.show_message(f"CENTER → #{self.center_id:02d} · 列表与关系图已同时重算")

    def open_freq_for_doc(self) -> None:
        if self.doc_id is None:
            return
        self.mode = "frequency"
        self.freq_scope = "doc"
        self.freq_algo = "top"
        self.doc_open = False
        self.canvas.set_doc_open(False)
        self._sync_rail()
        self.panel_title.setText(TOOL_META[self.mode][0])
        self.panel_hint.setText(TOOL_META[self.mode][1])
        self._refresh_panel(preserve_scroll=False)

    def set_preset(self, preset: str) -> None:
        if preset not in PRESET_CN:
            return
        self.preset = preset
        self._refresh_all(preserve_panel_scroll=False)
        self.panel_scroll.verticalScrollBar().setValue(0)

    def set_freq_scope(self, scope: str) -> None:
        self.freq_scope = scope
        self._refresh_panel(preserve_scroll=False)

    def set_freq_algo(self, algo: str) -> None:
        self.freq_algo = algo
        self._refresh_panel(preserve_scroll=False)

    def select_folder(self, path: str) -> None:
        self.folder = path
        self.mode = "folder"
        self._sync_rail()
        self.panel_title.setText(TOOL_META[self.mode][0])
        self.panel_hint.setText(TOOL_META[self.mode][1])
        self._refresh_panel(preserve_scroll=True)

    def toggle_folder(self, path: str) -> None:
        if path in self.expanded:
            self.expanded.remove(path)
        else:
            self.expanded.add(path)
        self._refresh_panel(preserve_scroll=True)

    def _on_graph_node(self, doc_id: int) -> None:
        self.open_doc(doc_id)
        self.toast.show_message(f"OPEN #{doc_id:02d} · 推荐中心未改变")

    # ============================================================
    # 页面缩放
    # ============================================================
    def zoom_in(self) -> None:
        self.view.step_zoom(1)

    def zoom_out(self) -> None:
        self.view.step_zoom(-1)

    def reset_zoom(self) -> None:
        self.view.reset_zoom()

    def _on_zoom_changed(self, percent: int) -> None:
        self.zoom = percent / 100.0
        if hasattr(self, "zoom_control"):
            self.zoom_control.set_value(percent)
        if self._zoom_initialized:
            self.toast.show_message(f"页面缩放 · {percent}%")

    def _build_shortcuts(self) -> None:
        self._shortcuts: list[QShortcut] = []
        bindings = [
            ("Ctrl+=", self.zoom_in),
            ("Ctrl++", self.zoom_in),
            ("Ctrl+-", self.zoom_out),
            ("Ctrl+0", self.reset_zoom),
            ("Esc", self._escape_action),
        ]
        for i, mode in enumerate(("folder", "search", "frequency", "recommend"), start=1):
            bindings.append((f"Ctrl+{i}", lambda m=mode: self.set_mode(m)))
        for seq, slot in bindings:
            shortcut = QShortcut(QKeySequence(seq), self)
            shortcut.setContext(Qt.ApplicationShortcut)
            shortcut.activated.connect(slot)
            self._shortcuts.append(shortcut)

    def _escape_action(self) -> None:
        if self._issue_popup is not None and self._issue_popup.isVisible():
            self._issue_popup.close()
        elif self.doc_open:
            self.close_doc()

    # ============================================================
    # 失败文件弹层
    # ============================================================
    def show_issues(self) -> None:
        if not self.summary.issues:
            self.toast.show_message("没有读取失败的文件")
            return
        if self._issue_popup is not None and self._issue_popup.isVisible():
            self._issue_popup.close()
            return
        if self._issue_popup is not None:
            self._issue_popup.deleteLater()
        # 子控件而不是顶层 Popup：这样它会跟随页面缩放，位置也随 Root 走。
        popup = QFrame(self.root)
        popup.setObjectName("IssuePopup")
        popup.setFixedWidth(344)
        lay = QVBoxLayout(popup)
        lay.setContentsMargins(15, 13, 15, 14)
        lay.setSpacing(8)
        top = QHBoxLayout()
        t = QLabel("LOAD ISSUES / 读取问题")
        t.setObjectName("IssueTitle")
        n = QLabel(f"{len(self.summary.issues)} FAILED")
        n.setObjectName("IssueFile")
        close = QPushButton("×")
        close.setObjectName("CloseButton")
        close.setFixedSize(22, 22)
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(popup.close)
        top.addWidget(t)
        top.addStretch()
        top.addWidget(n)
        top.addWidget(close)
        lay.addLayout(top)
        for issue in self.summary.issues:
            file_label = QLabel(issue.relative_path)
            file_label.setObjectName("IssueFile")
            file_label.setWordWrap(True)
            text = QLabel(issue.message)
            text.setObjectName("IssueText")
            text.setWordWrap(True)
            lay.addWidget(file_label)
            lay.addWidget(text)
        popup.adjustSize()
        pos = self.issue_btn.mapTo(self.root, QPoint(0, 0))
        popup.move(
            max(8, pos.x() + self.issue_btn.width() - popup.width()),
            pos.y() + self.issue_btn.height() + 8,
        )
        popup.show()
        popup.raise_()
        self._issue_popup = popup

    # ============================================================
    # 键盘
    # ============================================================
    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        # 代理控件里的焦点不会把 "/" 冒泡到 MainWindow，这里补一层。
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Slash:
            focus = QApplication.focusWidget()
            if not isinstance(focus, QLineEdit):
                self.search_input.setFocus()
                return True
        # Ctrl+滚轮在面板/QTextBrowser 上也要缩放整页，而不是只滚动子控件。
        if event.type() == QEvent.Wheel and event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y()
            if delta:
                self.view.step_zoom(1 if delta > 0 else -1)
            return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key_Slash:
            focus = QApplication.focusWidget()
            if not isinstance(focus, QLineEdit):
                self.search_input.setFocus()
                event.accept()
                return
        if event.key() == Qt.Key_Escape:
            if self._issue_popup is not None and self._issue_popup.isVisible():
                self._issue_popup.close()
            elif self.doc_open:
                self.close_doc()
            event.accept()
            return
        if event.modifiers() & Qt.ControlModifier:
            mapping = {
                Qt.Key_1: "folder",
                Qt.Key_2: "search",
                Qt.Key_3: "frequency",
                Qt.Key_4: "recommend",
            }
            if event.key() in mapping:
                self.set_mode(mapping[event.key()])
                event.accept()
                return
        super().keyPressEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "toast"):
            self.toast._position()
