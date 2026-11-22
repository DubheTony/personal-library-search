# Personal Library Search

[中文](README.md) | [English](README.en.md)

An offline document search and recommendation tool for Windows. It reads local Markdown files, UTF-8 plain text, and Word documents to help you find material by content and discover related documents.

## Features

- Browse documents by directory.
- Search full text with multiple keywords and see matching documents, locations, and context.
- Count word frequencies for a document or directory and compare the results of two sorting algorithms.
- Recommend documents based on directory relationships, word frequencies in their text, and shared high-frequency words; show the contribution of each factor and a relationship graph.
- Process documents locally without uploading them.

## Current status

The repository includes document readers, word segmentation, inverted-index search, word-frequency analysis, related-document recommendations, a shared service interface, automated tests, and a PySide6 desktop interface. A full sample document library has not yet been added to the repository.

## Desktop interface

Install dependencies and start the application:

```bash
python -m pip install -r requirements.txt
python main.py
```

On Windows, you can also double-click `运行.bat`.

The interface prefers the real `LibraryService`. If there is no `样例资料库/` directory in the project root or the real service fails to load, it falls back to 20 built-in demo documents. The window title displays “演示数据” (demo data) so you can try the interface immediately. Add real documents to `样例资料库/` to use the real backend automatically.

The interface includes a directory tree, full-text search, word-frequency analysis, three recommendation methods, a two-hop relationship graph, a document side panel, and notifications about files that could not be read. In the top-right corner, you can switch between the “纸质档案”, “观察台”, and “制图台” visual themes. The `− / percentage / +` controls at the top zoom the entire page from 85% to 150% (120% by default on large screens). You can also use `Ctrl + mouse wheel`, `Ctrl+=`, `Ctrl+-`, or `Ctrl+0`.

The sample document library remains excluded from the repository by `.gitignore`.

## Install and test

Requires Python 3.13 or a compatible version.

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Current tests cover core data structures, readers, service integration, and smoke tests using the GUI's demo data.

## Dependencies

PySide6, jieba, and python-docx. See `requirements.txt` for specific versions.
