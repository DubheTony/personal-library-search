"""使用 jieba 精确模式分词，并保留原文字符偏移。"""

from __future__ import annotations

from pathlib import Path

import jieba

from .models import Token


class Tokenizer:
    def __init__(self, stopwords_path: Path) -> None:
        self.stopwords_path = stopwords_path
        self._stopwords = self._load_stopwords(stopwords_path)

    @staticmethod
    def _load_stopwords(path: Path) -> set[str]:
        words: set[str] = set()
        for line in path.read_text(encoding="utf-8").splitlines():
            word = line.strip().casefold()
            if word and not word.startswith("#"):
                words.add(word)
        return words

    def tokenize(self, text: str) -> list[Token]:
        tokens: list[Token] = []
        for word, start, end in jieba.tokenize(text, mode="default"):
            normalized = word.casefold()
            if not normalized.strip() or normalized in self._stopwords:
                continue
            if not any(character.isalnum() for character in normalized):
                continue
            tokens.append(Token(normalized, start, end))
        return tokens
