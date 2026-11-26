"""Regression checks for the public demonstration corpus."""

from __future__ import annotations

import unittest
from collections import Counter
from pathlib import Path

from library_app.readers import MarkdownReader, TextReader, WordReader
from library_app.service import LibraryService

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_ROOT = PROJECT_ROOT / "样例资料库"
READERS = {
    ".md": MarkdownReader(),
    ".txt": TextReader(),
    ".docx": WordReader(),
}


class SampleCorpusTests(unittest.TestCase):
    def test_inventory_formats_size_and_article_lengths(self) -> None:
        files = [path for path in SAMPLE_ROOT.rglob("*") if path.is_file()]
        self.assertEqual(len(files), 34)
        self.assertEqual(
            Counter(path.suffix.casefold() for path in files),
            {".md": 26, ".txt": 5, ".docx": 3},
        )
        self.assertLessEqual(sum(path.stat().st_size for path in files), 2 * 1024 * 1024)
        for path in files:
            _title, body = READERS[path.suffix.casefold()].read(path)
            with self.subTest(path=path.relative_to(SAMPLE_ROOT).as_posix()):
                self.assertGreaterEqual(len(body), 500)
                self.assertLessEqual(len(body), 1500)

    def test_real_service_reads_the_corpus_without_errors(self) -> None:
        service = LibraryService(SAMPLE_ROOT)
        summary = service.load()
        self.assertEqual(summary.document_count, 34)
        self.assertEqual(summary.issues, [])
        root = service.get_tree()
        self.assertEqual(sum(item.kind == "folder" for item in root.children), 5)
        self.assertEqual(len(service.list_folder("")), 34)

        matches = service.search("梯度")
        self.assertTrue(any("损失函数与梯度下降" in item.relative_path for item in matches))
        report = service.analyze_frequency(doc_id=0, k=10)
        self.assertGreaterEqual(len(report.top_k), 1)
        recommendation = service.recommend(0, "balanced", limit=5)
        self.assertEqual(len(recommendation.items), 5)
        self.assertTrue(
            any(node.doc_id == 0 and node.hop == 0 for node in recommendation.graph.nodes)
        )
    def test_search_keeps_modal_words_while_analysis_filters_them(self) -> None:
        service = LibraryService(SAMPLE_ROOT)
        service.load()

        search_results = service.search("可能")
        self.assertTrue(search_results)
        self.assertTrue(
            any("可能" in result.relative_path or any(hit.word == "可能" for hit in result.hits)
                for result in search_results)
        )

        frequency = service.analyze_frequency(folder_path="", k=1000)
        frequency_words = {entry.word for entry in frequency.quick_sorted}
        self.assertFalse({"可能", "会"} & frequency_words, "分析词频应排除常见语气词")

        center_id = next(
            document.doc_id
            for document in service.list_folder("天文学/天体")
            if document.relative_path.endswith("恒星的形成与演化.md")
        )
        recommendations = service.recommend(center_id, "balanced", limit=10)
        shared_words = {
            word
            for item in recommendations.items
            for word in item.shared_keywords
        }
        self.assertNotIn("可能", shared_words)
        self.assertNotIn("会", shared_words)


if __name__ == "__main__":
    unittest.main()
