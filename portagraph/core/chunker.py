"""Нарезка файла на фрагменты для поиска.

Если известны границы символов (классов, функций), фрагменты режутся по ним;
иначе — окнами фиксированного размера с перекрытием, чтобы контекст на стыке
не терялся. Номера строк сохраняются для ссылок «файл:строки».
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SymbolSpan:
    name: str
    kind: str
    start_line: int
    end_line: int


@dataclass(frozen=True)
class Chunk:
    start_line: int
    end_line: int
    symbol: str | None
    content: str


class CodeChunker:
    def __init__(self, window: int = 60, overlap: int = 10):
        if window < 5:
            raise ValueError("Окно должно быть не меньше 5 строк")
        if not 0 <= overlap < window:
            raise ValueError("Перекрытие должно быть в диапазоне [0, окно)")
        self.window, self.overlap = window, overlap

    def chunk(self, content: str, symbols: list[SymbolSpan] | None = None) -> list[Chunk]:
        lines = content.split("\n")
        if symbols:
            out: list[Chunk] = []
            covered = [False] * (len(lines) + 2)
            # только символы верхнего уровня: вложенные уже входят в родителя
            top = [s for s in symbols if not any(o is not s and o.start_line <= s.start_line and s.end_line <= o.end_line
                                                 and (o.end_line - o.start_line) > (s.end_line - s.start_line) for o in symbols)]
            for s in sorted(top, key=lambda s: s.start_line):
                a, b = max(1, s.start_line), min(len(lines), s.end_line)
                if a > b:
                    continue
                out.extend(self._window(lines, a, b, s.name))
                for i in range(a, b + 1):
                    covered[i] = True
            # заголовок файла (импорты, конфигурация) тоже ищется
            first = next((i for i in range(1, len(lines) + 1) if covered[i]), None)
            if first and first > 3:
                out[:0] = self._window(lines, 1, first - 1, None)
            return out or self._window(lines, 1, len(lines), None)
        return self._window(lines, 1, len(lines), None)

    def _window(self, lines: list[str], a: int, b: int, symbol: str | None) -> list[Chunk]:
        out, start = [], a
        while start <= b:
            end = min(b, start + self.window - 1)
            out.append(Chunk(start, end, symbol, "\n".join(lines[start - 1:end])))
            if end == b:
                break
            start = end - self.overlap + 1
        return out
