"""邻接表有向图；提供当前中心文档的两跳 BFS 展示子图。"""

from __future__ import annotations

from dataclasses import dataclass

from .algorithms.sorting import quick_sort
from .models import Document, GraphEdge, GraphNode, GraphView
from .structures.queue import Queue


@dataclass
class GraphConnection:
    target_id: int
    has_structure: bool = False
    recommended: bool = False


class RelationGraph:
    def __init__(self) -> None:
        self._documents: list[Document] = []
        self._scores: list[list[float]] = []
        self._adjacency: list[list[GraphConnection]] = []

    def build(
        self,
        documents: list[Document],
        scores: list[list[float]],
        top_three: list[list[int]],
    ) -> None:
        self._documents = documents
        self._scores = scores
        size = len(documents)
        self._adjacency = [[] for _ in range(size)]

        for left_id in range(size):
            left_parent = documents[left_id].relative_path.rpartition("/")[0]
            for right_id in range(left_id + 1, size):
                right_parent = documents[right_id].relative_path.rpartition("/")[0]
                if left_parent == right_parent:
                    self._add_connection(left_id, right_id, structure=True)
                    self._add_connection(right_id, left_id, structure=True)

        for source_id, targets in enumerate(top_three):
            for target_id in targets:
                if source_id != target_id:
                    self._add_connection(source_id, target_id, recommended=True)

    def extract(self, center_id: int) -> GraphView:
        size = len(self._documents)
        if center_id < 0 or center_id >= size:
            raise ValueError(f"无效图中心文档编号：{center_id}")

        hops = [-1] * size
        excluded = [False] * size
        layers: list[list[int]] = [[], [], []]
        hops[center_id] = 0
        layers[0].append(center_id)
        queue: Queue[int] = Queue()
        queue.enqueue(center_id)

        while not queue.is_empty():
            source_id = queue.dequeue()
            source_hop = hops[source_id]
            if source_hop >= 2:
                continue
            connections = quick_sort(
                self._adjacency[source_id],
                lambda left, right: self._neighbor_before(source_id, left, right),
            )
            next_hop = source_hop + 1
            for connection in connections:
                target_id = connection.target_id
                if hops[target_id] >= 0 or excluded[target_id]:
                    continue
                if len(layers[next_hop]) >= 10:
                    excluded[target_id] = True
                    continue
                hops[target_id] = next_hop
                layers[next_hop].append(target_id)
                queue.enqueue(target_id)

        visible = [False] * size
        ordered_ids = layers[0] + layers[1] + layers[2]
        for doc_id in ordered_ids:
            visible[doc_id] = True

        nodes = [
            GraphNode(doc_id, self._documents[doc_id].title, hops[doc_id])
            for doc_id in ordered_ids
        ]
        edges: list[GraphEdge] = []
        # Return the induced graph on visible nodes, not only BFS discovery edges.
        for low_id in range(size):
            if not visible[low_id]:
                continue
            for high_id in range(low_id + 1, size):
                if not visible[high_id]:
                    continue
                low_to_high = self._find_connection(low_id, high_id)
                high_to_low = self._find_connection(high_id, low_id)
                if low_to_high is None and high_to_low is None:
                    continue
                edges.append(
                    GraphEdge(
                        low_id=low_id,
                        high_id=high_id,
                        has_structure=(
                            (low_to_high is not None and low_to_high.has_structure)
                            or (high_to_low is not None and high_to_low.has_structure)
                        ),
                        low_to_high=(
                            low_to_high is not None and low_to_high.recommended
                        ),
                        high_to_low=(
                            high_to_low is not None and high_to_low.recommended
                        ),
                    )
                )
        return GraphView(nodes=nodes, edges=edges)

    def _add_connection(
        self,
        source_id: int,
        target_id: int,
        *,
        structure: bool = False,
        recommended: bool = False,
    ) -> None:
        current = self._find_connection(source_id, target_id)
        if current is None:
            self._adjacency[source_id].append(
                GraphConnection(target_id, structure, recommended)
            )
        else:
            current.has_structure = current.has_structure or structure
            current.recommended = current.recommended or recommended

    def _find_connection(
        self, source_id: int, target_id: int
    ) -> GraphConnection | None:
        for connection in self._adjacency[source_id]:
            if connection.target_id == target_id:
                return connection
        return None

    def _neighbor_before(
        self,
        source_id: int,
        left: GraphConnection,
        right: GraphConnection,
    ) -> bool:
        left_score = self._scores[source_id][left.target_id]
        right_score = self._scores[source_id][right.target_id]
        if left_score != right_score:
            return left_score > right_score
        return left.target_id < right.target_id
