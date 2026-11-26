"""样例资料库加载、编号和多叉目录树管理。"""

from __future__ import annotations

from pathlib import Path
from zipfile import BadZipFile

from docx.opc.exceptions import PackageNotFoundError

from .algorithms.sorting import merge_sort
from .models import (
    Document,
    DocumentView,
    LoadIssue,
    LoadSummary,
    Token,
    TreeItem,
)
from .readers import DocumentReader, MarkdownReader, TextReader, WordReader
from .structures.hash_table import HashTable
from .structures.tree import TreeNode
from .tokenizer import Tokenizer

_SUPPORTED_SUFFIXES = {".md", ".txt", ".docx"}


class LibraryRepository:
    def __init__(self) -> None:
        self._documents: list[Document] = []
        self._root_node: TreeNode | None = None
        self._issues: list[LoadIssue] = []
        self._readers: HashTable[str, DocumentReader] = HashTable()
        self._readers.put(".md", MarkdownReader())
        self._readers.put(".txt", TextReader())
        self._readers.put(".docx", WordReader())

    @property
    def documents(self) -> list[Document]:
        return self._documents

    def load(self, root: Path, tokenizer: Tokenizer) -> LoadSummary:
        root = root.resolve()
        if not root.exists() or not root.is_dir():
            raise FileNotFoundError(f"样例资料库目录不存在：{root}")

        self._documents = []
        self._issues = []
        self._root_node = TreeNode(root.name, "", "folder")
        files: list[Path] = []
        self._collect_tree(root, self._root_node, files)
        files = merge_sort(files, self._path_before)

        for path in files:
            relative_path = path.relative_to(root).as_posix()
            reader = self._readers.get(path.suffix.casefold())
            if reader is None:
                continue
            try:
                title, body = reader.read(path)
            except (OSError, UnicodeError, ValueError, BadZipFile, PackageNotFoundError) as exc:
                self._issues.append(
                    LoadIssue(relative_path, f"{type(exc).__name__}: {exc}")
                )
                continue

            doc_id = len(self._documents)
            document = Document(
                doc_id=doc_id,
                relative_path=relative_path,
                title=title,
                body=body,
                title_tokens=tokenizer.tokenize(title, keep_stopwords=True),
                body_tokens=tokenizer.tokenize(body, keep_stopwords=True),
                body_analysis_tokens=tokenizer.tokenize(body),
            )
            self._documents.append(document)
            parent_node = self._find_directory(relative_path.rpartition("/")[0])
            parent_node.add_child(
                TreeNode(path.name, relative_path, "document", doc_id)
            )

        return LoadSummary(
            root_path=str(root),
            document_count=len(self._documents),
            issues=list(self._issues),
        )

    def get_tree(self) -> TreeItem:
        if self._root_node is None:
            raise RuntimeError("资料库尚未加载")
        return self._to_tree_item(self._root_node)

    def list_folder(self, folder_path: str) -> list[DocumentView]:
        node = self._find_directory(folder_path)
        documents: list[DocumentView] = []
        for child in node.depth_first():
            if child.kind == "document" and child.doc_id is not None:
                documents.append(self._view(self._documents[child.doc_id]))
        return merge_sort(documents, lambda left, right: left.doc_id < right.doc_id)

    def get_document(self, doc_id: int) -> DocumentView:
        if doc_id < 0 or doc_id >= len(self._documents):
            raise ValueError(f"无效文档编号：{doc_id}")
        return self._view(self._documents[doc_id])

    def _collect_tree(
        self, directory: Path, node: TreeNode, files: list[Path]
    ) -> None:
        entries = merge_sort(list(directory.iterdir()), self._entry_before)
        for entry in entries:
            if entry.is_symlink():
                continue
            # Compute paths from the node's stable relative path, not from the process CWD.
            child_relative = (
                f"{node.relative_path}/{entry.name}" if node.relative_path else entry.name
            )
            if entry.is_dir():
                child = TreeNode(entry.name, child_relative, "folder")
                node.add_child(child)
                try:
                    self._collect_tree(entry, child, files)
                except OSError as exc:
                    self._issues.append(
                        LoadIssue(child_relative, f"{type(exc).__name__}: {exc}")
                    )
            elif entry.is_file() and entry.suffix.casefold() in _SUPPORTED_SUFFIXES:
                files.append(entry)

    @staticmethod
    def _entry_before(left: Path, right: Path) -> bool:
        left_dir = left.is_dir()
        right_dir = right.is_dir()
        if left_dir != right_dir:
            return left_dir
        left_name = left.name.casefold()
        right_name = right.name.casefold()
        if left_name != right_name:
            return left_name < right_name
        return left.name < right.name

    @staticmethod
    def _path_before(left: Path, right: Path) -> bool:
        left_path = left.as_posix().casefold()
        right_path = right.as_posix().casefold()
        if left_path != right_path:
            return left_path < right_path
        return left.as_posix() < right.as_posix()

    def _find_directory(self, folder_path: str) -> TreeNode:
        if self._root_node is None:
            raise RuntimeError("资料库尚未加载")
        normalized = folder_path.strip("/")
        node = self._root_node
        if not normalized:
            return node
        for part in normalized.split("/"):
            next_node: TreeNode | None = None
            for child in node.children:
                if child.kind == "folder" and child.name == part:
                    next_node = child
                    break
            if next_node is None:
                raise ValueError(f"无效目录路径：{folder_path}")
            node = next_node
        return node

    @staticmethod
    def _view(document: Document) -> DocumentView:
        return DocumentView(
            document.doc_id,
            document.title,
            document.relative_path,
            document.body,
        )

    @classmethod
    def _to_tree_item(cls, node: TreeNode) -> TreeItem:
        return TreeItem(
            name=node.name,
            relative_path=node.relative_path,
            kind=node.kind,
            doc_id=node.doc_id,
            children=[cls._to_tree_item(child) for child in node.children],
        )
