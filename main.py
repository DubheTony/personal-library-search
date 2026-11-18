"""个人资料库检索系统 · GUI 入口。

优先使用真实 LibraryService；项目里没有样例资料库时退回内置演示数据，
这样只拿到仓库的人也能直接查看界面。
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from library_app.mock_service import MockLibraryService
from library_app.ui.main_window import MainWindow


def _build_service(sample_root: Path):
    """优先真实后端；仓库不包含样例库时退回内置演示数据。"""
    try:
        from library_app.service import LibraryService
    except Exception as exc:  # jieba / python-docx 未安装等
        print(f"[gui] 真实服务不可用：{exc}", file=sys.stderr)
        LibraryService = None

    if LibraryService is not None and sample_root.exists():
        try:
            service = LibraryService(sample_root)
            service.load()
            return service, False
        except Exception as exc:
            print(f"[gui] 真实样例库加载失败，改用演示数据：{exc}", file=sys.stderr)

    service = MockLibraryService(sample_root)
    service.load()
    return service, True


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("ATLAS")
    app.setOrganizationName("DataStructureLab")

    sample_root = Path(__file__).resolve().parent / "样例资料库"
    try:
        service, demo = _build_service(sample_root)
        window = MainWindow(service)
    except Exception as exc:  # 真实 LibraryLoadError 或其他启动问题
        QMessageBox.critical(None, "启动失败", f"无法打开样例库：\n\n{exc}")
        return 1
    if demo:
        window.setWindowTitle("ATLAS · 个人资料库（演示数据）")
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
