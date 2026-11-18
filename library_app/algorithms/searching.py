"""在有序序列中执行对半查找。"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TypeVar

T = TypeVar("T")


def binary_search(
    items: Sequence[T], target: int, key: Callable[[T], int]
) -> int:
    """返回 key(item) == target 的下标；未找到时返回 -1。"""
    low = 0
    high = len(items) - 1
    while low <= high:
        middle = (low + high) // 2
        value = key(items[middle])
        if value == target:
            return middle
        if value < target:
            low = middle + 1
        else:
            high = middle - 1
    return -1
