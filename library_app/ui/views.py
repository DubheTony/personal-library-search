"""主工作区视图：目录、检索、词频、推荐、文档。

每个视图独占主工作区，不再共用固定侧栏和常驻关系图。
"""
from __future__ import annotations

import heapq
import html
import re
from typing import Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPen,
    QTextBlockFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
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
    DocumentView as DocModel,
    FrequencyReport,
    GraphView,
    RecommendationView,
    SearchResult,
    TreeItem,
    WordCount,
)
from ..theme import Theme
from .graph_view import GraphViewWidget
from .widgets import ClickableCard, clear_layout


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


def doc_html(doc: DocModel, theme: Theme, title_spans=None, body_spans=None) -> str:
    title_html = html_with_spans(doc.title, title_spans or [], theme)
    paragraphs = [(m.start(), m.group()) for m in re.finditer(r"[^\n]+", doc.body)]
    body_html: list[str] = []
    for offset, paragraph in paragraphs:
        local_spans = []
        if body_spans:
            from ..models import Span

            for span in body_spans:
                if span.start >= offset and span.end <= offset + len(paragraph):
                    local_spans.append(Span(span.start - offset, span.end - offset))
        content = html_with_spans(paragraph, local_spans, theme)
        body_html.append(
            f'<p style="margin:0 0 14px 0;text-align:justify;">{content}</p>'
        )
    return f"""
    <html><body style="font-family:{theme.serif};color:{theme.text};">
      <h1 style="font-family:{theme.serif};font-size:24px;font-weight:600;
                 color:{theme.text};margin:0 0 18px 0;">{title_html}</h1>
      <div style="font-family:{theme.serif};font-size:15px;color:{theme.text};">
        {''.join(body_html)}
      </div>
    </body></html>
    """


class ViewHeader(QFrame):
    """视图标题行：中文标题 + 一条动态副标题，右侧可放操作。"""

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ViewHead")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(28, 16, 28, 12)
        lay.setSpacing(16)
        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)
        self.title = QLabel(title)
        self.title.setObjectName("ViewTitle")
        self.sub = QLabel("")
        self.sub.setObjectName("ViewSub")
        self.sub.setWordWrap(True)
        text_col.addWidget(self.title)
        text_col.addWidget(self.sub)
        lay.addLayout(text_col, 1)
        self.right = QWidget()
        self.right_lay = QHBoxLayout(self.right)
        self.right_lay.setContentsMargins(0, 0, 0, 0)
        self.right_lay.setSpacing(8)
        lay.addWidget(self.right, 0, Qt.AlignVCenter)

    def set_sub(self, text: str) -> None:
        self.sub.setText(text)


def _scroll_host(parent: QWidget) -> tuple[QScrollArea, QWidget, QVBoxLayout]:
    scroll = QScrollArea(parent)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    host = QWidget()
    lay = QVBoxLayout(host)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    scroll.setWidget(host)
    return scroll, host, lay


class DirectoryView(QWidget):
    def __init__(self, controller) -> None:
        super().__init__()
        self.c = controller
        self._theme: Theme = controller.theme
        self._traversal_open = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.header = ViewHeader("目录")
        root.addWidget(self.header)

        body = QWidget()
        body_lay = QHBoxLayout(body)
        body_lay.setContentsMargins(28, 16, 28, 22)
        body_lay.setSpacing(22)
        root.addWidget(body, 1)

        # 左：文件夹树
        left = QWidget()
        left.setFixedWidth(330)
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(8)

        tree_head = QHBoxLayout()
        tree_head.setContentsMargins(0, 0, 0, 0)
        tree_head.setSpacing(8)
        tree_title = QLabel("文件夹")
        tree_title.setObjectName("SectionTitle")
        self.traversal_btn = QPushButton("查看遍历顺序")
        self.traversal_btn.setObjectName("LinkButton")
        self.traversal_btn.setCursor(Qt.PointingHandCursor)
        self.traversal_btn.setToolTip("查看目录树按深度优先展开的顺序")
        self.traversal_btn.clicked.connect(self._toggle_traversal)
        tree_head.addWidget(tree_title)
        tree_head.addStretch(1)
        tree_head.addWidget(self.traversal_btn)
        left_lay.addLayout(tree_head)

        self.tree_scroll, self.tree_host, self.tree_lay = _scroll_host(self)
        left_lay.addWidget(self.tree_scroll, 1)

        self.traversal = QFrame()
        self.traversal.setObjectName("Card")
        self.traversal.setFixedHeight(170)
        traversal_outer = QVBoxLayout(self.traversal)
        traversal_outer.setContentsMargins(10, 8, 10, 8)
        traversal_outer.setSpacing(4)
        t_title = QLabel("深度优先展开顺序")
        t_title.setObjectName("Kicker")
        traversal_outer.addWidget(t_title)
        t_scroll, t_host, self.traversal_lay = _scroll_host(self)
        traversal_outer.addWidget(t_scroll, 1)
        self.traversal.hide()
        left_lay.addWidget(self.traversal)

        # 右：当前目录的文档
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(6)
        docs_head = QHBoxLayout()
        docs_head.setContentsMargins(0, 0, 0, 0)
        docs_head.setSpacing(8)
        self.folder_title = QLabel("全部文档")
        self.folder_title.setObjectName("SectionTitle")
        self.folder_count = QLabel("")
        self.folder_count.setObjectName("MonoMuted")
        docs_head.addWidget(self.folder_title)
        docs_head.addStretch(1)
        docs_head.addWidget(self.folder_count)
        right_lay.addLayout(docs_head)
        self.docs_scroll, self.docs_host, self.docs_lay = _scroll_host(self)
        right_lay.addWidget(self.docs_scroll, 1)

        body_lay.addWidget(left)
        body_lay.addWidget(right, 1)

    # ---------- 构建 ----------
    def refresh(self) -> None:
        self._rebuild_tree()
        self._rebuild_docs()
        self._rebuild_traversal()
        self.header.set_sub("按文件夹浏览")
        self.traversal_btn.setText("收起遍历顺序" if self._traversal_open else "查看遍历顺序")

    def _rebuild_tree(self) -> None:
        clear_layout(self.tree_lay)
        root = ClickableCard("TreeRow")
        root.setProperty("kind", "folder")
        root.set_active(self.c.folder == "")
        row = QHBoxLayout(root)
        row.setContentsMargins(6, 0, 6, 0)
        row.setSpacing(5)
        name = QLabel("全部文档")
        name.setObjectName("TreeName")
        count = QLabel(str(len(self.c.all_docs)))
        count.setObjectName("TreeCount")
        name.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        count.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        row.addWidget(name, 1)
        row.addWidget(count)
        root.setFixedHeight(26)
        root.clicked.connect(lambda: self.c.select_folder(""))
        self.tree_lay.addWidget(root)

        def walk(node: TreeItem, depth: int) -> None:
            for child in node.children:
                if child.kind != "folder":
                    continue
                expanded = child.relative_path in self.c.expanded
                card = ClickableCard("TreeRow")
                card.setProperty("kind", "folder")
                card.set_active(child.relative_path == self.c.folder)
                lay = QHBoxLayout(card)
                lay.setContentsMargins(6 + depth * 12, 0, 6, 0)
                lay.setSpacing(5)
                caret = QToolButton()
                caret.setObjectName("Caret")
                caret.setText("▾" if expanded else "▸")
                caret.setFixedWidth(13)
                caret.setCursor(Qt.PointingHandCursor)
                caret.clicked.connect(
                    lambda checked=False, p=child.relative_path: self.c.toggle_folder(p)
                )
                name = QLabel(child.name)
                name.setObjectName("TreeName")
                name.setToolTip(child.relative_path)
                count = QLabel(str(self.c._folder_count(child)))
                count.setObjectName("TreeCount")
                name.setAttribute(Qt.WA_TransparentForMouseEvents, True)
                count.setAttribute(Qt.WA_TransparentForMouseEvents, True)
                lay.addWidget(caret)
                lay.addWidget(name, 1)
                lay.addWidget(count)
                card.setFixedHeight(26)
                card.clicked.connect(
                    lambda p=child.relative_path: self.c.select_folder(p)
                )
                self.tree_lay.addWidget(card)
                if expanded:
                    walk(child, depth + 1)

        walk(self.c.tree_root, 0)
        self.tree_lay.addStretch(1)

    def _rebuild_docs(self) -> None:
        docs = self.c.service.list_folder(self.c.folder)
        name = "全部文档" if self.c.folder == "" else self.c.folder.rsplit("/", 1)[-1]
        self.folder_title.setText(name)
        self.folder_count.setText(f"{len(docs)} 篇")
        clear_layout(self.docs_lay)
        if not docs:
            empty = QLabel("这个目录里没有文档")
            empty.setObjectName("Note")
            hint = QLabel("换一个目录，或查看全部文档。")
            hint.setObjectName("Note")
            self.docs_lay.addWidget(empty)
            self.docs_lay.addWidget(hint)
            self.docs_lay.addStretch(1)
            return
        for doc in docs:
            card = ClickableCard("DocRow")
            lay = QVBoxLayout(card)
            lay.setContentsMargins(6, 9, 6, 9)
            lay.setSpacing(2)
            title = QLabel(doc.title)
            title.setObjectName("RowTitle")
            path = QLabel(doc.relative_path)
            path.setObjectName("RowPath")
            lay.addWidget(title)
            lay.addWidget(path)
            card.set_active(doc.doc_id == self.c.doc_id)
            card.clicked.connect(lambda d=doc.doc_id: self.c.open_doc(d))
            card.make_children_transparent()
            self.docs_lay.addWidget(card)
        self.docs_lay.addStretch(1)

    def _rebuild_traversal(self) -> None:
        clear_layout(self.traversal_lay)
        rows: list[tuple[str, int, int]] = []

        def walk(node: TreeItem, depth: int) -> None:
            for child in node.children:
                if child.kind == "folder":
                    rows.append((child.relative_path, self.c._folder_count(child), depth))
                    walk(child, depth + 1)

        walk(self.c.tree_root, 0)
        if not rows:
            label = QLabel("没有子目录")
            label.setObjectName("Note")
            self.traversal_lay.addWidget(label)
        else:
            for path, count, depth in rows:
                row = QLabel(f"{'    ' * depth}{path} · {count} 篇")
                row.setObjectName("AlgoLine")
                row.setWordWrap(True)
                self.traversal_lay.addWidget(row)
        self.traversal_lay.addStretch(1)

    def _toggle_traversal(self) -> None:
        self._traversal_open = not self._traversal_open
        self.traversal.setVisible(self._traversal_open)
        self.traversal_btn.setText("收起遍历顺序" if self._traversal_open else "查看遍历顺序")

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme


class SearchView(QWidget):
    def __init__(self, controller) -> None:
        super().__init__()
        self.c = controller
        self._theme: Theme = controller.theme
        self._results: list[SearchResult] = []
        self._query = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        head = QFrame()
        head.setObjectName("ViewHead")
        h = QHBoxLayout(head)
        h.setContentsMargins(28, 16, 28, 12)
        h.setSpacing(12)
        self.back_btn = QPushButton("← 返回")
        self.back_btn.setObjectName("LinkButton")
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.clicked.connect(self.c.close_search)
        title = QLabel("检索")
        title.setObjectName("ViewTitle")
        h.addWidget(self.back_btn)
        h.addWidget(title)
        h.addStretch(1)
        self.count = QLabel("")
        self.count.setObjectName("MonoMuted")
        h.addWidget(self.count)
        root.addWidget(head)

        top = QWidget()
        top_lay = QVBoxLayout(top)
        top_lay.setContentsMargins(28, 10, 28, 8)
        top_lay.setSpacing(6)
        self.query_label = QLabel("")
        self.query_label.setObjectName("ViewSub")
        self.terms_lay = QHBoxLayout()
        self.terms_lay.setContentsMargins(0, 0, 0, 0)
        self.terms_lay.setSpacing(6)
        top_lay.addWidget(self.query_label)
        top_lay.addLayout(self.terms_lay)
        root.addWidget(top)

        self.scroll, self.host, self.results_lay = _scroll_host(self)
        body_wrap = QWidget()
        body_lay = QVBoxLayout(body_wrap)
        body_lay.setContentsMargins(28, 0, 28, 24)
        body_lay.setSpacing(0)
        body_lay.addWidget(self.scroll)
        root.addWidget(body_wrap, 1)

    def show_results(self, query: str, results: list[SearchResult]) -> None:
        self._query = query
        self._results = results
        self.count.setText(f"{len(results)} 条结果")
        self.query_label.setText(f"「{query}」" if query else "在顶部输入关键词后回车")
        clear_layout(self.terms_lay)
        tag = QLabel("倒排命中")
        tag.setObjectName("Kicker")
        self.terms_lay.addWidget(tag)
        counts: dict[str, int] = {}
        docs: dict[str, int] = {}
        for result in results:
            seen: set[str] = set()
            for hit in result.hits:
                counts[hit.word] = counts.get(hit.word, 0) + 1
                seen.add(hit.word)
            for word in seen:
                docs[word] = docs.get(word, 0) + 1
        for term in dict.fromkeys(query.split()):
            chip = QLabel(f"{term} · {docs.get(term, 0)} 篇 / {counts.get(term, 0)} 处")
            chip.setObjectName("Chips")
            self.terms_lay.addWidget(chip)
        self.terms_lay.addStretch(1)

        clear_layout(self.results_lay)
        if not results:
            self.results_lay.addSpacing(24)
            empty = QLabel("没有找到同时包含这些词的文档")
            empty.setObjectName("EmptyTitle")
            self.results_lay.addWidget(empty)
            hint = QLabel("减少关键词，或换一个词再试。")
            hint.setObjectName("Note")
            self.results_lay.addWidget(hint)
            self.results_lay.addStretch(1)
            return

        for result in results:
            card = ClickableCard("ResultCard")
            lay = QVBoxLayout(card)
            lay.setContentsMargins(10, 12, 10, 12)
            lay.setSpacing(5)
            top_row = QHBoxLayout()
            top_row.setContentsMargins(0, 0, 0, 0)
            top_row.setSpacing(8)
            title = QLabel(self._title_html(result))
            title.setObjectName("RowTitle")
            title.setTextFormat(Qt.RichText)
            title.setWordWrap(True)
            badge = QLabel(f"{result.match_count} 处")
            badge.setObjectName("HitBadge")
            top_row.addWidget(title, 1)
            top_row.addWidget(badge, 0, Qt.AlignTop)
            path = QLabel(result.relative_path)
            path.setObjectName("RowPath")
            snippet = QLabel(self._snippet_html(result))
            snippet.setObjectName("Snippet")
            snippet.setTextFormat(Qt.RichText)
            snippet.setWordWrap(True)
            positions = QLabel(self._hit_positions(result))
            positions.setObjectName("AlgoLine")
            positions.setWordWrap(True)
            lay.addLayout(top_row)
            lay.addWidget(path)
            lay.addWidget(snippet)
            lay.addWidget(positions)
            terms = list(dict.fromkeys(hit.word for hit in result.hits))
            card.clicked.connect(
                lambda d=result.doc_id, t=terms: self.c.open_doc(
                    d, highlight_terms=t, selected=d
                )
            )
            card.make_children_transparent()
            self.results_lay.addWidget(card)
        self.results_lay.addStretch(1)

    def _title_html(self, result: SearchResult) -> str:
        spans = [hit.span for hit in result.hits if hit.field == "title"]
        return html_with_spans(result.title, spans, self._theme)

    def _snippet_html(self, result: SearchResult) -> str:
        return html_with_spans(result.snippet, result.snippet_spans, self._theme)

    @staticmethod
    def _hit_positions(result: SearchResult) -> str:
        by_field: dict[str, list[int]] = {}
        for hit in result.hits:
            by_field.setdefault(hit.field, []).append(hit.span.start)
        parts: list[str] = []
        for field, label in (("title", "标题"), ("body", "正文")):
            starts = by_field.get(field, [])
            if not starts:
                continue
            shown = "、".join(str(value + 1) for value in starts[:4])
            if len(starts) > 4:
                shown += "…"
            parts.append(f"{label} {len(starts)} 处（第 {shown} 字）")
        return "命中位置：" + " · ".join(parts) if parts else ""

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        if self._results:
            self.show_results(self._query, self._results)


class HeapView(QWidget):
    """Top-K 最小堆的最终结构，数据来自本次词频报告。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._items: list[WordCount] = []
        self._theme: Optional[Theme] = None
        self.setMinimumHeight(210)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def set_items(self, items: list[WordCount]) -> None:
        self._items = list(items)
        self.updateGeometry()
        self.update()

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        theme = self._theme
        if theme is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if not self._items:
            p.setPen(QColor(theme.muted))
            p.setFont(QFont(theme.sans, 10))
            p.drawText(self.rect(), Qt.AlignCenter, "暂无词频数据")
            p.end()
            return

        heap = [(item.count, item.word) for item in self._items]
        heapq.heapify(heap)
        count = len(heap)
        positions: dict[int, tuple[float, int]] = {}

        def place(index: int, depth: int, left: float, right: float) -> None:
            if index >= count:
                return
            mid = (left + right) / 2
            positions[index] = (mid, depth)
            place(index * 2 + 1, depth + 1, left, mid)
            place(index * 2 + 2, depth + 1, mid, right)

        place(0, 0, 8.0, self.width() - 8.0)
        max_depth = max(depth for _, depth in positions.values())
        gap = max(40.0, min(62.0, (self.height() - 34) / (max_depth + 1)))
        top = 18.0
        box_w, box_h = 64.0, 28.0

        points = {
            index: (x, top + depth * gap) for index, (x, depth) in positions.items()
        }
        p.setPen(QPen(QColor(theme.line), 1))
        for index in range(count):
            for child in (index * 2 + 1, index * 2 + 2):
                if child < count:
                    p.drawLine(
                        int(points[index][0]),
                        int(points[index][1] + box_h),
                        int(points[child][0]),
                        int(points[child][1]),
                    )

        font = QFont(theme.mono)
        font.setPixelSize(9)
        p.setFont(font)
        for index, (c, word) in enumerate(heap):
            x, y = points[index]
            box = QRectF(x - box_w / 2, y, box_w, box_h)
            p.setBrush(QColor(theme.card))
            p.setPen(QPen(QColor(theme.accent if index == 0 else theme.line), 1.2))
            p.drawRoundedRect(box, theme.radius + 2, theme.radius + 2)
            label = word if len(word) <= 6 else word[:5] + "…"
            p.setPen(QColor(theme.text))
            p.drawText(
                int(box.left() + 4),
                int(box.top()),
                int(box_w - 8),
                int(box_h - 10),
                Qt.AlignLeft | Qt.AlignVCenter,
                label,
            )
            p.setPen(QColor(theme.muted))
            p.drawText(
                int(box.left() + 4),
                int(box.top() + box_h - 12),
                int(box_w - 8),
                10,
                Qt.AlignRight | Qt.AlignVCenter,
                str(c),
            )
        p.end()


class FrequencyView(QWidget):
    def __init__(self, controller) -> None:
        super().__init__()
        self.c = controller
        self._theme: Theme = controller.theme
        self._report: Optional[FrequencyReport] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.header = ViewHeader("词频")
        root.addWidget(self.header)

        controls = QWidget()
        control_lay = QHBoxLayout(controls)
        control_lay.setContentsMargins(28, 0, 28, 12)
        control_lay.setSpacing(16)

        scope_box = QHBoxLayout()
        scope_box.setContentsMargins(0, 0, 0, 0)
        scope_box.setSpacing(4)
        self.scope_group = QButtonGroup(self)
        self.scope_group.setExclusive(True)
        self.scope_buttons: dict[str, QPushButton] = {}
        for key, text in (("doc", "当前文档"), ("folder", "当前目录"), ("all", "全库")):
            button = QPushButton(text)
            button.setObjectName("Segment")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(
                lambda checked=False, value=key: self.c.set_freq_scope(value)
            )
            self.scope_group.addButton(button)
            self.scope_buttons[key] = button
            scope_box.addWidget(button)
        control_lay.addLayout(scope_box)

        algo_box = QHBoxLayout()
        algo_box.setContentsMargins(0, 0, 0, 0)
        algo_box.setSpacing(4)
        self.algo_group = QButtonGroup(self)
        self.algo_group.setExclusive(True)
        self.algo_buttons: dict[str, QPushButton] = {}
        for key, text in (("top", "Top-K 堆"), ("quick", "快速排序"), ("merge", "归并排序")):
            button = QPushButton(text)
            button.setObjectName("Segment")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(
                lambda checked=False, value=key: self.c.set_freq_algo(value)
            )
            self.algo_group.addButton(button)
            self.algo_buttons[key] = button
            algo_box.addWidget(button)
        control_lay.addLayout(algo_box)
        control_lay.addStretch(1)
        root.addWidget(controls)

        body = QWidget()
        body_lay = QHBoxLayout(body)
        body_lay.setContentsMargins(28, 0, 28, 22)
        body_lay.setSpacing(18)
        root.addWidget(body, 1)

        words_card = QFrame()
        words_card.setObjectName("AlgoCard")
        words_lay = QVBoxLayout(words_card)
        words_lay.setContentsMargins(14, 12, 14, 12)
        words_lay.setSpacing(8)
        words_title = QLabel("出现次数最多的词")
        words_title.setObjectName("SectionTitle")
        words_lay.addWidget(words_title)
        self.words_scroll, self.words_host, self.words_lay = _scroll_host(self)
        words_lay.addWidget(self.words_scroll, 1)
        body_lay.addWidget(words_card, 3)

        right = QScrollArea()
        right.setWidgetResizable(True)
        right.setFrameShape(QFrame.NoFrame)
        right.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        right_host = QWidget()
        right_lay = QVBoxLayout(right_host)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(12)
        right.setWidget(right_host)

        hash_card = QFrame()
        hash_card.setObjectName("AlgoCard")
        hash_lay = QVBoxLayout(hash_card)
        hash_lay.setContentsMargins(14, 12, 14, 12)
        hash_lay.setSpacing(4)
        hash_title = QLabel("哈希计数")
        hash_title.setObjectName("AlgoTitle")
        self.hash_line = QLabel("")
        self.hash_line.setObjectName("AlgoLine")
        self.hash_line.setWordWrap(True)
        hash_lay.addWidget(hash_title)
        hash_lay.addWidget(self.hash_line)
        right_lay.addWidget(hash_card)

        heap_card = QFrame()
        heap_card.setObjectName("AlgoCard")
        heap_lay = QVBoxLayout(heap_card)
        heap_lay.setContentsMargins(14, 12, 14, 12)
        heap_lay.setSpacing(4)
        heap_title = QLabel("Top-K 最小堆")
        heap_title.setObjectName("AlgoTitle")
        self.heap_caption = QLabel("堆顶是当前第 K 名；词频更高的词会替换它并向下调整。")
        self.heap_caption.setObjectName("AlgoLine")
        self.heap_caption.setWordWrap(True)
        self.heap_view = HeapView()
        heap_lay.addWidget(heap_title)
        heap_lay.addWidget(self.heap_view)
        heap_lay.addWidget(self.heap_caption)
        right_lay.addWidget(heap_card)

        sort_card = QFrame()
        sort_card.setObjectName("AlgoCard")
        sort_lay = QVBoxLayout(sort_card)
        sort_lay.setContentsMargins(14, 12, 14, 12)
        sort_lay.setSpacing(4)
        sort_title = QLabel("快速排序 / 归并排序")
        sort_title.setObjectName("AlgoTitle")
        self.sort_line = QLabel("")
        self.sort_line.setObjectName("AlgoLine")
        self.sort_line.setWordWrap(True)
        self.trace_label = QLabel("")
        self.trace_label.setObjectName("AlgoStep")
        self.trace_label.setWordWrap(True)
        sort_lay.addWidget(sort_title)
        sort_lay.addWidget(self.sort_line)
        sort_lay.addWidget(self.trace_label)
        right_lay.addWidget(sort_card)
        right_lay.addStretch(1)
        body_lay.addWidget(right, 2)

    def refresh(self) -> None:
        for key, button in self.scope_buttons.items():
            button.setChecked(key == self.c.freq_scope)
            if key == "doc":
                button.setEnabled(self.c.doc_id is not None)
        for key, button in self.algo_buttons.items():
            button.setChecked(key == self.c.freq_algo)

        report = self.c._ensure_freq()
        self._report = report
        if report is None or not report.top_k:
            self.header.set_sub(f"范围：{self.c._freq_scope_name()}")
            clear_layout(self.words_lay)
            hint = QLabel("这个范围里没有可统计的词，换一个范围试试。")
            hint.setObjectName("Note")
            hint.setWordWrap(True)
            self.words_lay.addWidget(hint)
            self.words_lay.addStretch(1)
            self.hash_line.setText("")
            self.sort_line.setText("")
            self.trace_label.setText("")
            self.heap_view.set_items([])
            return

        scope = self.c._freq_scope_name()
        distinct = len(report.quick_sorted)
        tokens = sum(item.count for item in report.quick_sorted)
        self.header.set_sub(f"范围：{scope}")
        example = report.quick_sorted[0] if report.quick_sorted else None
        example_text = (
            f"；例如 {example.word}→{example.count}" if example is not None else ""
        )
        self.hash_line.setText(
            f"不同词 {distinct} 个，累计词次 {tokens}{example_text}。"
        )

        clear_layout(self.words_lay)
        max_count = max((item.count for item in report.top_k), default=1) or 1
        for index, item in enumerate(report.top_k, start=1):
            row = QWidget()
            row_lay = QHBoxLayout(row)
            row_lay.setContentsMargins(0, 2, 0, 2)
            row_lay.setSpacing(8)
            rank = QLabel(f"{index:02d}")
            rank.setObjectName("MonoFaint")
            rank.setFixedWidth(20)
            word = QLabel(item.word)
            word.setObjectName("RowTitle")
            word.setFixedWidth(88)
            bar = QProgressBar()
            bar.setObjectName("BarHot" if index <= 3 else "Bar")
            bar.setRange(0, max_count)
            bar.setValue(item.count)
            bar.setTextVisible(False)
            bar.setFixedHeight(5)
            bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            count = QLabel(str(item.count))
            count.setObjectName("MonoMuted")
            count.setFixedWidth(34)
            count.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            row_lay.addWidget(rank)
            row_lay.addWidget(word)
            row_lay.addWidget(bar, 1)
            row_lay.addWidget(count)
            row.setFixedHeight(28)
            self.words_lay.addWidget(row)
        self.words_lay.addStretch(1)

        self.heap_view.set_items(report.top_k)
        heap_root = min(
            ((item.count, item.word) for item in report.top_k), default=None
        )
        if heap_root is not None:
            self.heap_caption.setText(
                f"堆顶：{heap_root[1]}（{heap_root[0]} 次），是保留的 "
                f"{len(report.top_k)} 个词里最低的。"
            )

        same = [(w.word, w.count) for w in report.quick_sorted] == [
            (w.word, w.count) for w in report.merge_sorted
        ]
        equality = "两次排序结果一致" if same else "两次排序结果不一致"
        self.sort_line.setText(
            f"快速排序 {report.quick_ms:.2f} ms · 归并排序 {report.merge_ms:.2f} ms · {equality}"
        )
        trace = self._trace_text(report)
        self.trace_label.setText(trace)
        self.trace_label.setVisible(bool(trace))

    def _trace_text(self, report: FrequencyReport) -> str:
        items = list(report.top_k[:8])
        if len(items) < 2:
            return ""
        ordered = sorted(items, key=lambda item: item.word)
        if self.c.freq_algo == "quick":
            steps: list[str] = []
            self._quick_steps(ordered, steps)
            body = "\n".join(steps[:4])
            return (
                "步骤示意（本次 Top 8 词，输入按词名排列）：\n" + body
            )
        if self.c.freq_algo == "merge":
            steps = self._merge_steps(ordered)
            return (
                "步骤示意（本次 Top 8 词，输入按词名排列）：\n" + "\n".join(steps[:4])
            )
        return ""

    @staticmethod
    def _quick_steps(items: list[WordCount], steps: list[str], depth: int = 0) -> None:
        if len(items) <= 1 or len(steps) >= 4:
            return
        pivot = items[-1]
        left = [item for item in items[:-1] if (item.count, item.word) > (pivot.count, pivot.word)]
        right = [item for item in items[:-1] if (item.count, item.word) <= (pivot.count, pivot.word)]
        steps.append(
            f"基准 {pivot.word}（{pivot.count}）：左边 {len(left)} 项，右边 {len(right)} 项"
        )
        FrequencyView._quick_steps(left, steps, depth + 1)
        FrequencyView._quick_steps(right, steps, depth + 1)

    @staticmethod
    def _merge_steps(items: list[WordCount]) -> list[str]:
        runs = [[item] for item in items]
        steps: list[str] = []
        while len(runs) > 1 and len(steps) < 4:
            merged_runs: list[list[WordCount]] = []
            for index in range(0, len(runs), 2):
                if index + 1 >= len(runs):
                    merged_runs.append(runs[index])
                    continue
                left, right = runs[index], runs[index + 1]
                merged = sorted(
                    left + right, key=lambda item: (-item.count, item.word)
                )
                if len(steps) < 4:
                    def fmt(run):
                        return "、".join(f"{item.word}({item.count})" for item in run)
                    steps.append(f"合并 [{fmt(left)}] + [{fmt(right)}] → [{fmt(merged)}]")
                merged_runs.append(merged)
            runs = merged_runs
        return steps

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.heap_view.set_theme(theme)


class RecommendView(QWidget):
    def __init__(self, controller) -> None:
        super().__init__()
        self.c = controller
        self._theme: Theme = controller.theme

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.header = ViewHeader("推荐")
        self.change_btn = QPushButton("去目录换起点")
        self.change_btn.setObjectName("LinkButton")
        self.change_btn.setCursor(Qt.PointingHandCursor)
        self.change_btn.setToolTip("到目录里打开文档，再设为推荐起点")
        self.change_btn.clicked.connect(lambda: self.c.set_mode("folder"))
        self.header.right_lay.addWidget(self.change_btn)
        root.addWidget(self.header)

        preset_row = QWidget()
        preset_lay = QHBoxLayout(preset_row)
        preset_lay.setContentsMargins(28, 0, 28, 10)
        preset_lay.setSpacing(4)
        self.preset_group = QButtonGroup(self)
        self.preset_group.setExclusive(True)
        self.preset_buttons: dict[str, QPushButton] = {}
        for key, text in (("balanced", "均衡"), ("structure", "结构优先"), ("content", "内容优先")):
            button = QPushButton(text)
            button.setObjectName("Segment")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(
                lambda checked=False, value=key: self.c.set_preset(value)
            )
            self.preset_group.addButton(button)
            self.preset_buttons[key] = button
            preset_lay.addWidget(button)
        preset_lay.addStretch(1)
        self.weights = QLabel("")
        self.weights.setObjectName("MonoMuted")
        preset_lay.addWidget(self.weights)
        root.addWidget(preset_row)

        body = QWidget()
        body_lay = QHBoxLayout(body)
        body_lay.setContentsMargins(28, 0, 28, 22)
        body_lay.setSpacing(18)
        root.addWidget(body, 1)

        self.list_scroll, self.list_host, self.list_lay = _scroll_host(self)
        body_lay.addWidget(self.list_scroll, 3)

        graph_card = QFrame()
        graph_card.setObjectName("AlgoCard")
        graph_lay = QVBoxLayout(graph_card)
        graph_lay.setContentsMargins(12, 10, 12, 12)
        graph_lay.setSpacing(4)
        graph_title = QLabel("两跳关系")
        graph_title.setObjectName("SectionTitle")
        self.graph_sub = QLabel("")
        self.graph_sub.setObjectName("AlgoLine")
        self.graph_sub.setWordWrap(True)
        self.graph_sub.hide()
        self.graph = GraphViewWidget()
        self.graph.node_clicked.connect(self.c.open_doc)
        graph_lay.addWidget(graph_title)
        graph_lay.addWidget(self.graph_sub)
        graph_lay.addWidget(self.graph, 1)
        body_lay.addWidget(graph_card, 2)

    def set_data(
        self,
        view: Optional[RecommendationView],
        center_title: str,
        preset: str,
    ) -> None:
        for key, button in self.preset_buttons.items():
            button.setChecked(key == preset)
        wd, wc, wk = self.c.preset_weights[preset]
        self.weights.setText(f"权重：目录 {wd:.1f} · 正文 {wc:.1f} · 关键词 {wk:.1f}")
        self.header.set_sub(f"起点：《{center_title}》" if center_title else "还没有推荐起点")
        clear_layout(self.list_lay)
        if view is None:
            self.graph.set_graph(GraphView(nodes=[], edges=[]), "", "")
            return
        self.graph.set_graph(view.graph, center_title, preset)
        self.graph.set_paths(self.c.paths)
        if not view.items:
            empty = QLabel("没有其他文档可以推荐")
            empty.setObjectName("EmptyTitle")
            hint = QLabel("至少需要两篇文档。")
            hint.setObjectName("Note")
            self.list_lay.addWidget(empty)
            self.list_lay.addWidget(hint)
            self.list_lay.addStretch(1)
            return
        for index, item in enumerate(view.items, start=1):
            card = ClickableCard("RecCard")
            lay = QHBoxLayout(card)
            lay.setContentsMargins(0, 10, 4, 10)
            lay.setSpacing(10)
            rank = QLabel(f"{index:02d}")
            rank.setObjectName("MonoFaint")
            rank.setFixedWidth(22)
            rank.setAlignment(Qt.AlignTop | Qt.AlignRight)
            body = QVBoxLayout()
            body.setContentsMargins(0, 0, 0, 0)
            body.setSpacing(4)
            top = QHBoxLayout()
            top.setContentsMargins(0, 0, 0, 0)
            top.setSpacing(8)
            title = QLabel(item.title)
            title.setObjectName("RowTitle")
            title.setWordWrap(True)
            total = QLabel(f"{item.scores.total:.2f}")
            total.setObjectName("RecTotal")
            top.addWidget(title, 1)
            top.addWidget(total, 0, Qt.AlignTop)
            body.addLayout(top)
            path = QLabel(item.relative_path)
            path.setObjectName("RowPath")
            body.addWidget(path)
            for label, value, meter in (
                ("目录", item.scores.directory, "MeterD"),
                ("正文", item.scores.content, "MeterC"),
                ("关键词", item.scores.keywords, "MeterK"),
            ):
                row = QHBoxLayout()
                row.setContentsMargins(0, 0, 0, 0)
                row.setSpacing(6)
                name = QLabel(label)
                name.setObjectName("MonoFaint")
                name.setFixedWidth(42)
                bar = QProgressBar()
                bar.setObjectName(meter)
                bar.setRange(0, 100)
                bar.setValue(int(round(max(0.0, min(1.0, value)) * 100)))
                bar.setTextVisible(False)
                bar.setFixedHeight(4)
                bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                value_label = QLabel(f"{value:.2f}")
                value_label.setObjectName("MonoFaint")
                value_label.setFixedWidth(30)
                value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                row.addWidget(name)
                row.addWidget(bar, 1)
                row.addWidget(value_label)
                body.addLayout(row)
            reason = QLabel(item.reason)
            reason.setObjectName("Reason")
            reason.setWordWrap(True)
            body.addWidget(reason)
            lay.addWidget(rank)
            lay.addLayout(body, 1)
            card.clicked.connect(lambda d=item.doc_id: self.c.open_doc(d))
            card.make_children_transparent()
            self.list_lay.addWidget(card)
        self.list_lay.addStretch(1)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.graph.set_theme(theme)


class DocumentView(QWidget):
    def __init__(self, controller) -> None:
        super().__init__()
        self.c = controller
        self._theme: Theme = controller.theme
        self._doc: Optional[DocModel] = None
        self._terms: Optional[list[str]] = None
        self._hits = None
        self._is_center = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        bar = QFrame()
        bar.setObjectName("DocBar")
        bar_lay = QHBoxLayout(bar)
        bar_lay.setContentsMargins(24, 10, 24, 10)
        bar_lay.setSpacing(12)
        self.back_btn = QPushButton("← 返回")
        self.back_btn.setObjectName("LinkButton")
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.clicked.connect(self.c.go_back_from_document)
        self.path = QLabel("")
        self.path.setObjectName("MonoFaint")
        self.path.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.center_badge = QLabel("当前推荐起点")
        self.center_badge.setObjectName("CenterBadge")
        self.start_btn = QPushButton("以这篇为推荐起点")
        self.start_btn.setObjectName("Primary")
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.setToolTip("把这篇文档作为推荐列表和两跳关系图的起点")
        self.start_btn.clicked.connect(self.c.set_start_from_document)
        self.freq_btn = QPushButton("查看词频")
        self.freq_btn.setObjectName("Ghost")
        self.freq_btn.setCursor(Qt.PointingHandCursor)
        self.freq_btn.setToolTip("查看这篇文档的词频")
        self.freq_btn.clicked.connect(self.c.open_freq_for_doc)
        bar_lay.addWidget(self.back_btn)
        bar_lay.addWidget(self.path, 1)
        bar_lay.addWidget(self.center_badge)
        bar_lay.addWidget(self.start_btn)
        bar_lay.addWidget(self.freq_btn)
        root.addWidget(bar)

        body = QWidget()
        body_lay = QHBoxLayout(body)
        body_lay.setContentsMargins(24, 18, 24, 24)
        body_lay.addStretch(1)
        self.text = QTextBrowser()
        self.text.setObjectName("DocText")
        self.text.setFrameShape(QFrame.NoFrame)
        self.text.setOpenExternalLinks(False)
        self.text.setMaximumWidth(920)
        self.text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.text.document().setDocumentMargin(0)
        self.text.setStyleSheet("QTextBrowser#DocText { padding: 0 24px; }")
        body_lay.addWidget(self.text, 12)
        body_lay.addStretch(1)
        root.addWidget(body, 1)

    def show_document(
        self,
        doc: DocModel,
        terms: Optional[list[str]],
        hits,
        is_center: bool,
    ) -> None:
        self._doc = doc
        self._terms = terms
        self._hits = hits
        self._is_center = is_center
        self.path.setText(doc.relative_path)
        self.center_badge.setVisible(is_center)
        self.start_btn.setVisible(not is_center)
        self._render()

    def _render(self) -> None:
        doc = self._doc
        if doc is None:
            return
        title_spans = [hit.span for hit in (self._hits or []) if getattr(hit, "field", "") == "title"]
        body_spans = [hit.span for hit in (self._hits or []) if getattr(hit, "field", "") == "body"]
        self.text.setHtml(doc_html(doc, self._theme, title_spans, body_spans))
        cursor = QTextCursor(self.text.document())
        cursor.select(QTextCursor.Document)
        fmt = QTextBlockFormat()
        fmt.setLineHeight(172.0, QTextBlockFormat.ProportionalHeight.value)
        cursor.mergeBlockFormat(fmt)
        cursor.clearSelection()
        cursor.setPosition(0)
        self.text.setTextCursor(cursor)
        self.text.verticalScrollBar().setValue(0)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._render()
