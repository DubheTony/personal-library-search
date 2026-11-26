"""基于自实现哈希表的有序倒排索引。"""

from __future__ import annotations

from dataclasses import dataclass, field

from .algorithms.searching import binary_search
from .algorithms.sorting import merge_sort
from .models import Document, SearchHit, SearchResult, Span, Token
from .structures.hash_table import HashTable
from .tokenizer import Tokenizer


@dataclass
class Posting:
    doc_id: int
    title_spans: list[Span] = field(default_factory=list)
    body_spans: list[Span] = field(default_factory=list)


class SearchEngine:
    def __init__(self) -> None:
        self._index: HashTable[str, list[Posting]] = HashTable()
        self._documents: list[Document] = []

    def build(self, documents: list[Document]) -> None:
        self._documents = documents
        self._index = HashTable()
        for document in documents:
            self._add_tokens(document, document.title_tokens, "title")
            self._add_tokens(document, document.body_tokens, "body")

    def search(
        self, query: str, tokenizer: Tokenizer, mode: str = "word"
    ) -> list[SearchResult]:
        if mode == "phrase":
            return self._search_phrase(query, tokenizer)

        words: list[str] = []
        for token in tokenizer.tokenize(query, keep_stopwords=True):
            if token.word not in words:
                words.append(token.word)
        if not words:
            return []

        posting_lists: list[list[Posting]] = []
        for word in words:
            postings = self._index.get(word)
            if not postings:
                return []
            posting_lists.append(postings)

        common_ids = [posting.doc_id for posting in posting_lists[0]]
        for postings in posting_lists[1:]:
            common_ids = self._intersect_ids(common_ids, postings)
            if not common_ids:
                return []

        results: list[SearchResult] = []
        for doc_id in common_ids:
            hits: list[SearchHit] = []
            for word, postings in zip(words, posting_lists):
                index = binary_search(postings, doc_id, lambda item: item.doc_id)
                if index < 0:
                    break
                posting = postings[index]
                hits.extend(
                    SearchHit(word, "title", span) for span in posting.title_spans
                )
                hits.extend(
                    SearchHit(word, "body", span) for span in posting.body_spans
                )
            else:
                hits = merge_sort(hits, self._hit_before)
                document = self._documents[doc_id]
                snippet, snippet_spans = self._make_snippet(document, hits)
                results.append(
                    SearchResult(
                        doc_id=doc_id,
                        title=document.title,
                        relative_path=document.relative_path,
                        match_count=len(hits),
                        hits=hits,
                        snippet=snippet,
                        snippet_spans=snippet_spans,
                    )
                )
        return results

    def _search_phrase(
        self, query: str, tokenizer: Tokenizer
    ) -> list[SearchResult]:
        query_tokens = [
            token.word
            for token in tokenizer.tokenize(query, keep_stopwords=True)
        ]
        if not query_tokens:
            return []
        results: list[SearchResult] = []
        for document in self._documents:
            title_tokens = tokenizer.tokenize(document.title, keep_stopwords=True)
            body_tokens = tokenizer.tokenize(document.body, keep_stopwords=True)
            hits = self._phrase_hits(
                query.strip(), title_tokens, "title", query_tokens
            )
            hits.extend(
                self._phrase_hits(query.strip(), body_tokens, "body", query_tokens)
            )
            if not hits:
                continue
            hits = merge_sort(hits, self._hit_before)
            snippet, snippet_spans = self._make_snippet(document, hits)
            results.append(
                SearchResult(
                    doc_id=document.doc_id,
                    title=document.title,
                    relative_path=document.relative_path,
                    match_count=len(hits),
                    hits=hits,
                    snippet=snippet,
                    snippet_spans=snippet_spans,
                )
            )
        return results

    @staticmethod
    def _phrase_hits(
        phrase: str, tokens: list[Token], field_name: str, query_tokens: list[str]
    ) -> list[SearchHit]:
        hits: list[SearchHit] = []
        window = len(query_tokens)
        for index in range(len(tokens) - window + 1):
            if all(
                tokens[index + offset].word == query_tokens[offset]
                for offset in range(window)
            ):
                start = tokens[index].start
                end = tokens[index + window - 1].end
                hits.append(SearchHit(phrase, field_name, Span(start, end)))
        return hits

    def _add_tokens(
        self, document: Document, tokens: list[Token], field_name: str
    ) -> None:
        for token in tokens:
            postings = self._index.get_or_insert(token.word, list)
            if postings and postings[-1].doc_id == document.doc_id:
                posting = postings[-1]
            else:
                posting = Posting(document.doc_id)
                postings.append(posting)
            span = Span(token.start, token.end)
            if field_name == "title":
                posting.title_spans.append(span)
            else:
                posting.body_spans.append(span)

    @staticmethod
    def _intersect_ids(current: list[int], postings: list[Posting]) -> list[int]:
        common: list[int] = []
        left = 0
        right = 0
        while left < len(current) and right < len(postings):
            current_id = current[left]
            posting_id = postings[right].doc_id
            if current_id == posting_id:
                common.append(current_id)
                left += 1
                right += 1
            elif current_id < posting_id:
                left += 1
            else:
                right += 1
        return common

    @staticmethod
    def _hit_before(left: SearchHit, right: SearchHit) -> bool:
        left_field = 0 if left.field == "title" else 1
        right_field = 0 if right.field == "title" else 1
        if left_field != right_field:
            return left_field < right_field
        if left.span.start != right.span.start:
            return left.span.start < right.span.start
        if left.span.end != right.span.end:
            return left.span.end < right.span.end
        return left.word < right.word

    @staticmethod
    def _make_snippet(
        document: Document, hits: list[SearchHit]
    ) -> tuple[str, list[Span]]:
        body_hit: SearchHit | None = None
        for hit in hits:
            if hit.field == "body":
                body_hit = hit
                break
        if body_hit is None:
            return document.title, [hit.span for hit in hits if hit.field == "title"]

        start = max(0, body_hit.span.start - 30)
        end = min(len(document.body), body_hit.span.end + 30)
        snippet = document.body[start:end]
        snippet_spans: list[Span] = []
        for hit in hits:
            if hit.field != "body":
                continue
            hit_start = max(hit.span.start, start)
            hit_end = min(hit.span.end, end)
            if hit_start < hit_end:
                snippet_spans.append(Span(hit_start - start, hit_end - start))
        return snippet, snippet_spans
