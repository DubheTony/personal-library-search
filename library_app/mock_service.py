"""MockLibraryService：给 GUI 联调用的 LibraryService 替身。

正式实现由组内按《技术设计与接口约定》完成。GUI 只调用与本类相同
的公开方法，因此替换时不需要改界面代码。这里刻意不做索引、堆、排序
等数据结构，只用最简单的 Python 容器保持接口可用。
"""
from __future__ import annotations

import heapq
import re
from collections import deque
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Optional

from .mock_data import MOCK_DOCS, MOCK_ISSUES
from .models import (
    AssocPath,
    Document,
    DocumentView,
    FrequencyReport,
    GraphEdge,
    GraphNode,
    GraphView,
    LoadIssue,
    LoadSummary,
    PathNode,
    PathSegment,
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


_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[一-鿿]")


def _mock_tokens(text: str) -> list[tuple[str, int, int]]:
    return [
        (match.group(0).casefold(), match.start(), match.end())
        for match in _TOKEN_RE.finditer(text)
    ]


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
    def search(self, query: str, mode: str = "word") -> list[SearchResult]:
        self._ensure_loaded()
        if mode == "phrase":
            return self._search_phrase(query)

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
            snippet, snippet_spans = self._snippet(doc, hits)
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

    def _search_phrase(self, query: str) -> list[SearchResult]:
        phrase = query.strip()
        query_tokens = [token[0] for token in _mock_tokens(phrase)]
        if not query_tokens:
            return []
        results: list[SearchResult] = []
        for doc in self._sorted_docs():
            hits = self._phrase_hits(doc.title, "title", query_tokens, phrase)
            hits.extend(self._phrase_hits(doc.body, "body", query_tokens, phrase))
            if not hits:
                continue
            snippet, snippet_spans = self._snippet(doc, hits)
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

    @staticmethod
    def _phrase_hits(
        text: str, field: str, query_tokens: list[str], phrase: str
    ) -> list[SearchHit]:
        tokens = _mock_tokens(text)
        window = len(query_tokens)
        hits: list[SearchHit] = []
        for index in range(len(tokens) - window + 1):
            if all(
                tokens[index + offset][0] == query_tokens[offset]
                for offset in range(window)
            ):
                start = tokens[index][1]
                end = tokens[index + window - 1][2]
                hits.append(SearchHit(word=phrase, field=field, span=Span(start, end)))
        return hits

    @staticmethod
    def _snippet(doc: Document, hits: list[SearchHit]) -> tuple[str, list[Span]]:
        body_hits = [hit for hit in hits if hit.field == "body"]
        snippet = doc.title
        snippet_spans: list[Span] = []
        if body_hits:
            first = min(body_hits, key=lambda hit: hit.span.start)
            start = max(0, first.span.start - 30)
            end = min(len(doc.body), first.span.end + 30)
            prefix = "…" if start > 0 else ""
            suffix = "…" if end < len(doc.body) else ""
            snippet = prefix + doc.body[start:end] + suffix
            offset = start - len(prefix)
            for hit in body_hits:
                if start <= hit.span.start and hit.span.end <= end:
                    snippet_spans.append(
                        Span(hit.span.start - offset, hit.span.end - offset)
                    )
        else:
            for hit in hits:
                if hit.field == "title":
                    snippet_spans.append(Span(hit.span.start, hit.span.end))
        return snippet, snippet_spans

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
        rec, struct = self._relations(preset)
        clusters = self._cluster_map(rec, struct)
        cluster_sizes: dict[int, int] = {}
        for cluster_id in clusters.values():
            cluster_sizes[cluster_id] = cluster_sizes.get(cluster_id, 0) + 1
        center_cluster = clusters.get(doc_id)
        items = self._rank(center, preset)[: min(limit, len(self._docs) - 1)]
        enriched = [
            replace(
                item,
                paths=self._paths(doc_id, item.doc_id, preset, rec, struct),
                cluster_id=clusters.get(item.doc_id),
                same_cluster=clusters.get(item.doc_id) == center_cluster,
            )
            for item in items
        ]
        return RecommendationView(
            items=enriched,
            graph=self._build_graph(center, preset, rec, struct, clusters),
            cluster_sizes=cluster_sizes,
            center_cluster_id=center_cluster,
        )

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

    def _relations(
        self, preset: str
    ) -> tuple[dict[int, set[int]], dict[int, set[int]]]:
        docs = self._sorted_docs()
        rec: dict[int, set[int]] = {}
        struct: dict[int, set[int]] = {}
        for doc in docs:
            rec[doc.doc_id] = {
                item.doc_id for item in self._rank(doc, preset)[:3]
            }
            struct[doc.doc_id] = {
                other.doc_id
                for other in docs
                if other.doc_id != doc.doc_id
                and folder_of(other.relative_path) == folder_of(doc.relative_path)
            }
        return rec, struct

    def _cluster_map(
        self, rec: dict[int, set[int]], struct: dict[int, set[int]]
    ) -> dict[int, int]:
        ids = sorted(self._docs)
        parent = {doc_id: doc_id for doc_id in ids}

        def find(node: int) -> int:
            while parent[node] != node:
                parent[node] = parent[parent[node]]
                node = parent[node]
            return node

        def union(left: int, right: int) -> None:
            root_left, root_right = find(left), find(right)
            if root_left != root_right:
                parent[root_right] = root_left

        for doc_id in ids:
            for other in rec.get(doc_id, set()) | struct.get(doc_id, set()):
                if other in parent:
                    union(doc_id, other)

        roots: dict[int, int] = {}
        mapping: dict[int, int] = {}
        for doc_id in ids:
            root = find(doc_id)
            if root not in roots:
                roots[root] = len(roots)
            mapping[doc_id] = roots[root]
        return mapping

    def _edge_basis_mock(
        self,
        left_id: int,
        right_id: int,
        rec: dict[int, set[int]],
        struct: dict[int, set[int]],
    ) -> str:
        structure = right_id in struct.get(left_id, set())
        recommended = (
            right_id in rec.get(left_id, set())
            or left_id in rec.get(right_id, set())
        )
        if structure and recommended:
            return "同目录 · 推荐关系"
        if structure:
            return "同目录"
        if recommended:
            return "推荐关系"
        return "关联"

    @staticmethod
    def _empty_assoc_path() -> AssocPath:
        return AssocPath(nodes=[], segments=[], total_cost=0.0, hops=0)

    def _make_mock_path(
        self,
        ids: list[int],
        bases: list[str],
        costs: list[float],
        total_cost: float,
    ) -> AssocPath:
        nodes = [PathNode(doc_id, self._docs[doc_id].title) for doc_id in ids]
        segments = [
            PathSegment(ids[index], ids[index + 1], bases[index], costs[index])
            for index in range(len(ids) - 1)
        ]
        return AssocPath(
            nodes=nodes,
            segments=segments,
            total_cost=total_cost,
            hops=len(segments),
        )

    def _paths(
        self,
        center_id: int,
        target_id: int,
        preset: str,
        rec: dict[int, set[int]],
        struct: dict[int, set[int]],
    ) -> dict[str, AssocPath]:
        return {
            "bfs": self._bfs_path_mock(center_id, target_id, rec, struct),
            "dijkstra": self._dijkstra_path_mock(
                center_id, target_id, preset, rec, struct
            ),
        }

    def _bfs_path_mock(
        self,
        center_id: int,
        target_id: int,
        rec: dict[int, set[int]],
        struct: dict[int, set[int]],
    ) -> AssocPath:
        if center_id == target_id:
            return self._empty_assoc_path()
        parents: dict[int, int | None] = {center_id: None}
        bases: dict[int, str] = {}
        queue: deque[tuple[int, int]] = deque([(center_id, 0)])
        found = False
        while queue and not found:
            node, depth = queue.popleft()
            if depth >= 2:
                continue
            neighbors = sorted(rec.get(node, set()) | struct.get(node, set()))
            for other in neighbors:
                if other in parents:
                    continue
                parents[other] = node
                bases[other] = self._edge_basis_mock(node, other, rec, struct)
                if other == target_id:
                    found = True
                    break
                queue.append((other, depth + 1))
        if target_id not in parents:
            return self._empty_assoc_path()
        ids: list[int] = []
        current: int | None = target_id
        while current is not None:
            ids.append(current)
            current = parents[current]
        ids.reverse()
        edge_bases = [bases[ids[index + 1]] for index in range(len(ids) - 1)]
        return self._make_mock_path(
            ids,
            edge_bases,
            [1.0] * len(edge_bases),
            float(len(edge_bases)),
        )

    def _dijkstra_path_mock(
        self,
        center_id: int,
        target_id: int,
        preset: str,
        rec: dict[int, set[int]],
        struct: dict[int, set[int]],
    ) -> AssocPath:
        if center_id == target_id:
            return self._empty_assoc_path()
        pairs: set[tuple[int, int]] = set()
        for doc_id in self._docs:
            for other in rec.get(doc_id, set()) | struct.get(doc_id, set()):
                if other in self._docs:
                    pairs.add((min(doc_id, other), max(doc_id, other)))
        adjacency: dict[int, list[tuple[int, float, str]]] = {
            doc_id: [] for doc_id in self._docs
        }
        for left_id, right_id in sorted(pairs):
            score = max(
                self._score_pair(
                    self._docs[left_id], self._docs[right_id], preset
                )[3],
                self._score_pair(
                    self._docs[right_id], self._docs[left_id], preset
                )[3],
            )
            cost = max(0.05, 1.0 - score)
            basis = self._edge_basis_mock(left_id, right_id, rec, struct)
            adjacency[left_id].append((right_id, cost, basis))
            adjacency[right_id].append((left_id, cost, basis))

        infinity = float("inf")
        distances = {doc_id: infinity for doc_id in self._docs}
        parents: dict[int, int | None] = {doc_id: None for doc_id in self._docs}
        edge_info: dict[int, tuple[str, float] | None] = {
            doc_id: None for doc_id in self._docs
        }
        distances[center_id] = 0.0
        heap: list[tuple[float, int]] = [(0.0, center_id)]
        while heap:
            distance, node = heapq.heappop(heap)
            if distance > distances[node]:
                continue
            if node == target_id:
                break
            for other, cost, basis in adjacency[node]:
                candidate = distance + cost
                if candidate < distances[other] - 1e-12:
                    distances[other] = candidate
                    parents[other] = node
                    edge_info[other] = (basis, cost)
                    heapq.heappush(heap, (candidate, other))
        if distances[target_id] == infinity:
            return self._empty_assoc_path()
        ids: list[int] = []
        bases: list[str] = []
        costs: list[float] = []
        current: int | None = target_id
        while current is not None and current != center_id:
            ids.append(current)
            info = edge_info[current]
            if info is None:
                return self._empty_assoc_path()
            bases.append(info[0])
            costs.append(info[1])
            current = parents[current]
        if current != center_id:
            return self._empty_assoc_path()
        ids.append(center_id)
        ids.reverse()
        bases.reverse()
        costs.reverse()
        return self._make_mock_path(ids, bases, costs, distances[target_id])

    def _build_graph(
        self,
        center: Document,
        preset: str,
        rec: dict[int, set[int]],
        struct: dict[int, set[int]],
        clusters: dict[int, int],
    ) -> GraphViewEx:
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
        nodes = [
            GraphNode(
                doc_id=i,
                title=self._docs[i].title,
                hop=kept[i],
                cluster_id=clusters.get(i),
            )
            for i in ids
        ]
        return GraphViewEx(nodes=nodes, edges=edges, truncated=truncated)
