"""自实现的链式哈希表。"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Generic, TypeVar, cast

K = TypeVar("K", bound=str)
V = TypeVar("V")
_MISSING = object()


class HashTable(Generic[K, V]):
    """以拉链法解决冲突；哈希值使用字符折叠后除留余数压缩。"""

    def __init__(self, initial_capacity: int = 8) -> None:
        if initial_capacity < 2:
            raise ValueError("initial_capacity 至少为 2")
        self._buckets: list[list[tuple[K, V]]] = [
            [] for _ in range(initial_capacity)
        ]
        self._size = 0

    def __len__(self) -> int:
        return self._size

    def _hash_value(self, key: K) -> int:
        value = 0
        for character in key:
            value = (value * 31 + ord(character)) & 0xFFFFFFFF
        return value

    def _bucket_index(self, key: K) -> int:
        # 压缩法中的除留余数法。
        return self._hash_value(key) % len(self._buckets)

    def get(self, key: K, default: V | None = None) -> V | None:
        for stored_key, value in self._buckets[self._bucket_index(key)]:
            if stored_key == key:
                return value
        return default

    def put(self, key: K, value: V) -> V | None:
        bucket = self._buckets[self._bucket_index(key)]
        for index, (stored_key, old_value) in enumerate(bucket):
            if stored_key == key:
                bucket[index] = (key, value)
                return old_value
        bucket.append((key, value))
        self._size += 1
        if self._size / len(self._buckets) > 0.75:
            self._resize(len(self._buckets) * 2)
        return None

    def get_or_insert(self, key: K, factory: Callable[[], V]) -> V:
        existing = self.get(key, cast(V, _MISSING))
        if existing is not _MISSING:
            return cast(V, existing)
        value = factory()
        self.put(key, value)
        return value

    def items(self) -> Iterator[tuple[K, V]]:
        for bucket in self._buckets:
            for key, value in bucket:
                yield key, value

    def _resize(self, capacity: int) -> None:
        old_items = list(self.items())
        self._buckets = [[] for _ in range(capacity)]
        self._size = 0
        for key, value in old_items:
            bucket = self._buckets[self._bucket_index(key)]
            bucket.append((key, value))
            self._size += 1
