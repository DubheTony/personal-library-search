"""项目内部模型与稳定的 GUI 返回类型。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Token:
    word: str
    start: int
    end: int


@dataclass
class Document:
    doc_id: int
    relative_path: str
    title: str
    body: str
    title_tokens: list[Token] = field(default_factory=list)
    body_tokens: list[Token] = field(default_factory=list)
    body_analysis_tokens: list[Token] = field(default_factory=list)


@dataclass(frozen=True)
class LoadIssue:
    relative_path: str
    message: str


@dataclass(frozen=True)
class LoadSummary:
    root_path: str
    document_count: int
    issues: list[LoadIssue]


@dataclass(frozen=True)
class TreeItem:
    name: str
    relative_path: str
    kind: str
    doc_id: int | None
    children: list[TreeItem]


@dataclass(frozen=True)
class DocumentView:
    doc_id: int
    title: str
    relative_path: str
    body: str


@dataclass(frozen=True)
class Span:
    start: int
    end: int


@dataclass(frozen=True)
class SearchHit:
    word: str
    field: str
    span: Span


@dataclass(frozen=True)
class SearchResult:
    doc_id: int
    title: str
    relative_path: str
    match_count: int
    hits: list[SearchHit]
    snippet: str
    snippet_spans: list[Span]


@dataclass(frozen=True)
class WordCount:
    word: str
    count: int


@dataclass(frozen=True)
class FrequencyReport:
    top_k: list[WordCount]
    quick_sorted: list[WordCount]
    merge_sorted: list[WordCount]
    quick_ms: float
    merge_ms: float


@dataclass(frozen=True)
class ScoreParts:
    directory: float
    content: float
    keywords: float
    total: float


@dataclass(frozen=True)
class PathNode:
    doc_id: int
    title: str


@dataclass(frozen=True)
class PathSegment:
    source_id: int
    target_id: int
    basis: str
    cost: float


@dataclass(frozen=True)
class AssocPath:
    nodes: list[PathNode]
    segments: list[PathSegment]
    total_cost: float
    hops: int


@dataclass(frozen=True)
class RecommendationItem:
    doc_id: int
    title: str
    relative_path: str
    scores: ScoreParts
    shared_keywords: list[str]
    reason: str
    paths: dict[str, AssocPath] = field(default_factory=dict)
    cluster_id: int | None = None
    same_cluster: bool = False


@dataclass(frozen=True)
class GraphNode:
    doc_id: int
    title: str
    hop: int
    cluster_id: int | None = None


@dataclass(frozen=True)
class GraphEdge:
    low_id: int
    high_id: int
    has_structure: bool
    low_to_high: bool
    high_to_low: bool


@dataclass(frozen=True)
class GraphView:
    nodes: list[GraphNode]
    edges: list[GraphEdge]


@dataclass(frozen=True)
class RecommendationView:
    items: list[RecommendationItem]
    graph: GraphView
    cluster_sizes: dict[int, int] = field(default_factory=dict)
    center_cluster_id: int | None = None
