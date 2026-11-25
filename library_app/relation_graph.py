"""邻接表有向图；提供当前中心文档的两跳 BFS 展示子图。"""

from __future__ import annotations

import heapq
from collections import deque
from dataclasses import dataclass

from .algorithms.sorting import quick_sort
from .models import (
    AssocPath,
    Document,
    GraphEdge,
    GraphNode,
    GraphView,
    PathNode,
    PathSegment,
)
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

        clusters = self.cluster_map()
        nodes = [
            GraphNode(
                doc_id,
                self._documents[doc_id].title,
                hops[doc_id],
                clusters.get(doc_id),
            )
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

    # ---------- 资料簇与关联链 ----------
    def cluster_map(self) -> dict[int, int]:
        """按无向关联边求连通分量，孤立文档单独成簇。"""
        size = len(self._documents)
        parent = list(range(size))
        rank = [0] * size

        def find(node: int) -> int:
            while parent[node] != node:
                parent[node] = parent[parent[node]]
                node = parent[node]
            return node

        def union(left: int, right: int) -> None:
            root_left, root_right = find(left), find(right)
            if root_left == root_right:
                return
            if rank[root_left] < rank[root_right]:
                root_left, root_right = root_right, root_left
            parent[root_right] = root_left
            if rank[root_left] == rank[root_right]:
                rank[root_left] += 1

        for source_id, connections in enumerate(self._adjacency):
            for connection in connections:
                union(source_id, connection.target_id)

        roots: dict[int, int] = {}
        mapping: dict[int, int] = {}
        for doc_id in range(size):
            root = find(doc_id)
            if root not in roots:
                roots[root] = len(roots)
            mapping[doc_id] = roots[root]
        return mapping

    def cluster_sizes(self) -> dict[int, int]:
        sizes: dict[int, int] = {}
        for cluster_id in self.cluster_map().values():
            sizes[cluster_id] = sizes.get(cluster_id, 0) + 1
        return sizes

    def paths(self, center_id: int, target_id: int) -> dict[str, AssocPath]:
        return {
            "bfs": self._bfs_path(center_id, target_id),
            "dijkstra": self._dijkstra_path(center_id, target_id),
        }

    @staticmethod
    def _empty_path() -> AssocPath:
        return AssocPath(nodes=[], segments=[], total_cost=0.0, hops=0)

    def _make_path(
        self,
        ids: list[int],
        bases: list[str],
        costs: list[float],
        total_cost: float,
    ) -> AssocPath:
        nodes = [
            PathNode(doc_id, self._documents[doc_id].title) for doc_id in ids
        ]
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

    def _bfs_path(self, center_id: int, target_id: int) -> AssocPath:
        size = len(self._documents)
        if not (0 <= center_id < size and 0 <= target_id < size):
            return self._empty_path()
        if center_id == target_id:
            return self._empty_path()

        parents: dict[int, int | None] = {center_id: None}
        bases: dict[int, str] = {}
        queue: deque[tuple[int, int]] = deque([(center_id, 0)])
        found = False
        while queue and not found:
            source_id, depth = queue.popleft()
            if depth >= 2:
                continue
            for connection in self._adjacency[source_id]:
                next_id = connection.target_id
                if next_id in parents:
                    continue
                parents[next_id] = source_id
                bases[next_id] = self._edge_basis(source_id, next_id)
                if next_id == target_id:
                    found = True
                    break
                queue.append((next_id, depth + 1))

        if target_id not in parents:
            return self._empty_path()
        ids: list[int] = []
        current: int | None = target_id
        while current is not None:
            ids.append(current)
            current = parents[current]
        ids.reverse()
        edge_bases = [bases[ids[index + 1]] for index in range(len(ids) - 1)]
        return self._make_path(
            ids,
            edge_bases,
            [1.0] * len(edge_bases),
            float(len(edge_bases)),
        )

    def _dijkstra_path(self, center_id: int, target_id: int) -> AssocPath:
        size = len(self._documents)
        if not (0 <= center_id < size and 0 <= target_id < size):
            return self._empty_path()
        if center_id == target_id:
            return self._empty_path()

        adjacency: list[list[tuple[int, float, str]]] = [[] for _ in range(size)]
        seen: set[tuple[int, int]] = set()
        for source_id, connections in enumerate(self._adjacency):
            for connection in connections:
                target = connection.target_id
                key = (min(source_id, target), max(source_id, target))
                if key in seen:
                    continue
                seen.add(key)
                low, high = key
                score = max(
                    self._scores[low][high] if self._scores else 0.0,
                    self._scores[high][low] if self._scores else 0.0,
                )
                cost = max(0.05, 1.0 - score)
                basis = self._edge_basis(low, high)
                adjacency[low].append((high, cost, basis))
                adjacency[high].append((low, cost, basis))

        infinity = float("inf")
        distances = [infinity] * size
        parents: list[int | None] = [None] * size
        edge_info: list[tuple[str, float] | None] = [None] * size
        distances[center_id] = 0.0
        heap: list[tuple[float, int]] = [(0.0, center_id)]
        while heap:
            distance, node = heapq.heappop(heap)
            if distance > distances[node]:
                continue
            if node == target_id:
                break
            for neighbor, cost, basis in adjacency[node]:
                candidate = distance + cost
                if candidate < distances[neighbor] - 1e-12:
                    distances[neighbor] = candidate
                    parents[neighbor] = node
                    edge_info[neighbor] = (basis, cost)
                    heapq.heappush(heap, (candidate, neighbor))

        if distances[target_id] == infinity:
            return self._empty_path()
        ids: list[int] = []
        bases: list[str] = []
        costs: list[float] = []
        current: int | None = target_id
        while current is not None and current != center_id:
            ids.append(current)
            info = edge_info[current]
            if info is None:
                return self._empty_path()
            bases.append(info[0])
            costs.append(info[1])
            current = parents[current]
        if current != center_id:
            return self._empty_path()
        ids.append(center_id)
        ids.reverse()
        bases.reverse()
        costs.reverse()
        return self._make_path(ids, bases, costs, distances[target_id])

    def _edge_basis(self, left_id: int, right_id: int) -> str:
        left_to_right = self._find_connection(left_id, right_id)
        right_to_left = self._find_connection(right_id, left_id)
        structure = (
            (left_to_right is not None and left_to_right.has_structure)
            or (right_to_left is not None and right_to_left.has_structure)
        )
        recommended = (
            (left_to_right is not None and left_to_right.recommended)
            or (right_to_left is not None and right_to_left.recommended)
        )
        if structure and recommended:
            return "同目录 · 推荐关系"
        if structure:
            return "同目录"
        if recommended:
            return "推荐关系"
        return "关联"

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
