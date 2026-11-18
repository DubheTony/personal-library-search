"""MockLibraryService：给 GUI 联调用的 LibraryService 替身。

正式实现由组内按《技术设计与接口约定》完成。GUI 只调用与本类相同
的公开方法，因此替换时不需要改界面代码。这里刻意不做索引、堆、排序
等数据结构，只用最简单的 Python 容器保持接口可用。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .mock_data import MOCK_DOCS, MOCK_ISSUES
from .models import (
    Document,
    DocumentView,
    FrequencyReport,
    GraphEdge,
    GraphNode,
    GraphView,
    LoadIssue,
    LoadSummary,
    RecommendationItem,
    RecommendationView,
    ScoreParts,
    SearchHit,
    SearchResult,
    Span,
    TreeItem,
    WordCount,
)

PRESET_WEIGHTS = {
    "balanced": (0.3, 0.5, 0.2),
    "structure": (0.6, 0.3, 0.1),
    "content": (0.1, 0.7, 0.2),
}


@dataclass(frozen=True)
class GraphViewEx(GraphView):
    """在契约字段之外附带截去数量，仅用于界面提示。

    真实后端若不返回该字段，界面用 getattr(view, "truncated", 0) 兜底。
    """

    truncated: int = 0


def folder_of(path: str) -> str:
    i = path.rfind("/")
    return "" if i < 0 else path[:i]


def top_folder(path: str) -> str:
    return path.split("/", 1)[0]


def _occurrences(text: str, term: str) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    if not term:
        return out
    start = 0
    while True:
        i = text.find(term, start)
        if i < 0:
            break
        out.append((i, i + len(term)))
        start = i + len(term)
    return out


class MockLibraryService:
    is_demo = True

    def __init__(self, sample_root: Path) -> None:
        self.sample_root = Path(sample_root)
        self._docs: dict[int, Document] = {}
        self._loaded = False
        self._summary: Optional[LoadSummary] = None

    # ---------- 加载 ----------
    def load(self) -> LoadSummary:
        self._docs = {
            row["id"]: Document(
                doc_id=row["id"],
                relative_path=row["path"],
                title=row["title"],
                body=row["body"],
            )
            for row in MOCK_DOCS
        }
        issues = [LoadIssue(relative_path=x["path"], message=x["message"]) for x in MOCK_ISSUES]
        self._summary = LoadSummary(
            root_path=str(self.sample_root.resolve()),
            document_count=len(self._docs),
            issues=issues,
        )
        self._loaded = True
        return self._summary

    def get_tree(self) -> TreeItem:
        self._ensure_loaded()
        root = TreeItem(name="样例资料库", relative_path="", kind="folder",
                        doc_id=None, children=[])
        folders: dict[str, TreeItem] = {"": root}

        def ensure_folder(path: str) -> TreeItem:
            if path in folders:
                return folders[path]
            parent = ensure_folder(folder_of(path))
            node = TreeItem(name=path.rsplit("/", 1)[-1], relative_path=path, kind="folder",
                            doc_id=None, children=[])
            parent.children.append(node)
            folders[path] = node
            return node

        for doc in self._sorted_docs():
            parent = ensure_folder(folder_of(doc.relative_path))
            parent.children.append(
                TreeItem(
                    name=doc.title,
                    relative_path=doc.relative_path,
                    kind="document",
                    doc_id=doc.doc_id,
                    children=[],
                )
            )

        # 文件夹先于文件；文件按 doc_id；文件夹保持首次出现顺序。
        for node in folders.values():
            if node.kind != "folder":
                continue
            node.children.sort(key=lambda c: (0, "") if c.kind == "folder" else (1, str(c.doc_id)))
        return root

    def list_folder(self, folder_path: str) -> list[DocumentView]:
        self._ensure_loaded()
        docs = [
            d for d in self._sorted_docs()
            if folder_path == "" or d.relative_path.startswith(folder_path + "/") or folder_of(d.relative_path) == folder_path
        ]
        # 只返回后代文件，不包含目录本身；上面条件覆盖 "" 全库。
        return [self._view(d) for d in docs]

    def get_document(self, doc_id: int) -> DocumentView:
        self._ensure_loaded()
        doc = self._docs.get(doc_id)
        if doc is None:
            raise ValueError(f"无效文档编号：{doc_id}")
        return self._view(doc)

    # ---------- 检索 ----------
    def search(self, query: str) -> list[SearchResult]:
        self._ensure_loaded()
        terms = [t for t in dict.fromkeys(query.strip().split()) if t]
        if not terms:
            return []
        results: list[SearchResult] = []
        for doc in self._sorted_docs():
            if not all(t in doc.title or t in doc.body for t in terms):
                continue
            hits: list[SearchHit] = []
            for term in terms:
                for s, e in _occurrences(doc.title, term):
                    hits.append(SearchHit(word=term, field="title", span=Span(s, e)))
                for s, e in _occurrences(doc.body, term):
                    hits.append(SearchHit(word=term, field="body", span=Span(s, e)))
            body_hits = [h for h in hits if h.field == "body"]
            snippet = doc.title
            snippet_spans: list[Span] = []
            if body_hits:
                first = min(body_hits, key=lambda h: h.span.start)
                start = max(0, first.span.start - 30)
                end = min(len(doc.body), first.span.end + 30)
                prefix = "…" if start > 0 else ""
                suffix = "…" if end < len(doc.body) else ""
                snippet = prefix + doc.body[start:end] + suffix
                offset = start - len(prefix)
                for h in body_hits:
                    if start <= h.span.start and h.span.end <= end:
                        snippet_spans.append(Span(h.span.start - offset, h.span.end - offset))
            else:
                for h in hits:
                    if h.field == "title":
                        snippet_spans.append(Span(h.span.start, h.span.end))
            results.append(
                SearchResult(
                    doc_id=doc.doc_id,
                    title=doc.title,
                    relative_path=doc.relative_path,
                    match_count=len(hits),
                    hits=hits,
                    snippet=snippet,
                    snippet_spans=snippet_spans,
                )
            )
        return results

    # ---------- 词频 ----------
    def analyze_frequency(
        self,
        *,
        doc_id: Optional[int] = None,
        folder_path: Optional[str] = None,
        k: int = 10,
    ) -> FrequencyReport:
        self._ensure_loaded()
        if (doc_id is None) == (folder_path is None):
            raise ValueError("doc_id 与 folder_path 必须恰好提供一个")
        if k <= 0:
            raise ValueError("k 必须为正整数")
        if doc_id is not None:
            doc = self._docs.get(doc_id)
            if doc is None:
                raise ValueError(f"无效文档编号：{doc_id}")
            rows = [MOCK_DOCS[doc_id]]
        else:
            rows = [
                row for row in MOCK_DOCS
                if folder_path == "" or folder_of(row["path"]) == folder_path or folder_of(row["path"]).startswith(folder_path + "/")
            ]
        counts: dict[str, int] = {}
        for row in rows:
            for word, count in row["counts"].items():
                counts[word] = counts.get(word, 0) + count
        ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        words = [WordCount(word=w, count=c) for w, c in ordered]
        v = len(words)
        tokens = sum(c for _, c in ordered)
        quick_ms = round(0.12 + v * 0.0048 + tokens * 0.00012, 2) if v else 0.0
        merge_ms = round(0.14 + v * 0.0061 + tokens * 0.00014, 2) if v else 0.0
        return FrequencyReport(
            top_k=words[: min(k, v)],
            quick_sorted=words,
            merge_sorted=words,
            quick_ms=quick_ms,
            merge_ms=merge_ms,
        )

    # ---------- 推荐 ----------
    def recommend(self, doc_id: int, preset: str = "balanced", limit: int = 10) -> RecommendationView:
        self._ensure_loaded()
        if preset not in PRESET_WEIGHTS:
            raise ValueError(f"未知预设：{preset}")
        if limit <= 0:
            raise ValueError("limit 必须为正整数")
        center = self._docs.get(doc_id)
        if center is None:
            raise ValueError(f"无效文档编号：{doc_id}")
        items = self._rank(center, preset)[: min(limit, len(self._docs) - 1)]
        return RecommendationView(items=items, graph=self._build_graph(center, preset))

    # ---------- 内部 ----------
    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def _sorted_docs(self) -> list[Document]:
        return [self._docs[i] for i in sorted(self._docs)]

    @staticmethod
    def _view(doc: Document) -> DocumentView:
        return DocumentView(
            doc_id=doc.doc_id,
            title=doc.title,
            relative_path=doc.relative_path,
            body=doc.body,
        )

    def _score_pair(self, a: Document, b: Document, preset: str) -> tuple[float, float, float, float, list[str]]:
        wd, wc, wk = PRESET_WEIGHTS[preset]
        da, db = folder_of(a.relative_path), folder_of(b.relative_path)
        if da == db:
            d = 1.0
        elif top_folder(a.relative_path) == top_folder(b.relative_path):
            d = 0.6
        else:
            d = 0.1

        ca = MOCK_DOCS[a.doc_id]["counts"]
        cb = MOCK_DOCS[b.doc_id]["counts"]
        total_a, total_b = sum(ca.values()), sum(cb.values())
        overlap = sum(min(ca[w], cb[w]) for w in ca.keys() & cb.keys())
        c = 0.0 if total_a + total_b == 0 else 2.0 * overlap / (total_a + total_b)

        top_a = {w for w, _ in sorted(ca.items(), key=lambda kv: (-kv[1], kv[0]))[:10]}
        top_b = {w for w, _ in sorted(cb.items(), key=lambda kv: (-kv[1], kv[0]))[:10]}
        shared = sorted(top_a & top_b)
        k = len(shared) / 10.0
        total = wd * d + wc * c + wk * k
        return d, c, k, total, shared

    def _rank(self, center: Document, preset: str) -> list[RecommendationItem]:
        items: list[RecommendationItem] = []
        for doc in self._sorted_docs():
            if doc.doc_id == center.doc_id:
                continue
            d, c, k, total, shared = self._score_pair(center, doc, preset)
            if d == 1.0:
                base = "同一目录"
            elif d == 0.6:
                base = f"同属「{top_folder(center.relative_path)}」"
            else:
                base = "跨一级目录"
            reason = base + (
                " · 共同高频词：" + "、".join(shared[:3]) if shared else " · 无共同高频词"
            )
            items.append(
                RecommendationItem(
                    doc_id=doc.doc_id,
                    title=doc.title,
                    relative_path=doc.relative_path,
                    scores=ScoreParts(directory=d, content=c, keywords=k, total=total),
                    shared_keywords=shared,
                    reason=reason,
                )
            )
        items.sort(key=lambda x: (-x.scores.total, x.doc_id))
        return items

    def _build_graph(self, center: Document, preset: str) -> GraphViewEx:
        rec: dict[int, set[int]] = {}
        struct: dict[int, set[int]] = {}
        for doc in self._sorted_docs():
            rec[doc.doc_id] = {item.doc_id for item in self._rank(doc, preset)[:3]}
            struct[doc.doc_id] = {
                other.doc_id for other in self._sorted_docs()
                if other.doc_id != doc.doc_id and folder_of(other.relative_path) == folder_of(doc.relative_path)
            }

        def outs(doc_id: int) -> list[tuple[int, float]]:
            target = self._docs[doc_id]
            neighbours = rec[doc_id] | struct[doc_id]
            scored = [
                (nid, self._score_pair(target, self._docs[nid], preset)[3])
                for nid in neighbours
            ]
            scored.sort(key=lambda x: (-x[1], x[0]))
            return scored

        kept: dict[int, int] = {center.doc_id: 0}
        hop1: list[int] = []
        hop2: list[int] = []
        truncated = 0
        for nid, _ in outs(center.doc_id):
            if nid in kept:
                continue
            if len(hop1) >= 10:
                truncated += 1
                continue
            kept[nid] = 1
            hop1.append(nid)
        for nid in hop1:
            for nei, _ in outs(nid):
                if nei in kept:
                    continue
                if len(hop2) >= 10:
                    truncated += 1
                    continue
                kept[nei] = 2
                hop2.append(nei)

        ids = list(kept)
        edges: list[GraphEdge] = []
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = ids[i], ids[j]
                low, high = min(a, b), max(a, b)
                has_struct = b in struct[a]
                a_to_b = b in rec[a]
                b_to_a = a in rec[b]
                if has_struct or a_to_b or b_to_a:
                    edges.append(
                        GraphEdge(
                            low_id=low,
                            high_id=high,
                            has_structure=has_struct,
                            low_to_high=(low == a and a_to_b) or (low == b and b_to_a),
                            high_to_low=(high == a and a_to_b) or (high == b and b_to_a),
                        )
                    )
        nodes = [GraphNode(doc_id=i, title=self._docs[i].title, hop=kept[i]) for i in ids]
        return GraphViewEx(nodes=nodes, edges=edges, truncated=truncated)
