"""共享小型集成测试夹具。"""

from __future__ import annotations

from pathlib import Path


def create_text_fixture(root: Path) -> None:
    texts = (
        ("A/one/aa.txt", "alpha alpha beta"),
        ("A/one/bb.txt", "alpha beta beta"),
        ("A/two/cc.txt", "alpha gamma"),
        ("B/one/dd.txt", "alpha beta"),
    )
    for relative_path, text in texts:
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def create_repository_document(doc_id: int, path: str, body: str):
    from library_app.models import Document
    from library_app.tokenizer import Tokenizer

    project_root = Path(__file__).resolve().parents[1]
    tokenizer = Tokenizer(project_root / "stopwords.txt")
    return Document(
        doc_id=doc_id,
        relative_path=path,
        title=Path(path).stem,
        body=body,
        title_tokens=tokenizer.tokenize(Path(path).stem, keep_stopwords=True),
        body_tokens=tokenizer.tokenize(body, keep_stopwords=True),
        body_analysis_tokens=tokenizer.tokenize(body),
    )
