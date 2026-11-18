"""Word 格式段落与表格顺序测试。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from docx import Document as WordDocument

from library_app.readers import WordReader
from library_app.service import LibraryService

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMP_ROOT = PROJECT_ROOT / "_临时"
TEMP_ROOT.mkdir(exist_ok=True)


class WordReaderTests(unittest.TestCase):
    def test_paragraphs_and_table_are_read_in_document_order(self) -> None:
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as temp:
            root = Path(temp)
            sample = root / "library"
            sample.mkdir()
            word = WordDocument()
            word.add_paragraph("first alpha")
            table = word.add_table(rows=1, cols=2)
            table.cell(0, 0).text = "middle beta"
            table.cell(0, 1).text = "table gamma"
            word.add_paragraph("last delta")
            file_path = sample / "ordered.docx"
            word.save(file_path)

            title, body = WordReader().read(file_path)
            self.assertEqual(title, "ordered")
            self.assertLess(body.index("first alpha"), body.index("middle beta"))
            self.assertLess(body.index("middle beta"), body.index("last delta"))

            service = LibraryService(sample)
            summary = service.load()
            self.assertEqual(summary.document_count, 1)
            self.assertIn("table gamma", service.get_document(0).body)


if __name__ == "__main__":
    unittest.main()
