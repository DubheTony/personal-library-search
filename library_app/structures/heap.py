"""自实现二叉最小堆及 Top-K 选择。"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Generic, TypeVar

T = TypeVar("T")


class MinHeap(Generic[T]):
    """less(a, b) 为真时，a 的堆优先级高于 b。"""

    def __init__(self, less: Callable[[T, T], bool]) -> None:
        self._items: list[T] = []
        self._less = less

    def __len__(self) -> int:
        return len(self._items)

    def is_empty(self) -> bool:
        return not self._items

    def peek(self) -> T:
        if not self._items:
            raise IndexError("查看空堆")
        return self._items[0]

    def push(self, item: T) -> None:
        self._items.append(item)
        child = len(self._items) - 1
        while child > 0:
            parent = (child - 1) // 2
            if not self._less(self._items[child], self._items[parent]):
                break
            self._items[child], self._items[parent] = (
                self._items[parent],
                self._items[child],
            )
            child = parent

    def pop(self) -> T:
        if not self._items:
            raise IndexError("从空堆取值")
        root = self._items[0]
        last = self._items.pop()
        if self._items:
            self._items[0] = last
            parent = 0
            size = len(self._items)
            while True:
                left = parent * 2 + 1
                right = left + 1
                smallest = parent
                if left < size and self._less(
                    self._items[left], self._items[smallest]
                ):
                    smallest = left
                if right < size and self._less(
                    self._items[right], self._items[smallest]
                ):
                    smallest = right
                if smallest == parent:
                    break
                self._items[parent], self._items[smallest] = (
                    self._items[smallest],
                    self._items[parent],
                )
                parent = smallest
        return root


def select_top_k(
    items: Iterable[T], k: int, better: Callable[[T, T], bool]
) -> list[T]:
    """选出最好的 k 项；返回顺序不作承诺，调用方负责最终排序。"""
    if k <= 0:
        return []
    # 将“更好”反转成堆序，使堆顶始终是当前结果中最差的一项。
    heap = MinHeap(lambda left, right: better(right, left))
    for item in items:
        if len(heap) < k:
            heap.push(item)
        elif better(item, heap.peek()):
            heap.pop()
            heap.push(item)
    chosen: list[T] = []
    while not heap.is_empty():
        chosen.append(heap.pop())
    return chosen
