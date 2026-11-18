"""自实现循环队列，避免重复移动已出队元素。"""

from __future__ import annotations

from typing import Generic, TypeVar

T = TypeVar("T")


class Queue(Generic[T]):
    def __init__(self) -> None:
        self._items: list[T | None] = []
        self._head = 0

    def enqueue(self, item: T) -> None:
        self._items.append(item)

    def dequeue(self) -> T:
        if self.is_empty():
            raise IndexError("从空队列取值")
        item = self._items[self._head]
        self._items[self._head] = None
        self._head += 1
        if self._head >= 32 and self._head * 2 >= len(self._items):
            self._items = self._items[self._head :]
            self._head = 0
        return item  # type: ignore[return-value]

    def is_empty(self) -> bool:
        return self._head >= len(self._items)

    def __len__(self) -> int:
        return len(self._items) - self._head
