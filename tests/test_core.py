"""自实现结构、检索、词频与推荐的单元测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from library_app.algorithms.searching import binary_search
from library_app.algorithms.sorting import merge_sort, quick_sort
from library_app.models import GraphEdge, Span
from library_app.relation_graph import RelationGraph
from library_app.service import LibraryLoadError, LibraryService
from library_app.structures.hash_table import HashTable
from library_app.structures.heap import MinHeap, select_top_k
from library_app.structures.queue import Queue
from library_app.structures.stack import Stack
from library_app.tokenizer import Tokenizer
from support import create_repository_document, create_text_fixture


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMP_ROOT = PROJECT_ROOT / "_临时"
TEMP_ROOT.mkdir(exist_ok=True)


class StructureTests(unittest.TestCase):
    def test_hash_table_collision_resize_and_factory(self) -> None:
        table: HashTable[str, int] = HashTable(initial_capacity=2)
        # The character-folding hash sends these keys to the same initial bucket.
        self.assertEqual(table._bucket_index("a"), table._bucket_index("c"))
        table.put("a", 1)
        table.put("c", 3)
        self.assertEqual(table.get("a"), 1)
        self.assertEqual(table.get("c"), 3)
        calls = 0

        def make_value() -> int:
            nonlocal calls
            calls += 1
            return 9

        self.assertEqual(table.get_or_insert("new", make_value), 9)
        self.assertEqual(table.get_or_insert("new", make_value), 9)
        self.assertEqual(calls, 1)
        for number in range(40):
            table.put(f"key-{number}", number)
        for number in range(40):
            self.assertEqual(table.get(f"key-{number}"), number)

    def test_stack_queue_and_heap(self) -> None:
        stack: Stack[int] = Stack()
        stack.push(1)
        stack.push(2)
        self.assertEqual([stack.pop(), stack.pop()], [2, 1])
        with self.assertRaises(IndexError):
            stack.pop()

        queue: Queue[int] = Queue()
        for number in range(50):
            queue.enqueue(number)
        self.assertEqual([queue.dequeue() for _ in range(50)], list(range(50)))
        self.assertTrue(queue.is_empty())
        with self.assertRaises(IndexError):
            queue.dequeue()

        heap: MinHeap[int] = MinHeap(lambda left, right: left < right)
        for number in (5, 1, 3, 2, 4):
            heap.push(number)
        self.assertEqual([heap.pop() for _ in range(5)], [1, 2, 3, 4, 5])

    def test_sorting_and_binary_search(self) -> None:
        values = [7, 2, 9, 2, 1, 8, 3, 2]
        before = lambda left, right: left < right
        self.assertEqual(quick_sort(values, before), [1, 2, 2, 2, 3, 7, 8, 9])
        self.assertEqual(merge_sort(values, before), [1, 2, 2, 2, 3, 7, 8, 9])
        self.assertEqual(binary_search([1, 3, 5, 7], 1, lambda item: item), 0)
        self.assertEqual(binary_search([1, 3, 5, 7], 7, lambda item: item), 3)
        self.assertEqual(binary_search([1, 3, 5, 7], 4, lambda item: item), -1)

    def test_top_k_preserves_total_order(self) -> None:
        values = [(4, "z"), (7, "c"), (7, "a"), (3, "b"), (7, "b")]
        better = lambda left, right: left[0] > right[0] or (
            left[0] == right[0] and left[1] < right[1]
        )
        chosen = select_top_k(values, 3, better)
        self.assertEqual(merge_sort(chosen, better), [(7, "a"), (7, "b"), (7, "c")])


class TokenizerTests(unittest.TestCase):
    def test_token_offsets_are_python_string_offsets(self) -> None:
        tokenizer = Tokenizer(PROJECT_ROOT / "stopwords.txt")
        text = "索引 alpha，检索"
        tokens = tokenizer.tokenize(text)
        alpha = next(token for token in tokens if token.word == "alpha")
        self.assertEqual(text[alpha.start : alpha.end], "alpha")
        self.assertEqual(tokens, sorted(tokens, key=lambda token: token.start))

    def test_markdown_cleaning_and_title(self) -> None:
        from library_app.readers import MarkdownReader

        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as temp:
            path = Path(temp) / "note.md"
            path.write_text(
                "# Main **Title**\n\n- **alpha** [beta](https://example.invalid)\n"
                "> gamma\n```text\ncode sample\n```\n",
                encoding="utf-8",
            )
            title, body = MarkdownReader().read(path)
        self.assertEqual(title, "Main Title")
        self.assertIn("alpha beta", body)
        self.assertIn("gamma", body)
        self.assertIn("code sample", body)
        self.assertNotIn("**", body)
        self.assertNotIn("https://", body)


class ServiceIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=TEMP_ROOT)
        self.root = Path(self.temp.name)
        create_text_fixture(self.root)
        self.service = LibraryService(self.root)
        self.summary = self.service.load()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_load_tree_and_folder_listing(self) -> None:
        self.assertEqual(self.summary.document_count, 4)
        self.assertEqual(
            [self.service.get_document(index).relative_path for index in range(4)],
            [
                "A/one/aa.txt",
                "A/one/bb.txt",
                "A/two/cc.txt",
                "B/one/dd.txt",
            ],
        )
        self.assertEqual(
            [document.doc_id for document in self.service.list_folder("A")],
            [0, 1, 2],
        )
        self.assertEqual(len(self.service.list_folder("")), 4)
        tree = self.service.get_tree()
        self.assertEqual(tree.kind, "folder")
        self.assertEqual(tree.children[0].name, "A")
        with self.assertRaises(ValueError):
            self.service.list_folder("missing")

    def test_search_all_terms_and_positions(self) -> None:
        results = self.service.search("alpha beta")
        self.assertEqual([result.doc_id for result in results], [0, 1, 3])
        self.assertEqual([result.match_count for result in results], [3, 3, 2])
        self.assertEqual(
            [(hit.span.start, hit.span.end) for hit in results[0].hits],
            [(0, 5), (6, 11), (12, 16)],
        )
        self.assertEqual(self.service.search("absent"), [])
        self.assertEqual(self.service.search("   "), [])

    def test_phrase_search_across_punctuation_and_scattered_words(self) -> None:
        (self.root / "A/two/ee.txt").write_text("alpha gamma beta", encoding="utf-8")
        (self.root / "A/two/ff.txt").write_text("alpha，beta", encoding="utf-8")
        (self.root / "A/two/gg.md").write_text(
            "# Alpha Beta" + chr(10) + chr(10) + "plain", encoding="utf-8"
        )
        self.service.load()

        word = self.service.search("alpha beta")
        phrase = self.service.search("alpha beta", mode="phrase")
        scattered = next(
            result for result in word if result.relative_path.endswith("ee.txt")
        )
        self.assertNotIn(
            scattered.doc_id, {result.doc_id for result in phrase}
        )
        phrase_paths = {result.relative_path for result in phrase}
        self.assertEqual(len(phrase), 5)
        self.assertTrue(
            {
                "A/one/aa.txt",
                "A/one/bb.txt",
                "B/one/dd.txt",
                "A/two/ff.txt",
                "A/two/gg.md",
            }.issubset(phrase_paths)
        )
        self.assertNotIn("A/two/ee.txt", phrase_paths)

        punctuated = next(
            result for result in phrase if result.relative_path.endswith("ff.txt")
        )
        self.assertEqual(punctuated.match_count, 1)
        self.assertEqual(punctuated.hits[0].span, Span(0, 10))
        self.assertEqual(
            self.service.get_document(punctuated.doc_id).body[0:10],
            "alpha，beta",
        )

        title_only = next(
            result for result in phrase if result.relative_path.endswith("gg.md")
        )
        self.assertTrue(all(hit.field == "title" for hit in title_only.hits))
        self.assertEqual(title_only.snippet, "Alpha Beta")
        self.assertEqual(self.service.search("", mode="phrase"), [])

    def test_recommendation_paths_and_clusters(self) -> None:
        view = self.service.recommend(0, "balanced")
        self.assertTrue(view.cluster_sizes)
        self.assertEqual(sum(view.cluster_sizes.values()), self.summary.document_count)
        self.assertIn(view.center_cluster_id, view.cluster_sizes)
        for item in view.items:
            self.assertEqual(set(item.paths), {"bfs", "dijkstra"})
            self.assertIsNotNone(item.cluster_id)
            self.assertEqual(
                item.same_cluster,
                item.cluster_id == view.center_cluster_id,
            )
            for path in item.paths.values():
                self.assertEqual(path.hops, len(path.segments))
        structure = self.service.recommend(0, "structure")
        self.assertEqual(sum(structure.cluster_sizes.values()), self.summary.document_count)
        self.assertTrue(all(item.paths for item in structure.items))

    def test_frequency_two_sorts_and_top_k(self) -> None:
        report = self.service.analyze_frequency(doc_id=0, k=2)
        self.assertEqual(
            [(item.word, item.count) for item in report.top_k],
            [("alpha", 2), ("beta", 1)],
        )
        self.assertEqual(report.quick_sorted, report.merge_sorted)
        self.assertEqual(
            [(item.word, item.count) for item in report.quick_sorted],
            [("alpha", 2), ("beta", 1)],
        )
        with self.assertRaises(ValueError):
            self.service.analyze_frequency(k=2)
        with self.assertRaises(ValueError):
            self.service.analyze_frequency(doc_id=0, folder_path="A")

    def test_recommendation_scores_and_preset_order(self) -> None:
        balanced = self.service.recommend(0, "balanced")
        self.assertEqual([item.title for item in balanced.items], ["bb", "dd", "cc"])
        expected = {
            "bb": (1.0, 2 / 3, 0.2, 101 / 150),
            "cc": (0.6, 0.4, 0.1, 0.4),
            "dd": (0.1, 0.8, 0.2, 0.47),
        }
        for item in balanced.items:
            values = expected[item.title]
            actual = (
                item.scores.directory,
                item.scores.content,
                item.scores.keywords,
                item.scores.total,
            )
            for actual_value, expected_value in zip(actual, values):
                self.assertLess(abs(actual_value - expected_value), 1e-9)
        self.assertEqual(
            [item.title for item in self.service.recommend(0, "structure").items],
            ["bb", "cc", "dd"],
        )
        self.assertEqual(
            [item.title for item in self.service.recommend(0, "content").items],
            ["dd", "bb", "cc"],
        )
        self.assertEqual(balanced.items[0].shared_keywords, ["alpha", "beta"])

    def test_title_only_hit_and_unreadable_file(self) -> None:
        path = self.root / "A/one/heading.md"
        path.write_text("# Alpha\n\nplain body", encoding="utf-8")
        (self.root / "A/one/broken.docx").write_text("not a Word archive", encoding="utf-8")
        summary = self.service.load()
        self.assertEqual(summary.document_count, 5)
        self.assertEqual(len(summary.issues), 1)
        title_result = self.service.search("alpha")
        result = next(item for item in title_result if item.relative_path.endswith("heading.md"))
        self.assertEqual(result.snippet, "Alpha")
        self.assertTrue(result.hits)
        self.assertTrue(all(hit.field == "title" for hit in result.hits))

    def test_missing_or_empty_sample_library_fails_clearly(self) -> None:
        missing = LibraryService(self.root / "missing")
        with self.assertRaisesRegex(LibraryLoadError, "样例资料库目录不存在"):
            missing.load()

        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as empty:
            empty_service = LibraryService(Path(empty))
            with self.assertRaisesRegex(LibraryLoadError, "没有可读取"):
                empty_service.load()


class GraphTests(unittest.TestCase):
    def test_one_hop_cap_does_not_recycle_truncated_nodes(self) -> None:
        documents = [
            create_repository_document(i, f"A/shared/doc-{i:02}.txt", "word")
            for i in range(13)
        ]
        scores = [[0.0] * 13 for _ in range(13)]
        top_three = [[] for _ in range(13)]
        graph = RelationGraph()
        graph.build(documents, scores, top_three)
        view = graph.extract(0)
        self.assertEqual(sum(node.hop == 1 for node in view.nodes), 10)
        self.assertEqual(sum(node.hop == 2 for node in view.nodes), 0)
        self.assertTrue(all(edge.has_structure for edge in view.edges))
        self.assertTrue(all(edge.low_id < edge.high_id for edge in view.edges))

    def test_paths_and_clusters(self) -> None:
        documents = [
            create_repository_document(0, "A/x/0.txt", "doc0"),
            create_repository_document(1, "A/x/1.txt", "doc1"),
            create_repository_document(2, "B/y/2.txt", "doc2"),
            create_repository_document(3, "C/z/3.txt", "doc3"),
        ]
        scores = [
            [0.0, 0.9, 0.1, 0.0],
            [0.9, 0.0, 0.9, 0.0],
            [0.1, 0.9, 0.0, 0.0],
            [0.0, 0.0, 0.0, 0.0],
        ]
        top_three = [[2, 1], [2], [0, 1], []]
        graph = RelationGraph()
        graph.build(documents, scores, top_three)
        self.assertEqual(graph.cluster_map(), {0: 0, 1: 0, 2: 0, 3: 1})
        self.assertEqual(graph.cluster_sizes(), {0: 3, 1: 1})

        paths = graph.paths(0, 2)
        self.assertEqual([node.doc_id for node in paths["bfs"].nodes], [0, 2])
        self.assertEqual(paths["bfs"].hops, 1)
        self.assertEqual(
            [node.doc_id for node in paths["dijkstra"].nodes], [0, 1, 2]
        )
        self.assertEqual(paths["dijkstra"].hops, 2)
        self.assertLess(
            paths["dijkstra"].total_cost, paths["bfs"].total_cost
        )
        self.assertTrue(all(segment.basis for segment in paths["dijkstra"].segments))

        view = graph.extract(0)
        self.assertEqual({node.doc_id for node in view.nodes}, {0, 1, 2})
        self.assertTrue(all(node.cluster_id == 0 for node in view.nodes))

    def test_structure_and_recommendation_edges_merge(self) -> None:
        documents = [
            create_repository_document(0, "A/shared/a.txt", "a"),
            create_repository_document(1, "A/shared/b.txt", "b"),
        ]
        graph = RelationGraph()
        graph.build(documents, [[0.0, 0.8], [0.2, 0.0]], [[1], [0]])
        view = graph.extract(0)
        self.assertEqual(
            view.edges,
            [GraphEdge(0, 1, True, True, True)],
        )


if __name__ == "__main__":
    unittest.main()
