"""主窗口：目录、词频、推荐三个入口，检索和文档使用独立视图。"""
from __future__ import annotations

import html
from types import SimpleNamespace
from typing import Optional

from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QColor, QKeyEvent, QKeySequence, QPalette, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..models import (
    DocumentView as DocumentModel,
    FrequencyReport,
    LoadSummary,
    RecommendationView,
    SearchResult,
    TreeItem,
)
from ..theme import build_qss, THEMES
from .views import (
    DirectoryView,
    DocumentView,
    FrequencyView,
    RecommendView,
    SearchView,
)
from .widgets import (
    LogoMark,
    RailButton,
    ThemeSwitcher,
    Toast,
    ZoomControl,
)
from .zoom_view import ZoomView

PRESET_CN = {"balanced": "均衡", "structure": "结构优先", "content": "内容优先"}
PRESET_WEIGHTS = {
    "balanced": (0.3, 0.5, 0.2),
    "structure": (0.6, 0.3, 0.1),
    "content": (0.1, 0.7, 0.2),
}
RAIL_ITEMS = [
    ("folder", "目录"),
    ("frequency", "词频"),
    ("recommend", "推荐"),
]


class MainWindow(QMainWindow):
    def __init__(self, service) -> None:
        super().__init__()
        self.service = service
        self.summary: LoadSummary = service.load()
        self.tree_root: TreeItem = service.get_tree()
        self.all_docs: list[DocumentModel] = service.list_folder("")
        self.docs_by_id = {doc.doc_id: doc for doc in self.all_docs}
        self.paths = {doc.doc_id: doc.relative_path for doc in self.all_docs}
        self.preset_weights = PRESET_WEIGHTS

        self.theme_key = "drafting"
        self.theme = THEMES[self.theme_key]
        self.zoom = 1.25
        self._zoom_initialized = False
        self.mode = "folder"
        self.preset = "balanced"
        self.folder = ""
        self.doc_id: Optional[int] = (
            5 if 5 in self.docs_by_id else (self.all_docs[0].doc_id if self.all_docs else None)
        )
        self.center_id = self.doc_id
        self.query = ""
        self.search_mode = "word"
        self.results: list[SearchResult] = []
        self.selected_result_id: Optional[int] = None
        self.highlight_terms: Optional[list[str]] = None
        self.doc_open = False
        self.expanded = self._all_folder_paths()
        self._rec_view: Optional[RecommendationView] = None
        self._freq_report: Optional[FrequencyReport] = None
        self._freq_key = None
        self._issue_popup: Optional[QFrame] = None
        self._search_return_view = None
        self._doc_return_view = None

        self.setWindowTitle("ATLAS · 个人资料库")
        self.setMinimumSize(1180, 680)
        screen = QApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            self.resize(
                min(1560, max(1180, avail.width() - 20)),
                min(960, max(680, avail.height() - 40)),
            )
        else:
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

        self.workspace = QStackedWidget()
        self.workspace.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.directory_view = DirectoryView(self)
        self.search_view = SearchView(self)
        self.frequency_view = FrequencyView(self)
        self.recommend_view = RecommendView(self)
        self.document_view = DocumentView(self)
        for view in (
            self.directory_view,
            self.search_view,
            self.frequency_view,
            self.recommend_view,
            self.document_view,
        ):
            self.workspace.addWidget(view)
        self.workspace.setCurrentWidget(self.directory_view)
        body_lay.addWidget(self.workspace, 1)
        lay.addWidget(body, 1)

        lay.addWidget(self._build_status())

        self.toast = Toast(root)
        self.toast.set_theme(self.theme)

        # 兼容旧测试/调试脚本的访问点。
        self.canvas = SimpleNamespace(
            graph=self.recommend_view.graph,
            doc_panel=self.document_view,
        )

        self.view = ZoomView(self)
        self.view.set_widget(root)
        self.setCentralWidget(self.view)
        self.view.zoom_changed.connect(self._on_zoom_changed)
        self.view.set_zoom(self.zoom)
        self._zoom_initialized = True

        self.search_input.returnPressed.connect(self.perform_search)
        self.search_btn.clicked.connect(self.perform_search)
        self._build_shortcuts()

    def _build_topbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(58)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 0, 20, 0)
        lay.setSpacing(14)

        self.logo = LogoMark()
        lay.addWidget(self.logo)

        brand = QWidget()
        brand_lay = QHBoxLayout(brand)
        brand_lay.setContentsMargins(0, 0, 0, 0)
        brand_lay.setSpacing(8)
        en = QLabel("ATLAS")
        en.setObjectName("BrandTitle")
        cn = QLabel("个人资料库")
        cn.setObjectName("BrandCn")
        self.demo_badge = QLabel("演示数据")
        self.demo_badge.setObjectName("DemoBadge")
        self.demo_badge.setToolTip("当前没有样例资料库，显示的是内置演示数据")
        self.demo_badge.setFixedHeight(22)
        self.demo_badge.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.demo_badge.setVisible(getattr(self.service, "is_demo", False))
        brand_lay.addWidget(en)
        brand_lay.addWidget(cn)
        brand_lay.addWidget(self.demo_badge, 0, Qt.AlignVCenter)
        lay.addWidget(brand)

        search = QFrame()
        search.setObjectName("TopSearch")
        search.setFixedHeight(34)
        search.setMinimumWidth(280)
        search.setMaximumWidth(620)
        search.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        search_lay = QHBoxLayout(search)
        search_lay.setContentsMargins(0, 0, 0, 0)
        search_lay.setSpacing(0)
        prefix = QLabel("检索")
        prefix.setObjectName("SearchPrefix")
        prefix.setFixedHeight(32)
        self.search_input = QLineEdit()
        self.search_input.setObjectName("SearchInput")
        self.search_input.setPlaceholderText("输入关键词，空格分隔")
        self.search_input.setToolTip("例如：检索 索引")
        self.search_btn = QPushButton("查询")
        self.search_btn.setObjectName("SearchButton")
        self.search_btn.setFixedSize(58, 32)
        self.search_btn.setCursor(Qt.PointingHandCursor)
        search_lay.addWidget(prefix)
        search_lay.addWidget(self.search_input, 1)
        search_lay.addWidget(self.search_btn)
        lay.addWidget(search, 1)
        lay.addStretch(0)

        self.zoom_control = ZoomControl(round(self.zoom * 100))
        self.zoom_control.zoom_out.connect(self.zoom_out)
        self.zoom_control.zoom_in.connect(self.zoom_in)
        self.zoom_control.reset.connect(self.reset_zoom)
        lay.addWidget(self.zoom_control)

        self.theme_switcher = ThemeSwitcher(self.theme_key)
        self.theme_switcher.theme_selected.connect(self._apply_theme)
        lay.addWidget(self.theme_switcher)
        return bar

    def _build_rail(self) -> QFrame:
        rail = QFrame()
        rail.setObjectName("Rail")
        rail.setFixedWidth(64)
        rail_lay = QVBoxLayout(rail)
        rail_lay.setContentsMargins(0, 8, 0, 0)
        rail_lay.setSpacing(0)
        self.rail_group = QButtonGroup(self)
        self.rail_group.setExclusive(True)
        self.rail_buttons: dict[str, RailButton] = {}
        for mode, text in RAIL_ITEMS:
            btn = RailButton(mode, text)
            btn.set_theme(self.theme)
            btn.clicked.connect(lambda checked=False, m=mode: self.set_mode(m))
            rail_lay.addWidget(btn)
            self.rail_group.addButton(btn)
            self.rail_buttons[mode] = btn
        rail_lay.addStretch(1)
        return rail

    def _build_status(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("StatusBar")
        bar.setFixedHeight(28)
        self.status_bar = bar
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 0, 20, 0)
        lay.setSpacing(12)
        self.status_left = QLabel("")
        self.status_left.setObjectName("StatusText")
        self.status_left.setTextFormat(Qt.PlainText)
        self.issue_btn = QPushButton("")
        self.issue_btn.setObjectName("IssueButton")
        self.issue_btn.setCursor(Qt.PointingHandCursor)
        self.issue_btn.setFixedHeight(20)
        self.issue_btn.clicked.connect(self.show_issues)
        lay.addWidget(self.status_left, 1)
        lay.addWidget(self.issue_btn)
        return bar

    # ============================================================
    # 主题与缩放
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
        self.view.set_theme(self.theme)
        self.toast.set_theme(self.theme)
        for view in (
            self.directory_view,
            self.search_view,
            self.frequency_view,
            self.recommend_view,
            self.document_view,
        ):
            view.set_theme(self.theme)
        pal = self.search_input.palette()
        pal.setColor(QPalette.PlaceholderText, QColor(self.theme.faint))
        self.search_input.setPalette(pal)
        if self._issue_popup is not None:
            self._issue_popup.close()
            self._issue_popup.deleteLater()
            self._issue_popup = None
        self._refresh_all()
        if not first:
            self.toast.show_message(f"皮肤 · {self.theme.cn}")

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

    # ============================================================
    # 数据刷新
    # ============================================================
    def _refresh_all(self) -> None:
        if self.center_id is None and self.doc_id is not None:
            self.center_id = self.doc_id
        self._refresh_recommend()
        self.directory_view.refresh()
        self.frequency_view.refresh()
        self._update_status()

    def _refresh_recommend(self) -> None:
        if self.center_id is None or self.center_id not in self.docs_by_id:
            self._rec_view = None
            self.recommend_view.set_data(None, "", self.preset)
            return
        self._rec_view = self.service.recommend(self.center_id, self.preset)
        self.recommend_view.set_data(
            self._rec_view,
            self.docs_by_id[self.center_id].title,
            self.preset,
        )

    def _update_status(self) -> None:
        issues = len(self.summary.issues)
        self.status_left.setText("")
        self.issue_btn.setVisible(issues > 0)
        if issues > 0:
            self.issue_btn.setText(f"读取问题 {issues}")
        self.status_bar.setVisible(issues > 0)

    # ============================================================
    # 导航
    # ============================================================
    def _check_rail(self, mode: str) -> None:
        btn = self.rail_buttons.get(mode)
        if btn is not None and not btn.isChecked():
            btn.setChecked(True)

    def _uncheck_rail(self) -> None:
        self.rail_group.setExclusive(False)
        for btn in self.rail_buttons.values():
            btn.setChecked(False)
        self.rail_group.setExclusive(True)

    def _check_rail_for_view(self, view: QWidget) -> None:
        if view is self.directory_view:
            self._check_rail("folder")
        elif view is self.frequency_view:
            self._check_rail("frequency")
        elif view is self.recommend_view:
            self._check_rail("recommend")
        else:
            self._uncheck_rail()

    def set_mode(self, mode: str) -> None:
        if mode == "folder":
            self.directory_view.refresh()
            self.workspace.setCurrentWidget(self.directory_view)
        elif mode == "frequency":
            self.frequency_view.refresh()
            self.workspace.setCurrentWidget(self.frequency_view)
        elif mode == "recommend":
            self._refresh_recommend()
            self.workspace.setCurrentWidget(self.recommend_view)
        else:
            return
        self.mode = mode
        self.doc_open = False
        self._check_rail(mode)
        self._update_status()

    def perform_search(self) -> None:
        current = self.workspace.currentWidget()
        if current is not self.search_view:
            self._search_return_view = current
        elif self._search_return_view is None:
            self._search_return_view = self.directory_view
        self.query = self.search_input.text().strip()
        self.results = (
            self.service.search(self.query, mode=self.search_mode)
            if self.query
            else []
        )
        self.selected_result_id = None
        self.highlight_terms = None
        self.doc_open = False
        self.search_view.show_results(self.query, self.results)
        self.workspace.setCurrentWidget(self.search_view)
        self._uncheck_rail()
        self._update_status()

    def set_search_mode(self, mode: str) -> None:
        if mode not in ("word", "phrase"):
            return
        self.search_mode = mode
        self.search_input.setPlaceholderText(
            "输入完整短语" if mode == "phrase" else "输入关键词，空格分隔"
        )
        if self.search_input.text().strip():
            self.perform_search()
        else:
            self.search_view.show_results("", [])

    def close_search(self) -> None:
        target = self._search_return_view or self.directory_view
        self.workspace.setCurrentWidget(target)
        self._check_rail_for_view(target)
        self._update_status()

    def open_doc(
        self,
        doc_id: int,
        highlight_terms: Optional[list[str]] = None,
        selected: Optional[int] = None,
    ) -> None:
        if doc_id not in self.docs_by_id:
            return
        current = self.workspace.currentWidget()
        if current is not self.document_view:
            self._doc_return_view = current
        self.doc_id = doc_id
        self.doc_open = True
        if highlight_terms is not None:
            self.highlight_terms = highlight_terms
            self.selected_result_id = selected
        else:
            self.highlight_terms = None
            self.selected_result_id = None
        doc = self.service.get_document(doc_id)
        hits = None
        if self.highlight_terms:
            hit_doc = next((r for r in self.results if r.doc_id == doc_id), None)
            hits = hit_doc.hits if hit_doc is not None else None
        is_center = doc_id == self.center_id
        self.document_view.show_document(doc, self.highlight_terms, hits, is_center)
        self.workspace.setCurrentWidget(self.document_view)
        self._uncheck_rail()
        self._update_status()

    def go_back_from_document(self) -> None:
        target = self._doc_return_view or self.directory_view
        self.workspace.setCurrentWidget(target)
        self.doc_open = False
        if target is self.directory_view:
            self.directory_view.refresh_tree()
        self._check_rail_for_view(target)
        self._update_status()

    def set_start_from_document(self) -> None:
        if self.doc_id is None or self.doc_id not in self.docs_by_id:
            return
        self.center_id = self.doc_id
        self._refresh_recommend()
        now_center = self.doc_id == self.center_id
        self.document_view.show_document(
            self.service.get_document(self.doc_id),
            self.highlight_terms,
            None,
            now_center,
        )
        self.mode = "recommend"
        self.doc_open = False
        self._check_rail("recommend")
        self.workspace.setCurrentWidget(self.recommend_view)
        self._update_status()
        title = self.docs_by_id[self.doc_id].title
        self.toast.show_message(f"推荐起点已改为《{title}》，列表和关系图已重算")

    def open_freq_for_doc(self) -> None:
        if self.doc_id is None:
            return
        self.freq_scope = "doc"
        self.freq_algo = "top"
        self._freq_report = None
        self._freq_key = None
        self.mode = "frequency"
        self.doc_open = False
        self._check_rail("frequency")
        self.frequency_view.refresh()
        self.workspace.setCurrentWidget(self.frequency_view)
        self._update_status()

    def set_preset(self, preset: str) -> None:
        if preset not in PRESET_CN:
            return
        self.preset = preset
        self._refresh_recommend()
        self._update_status()

    def set_current_folder(self, path: str) -> None:
        self.folder = path
        self.directory_view.refresh_tree()
        self.document_view.refresh_tree()

    def select_folder(self, path: str) -> None:
        self.set_current_folder(path)

    def toggle_folder(self, path: str) -> None:
        if path in self.expanded:
            self.expanded.remove(path)
        else:
            self.expanded.add(path)
        self.directory_view.refresh_tree()
        self.document_view.refresh_tree()

    def _folder_count(self, node: TreeItem) -> int:
        if node.kind == "document":
            return 1
        return sum(self._folder_count(child) for child in node.children)

    def _all_folder_paths(self) -> set[str]:
        paths: set[str] = set()

        def walk(node: TreeItem) -> None:
            for child in node.children:
                if child.kind == "folder":
                    paths.add(child.relative_path)
                    walk(child)

        walk(self.tree_root)
        return paths

    # ============================================================
    # 词频
    # ============================================================
    freq_scope = "all"
    freq_algo = "top"

    def _freq_key_value(self):
        if self.freq_scope == "doc":
            return ("doc", self.doc_id)
        if self.freq_scope == "all":
            return ("all", "")
        return ("folder", self.folder)

    def _freq_scope_name(self) -> str:
        if self.freq_scope == "doc":
            if self.doc_id in self.docs_by_id:
                return f"《{self.docs_by_id[self.doc_id].title}》"
            return "当前文档"
        if self.freq_scope == "folder":
            return self.folder or "全库"
        return "全库"

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

    def set_freq_scope(self, scope: str) -> None:
        self.freq_scope = scope
        self._freq_report = None
        self._freq_key = None
        self.frequency_view.refresh()
        self._update_status()

    def set_freq_algo(self, algo: str) -> None:
        self.freq_algo = algo
        self.frequency_view.refresh()

    # ============================================================
    # 失败文件
    # ============================================================
    def show_issues(self) -> None:
        if not self.summary.issues:
            return
        if self._issue_popup is not None and self._issue_popup.isVisible():
            self._issue_popup.close()
            return
        if self._issue_popup is not None:
            self._issue_popup.deleteLater()
        popup = QFrame(self.root)
        popup.setObjectName("IssuePopup")
        popup.setFixedWidth(380)
        lay = QVBoxLayout(popup)
        lay.setContentsMargins(15, 13, 15, 14)
        lay.setSpacing(8)
        top = QHBoxLayout()
        title = QLabel("读取问题")
        title.setObjectName("IssueTitle")
        close = QPushButton("×")
        close.setObjectName("CloseButton")
        close.setFixedSize(22, 22)
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(popup.close)
        top.addWidget(title)
        top.addStretch(1)
        top.addWidget(close)
        lay.addLayout(top)
        for issue in self.summary.issues:
            file_label = QLabel(issue.relative_path)
            file_label.setObjectName("IssueFile")
            file_label.setWordWrap(True)
            reason = QLabel(issue.message)
            reason.setObjectName("IssueText")
            reason.setWordWrap(True)
            lay.addWidget(file_label)
            lay.addWidget(reason)
        popup.adjustSize()
        pos = self.issue_btn.mapTo(self.root, QPoint(0, 0))
        popup.move(
            max(8, pos.x() + self.issue_btn.width() - popup.width()),
            pos.y() - popup.height() - 8,
        )
        popup.show()
        popup.raise_()
        self._issue_popup = popup

    # ============================================================
    # 键盘
    # ============================================================
    def _build_shortcuts(self) -> None:
        self._shortcuts: list[QShortcut] = []
        bindings = [
            ("Ctrl+=", self.zoom_in),
            ("Ctrl++", self.zoom_in),
            ("Ctrl+-", self.zoom_out),
            ("Ctrl+0", self.reset_zoom),
            ("Esc", self._escape_action),
            ("Ctrl+1", lambda: self.set_mode("folder")),
            ("Ctrl+2", lambda: self.set_mode("frequency")),
            ("Ctrl+3", lambda: self.set_mode("recommend")),
        ]
        for seq, slot in bindings:
            shortcut = QShortcut(QKeySequence(seq), self)
            shortcut.setContext(Qt.ApplicationShortcut)
            shortcut.activated.connect(slot)
            self._shortcuts.append(shortcut)

    def _escape_action(self) -> None:
        if self._issue_popup is not None and self._issue_popup.isVisible():
            self._issue_popup.close()
        elif self.workspace.currentWidget() is self.document_view:
            self.go_back_from_document()
        elif self.workspace.currentWidget() is self.search_view:
            self.close_search()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Slash:
            focus = QApplication.focusWidget()
            if not isinstance(focus, QLineEdit):
                self.search_input.setFocus()
                return True
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
            self._escape_action()
            event.accept()
            return
        super().keyPressEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "toast"):
            self.toast._position()
