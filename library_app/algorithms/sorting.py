"""不用内置排序函数的快速排序和稳定归并排序。"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TypeVar

T = TypeVar("T")
Before = Callable[[T, T], bool]


def quick_sort(items: Sequence[T], before: Before[T]) -> list[T]:
    """返回按 before 定义的顺序排列的新列表，使用三路分区。"""
    result = list(items)
    if len(result) < 2:
        return result

    ranges = [(0, len(result) - 1)]
    while ranges:
        low, high = ranges.pop()
        if low >= high:
            continue

        pivot = result[(low + high) // 2]
        less_end = low
        current = low
        greater_start = high
        while current <= greater_start:
            if before(result[current], pivot):
                result[less_end], result[current] = result[current], result[less_end]
                less_end += 1
                current += 1
            elif before(pivot, result[current]):
                result[current], result[greater_start] = result[greater_start], result[current]
                greater_start -= 1
            else:
                current += 1

        left = (low, less_end - 1)
        right = (greater_start + 1, high)
        # Push the larger side first so the smaller side is processed next.
        if left[1] - left[0] > right[1] - right[0]:
            ranges.append(left)
            ranges.append(right)
        else:
            ranges.append(right)
            ranges.append(left)

    return result


def merge_sort(items: Sequence[T], before: Before[T]) -> list[T]:
    """返回稳定排序的新列表。"""
    result = list(items)
    size = len(result)
    if size < 2:
        return result

    buffer = list(result)
    width = 1
    while width < size:
        start = 0
        while start < size:
            middle = min(start + width, size)
            end = min(start + width * 2, size)
            left = start
            right = middle
            output = start

            while left < middle and right < end:
                if before(result[right], result[left]):
                    buffer[output] = result[right]
                    right += 1
                else:
                    # Keep the left item first when neither is strictly before the other.
                    buffer[output] = result[left]
                    left += 1
                output += 1

            while left < middle:
                buffer[output] = result[left]
                left += 1
                output += 1
            while right < end:
                buffer[output] = result[right]
                right += 1
                output += 1
            start = end

        result, buffer = buffer, result
        width *= 2

    return result
