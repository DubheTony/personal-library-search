"""目录和图共用的多叉树节点。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

from .stack import Stack


@dataclass
class TreeNode:
    name: str
    relative_path: str
    kind: str
    doc_id: int | None = None
    parent: TreeNode | None = None
    children: list[TreeNode] = field(default_factory=list)

    def add_child(self, child: TreeNode) -> None:
        child.parent = self
        self.children.append(child)

    def depth_first(self) -> Iterator[TreeNode]:
        stack: Stack[TreeNode] = Stack()
        stack.push(self)
        while not stack.is_empty():
            node = stack.pop()
            yield node
            for child in reversed(node.children):
                stack.push(child)
