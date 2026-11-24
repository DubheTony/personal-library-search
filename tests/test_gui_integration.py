"""真实 LibraryService 与 PySide6 主窗口的离屏集成测试。"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from main import _build_service
from library_app.ui.main_window import MainWindow
from support import create_text_fixture

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMP_ROOT = PROJECT_ROOT / "_临时"
TEMP_ROOT.mkdir(exist_ok=True)


class RealBackendGuiIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def test_real_backend_drives_search_frequency_recommend_and_folder(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as temp:
            sample_root = Path(temp) / "library"
            sample_root.mkdir()
            create_text_fixture(sample_root)
            service, demo = _build_service(sample_root)
            window = MainWindow(service)
            self.addCleanup(self.application.processEvents)
            self.addCleanup(window.deleteLater)
            self.addCleanup(window.close)
            window.show()
            self.application.processEvents()

            self.assertFalse(demo)
            self.assertEqual(window.summary.document_count, 4)

            window.search_input.setText("alpha beta")
            window.search_btn.click()
            self.application.processEvents()
            self.assertEqual([item.doc_id for item in window.results], [0, 1, 3])

            window.open_doc(0, highlight_terms=["alpha", "beta"], selected=0)
            self.application.processEvents()
            self.assertEqual(window.doc_id, 0)
            self.assertTrue(window.doc_open)
            self.assertIsNotNone(window.canvas.doc_panel)

            window.open_freq_for_doc()
            report = window._ensure_freq()
            self.assertIsNotNone(report)
            self.assertEqual(
                [(entry.word, entry.count) for entry in report.top_k[:2]],
                [("alpha", 2), ("beta", 1)],
            )

            window.set_preset("structure")
            self.application.processEvents()
            self.assertEqual(
                [item.doc_id for item in window._rec_view.items], [1, 2, 3]
            )
            self.assertEqual(window.canvas.graph._graph, window._rec_view.graph)

            window.select_folder("A/one")
            self.application.processEvents()
            self.assertEqual(window.folder, "A/one")
            self.assertEqual(
                [doc.doc_id for doc in service.list_folder(window.folder)], [0, 1]
            )
    def test_launcher_falls_back_to_labeled_demo_service_without_sample_data(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as temp:
            missing_root = Path(temp) / "missing-library"
            service, demo = _build_service(missing_root)
            window = MainWindow(service)
            self.addCleanup(self.application.processEvents)
            self.addCleanup(window.deleteLater)
            self.addCleanup(window.close)
            window.show()
            self.application.processEvents()

            self.assertTrue(demo)
            self.assertTrue(getattr(service, "is_demo", False))
            self.assertEqual(window.summary.document_count, 20)
            self.assertEqual(len(window.docs_by_id), 20)


if __name__ == "__main__":
    unittest.main()
