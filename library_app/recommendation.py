"""教材范围内的三路文档关联评分与推荐。"""

from __future__ import annotations

from dataclasses import dataclass

from .algorithms.sorting import merge_sort
from .models import (
    Document,
    RecommendationItem,
    RecommendationView,
    ScoreParts,
    WordCount,
)
from .relation_graph import RelationGraph
from .structures.hash_table import HashTable
from .structures.heap import select_top_k

_PRESETS = {
    "balanced": (0.3, 0.5, 0.2),
    "structure": (0.6, 0.3, 0.1),
    "content": (0.1, 0.7, 0.2),
}


@dataclass(frozen=True)
class _Candidate:
    doc_id: int
    score: float


class RecommendationEngine:
    def __init__(self) -> None:
        self._documents: list[Document] = []
        self._word_to_id: HashTable[str, int] = HashTable()
        self._words: list[str] = []
        self._term_counts: list[list[int]] = []
        self._word_totals: list[int] = []
        self._top_word_ids: list[list[int]] = []
        self._graph = RelationGraph()

    def build(self, documents: list[Document]) -> None:
        self._documents = documents
        self._word_to_id = HashTable()
        self._words = []
        for document in documents:
            for token in document.body_tokens:
                if self._word_to_id.get(token.word, -1) == -1:
                    word_id = len(self._words)
                    self._word_to_id.put(token.word, word_id)
                    self._words.append(token.word)

        vocabulary_size = len(self._words)
        self._term_counts = [
            [0] * vocabulary_size for _ in range(len(documents))
        ]
        self._word_totals = [0] * len(documents)
        self._top_word_ids = [[] for _ in documents]

        for document in documents:
            vector = self._term_counts[document.doc_id]
            for token in document.body_tokens:
                word_id = self._word_to_id.get(token.word)
                if word_id is None:
                    continue
                vector[word_id] += 1
            self._word_totals[document.doc_id] = sum(vector)
            self._top_word_ids[document.doc_id] = self._find_top_word_ids(vector)

    def recommend(
        self, doc_id: int, preset: str, limit: int
    ) -> RecommendationView:
        if doc_id < 0 or doc_id >= len(self._documents):
            raise ValueError(f"无效文档编号：{doc_id}")
        if preset not in _PRESETS:
            raise ValueError(f"未知推荐预设：{preset}")
        if limit <= 0:
            raise ValueError("limit 必须为正整数")

        directory_weight, content_weight, keyword_weight = _PRESETS[preset]
        size = len(self._documents)
        scores = [[0.0] * size for _ in range(size)]
        all_items: list[RecommendationItem] = []
        for source_id in range(size):
            for candidate_id in range(size):
                if source_id == candidate_id:
                    continue
                directory = self._directory_score(source_id, candidate_id)
                content = self._content_score(source_id, candidate_id)
                keywords, shared_ids = self._keyword_score(source_id, candidate_id)
                total = (
                    directory_weight * directory
                    + content_weight * content
                    + keyword_weight * keywords
                )
                scores[source_id][candidate_id] = total
                if source_id == doc_id:
                    shared_words = [self._words[word_id] for word_id in shared_ids]
                    shared_words = merge_sort(shared_words, lambda left, right: left < right)
                    reason = self._reason(directory, content, shared_words)
                    all_items.append(
                        RecommendationItem(
                            doc_id=candidate_id,
                            title=self._documents[candidate_id].title,
                            relative_path=self._documents[candidate_id].relative_path,
                            scores=ScoreParts(directory, content, keywords, total),
                            shared_keywords=shared_words,
                            reason=reason,
                        )
                    )

        top_three: list[list[int]] = [[] for _ in range(size)]
        for source_id in range(size):
            candidates = [
                _Candidate(target_id, scores[source_id][target_id])
                for target_id in range(size)
                if target_id != source_id
            ]
            selected = select_top_k(candidates, 3, self._candidate_better)
            selected = merge_sort(selected, self._candidate_before)
            top_three[source_id] = [item.doc_id for item in selected]

        self._graph.build(self._documents, scores, top_three)
        items = select_top_k(all_items, limit, self._item_better)
        items = merge_sort(items, self._item_before)
        return RecommendationView(items=items, graph=self._graph.extract(doc_id))

    def _find_top_word_ids(self, vector: list[int]) -> list[int]:
        entries = [
            WordCount(self._words[word_id], count)
            for word_id, count in enumerate(vector)
            if count > 0
        ]
        top = select_top_k(entries, 10, self._word_better)
        ids: list[int] = []
        for entry in top:
            word_id = self._word_to_id.get(entry.word)
            if word_id is not None:
                ids.append(word_id)
        return merge_sort(ids, lambda left, right: left < right)

    def _directory_score(self, left_id: int, right_id: int) -> float:
        left_folder = self._documents[left_id].relative_path.rpartition("/")[0]
        right_folder = self._documents[right_id].relative_path.rpartition("/")[0]
        if left_folder == right_folder:
            return 1.0
        left_parts = left_folder.split("/") if left_folder else []
        right_parts = right_folder.split("/") if right_folder else []
        if left_parts and right_parts and left_parts[0] == right_parts[0]:
            return 0.6
        return 0.1

    def _content_score(self, left_id: int, right_id: int) -> float:
        denominator = self._word_totals[left_id] + self._word_totals[right_id]
        if denominator == 0:
            return 0.0
        left = self._term_counts[left_id]
        right = self._term_counts[right_id]
        overlap = 0
        for word_id in range(len(self._words)):
            overlap += min(left[word_id], right[word_id])
        return 2.0 * overlap / denominator

    def _keyword_score(self, left_id: int, right_id: int) -> tuple[float, list[int]]:
        left = self._top_word_ids[left_id]
        right = self._top_word_ids[right_id]
        common: list[int] = []
        left_index = 0
        right_index = 0
        while left_index < len(left) and right_index < len(right):
            if left[left_index] == right[right_index]:
                common.append(left[left_index])
                left_index += 1
                right_index += 1
            elif left[left_index] < right[right_index]:
                left_index += 1
            else:
                right_index += 1
        return len(common) / 10.0, common

    @staticmethod
    def _reason(directory: float, content: float, shared_words: list[str]) -> str:
        if directory == 1.0:
            directory_text = "同一直接父目录"
        elif directory == 0.6:
            directory_text = "同属一个一级目录"
        else:
            directory_text = "不属同一一级目录"
        shared_text = "、".join(shared_words) if shared_words else "无共同高频词"
        return f"{directory_text}；正文词频重合度 {content:.2f}；共同高频词：{shared_text}"

    @staticmethod
    def _word_better(left: WordCount, right: WordCount) -> bool:
        if left.count != right.count:
            return left.count > right.count
        return left.word < right.word

    @classmethod
    def _candidate_better(cls, left: _Candidate, right: _Candidate) -> bool:
        if left.score != right.score:
            return left.score > right.score
        return left.doc_id < right.doc_id

    @classmethod
    def _candidate_before(cls, left: _Candidate, right: _Candidate) -> bool:
        return cls._candidate_better(left, right)

    @staticmethod
    def _item_better(left: RecommendationItem, right: RecommendationItem) -> bool:
        if left.scores.total != right.scores.total:
            return left.scores.total > right.scores.total
        return left.doc_id < right.doc_id

    @classmethod
    def _item_before(cls, left: RecommendationItem, right: RecommendationItem) -> bool:
        return cls._item_better(left, right)
