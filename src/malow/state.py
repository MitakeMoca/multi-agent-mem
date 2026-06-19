"""非文本中间状态表示和交换。"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import blake2b
from math import sqrt
from typing import Iterable, List, Sequence
import re


TOKEN_RE = re.compile(r"[A-Za-z0-9_\u4e00-\u9fff]+")


def tokenize(text: str) -> List[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]


@dataclass
class VectorState:
    """Agent 间直接传递的语义向量状态。"""

    source_agent: str
    task_id: str
    vector: List[float]
    bytes_size: int
    description: str


class Vectorizer:
    """无依赖哈希向量器，用于可复现语义状态生成。"""

    def __init__(self, dim: int = 64) -> None:
        self.dim = dim

    def encode(self, text: str) -> List[float]:
        vec = [0.0] * self.dim
        for tok in tokenize(text):
            digest = blake2b(tok.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "little") % self.dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[bucket] += sign
        return normalize(vec)

    def merge(self, vectors: Iterable[Sequence[float]]) -> List[float]:
        acc = [0.0] * self.dim
        count = 0
        for vec in vectors:
            count += 1
            for i, val in enumerate(vec):
                acc[i] += float(val)
        if count == 0:
            return acc
        return normalize(acc)


def normalize(vec: Sequence[float]) -> List[float]:
    norm = sqrt(sum(v * v for v in vec))
    if norm == 0:
        return [0.0 for _ in vec]
    return [float(v) / norm for v in vec]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b:
        return 0.0
    return sum(float(x) * float(y) for x, y in zip(a, b))


def vector_bytes(vec: Sequence[float]) -> int:
    """按 float32 估算非文本状态传输规模。"""

    return len(vec) * 4
