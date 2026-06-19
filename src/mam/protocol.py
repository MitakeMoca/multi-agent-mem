from __future__ import annotations

from dataclasses import dataclass, field
import json
import hashlib
import time
import uuid
from typing import Any
__all__ = ['now_ms', 'approx_tokens', 'parse_text_payload', 'Capability', 'ProtocolMessage', 'TextMessage', 'Metrics']



def now_ms() -> int:
    return int(time.time() * 1000)


def approx_tokens(text: str) -> int:
    """用稳定近似值估算 token 数，便于无依赖评测。"""
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def parse_text_payload(text: str) -> dict[str, object]:
    """模拟纯文本协作中的长上下文解析成本。

    这里不使用 sleep 或随机数，而是对文本执行确定性的分词、关键词扫描和摘要指纹计算。
    结构化模式可以直接读取字段，纯文本模式则需要把长消息重新解析成可执行线索。
    """
    normalized = "".join(ch.lower() if ch.isalnum() else " " for ch in text)
    words = [word for word in normalized.split() if word]
    keywords = ("agent", "protocol", "memory", "state", "evidence", "task", "结构化", "记忆", "状态")
    counts = {key: normalized.count(key) for key in keywords}
    digest = hashlib.blake2b(text.encode("utf-8"), digest_size=16)
    # 多轮 update 模拟长文本上下文被下游 Agent 反复扫描和抽取线索。
    for word in words:
        digest.update(word.encode("utf-8"))
    return {
        "word_count": len(words),
        "keyword_hits": sum(counts.values()),
        "fingerprint": digest.hexdigest(),
    }


@dataclass(frozen=True)
class Capability:
    name: str
    actions: tuple[str, ...]
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "actions": list(self.actions),
            "description": self.description,
        }


@dataclass
class ProtocolMessage:
    sender: str
    receiver: str
    action: str
    params: dict[str, Any]
    result: dict[str, Any] | None = None
    capability: dict[str, Any] | None = None
    state_ref: str | None = None
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_ms: int = field(default_factory=now_ms)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.message_id,
            "ts": self.created_ms,
            "from": self.sender,
            "to": self.receiver,
            "action": self.action,
            "params": self.params,
            "result": self.result or {},
            "capability": self.capability or {},
            "state_ref": self.state_ref,
        }

    def to_wire(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass
class TextMessage:
    sender: str
    receiver: str
    content: str
    created_ms: int = field(default_factory=now_ms)

    def to_wire(self) -> str:
        return f"[{self.created_ms}] {self.sender} -> {self.receiver}\n{self.content}"


@dataclass
class Metrics:
    message_count: int = 0
    text_chars: int = 0
    estimated_tokens: int = 0
    state_transfers: int = 0
    state_bytes: int = 0
    memory_queries: int = 0
    memory_hits: int = 0
    memory_hit_queries: int = 0
    lifecycle_memory_hits: int = 0
    linked_memory_hits: int = 0
    elapsed_ms: float = 0.0

    def record_text(self, wire: str) -> None:
        self.message_count += 1
        self.text_chars += len(wire)
        self.estimated_tokens += approx_tokens(wire)

    def record_state(self, byte_size: int) -> None:
        self.state_transfers += 1
        self.state_bytes += byte_size

    def merge(self, other: "Metrics") -> None:
        self.message_count += other.message_count
        self.text_chars += other.text_chars
        self.estimated_tokens += other.estimated_tokens
        self.state_transfers += other.state_transfers
        self.state_bytes += other.state_bytes
        self.memory_queries += other.memory_queries
        self.memory_hits += other.memory_hits
        self.memory_hit_queries += other.memory_hit_queries
        self.lifecycle_memory_hits += other.lifecycle_memory_hits
        self.linked_memory_hits += other.linked_memory_hits
        self.elapsed_ms += other.elapsed_ms

    def to_dict(self) -> dict[str, Any]:
        hit_rate = self.memory_hit_queries / self.memory_queries if self.memory_queries else 0.0
        avg_hits = self.memory_hits / self.memory_queries if self.memory_queries else 0.0
        return {
            "message_count": self.message_count,
            "text_chars": self.text_chars,
            "estimated_tokens": self.estimated_tokens,
            "state_transfers": self.state_transfers,
            "state_bytes": self.state_bytes,
            "memory_queries": self.memory_queries,
            "memory_hits": self.memory_hits,
            "memory_hit_queries": self.memory_hit_queries,
            "lifecycle_memory_hits": self.lifecycle_memory_hits,
            "linked_memory_hits": self.linked_memory_hits,
            "memory_hit_rate": round(hit_rate, 4),
            "memory_avg_hits_per_query": round(avg_hits, 4),
            "elapsed_ms": round(self.elapsed_ms, 3),
        }
