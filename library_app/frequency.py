"""词频计数、堆选 Top-K 与排序算法耗时对比。"""

from __future__ import annotations

from time import perf_counter_ns

from .algorithms.sorting import merge_sort, quick_sort
from .models import Document, FrequencyReport, WordCount
from .structures.hash_table import HashTable
from .structures.heap import select_top_k


class FrequencyAnalyzer:
    def analyze(
        self, documents: list[Document], doc_ids: list[int], k: int
    ) -> FrequencyReport:
        if k <= 0:
            raise ValueError("k 必须为正整数")

        counts: HashTable[str, int] = HashTable()
        for doc_id in doc_ids:
            if doc_id < 0 or doc_id >= len(documents):
                raise ValueError(f"无效文档编号：{doc_id}")
            for token in documents[doc_id].body_tokens:
                counts.put(token.word, (counts.get(token.word, 0) or 0) + 1)

        entries = [WordCount(word, count) for word, count in counts.items()]
        top_k = select_top_k(entries, k, self._word_better)
        top_k = merge_sort(top_k, self._word_before)

        quick_input = list(entries)
        start = perf_counter_ns()
        quick_sorted = quick_sort(quick_input, self._word_before)
        quick_ms = (perf_counter_ns() - start) / 1_000_000

        merge_input = list(entries)
        start = perf_counter_ns()
        merge_sorted = merge_sort(merge_input, self._word_before)
        merge_ms = (perf_counter_ns() - start) / 1_000_000

        return FrequencyReport(
            top_k=top_k,
            quick_sorted=quick_sorted,
            merge_sorted=merge_sorted,
            quick_ms=quick_ms,
            merge_ms=merge_ms,
        )

    @staticmethod
    def _word_better(left: WordCount, right: WordCount) -> bool:
        if left.count != right.count:
            return left.count > right.count
        return left.word < right.word

    @staticmethod
    def _word_before(left: WordCount, right: WordCount) -> bool:
        return FrequencyAnalyzer._word_better(left, right)
