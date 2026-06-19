from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import struct


DEFAULT_DIM = 64
__all__ = ['DEFAULT_DIM', 'embed_text', 'cosine', 'pack_vector', 'unpack_vector', 'StatePacket']



def _tokens(text: str) -> list[str]:
    normalized = "".join(ch.lower() if ch.isalnum() else " " for ch in text)
    parts = [p for p in normalized.split() if p]
    if not parts:
        return []
    grams: list[str] = []
    for part in parts:
        grams.append(part)
        if len(part) >= 3:
            grams.extend(part[i : i + 3] for i in range(len(part) - 2))
    return grams


def embed_text(text: str, dim: int = DEFAULT_DIM) -> list[float]:
    """确定性哈希向量，避免外部模型依赖。"""
    vector = [0.0] * dim
    for token in _tokens(text):
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        raw = int.from_bytes(digest, "big")
        index = raw % dim
        sign = 1.0 if (raw >> 8) & 1 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0:
        return vector
    return [v / norm for v in vector]


def cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def pack_vector(vector: list[float]) -> bytes:
    return struct.pack(f"!{len(vector)}f", *vector)


def unpack_vector(blob: bytes) -> list[float]:
    if not blob:
        return []
    count = len(blob) // 4
    return list(struct.unpack(f"!{count}f", blob))


@dataclass(frozen=True)
class StatePacket:
    state_id: str
    topic: str
    vector: list[float]
    origin_agent: str

    @property
    def byte_size(self) -> int:
        return len(pack_vector(self.vector))

    def as_payload(self) -> dict[str, object]:
        return {
            "state_id": self.state_id,
            "topic": self.topic,
            "dim": len(self.vector),
            "bytes": self.byte_size,
            "origin_agent": self.origin_agent,
        }
