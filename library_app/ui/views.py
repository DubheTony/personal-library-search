"""主工作区视图：目录、检索、词频、推荐、文档。

每个视图独占主工作区，不再共用固定侧栏和常驻关系图。
"""
from __future__ import annotations

import heapq
import html
import re
from typing import Optional

from PySide6.QtCore import QRectF, QTimer, Qt, Signal
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
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..models import (
    DocumentView as DocModel,
    FrequencyReport,
    GraphView,
    RecommendationItem,
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




class DirectoryTree(QWidget):
    """文件夹与文档合在同一棵树里；文件夹负责导航，文档打开阅读页。"""

    def __init__(self, controller, parent=None) -> None:
        super().__init__(parent)
        self.c = controller
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.scroll, self.host, self.tree_lay = _scroll_host(self)
        lay.addWidget(self.scroll)

    def rebuild(self) -> None:
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
        root.clicked.connect(lambda: self.c.set_current_folder(""))
        self.tree_lay.addWidget(root)

        def walk(node: TreeItem, depth: int) -> None:
            for child in node.children:
                if child.kind == "folder":
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
                        lambda p=child.relative_path: self.c.set_current_folder(p)
                    )
                    self.tree_lay.addWidget(card)
                    if expanded:
                        walk(child, depth + 1)
                else:
                    card = ClickableCard("TreeRow")
                    card.setProperty("kind", "doc")
                    card.set_active(child.doc_id == self.c.doc_id)
                    lay = QHBoxLayout(card)
                    lay.setContentsMargins(6 + depth * 12 + 13, 0, 6, 0)
                    lay.setSpacing(5)
                    dot = QLabel("•")
                    dot.setObjectName("Dot")
                    dot.setFixedWidth(7)
                    name = QLabel(child.name)
                    name.setObjectName("TreeName")
                    name.setToolTip(child.relative_path)
                    lay.addWidget(dot)
                    lay.addWidget(name, 1)
                    card.setFixedHeight(26)
                    card.clicked.connect(
                        lambda d=child.doc_id: self.c.open_doc(d)
                    )
                    dot.setAttribute(Qt.WA_TransparentForMouseEvents, True)
                    name.setAttribute(Qt.WA_TransparentForMouseEvents, True)
                    self.tree_lay.addWidget(card)

        walk(self.c.tree_root, 0)
        self.tree_lay.addStretch(1)


class TraversalAnim(QWidget):
    """真实目录树上的深度优先遍历动画。"""

    ROW_H = 22
    changed = Signal(int)
    playing_changed = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._theme: Optional[Theme] = None
        self._entries: list[tuple[str, str, int]] = []
        self._index = 0
        self._playing = False
        self._timer = QTimer(self)
        self._timer.setInterval(480)
        self._timer.timeout.connect(self._tick)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def set_tree(self, root: TreeItem) -> None:
        self._timer.stop()
        self._playing = False
        self._entries = [("folder", "全部文档", 0)]

        def walk(node: TreeItem, depth: int) -> None:
            for child in node.children:
                self._entries.append((child.kind, child.name, depth))
                if child.kind == "folder":
                    walk(child, depth + 1)

        walk(root, 1)
        self._index = 0
        self.setMinimumHeight(max(180, len(self._entries) * self.ROW_H + 16))
        self.update()
        self.changed.emit(0)
        self.playing_changed.emit(False)

    def current_index(self) -> int:
        return self._index

    def current_text(self) -> str:
        if not self._entries:
            return "没有可遍历的节点"
        kind, name, _ = self._entries[self._index]
        prefix = "目录" if kind == "folder" else "文档"
        return f"第 {self._index + 1} / {len(self._entries)} 步 · {prefix} {name}"

    def play(self) -> None:
        if not self._entries:
            return
        if self._index >= len(self._entries) - 1:
            self._index = 0
            self.changed.emit(0)
        self._playing = True
        self._timer.start()
        self.playing_changed.emit(True)
        self.update()

    def pause(self) -> None:
        self._timer.stop()
        self._playing = False
        self.playing_changed.emit(False)
        self.update()

    def toggle(self) -> None:
        if self._playing:
            self.pause()
        else:
            self.play()

    def step(self) -> None:
        if not self._entries:
            return
        if self._index < len(self._entries) - 1:
            self._index += 1
            self.changed.emit(self._index)
            self.update()
        else:
            self.pause()

    def reset(self) -> None:
        self._timer.stop()
        self._playing = False
        self._index = 0
        self.changed.emit(0)
        self.playing_changed.emit(False)
        self.update()

    def _tick(self) -> None:
        if self._index >= len(self._entries) - 1:
            self.pause()
            return
        self.step()

    def paintEvent(self, event) -> None:  # noqa: N802
        theme = self._theme
        if theme is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        font = QFont(theme.sans)
        font.setPixelSize(10)
        mono = QFont(theme.mono)
        mono.setPixelSize(9)
        for index, (kind, name, depth) in enumerate(self._entries):
            y = 8 + index * self.ROW_H
            if y > self.height():
                break
            current = index == self._index
            visited = index < self._index
            if current:
                p.fillRect(QRectF(0, y - 3, self.width(), self.ROW_H), QColor(theme.accent_soft))
                p.fillRect(QRectF(0, y - 3, 2, self.ROW_H), QColor(theme.accent))
            color = QColor(
                theme.text if current else (theme.text_dim if visited else theme.muted)
            )
            x = 10 + depth * 16
            p.setFont(mono)
            p.setPen(QColor(theme.faint))
            p.drawText(
                QRectF(x, y, 10, self.ROW_H),
                Qt.AlignLeft | Qt.AlignVCenter,
                "▸" if kind == "folder" else "•",
            )
            p.setFont(font)
            p.setPen(color)
            p.drawText(
                QRectF(x + 12, y, max(20, self.width() - x - 20), self.ROW_H),
                Qt.AlignLeft | Qt.AlignVCenter,
                name,
            )
        p.end()


class DirectoryView(QWidget):
    def __init__(self, controller) -> None:
        super().__init__()
        self.c = controller
        self._theme: Theme = controller.theme

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.header = ViewHeader("目录")
        self.header.set_sub("按文件夹浏览")
        root.addWidget(self.header)

        body = QWidget()
        body_lay = QHBoxLayout(body)
        body_lay.setContentsMargins(28, 16, 28, 22)
        body_lay.setSpacing(20)
        root.addWidget(body, 1)

        left = QWidget()
        left.setFixedWidth(380)
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(8)
        tree_title = QLabel("文件夹")
        tree_title.setObjectName("SectionTitle")
        left_lay.addWidget(tree_title)
        self.tree = DirectoryTree(self.c)
        left_lay.addWidget(self.tree, 1)
        body_lay.addWidget(left)

        right = QFrame()
        right.setObjectName("AlgoCard")
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(14, 12, 14, 12)
        right_lay.setSpacing(6)
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(8)
        anim_title = QLabel("深度优先遍历")
        anim_title.setObjectName("SectionTitle")
        self.traversal_label = QLabel("")
        self.traversal_label.setObjectName("MonoMuted")
        head.addWidget(anim_title)
        head.addStretch(1)
        head.addWidget(self.traversal_label)
        right_lay.addLayout(head)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(6)
        self.play_btn = QPushButton("播放")
        self.play_btn.setObjectName("LinkButton")
        self.play_btn.setCursor(Qt.PointingHandCursor)
        self.next_btn = QPushButton("下一步")
        self.next_btn.setObjectName("LinkButton")
        self.next_btn.setCursor(Qt.PointingHandCursor)
        self.reset_btn = QPushButton("重置")
        self.reset_btn.setObjectName("LinkButton")
        self.reset_btn.setCursor(Qt.PointingHandCursor)
        controls.addWidget(self.play_btn)
        controls.addWidget(self.next_btn)
        controls.addWidget(self.reset_btn)
        controls.addStretch(1)
        right_lay.addLayout(controls)

        self.traversal = TraversalAnim()
        self.traversal_scroll = QScrollArea()
        self.traversal_scroll.setWidgetResizable(True)
        self.traversal_scroll.setFrameShape(QFrame.NoFrame)
        self.traversal_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.traversal_scroll.setWidget(self.traversal)
        right_lay.addWidget(self.traversal_scroll, 1)
        body_lay.addWidget(right, 1)

        self.play_btn.clicked.connect(self.traversal.toggle)
        self.next_btn.clicked.connect(self.traversal.step)
        self.reset_btn.clicked.connect(self.traversal.reset)
        self.traversal.changed.connect(self._on_traversal_changed)
        self.traversal.playing_changed.connect(self._on_traversal_playing)

    def refresh(self) -> None:
        self.tree.rebuild()
        self.traversal.set_tree(self.c.tree_root)
        self._on_traversal_changed(0)

    def refresh_tree(self) -> None:
        self.tree.rebuild()

    def _on_traversal_changed(self, index: int) -> None:
        self.traversal_label.setText(self.traversal.current_text())
        QTimer.singleShot(0, self._scroll_to_current)

    def _on_traversal_playing(self, playing: bool) -> None:
        self.play_btn.setText("暂停" if playing else "播放")

    def _scroll_to_current(self) -> None:
        index = self.traversal.current_index()
        y = 8 + index * self.traversal.ROW_H
        bar = self.traversal_scroll.verticalScrollBar()
        target = y - self.traversal_scroll.viewport().height() // 2
        bar.setValue(max(0, min(bar.maximum(), target)))

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.traversal.set_theme(theme)


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

        mode_row = QHBoxLayout()
        mode_row.setContentsMargins(0, 0, 0, 0)
        mode_row.setSpacing(4)
        self.mode_buttons: dict[str, QPushButton] = {}
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        for key, text in (("word", "按词检索"), ("phrase", "短语精确查找")):
            button = QPushButton(text)
            button.setObjectName("Segment")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(
                lambda checked=False, value=key: self.c.set_search_mode(value)
            )
            self.mode_group.addButton(button)
            self.mode_buttons[key] = button
            mode_row.addWidget(button)
        mode_row.addStretch(1)
        top_lay.addLayout(mode_row)

        query_row = QHBoxLayout()
        query_row.setContentsMargins(0, 0, 0, 0)
        query_row.setSpacing(8)
        self.query_label = QLabel("")
        self.query_label.setObjectName("ViewSub")
        self.mode_label = QLabel("")
        self.mode_label.setObjectName("Kicker")
        query_row.addWidget(self.query_label)
        query_row.addWidget(self.mode_label)
        query_row.addStretch(1)
        top_lay.addLayout(query_row)

        self.terms_lay = QHBoxLayout()
        self.terms_lay.setContentsMargins(0, 0, 0, 0)
        self.terms_lay.setSpacing(6)
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
        mode = getattr(self.c, "search_mode", "word")
        for key, button in self.mode_buttons.items():
            button.setChecked(key == mode)
        self.mode_label.setText("短语精确匹配" if mode == "phrase" else "按词检索")
        self.count.setText(f"{len(results)} 条结果")
        if query:
            self.query_label.setText(f"「{query}」")
        else:
            self.query_label.setText(
                "在顶部输入完整短语后回车"
                if mode == "phrase"
                else "在顶部输入关键词后回车"
            )
        clear_layout(self.terms_lay)
        if mode != "phrase":
            tag = QLabel("倒排命中")
            tag.setObjectName("Kicker")
            self.terms_lay.addWidget(tag)
        if mode == "phrase":
            if query and results:
                total_hits = sum(result.match_count for result in results)
                chip = QLabel(f"{query} · {len(results)} 篇 / {total_hits} 处")
                chip.setObjectName("Chips")
                self.terms_lay.addWidget(chip)
        else:
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
                chip = QLabel(
                    f"{term} · {docs.get(term, 0)} 篇 / {counts.get(term, 0)} 处"
                )
                chip.setObjectName("Chips")
                self.terms_lay.addWidget(chip)
        self.terms_lay.addStretch(1)

        clear_layout(self.results_lay)
        if not results:
            if not query:
                self.results_lay.addStretch(1)
                return
            self.results_lay.addSpacing(24)
            if mode == "phrase":
                empty = QLabel("没有找到这个短语")
                empty.setObjectName("EmptyTitle")
                self.results_lay.addWidget(empty)
                hint = QLabel("换一个短语再试，或改用按词检索。")
                hint.setObjectName("Note")
                self.results_lay.addWidget(hint)
                switch = QPushButton("改用按词检索")
                switch.setObjectName("LinkButton")
                switch.setCursor(Qt.PointingHandCursor)
                switch.clicked.connect(lambda: self.c.set_search_mode("word"))
                self.results_lay.addWidget(switch)
            else:
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




class HashGrid(QWidget):
    """哈希计数的图形化总览：每个小格是一个词，颜色深浅表示次数。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._items: list[WordCount] = []
        self._theme: Optional[Theme] = None
        self.setMinimumHeight(140)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_items(self, items: list[WordCount]) -> None:
        self._items = list(items)
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
        max_count = max(item.count for item in self._items) or 1
        columns = max(1, self.width() // 38)
        rows = (len(self._items) + columns - 1) // columns
        cell_w = self.width() / columns
        cell_h = max(10.0, min(24.0, (self.height() - 4) / max(1, rows)))
        font = QFont(theme.mono)
        font.setPixelSize(8)
        p.setFont(font)
        for index, item in enumerate(self._items):
            row, col = divmod(index, columns)
            x = col * cell_w
            y = row * cell_h
            alpha = 24 + int(160 * min(1.0, item.count / max_count))
            color = QColor(theme.accent)
            color.setAlpha(alpha)
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(
                QRectF(x + 1, y + 1, max(4.0, cell_w - 2), max(4.0, cell_h - 2)),
                theme.radius + 1,
                theme.radius + 1,
            )
            if index < 12 and cell_h >= 14:
                p.setPen(
                    QColor(
                        theme.on_accent
                        if item.count / max_count > 0.55
                        else theme.text_dim
                    )
                )
                p.drawText(
                    QRectF(x + 2, y, max(4.0, cell_w - 4), cell_h),
                    Qt.AlignCenter,
                    item.word,
                )
        p.end()


class SortAnimWidget(QWidget):
    """用方块步进演示排序过程，数据来自本次词频的前几个词。"""

    changed = Signal(int)
    playing_changed = Signal(bool)

    def __init__(self, mode: str, parent=None) -> None:
        super().__init__(parent)
        self.mode = mode
        self._theme: Optional[Theme] = None
        self._items: list[tuple[str, int]] = []
        self._steps: list[tuple[list[tuple[str, int]], set[int], set[int]]] = []
        self._index = 0
        self._playing = False
        self._timer = QTimer(self)
        self._timer.setInterval(560)
        self._timer.timeout.connect(self._tick)
        self.setMinimumHeight(260)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def set_items(self, items: list[WordCount]) -> None:
        self._items = [(item.word, item.count) for item in items]
        self._steps = self._build_steps()
        self._index = 0
        self._timer.stop()
        self._playing = False
        self.update()
        self.changed.emit(0)
        self.playing_changed.emit(False)

    def step_count(self) -> int:
        return len(self._steps)

    def current_index(self) -> int:
        return self._index

    @staticmethod
    def _key(item: tuple[str, int]) -> tuple[int, str]:
        return (-item[1], item[0])

    def _build_steps(self):
        if len(self._items) < 2:
            return [(list(self._items), set(), set())]
        array = sorted(self._items, key=lambda item: item[0])
        steps: list[tuple[list[tuple[str, int]], set[int], set[int]]] = []
        if self.mode == "quick":
            self._quick(array, steps, 0, len(array) - 1)
        else:
            self._merge(array, steps)
        if not steps:
            steps.append((list(array), set(), set()))
        steps.append((list(array), set(), set(range(len(array)))))
        return steps

    def _quick(self, array, steps, low: int, high: int) -> None:
        if low >= high:
            return
        pivot = array[high]
        store = low
        for index in range(low, high):
            if self._key(array[index]) < self._key(pivot):
                array[store], array[index] = array[index], array[store]
                steps.append((list(array), {store, index, high}, set()))
                store += 1
        array[store], array[high] = array[high], array[store]
        steps.append((list(array), {store, high}, set()))
        self._quick(array, steps, low, store - 1)
        self._quick(array, steps, store + 1, high)

    def _merge(self, array, steps) -> None:
        width = 1
        while width < len(array):
            for low in range(0, len(array), 2 * width):
                middle = min(low + width, len(array))
                high = min(low + 2 * width, len(array))
                array[low:high] = sorted(array[low:high], key=self._key)
                steps.append((list(array), set(range(low, high)), set()))
            width *= 2

    def play(self) -> None:
        if not self._steps:
            return
        if self._index >= len(self._steps) - 1:
            self._index = 0
            self.changed.emit(0)
        self._playing = True
        self._timer.start()
        self.playing_changed.emit(True)
        self.update()

    def pause(self) -> None:
        self._timer.stop()
        self._playing = False
        self.playing_changed.emit(False)
        self.update()

    def toggle(self) -> None:
        if self._playing:
            self.pause()
        else:
            self.play()

    def step(self) -> None:
        if not self._steps:
            return
        if self._index < len(self._steps) - 1:
            self._index += 1
            self.changed.emit(self._index)
            self.update()
        else:
            self.pause()

    def reset(self) -> None:
        self._timer.stop()
        self._playing = False
        self._index = 0
        self.changed.emit(0)
        self.playing_changed.emit(False)
        self.update()

    def _tick(self) -> None:
        if self._index >= len(self._steps) - 1:
            self.pause()
            return
        self.step()

    def paintEvent(self, event) -> None:  # noqa: N802
        theme = self._theme
        if theme is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if not self._steps:
            p.setPen(QColor(theme.muted))
            p.setFont(QFont(theme.sans, 10))
            p.drawText(self.rect(), Qt.AlignCenter, "暂无词频数据")
            p.end()
            return
        array, active, finished = self._steps[self._index]
        count = len(array)
        gap = 8.0
        block_w = max(18.0, (self.width() - gap * (count + 1)) / max(1, count))
        block_h = min(150.0, max(70.0, self.height() * 0.40))
        top = (self.height() - block_h) / 2
        font = QFont(theme.sans)
        font.setPixelSize(10)
        mono = QFont(theme.mono)
        mono.setPixelSize(9)
        for index, (word, value) in enumerate(array):
            x = gap + index * (block_w + gap)
            rect = QRectF(x, top, block_w, block_h)
            if index in active:
                fill = QColor(theme.accent)
                border = QColor(theme.accent)
                text_color = QColor(theme.on_accent)
            elif index in finished:
                fill = QColor(theme.accent_soft)
                border = QColor(theme.signal)
                text_color = QColor(theme.text)
            else:
                fill = QColor(theme.card)
                border = QColor(theme.line)
                text_color = QColor(theme.text)
            p.setBrush(fill)
            p.setPen(QPen(border, 1.2))
            p.drawRoundedRect(rect, theme.radius + 2, theme.radius + 2)
            p.setFont(font)
            p.setPen(text_color)
            label = word if len(word) <= 4 else word[:3] + "…"
            p.drawText(
                QRectF(x + 2, top + 8, block_w - 4, 18),
                Qt.AlignCenter,
                label,
            )
            p.setFont(mono)
            p.setPen(text_color)
            p.drawText(
                QRectF(x + 2, top + block_h - 22, block_w - 4, 16),
                Qt.AlignCenter,
                str(value),
            )
        p.end()


class SortPage(QFrame):
    def __init__(self, title: str, mode: str, parent=None) -> None:
        super().__init__(parent)
        self.mode = mode
        self.setObjectName("AlgoCard")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(4)
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(8)
        title_label = QLabel(title)
        title_label.setObjectName("SectionTitle")
        head.addWidget(title_label)
        head.addStretch(1)
        lay.addLayout(head)
        self.compare_label = QLabel("")
        self.compare_label.setObjectName("AlgoLine")
        self.compare_label.setWordWrap(True)
        lay.addWidget(self.compare_label)
        self.anim = SortAnimWidget(mode)
        lay.addWidget(self.anim, 1)
        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(6)
        self.play_btn = QPushButton("播放")
        self.play_btn.setObjectName("LinkButton")
        self.play_btn.setCursor(Qt.PointingHandCursor)
        self.next_btn = QPushButton("下一步")
        self.next_btn.setObjectName("LinkButton")
        self.next_btn.setCursor(Qt.PointingHandCursor)
        self.reset_btn = QPushButton("重置")
        self.reset_btn.setObjectName("LinkButton")
        self.reset_btn.setCursor(Qt.PointingHandCursor)
        self.step_label = QLabel("")
        self.step_label.setObjectName("MonoFaint")
        controls.addWidget(self.play_btn)
        controls.addWidget(self.next_btn)
        controls.addWidget(self.reset_btn)
        controls.addStretch(1)
        controls.addWidget(self.step_label)
        lay.addLayout(controls)
        self.play_btn.clicked.connect(self.anim.toggle)
        self.next_btn.clicked.connect(self.anim.step)
        self.reset_btn.clicked.connect(self.anim.reset)
        self.anim.changed.connect(self._on_changed)
        self.anim.playing_changed.connect(self._on_playing)

    def set_data(self, items: list[WordCount], quick_ms: float, merge_ms: float) -> None:
        self.compare_label.setText(
            f"本次前 8 个词：快速 {quick_ms:.2f} ms · 归并 {merge_ms:.2f} ms"
        )
        self.anim.set_items(items)

    def set_theme(self, theme: Theme) -> None:
        self.anim.set_theme(theme)

    def _on_changed(self, index: int) -> None:
        total = max(1, self.anim.step_count())
        self.step_label.setText(f"第 {min(index + 1, total)} / {total} 步")

    def _on_playing(self, playing: bool) -> None:
        self.play_btn.setText("暂停" if playing else "播放")


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

        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(12)

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
        left_lay.addWidget(words_card, 1)

        hash_card = QFrame()
        hash_card.setObjectName("AlgoCard")
        hash_card.setFixedHeight(215)
        hash_lay = QVBoxLayout(hash_card)
        hash_lay.setContentsMargins(14, 10, 14, 10)
        hash_lay.setSpacing(4)
        hash_head = QHBoxLayout()
        hash_head.setContentsMargins(0, 0, 0, 0)
        hash_title = QLabel("哈希计数")
        hash_title.setObjectName("AlgoTitle")
        self.hash_count = QLabel("")
        self.hash_count.setObjectName("MonoMuted")
        hash_head.addWidget(hash_title)
        hash_head.addStretch(1)
        hash_head.addWidget(self.hash_count)
        hash_lay.addLayout(hash_head)
        self.hash_grid = HashGrid()
        hash_lay.addWidget(self.hash_grid, 1)
        left_lay.addWidget(hash_card)
        body_lay.addWidget(left, 3)

        self.algo_stack = QStackedWidget()
        heap_page = QFrame()
        heap_page.setObjectName("AlgoCard")
        heap_lay = QVBoxLayout(heap_page)
        heap_lay.setContentsMargins(14, 12, 14, 12)
        heap_lay.setSpacing(4)
        heap_title = QLabel("Top-K 最小堆")
        heap_title.setObjectName("SectionTitle")
        self.heap_caption = QLabel("")
        self.heap_caption.setObjectName("AlgoLine")
        self.heap_caption.setWordWrap(True)
        self.heap_view = HeapView()
        heap_lay.addWidget(heap_title)
        heap_lay.addWidget(self.heap_view, 1)
        heap_lay.addWidget(self.heap_caption)
        self.algo_stack.addWidget(heap_page)

        self.quick_page = SortPage("快速排序", "quick")
        self.merge_page = SortPage("归并排序", "merge")
        self.algo_stack.addWidget(self.quick_page)
        self.algo_stack.addWidget(self.merge_page)
        body_lay.addWidget(self.algo_stack, 2)

    def refresh(self) -> None:
        for key, button in self.scope_buttons.items():
            button.setChecked(key == self.c.freq_scope)
            if key == "doc":
                button.setEnabled(self.c.doc_id is not None)
        for key, button in self.algo_buttons.items():
            button.setChecked(key == self.c.freq_algo)
        index = {"top": 0, "quick": 1, "merge": 2}.get(self.c.freq_algo, 0)
        self.algo_stack.setCurrentIndex(index)

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
            self.hash_count.setText("")
            self.hash_grid.set_items([])
            self.heap_view.set_items([])
            self.heap_caption.setText("")
            self.quick_page.set_data([], 0.0, 0.0)
            self.merge_page.set_data([], 0.0, 0.0)
            return

        scope = self.c._freq_scope_name()
        distinct = len(report.quick_sorted)
        tokens = sum(item.count for item in report.quick_sorted)
        self.header.set_sub(f"范围：{scope}")
        self.hash_count.setText(f"{distinct} 个词 · {tokens} 个词次")
        self.hash_grid.set_items(report.quick_sorted)

        clear_layout(self.words_lay)
        max_count = max((item.count for item in report.top_k), default=1) or 1
        for position, item in enumerate(report.top_k, start=1):
            row = QWidget()
            row_lay = QHBoxLayout(row)
            row_lay.setContentsMargins(0, 2, 0, 2)
            row_lay.setSpacing(8)
            rank = QLabel(f"{position:02d}")
            rank.setObjectName("MonoFaint")
            rank.setFixedWidth(20)
            word = QLabel(item.word)
            word.setObjectName("RowTitle")
            word.setFixedWidth(88)
            bar = QProgressBar()
            bar.setObjectName("BarHot" if position <= 3 else "Bar")
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
        self.heap_caption.setText(
            f"堆顶：{heap_root[1]}（{heap_root[0]} 次）" if heap_root is not None else ""
        )
        demo_items = report.top_k[:8]
        self.quick_page.set_data(demo_items, report.quick_ms, report.merge_ms)
        self.merge_page.set_data(demo_items, report.quick_ms, report.merge_ms)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.hash_grid.set_theme(theme)
        self.heap_view.set_theme(theme)
        self.quick_page.set_theme(theme)
        self.merge_page.set_theme(theme)


class RecommendView(QWidget):
    def __init__(self, controller) -> None:
        super().__init__()
        self.c = controller
        self._theme: Theme = controller.theme
        self._view: Optional[RecommendationView] = None
        self._center_title = ""
        self._selected_doc_id: Optional[int] = None
        self._path_mode = "strength"
        self._only_same = False
        self._has_paths = False
        self._has_clusters = False
        self._items_by_id: dict[int, RecommendationItem] = {}
        self._cards: dict[int, ClickableCard] = {}

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
        for key, text in (
            ("balanced", "均衡"),
            ("structure", "结构优先"),
            ("content", "内容优先"),
        ):
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
        self.only_same = QCheckBox("只看同簇")
        self.only_same.setObjectName("FilterCheck")
        self.only_same.setCursor(Qt.PointingHandCursor)
        self.only_same.toggled.connect(self._filter_changed)
        self.only_same.hide()
        preset_lay.addWidget(self.only_same)
        preset_lay.addSpacing(12)
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

        self.path_panel = QWidget()
        path_lay = QVBoxLayout(self.path_panel)
        path_lay.setContentsMargins(0, 0, 0, 6)
        path_lay.setSpacing(4)
        path_head = QHBoxLayout()
        path_head.setContentsMargins(0, 0, 0, 0)
        path_head.setSpacing(6)
        path_title = QLabel("关联链")
        path_title.setObjectName("AlgoTitle")
        path_head.addWidget(path_title)
        path_head.addStretch(1)
        self.path_mode_group = QButtonGroup(self)
        self.path_mode_group.setExclusive(True)
        self.path_mode_buttons: dict[str, QPushButton] = {}
        for key, text in (("hops", "最少跳数"), ("strength", "最强关联")):
            button = QPushButton(text)
            button.setObjectName("Segment")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(
                lambda checked=False, value=key: self._set_path_mode(value)
            )
            self.path_mode_group.addButton(button)
            self.path_mode_buttons[key] = button
            path_head.addWidget(button)
        path_lay.addLayout(path_head)
        self.path_chain = QLabel("选择一条推荐查看关联链")
        self.path_chain.setObjectName("PathChain")
        self.path_chain.setTextFormat(Qt.PlainText)
        self.path_chain.setWordWrap(True)
        path_lay.addWidget(self.path_chain)
        self.path_hint = QLabel("")
        self.path_hint.setObjectName("Kicker")
        self.path_hint.setWordWrap(True)
        self.path_hint.hide()
        path_lay.addWidget(self.path_hint)
        self.path_panel.hide()
        graph_lay.addWidget(self.path_panel)

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

    # ---------- 数据 ----------
    def set_data(
        self,
        view: Optional[RecommendationView],
        center_title: str,
        preset: str,
    ) -> None:
        self._view = view
        self._center_title = center_title
        for key, button in self.preset_buttons.items():
            button.setChecked(key == preset)
        wd, wc, wk = self.c.preset_weights[preset]
        self.weights.setText(f"权重：目录 {wd:.1f} · 正文 {wc:.1f} · 关键词 {wk:.1f}")

        items = list(view.items) if view is not None else []
        self._items_by_id = {item.doc_id: item for item in items}
        self._has_paths = any(bool(getattr(item, "paths", None)) for item in items)
        self._has_clusters = bool(
            view is not None and getattr(view, "cluster_sizes", None)
        )
        self.only_same.setVisible(self._has_clusters)
        if not self._has_clusters:
            self.only_same.blockSignals(True)
            self.only_same.setChecked(False)
            self.only_same.blockSignals(False)
            self._only_same = False
        self.path_panel.setVisible(self._has_paths)
        self.path_hint.hide()

        subtitle = f"起点：《{center_title}》" if center_title else "还没有推荐起点"
        if self._has_clusters and view is not None:
            cluster_sizes = getattr(view, "cluster_sizes", {}) or {}
            center_cluster = getattr(view, "center_cluster_id", None)
            center_size = cluster_sizes.get(center_cluster, 0)
            cross_count = sum(
                1 for item in items if not getattr(item, "same_cluster", False)
            )
            subtitle += (
                f" · 当前文档所在资料簇 {center_size} 篇 · "
                f"跨簇推荐 {cross_count} 篇"
            )
        self.header.set_sub(subtitle)

        if self._selected_doc_id not in self._items_by_id:
            self._selected_doc_id = None

        if view is None:
            clear_layout(self.list_lay)
            self.graph.set_graph(GraphView(nodes=[], edges=[]), "", "")
            self.graph.set_highlight_path([])
            return
        self.graph.set_graph(view.graph, center_title, preset)
        self.graph.set_paths(self.c.paths)
        self._rebuild_list()
        self._update_path_panel()

    def _filtered_items(self):
        items = list(self._view.items) if self._view is not None else []
        if self._only_same:
            items = [item for item in items if getattr(item, "same_cluster", False)]
        return items

    def _rebuild_list(self) -> None:
        clear_layout(self.list_lay)
        self._cards: dict[int, ClickableCard] = {}
        if self._view is None:
            return
        if not self._view.items:
            empty = QLabel("没有其他文档可以推荐")
            empty.setObjectName("EmptyTitle")
            hint = QLabel("至少需要两篇文档。")
            hint.setObjectName("Note")
            self.list_lay.addWidget(empty)
            self.list_lay.addWidget(hint)
            self.list_lay.addStretch(1)
            return

        visible_ids = set()
        for index, item in enumerate(self._view.items, start=1):
            if self._only_same and not getattr(item, "same_cluster", False):
                continue
            visible_ids.add(item.doc_id)
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
            top.addWidget(title, 1)
            if self._has_clusters:
                badge = QLabel(
                    "同簇" if getattr(item, "same_cluster", False) else "跨簇"
                )
                badge.setObjectName("ClusterBadge")
                top.addWidget(badge, 0, Qt.AlignTop)
            total = QLabel(f"{item.scores.total:.2f}")
            total.setObjectName("RecTotal")
            top.addWidget(total, 0, Qt.AlignTop)
            body.addLayout(top)

            path_row = QHBoxLayout()
            path_row.setContentsMargins(0, 0, 0, 0)
            path_row.setSpacing(6)
            path = QLabel(item.relative_path)
            path.setObjectName("RowPath")
            open_btn = QPushButton("打开")
            open_btn.setObjectName("LinkButton")
            open_btn.setCursor(Qt.PointingHandCursor)
            open_btn.clicked.connect(lambda d=item.doc_id: self.c.open_doc(d))
            path_row.addWidget(path, 1)
            path_row.addWidget(open_btn, 0)
            body.addLayout(path_row)

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
            card.set_active(item.doc_id == self._selected_doc_id)
            card.clicked.connect(lambda d=item.doc_id: self._select_item(d))
            card.make_children_transparent()
            open_btn.setAttribute(Qt.WA_TransparentForMouseEvents, False)
            self._cards[item.doc_id] = card
            self.list_lay.addWidget(card)

        if self._selected_doc_id not in visible_ids:
            self._selected_doc_id = None
        if not visible_ids:
            empty = QLabel("当前筛选下没有推荐")
            empty.setObjectName("EmptyTitle")
            hint = QLabel("取消“只看同簇”试试。")
            hint.setObjectName("Note")
            self.list_lay.addWidget(empty)
            self.list_lay.addWidget(hint)
        self.list_lay.addStretch(1)

    def _select_item(self, doc_id: int) -> None:
        if doc_id not in self._items_by_id:
            return
        self._selected_doc_id = doc_id
        for item_id, card in self._cards.items():
            card.set_active(item_id == doc_id)
        self._update_path_panel()

    def _set_path_mode(self, mode: str) -> None:
        if mode not in ("hops", "strength"):
            return
        self._path_mode = mode
        self._update_path_panel()

    def _update_path_panel(self) -> None:
        for key, button in self.path_mode_buttons.items():
            button.setChecked(key == self._path_mode)
        if not self._has_paths:
            self.path_panel.hide()
            self.graph.set_highlight_path([])
            return
        self.path_panel.show()
        item = self._items_by_id.get(self._selected_doc_id)
        if item is None:
            self.path_chain.setText("选择一条推荐查看关联链")
            self.path_hint.hide()
            self.graph.set_highlight_path([])
            return

        paths = getattr(item, "paths", {}) or {}
        if not paths:
            self.path_chain.setText("关联链不可用")
            self.path_hint.hide()
            self.graph.set_highlight_path([])
            return
        key = "dijkstra" if self._path_mode == "strength" else "bfs"
        path = paths.get(key)
        if path is None:
            self.path_chain.setText("关联链不可用")
            self.path_hint.hide()
            self.graph.set_highlight_path([])
            return
        if not path.nodes:
            self.path_chain.setText(
                "无关联链，仅按内容相似推荐"
                if self._path_mode == "strength"
                else "两跳内不可达"
            )
            self.path_hint.hide()
            self.graph.set_highlight_path([])
            return

        parts = [f"起点《{path.nodes[0].title}》"]
        for segment, node in zip(path.segments, path.nodes[1:]):
            parts.append(
                f"→《{node.title}》（{segment.basis}，代价 {segment.cost:.2f}）"
            )
        chain = " ".join(parts)
        chain += f"\n跳数 {path.hops} · 总代价 {path.total_cost:.2f}"
        self.path_chain.setText(chain)

        visible = (
            {node.doc_id for node in self._view.graph.nodes}
            if self._view is not None
            else set()
        )
        hidden = any(node.doc_id not in visible for node in path.nodes)
        hint = "图中虚线为这条关联链"
        if self._has_clusters:
            hint += "；节点数字为资料簇编号"
        if hidden:
            hint += "；不在当前两跳图中的节点只显示在文字里"
        self.path_hint.setText(hint + "。")
        self.path_hint.show()
        self.graph.set_highlight_path([node.doc_id for node in path.nodes])

    def _filter_changed(self, checked: bool) -> None:
        self._only_same = bool(checked)
        item = self._items_by_id.get(self._selected_doc_id)
        if checked and item is not None and not getattr(item, "same_cluster", False):
            self._selected_doc_id = None
        self._rebuild_list()
        self._update_path_panel()

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
        self._tree_collapsed = False

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
        body_lay.setContentsMargins(0, 0, 24, 24)
        body_lay.setSpacing(0)

        self.tree_panel = QFrame()
        self.tree_panel.setObjectName("DocTreePanel")
        self.tree_panel.setFixedWidth(280)
        tree_lay = QVBoxLayout(self.tree_panel)
        tree_lay.setContentsMargins(10, 10, 10, 10)
        tree_lay.setSpacing(6)
        tree_head = QHBoxLayout()
        tree_head.setContentsMargins(0, 0, 0, 0)
        tree_head.setSpacing(6)
        self.tree_title = QLabel("目录")
        self.tree_title.setObjectName("Kicker")
        self.tree_toggle = QPushButton("收起")
        self.tree_toggle.setObjectName("LinkButton")
        self.tree_toggle.setCursor(Qt.PointingHandCursor)
        self.tree_toggle.clicked.connect(self._toggle_tree)
        tree_head.addWidget(self.tree_title)
        tree_head.addStretch(1)
        tree_head.addWidget(self.tree_toggle)
        tree_lay.addLayout(tree_head)
        self.tree = DirectoryTree(self.c)
        tree_lay.addWidget(self.tree, 1)
        tree_lay.addStretch(1)
        self._tree_layout = tree_lay
        tree_lay.setStretch(1, 1)
        tree_lay.setStretch(2, 0)
        body_lay.addWidget(self.tree_panel)

        reader = QWidget()
        reader_lay = QHBoxLayout(reader)
        reader_lay.setContentsMargins(24, 18, 0, 0)
        reader_lay.addStretch(1)
        self.text = QTextBrowser()
        self.text.setObjectName("DocText")
        self.text.setFrameShape(QFrame.NoFrame)
        self.text.setOpenExternalLinks(False)
        self.text.setMaximumWidth(920)
        self.text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.text.document().setDocumentMargin(0)
        self.text.setStyleSheet("QTextBrowser#DocText { padding: 0 24px; }")
        reader_lay.addWidget(self.text, 12)
        reader_lay.addStretch(1)
        body_lay.addWidget(reader, 1)
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
        self.tree.rebuild()
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

    def refresh_tree(self) -> None:
        self.tree.rebuild()

    def _toggle_tree(self) -> None:
        self._tree_collapsed = not self._tree_collapsed
        if self._tree_collapsed:
            self.tree_panel.setFixedWidth(44)
            self.tree_title.hide()
            self.tree.hide()
            self._tree_layout.setStretch(1, 0)
            self._tree_layout.setStretch(2, 1)
            self.tree_toggle.setText("目录")
        else:
            self.tree_panel.setFixedWidth(280)
            self.tree_title.show()
            self.tree.show()
            self._tree_layout.setStretch(1, 1)
            self._tree_layout.setStretch(2, 0)
            self.tree_toggle.setText("收起")

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._render()
