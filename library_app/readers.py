"""Markdown、纯文本和 Word 读取器。"""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document as OpenDocument
from docx.table import Table
from docx.text.paragraph import Paragraph


class DocumentReader:
    def read(self, path: Path) -> tuple[str, str]:
        raise NotImplementedError


class TextReader(DocumentReader):
    def read(self, path: Path) -> tuple[str, str]:
        return path.stem, path.read_text(encoding="utf-8")


class MarkdownReader(DocumentReader):
    _heading = re.compile(r"^\s{0,3}#\s+(.*)$")
    _fence = re.compile(r"^\s{0,3}(```+|~~~+)")
    _image = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
    _link = re.compile(r"\[([^\]]+)\]\([^)]*\)")
    _bold = re.compile(r"(\*\*|__)(.*?)\1")
    _italic = re.compile(r"(?<!\w)(\*|_)(.+?)\1")
    _inline_code = re.compile(r"`+([^`]+)`+")

    def read(self, path: Path) -> tuple[str, str]:
        source_lines = path.read_text(encoding="utf-8").splitlines()
        title = path.stem
        title_found = False
        body_lines: list[str] = []
        in_fence = False

        for line in source_lines:
            fence = self._fence.match(line)
            if fence:
                in_fence = not in_fence
                continue
            if not in_fence and not title_found:
                heading = self._heading.match(line)
                if heading:
                    title = self._clean_inline(heading.group(1)).strip() or path.stem
                    title_found = True
                    continue
            if in_fence:
                body_lines.append(line)
            else:
                body_lines.append(self._clean_line(line))

        return title, "\n".join(body_lines).strip()

    def _clean_line(self, line: str) -> str:
        text = re.sub(r"^\s{0,3}#{1,6}\s+", "", line)
        text = re.sub(r"^\s*>\s?", "", text)
        text = re.sub(r"^\s*(?:[-+*]|\d+[.)])\s+", "", text)
        return self._clean_inline(text)

    def _clean_inline(self, text: str) -> str:
        text = self._image.sub(r"\1", text)
        text = self._link.sub(r"\1", text)
        text = self._inline_code.sub(r"\1", text)
        text = self._bold.sub(r"\2", text)
        text = self._italic.sub(r"\2", text)
        text = text.replace("~~", "")
        return text


class WordReader(DocumentReader):
    def read(self, path: Path) -> tuple[str, str]:
        document = OpenDocument(path)
        title = path.stem
        text_blocks: list[str] = []

        for block in document.iter_inner_content():
            if isinstance(block, Paragraph):
                if block.text.strip():
                    text_blocks.append(block.text)
            elif isinstance(block, Table):
                for row in block.rows:
                    cells = [cell.text.replace("\n", " ").strip() for cell in row.cells]
                    if any(cells):
                        text_blocks.append("\t".join(cells))

        return title, "\n".join(text_blocks).strip()
