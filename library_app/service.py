"""面向 GUI 的服务门面和启动期装配。"""

from __future__ import annotations

from pathlib import Path

from .frequency import FrequencyAnalyzer
from .models import (
    DocumentView,
    FrequencyReport,
    GraphView,
    LoadSummary,
    RecommendationView,
    SearchResult,
    TreeItem,
)
from .recommendation import RecommendationEngine
from .repository import LibraryRepository
from .search import SearchEngine
from .tokenizer import Tokenizer


class LibraryLoadError(Exception):
    """样例库或启动所需资源无法加载。"""


class LibraryService:
    def __init__(self, sample_root: Path) -> None:
        self.sample_root = Path(sample_root)
        self._loaded = False
        self._summary: LoadSummary | None = None
        self._repository: LibraryRepository | None = None
        self._tokenizer: Tokenizer | None = None
        self._search: SearchEngine | None = None
        self._frequency = FrequencyAnalyzer()
        self._recommendation: RecommendationEngine | None = None

    def load(self) -> LoadSummary:
        self._loaded = False
        stopwords_path = Path(__file__).resolve().parent.parent / "stopwords.txt"
        try:
            tokenizer = Tokenizer(stopwords_path)
            repository = LibraryRepository()
            summary = repository.load(self.sample_root, tokenizer)
        except (OSError, UnicodeError) as exc:
            raise LibraryLoadError(
                f"无法加载样例资料库或停用词文件：{exc}"
            ) from exc

        if summary.document_count == 0:
            issue_text = "；".join(
                f"{issue.relative_path}: {issue.message}" for issue in summary.issues
            )
            detail = f"；读取错误：{issue_text}" if issue_text else ""
            raise LibraryLoadError(
                f"样例资料库中没有可读取的 .md、.txt 或 .docx 文档："
                f"{summary.root_path}{detail}"
            )

        search = SearchEngine()
        search.build(repository.documents)
        recommendation = RecommendationEngine()
        recommendation.build(repository.documents)

        self._tokenizer = tokenizer
        self._repository = repository
        self._search = search
        self._recommendation = recommendation
        self._summary = summary
        self._loaded = True
        return summary

    def get_tree(self) -> TreeItem:
        self._ensure_loaded()
        return self._repository.get_tree()  # type: ignore[union-attr]

    def list_folder(self, folder_path: str) -> list[DocumentView]:
        self._ensure_loaded()
        return self._repository.list_folder(folder_path)  # type: ignore[union-attr]

    def get_document(self, doc_id: int) -> DocumentView:
        self._ensure_loaded()
        return self._repository.get_document(doc_id)  # type: ignore[union-attr]

    def search(self, query: str) -> list[SearchResult]:
        self._ensure_loaded()
        return self._search.search(  # type: ignore[union-attr]
            query, self._tokenizer  # type: ignore[arg-type]
        )

    def analyze_frequency(
        self,
        *,
        doc_id: int | None = None,
        folder_path: str | None = None,
        k: int = 10,
    ) -> FrequencyReport:
        self._ensure_loaded()
        if (doc_id is None) == (folder_path is None):
            raise ValueError("doc_id 和 folder_path 必须且只能提供一个")
        if k <= 0:
            raise ValueError("k 必须为正整数")

        if doc_id is not None:
            if doc_id < 0 or doc_id >= len(self._repository.documents):  # type: ignore[union-attr]
                raise ValueError(f"无效文档编号：{doc_id}")
            doc_ids = [doc_id]
        else:
            views = self._repository.list_folder(folder_path or "")  # type: ignore[union-attr]
            doc_ids = [view.doc_id for view in views]
        return self._frequency.analyze(
            self._repository.documents, doc_ids, k  # type: ignore[union-attr]
        )

    def recommend(
        self, doc_id: int, preset: str = "balanced", limit: int = 10
    ) -> RecommendationView:
        self._ensure_loaded()
        if limit <= 0:
            raise ValueError("limit 必须为正整数")
        return self._recommendation.recommend(  # type: ignore[union-attr]
            doc_id, preset, limit
        )

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            raise RuntimeError("LibraryService.load() 尚未成功完成")
