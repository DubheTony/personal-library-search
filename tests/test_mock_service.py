"""服务层冒烟测试：不测试界面，只验证 GUI 依赖的返回结构。

运行：
    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import unittest
from pathlib import Path

from library_app.mock_service import MockLibraryService

ROOT = Path(__file__).resolve().parents[1] / "样例资料库"


class MockServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.service = MockLibraryService(ROOT)
        cls.summary = cls.service.load()

    def test_load_and_tree(self) -> None:
        self.assertEqual(self.summary.document_count, 20)
        self.assertEqual(len(self.summary.issues), 1)
        tree = self.service.get_tree()
        self.assertEqual(tree.kind, "folder")
        self.assertEqual(len([c for c in tree.children if c.kind == "folder"]), 5)
        all_docs = self.service.list_folder("")
        self.assertEqual(len(all_docs), 20)
        self.assertEqual([d.doc_id for d in all_docs], list(range(20)))

    def test_folder_and_document(self) -> None:
        notes = self.service.list_folder("数据结构/笔记")
        self.assertEqual([d.doc_id for d in notes], [2, 3, 4, 5])
        doc = self.service.get_document(5)
        self.assertEqual(doc.title, "哈希表与冲突处理")
        with self.assertRaises(ValueError):
            self.service.get_document(999)

    def test_search(self) -> None:
        self.assertEqual(self.service.search(""), [])
        results = self.service.search("检索 索引")
        self.assertGreaterEqual(len(results), 2)
        self.assertEqual([r.doc_id for r in results], sorted(r.doc_id for r in results))
        for result in results:
            self.assertIn("检索", result.title + result.hits[0].word + result.snippet)
            found = {hit.word for hit in result.hits}
            self.assertTrue({"检索", "索引"}.issubset(found))
            self.assertEqual(result.match_count, len(result.hits))
            for span in result.snippet_spans:
                self.assertGreaterEqual(span.start, 0)
                self.assertLessEqual(span.end, len(result.snippet))
        no_hit = self.service.search("不存在的词组合xyz")
        self.assertEqual(no_hit, [])
        phrase = self.service.search("检索 系统", mode="phrase")
        self.assertTrue(phrase)
        for result in phrase:
            self.assertEqual(result.match_count, len(result.hits))
            for span in result.snippet_spans:
                self.assertGreaterEqual(span.start, 0)
                self.assertLessEqual(span.end, len(result.snippet))
        self.assertEqual(self.service.search("", mode="phrase"), [])

    def test_frequency(self) -> None:
        report = self.service.analyze_frequency(doc_id=5, k=10)
        self.assertEqual(len(report.top_k), 10)
        self.assertEqual(report.top_k[0].word, "索引")
        self.assertEqual(report.top_k[0].count, 22)
        self.assertEqual(
            [(w.word, w.count) for w in report.top_k],
            [(w.word, w.count) for w in report.quick_sorted[:10]],
        )
        self.assertEqual(
            [(w.word, w.count) for w in report.quick_sorted],
            [(w.word, w.count) for w in report.merge_sorted],
        )
        self.assertGreater(report.quick_ms, 0)
        self.assertGreater(report.merge_ms, 0)

        empty = self.service.analyze_frequency(doc_id=6, k=10)  # 课程表正文很短，仍有词
        self.assertGreaterEqual(len(empty.top_k), 1)

        with self.assertRaises(ValueError):
            self.service.analyze_frequency(doc_id=1, folder_path="数据结构")
        with self.assertRaises(ValueError):
            self.service.analyze_frequency(doc_id=1, k=0)
        with self.assertRaises(ValueError):
            self.service.analyze_frequency(doc_id=999)

    def test_recommend(self) -> None:
        view = self.service.recommend(5, "balanced", limit=10)
        self.assertEqual(len(view.items), 10)
        self.assertNotIn(5, [item.doc_id for item in view.items])
        totals = [item.scores.total for item in view.items]
        self.assertEqual(totals, sorted(totals, reverse=True))
        for item in view.items:
            self.assertGreaterEqual(item.scores.directory, 0.0)
            self.assertLessEqual(item.scores.directory, 1.0)
            self.assertGreaterEqual(item.scores.total, 0.0)
            self.assertLessEqual(item.scores.total, 1.0)
            self.assertEqual(item.shared_keywords, sorted(item.shared_keywords))

        self.assertTrue(view.cluster_sizes)
        self.assertEqual(sum(view.cluster_sizes.values()), 20)
        self.assertIn(view.center_cluster_id, view.cluster_sizes)
        for item in view.items:
            self.assertEqual(set(item.paths), {"bfs", "dijkstra"})
            self.assertIsNotNone(item.cluster_id)
            self.assertEqual(
                item.same_cluster,
                item.cluster_id == view.center_cluster_id,
            )

        structure = self.service.recommend(5, "structure")
        self.assertEqual(structure.items[0].scores.directory, 1.0)
        with self.assertRaises(ValueError):
            self.service.recommend(5, "unknown")
        with self.assertRaises(ValueError):
            self.service.recommend(999)

    def test_graph(self) -> None:
        view = self.service.recommend(5, "content")
        graph = view.graph
        ids = [node.doc_id for node in graph.nodes]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids.count(5), 1)
        self.assertEqual(next(n.hop for n in graph.nodes if n.doc_id == 5), 0)
        for node in graph.nodes:
            self.assertIn(node.hop, (0, 1, 2))
        for edge in graph.edges:
            self.assertLess(edge.low_id, edge.high_id)
            self.assertIn(edge.low_id, ids)
            self.assertIn(edge.high_id, ids)
        hop1 = [n for n in graph.nodes if n.hop == 1]
        hop2 = [n for n in graph.nodes if n.hop == 2]
        self.assertLessEqual(len(hop1), 10)
        self.assertLessEqual(len(hop2), 10)
        self.assertGreaterEqual(int(getattr(graph, "truncated", 0)), 0)


if __name__ == "__main__":
    unittest.main()
