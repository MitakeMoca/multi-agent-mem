from __future__ import annotations

from dataclasses import dataclass, field
import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Iterable

from .vectors import cosine, embed_text, pack_vector, unpack_vector
from .logging import log, DEBUG

__all__ = ["MemoryRecord", "SharedMemory"]

@dataclass
class MemoryRecord:
    memory_id: str
    source_agent: str
    created_at: str
    topic: str
    summary: str
    tags: list[str]
    evidence: str
    strategy: str
    score: float = 0.0
    memory_type: str = "procedural"
    version: str = "1"
    status: str = "active"
    use_count: int = 0
    last_hit_at: str = ""
    confidence: float = 0.0
    parent_memory_id: str = ""
    linked_memory_ids: list[str] = field(default_factory=list)
    link_type: str = ""
    evolution_reason: str = ""

    def to_dict(self, include_score: bool = False) -> dict[str, object]:
        result = {
            "memory_id": self.memory_id,
            "source_agent": self.source_agent,
            "created_at": self.created_at,
            "topic": self.topic,
            "summary": self.summary,
            "tags": self.tags,
            "evidence": self.evidence,
            "strategy": self.strategy,
            "memory_type": self.memory_type,
            "version": self.version,
            "status": self.status,
            "use_count": self.use_count,
            "last_hit_at": self.last_hit_at,
            "confidence": self.confidence,
            "parent_memory_id": self.parent_memory_id,
            "linked_memory_ids": self.linked_memory_ids,
            "link_type": self.link_type,
            "evolution_reason": self.evolution_reason,
        }
        if include_score:
            result["score"] = round(self.score, 4)
        return result


class SharedMemory:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                memory_id TEXT PRIMARY KEY,
                source_agent TEXT NOT NULL,
                created_at TEXT NOT NULL,
                topic TEXT NOT NULL,
                summary TEXT NOT NULL,
                tags_json TEXT NOT NULL,
                evidence TEXT NOT NULL,
                strategy TEXT NOT NULL,
                vector_blob BLOB NOT NULL,
                memory_type TEXT NOT NULL DEFAULT 'procedural',
                version TEXT NOT NULL DEFAULT '1',
                status TEXT NOT NULL DEFAULT 'active',
                use_count INTEGER NOT NULL DEFAULT 0,
                last_hit_at TEXT NOT NULL DEFAULT '',
                confidence REAL NOT NULL DEFAULT 0.0,
                parent_memory_id TEXT NOT NULL DEFAULT '',
                linked_memory_ids_json TEXT NOT NULL DEFAULT '[]',
                link_type TEXT NOT NULL DEFAULT '',
                evolution_reason TEXT NOT NULL DEFAULT ''
            )
            """
        )
        self._ensure_columns()
        self.conn.commit()

    def _ensure_columns(self) -> None:
        existing = {row[1] for row in self.conn.execute("PRAGMA table_info(memories)").fetchall()}
        additions = {
            "memory_type": "TEXT NOT NULL DEFAULT 'procedural'",
            "version": "TEXT NOT NULL DEFAULT '1'",
            "status": "TEXT NOT NULL DEFAULT 'active'",
            "use_count": "INTEGER NOT NULL DEFAULT 0",
            "last_hit_at": "TEXT NOT NULL DEFAULT ''",
            "confidence": "REAL NOT NULL DEFAULT 0.0",
            "parent_memory_id": "TEXT NOT NULL DEFAULT ''",
            "linked_memory_ids_json": "TEXT NOT NULL DEFAULT '[]'",
            "link_type": "TEXT NOT NULL DEFAULT ''",
            "evolution_reason": "TEXT NOT NULL DEFAULT ''",
        }
        for column, ddl in additions.items():
            if column not in existing:
                self.conn.execute(f"ALTER TABLE memories ADD COLUMN {column} {ddl}")

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "SharedMemory":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def clear(self) -> None:
        self.conn.execute("DELETE FROM memories")
        self.conn.commit()

    def add(
        self,
        source_agent: str,
        topic: str,
        summary: str,
        tags: Iterable[str],
        evidence: str,
        strategy: str,
        memory_type: str = "procedural",
        version: str = "1",
        status: str = "active",
        confidence: float = 0.0,
        parent_memory_id: str = "",
        linked_memory_ids: Iterable[str] = (),
        link_type: str = "",
        evolution_reason: str = "",
    ) -> MemoryRecord:
        memory_id = uuid.uuid4().hex[:12]
        created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        tags_list = sorted(set(t.strip().lower() for t in tags if t.strip()))
        linked_ids = _normalize_ids(linked_memory_ids)
        vector = embed_text(" ".join([topic, summary, evidence, strategy, " ".join(tags_list)]))
        self.conn.execute(
            """
            INSERT INTO memories
            (
                memory_id, source_agent, created_at, topic, summary, tags_json, evidence, strategy, vector_blob,
                memory_type, version, status, use_count, last_hit_at, confidence, parent_memory_id,
                linked_memory_ids_json, link_type, evolution_reason
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memory_id,
                source_agent,
                created_at,
                topic,
                summary,
                json.dumps(tags_list, ensure_ascii=False),
                evidence,
                strategy,
                pack_vector(vector),
                memory_type,
                version,
                status,
                0,
                "",
                float(confidence),
                parent_memory_id,
                json.dumps(linked_ids, ensure_ascii=False),
                link_type,
                evolution_reason,
            ),
        )
        self.conn.commit()
        log(f"memory add: id={memory_id}, topic={topic}", DEBUG)
        return MemoryRecord(
            memory_id=memory_id,
            source_agent=source_agent,
            created_at=created_at,
            topic=topic,
            summary=summary,
            tags=tags_list,
            evidence=evidence,
            strategy=strategy,
            memory_type=memory_type,
            version=version,
            status=status,
            confidence=float(confidence),
            parent_memory_id=parent_memory_id,
            linked_memory_ids=linked_ids,
            link_type=link_type,
            evolution_reason=evolution_reason,
        )

    def search(
        self,
        query: str,
        tags: Iterable[str] = (),
        top_k: int = 3,
        min_score: float = 0.15,
    ) -> list[MemoryRecord]:
        query_tags = set(t.strip().lower() for t in tags if t.strip())
        query_vector = embed_text(query)
        rows = self.conn.execute(
            """
            SELECT
                memory_id, source_agent, created_at, topic, summary, tags_json, evidence, strategy, vector_blob,
                memory_type, version, status, use_count, last_hit_at, confidence, parent_memory_id,
                linked_memory_ids_json, link_type, evolution_reason
            FROM memories
            """
        ).fetchall()
        records: list[MemoryRecord] = []
        query_lower = query.lower()
        for row in rows:
            try:
                row_tags = json.loads(row[5])
            except (json.JSONDecodeError, TypeError):
                row_tags = []
            text_blob = " ".join([row[3], row[4], row[6], row[7], " ".join(row_tags)]).lower()
            semantic_score = cosine(query_vector, unpack_vector(row[8]))
            keyword_bonus = 0.12 if any(part in text_blob for part in query_lower.split()) else 0.0
            tag_bonus = 0.18 if query_tags.intersection(row_tags) else 0.0
            score = semantic_score + keyword_bonus + tag_bonus
            if score >= min_score:
                records.append(
                    MemoryRecord(
                        memory_id=row[0],
                        source_agent=row[1],
                        created_at=row[2],
                        topic=row[3],
                        summary=row[4],
                        tags=row_tags,
                        evidence=row[6],
                        strategy=row[7],
                        score=score,
                        memory_type=row[9],
                        version=row[10],
                        status=row[11],
                        use_count=int(row[12] or 0),
                        last_hit_at=row[13] or "",
                        confidence=float(row[14] or 0.0),
                        parent_memory_id=row[15] or "",
                        linked_memory_ids=_load_json_list(row[16]),
                        link_type=row[17] or "",
                        evolution_reason=row[18] or "",
                    )
                )
        records.sort(key=lambda r: r.score, reverse=True)
        result = records[:top_k]
        if result:
            hit_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            self.conn.executemany(
                "UPDATE memories SET use_count = use_count + 1, last_hit_at = ? WHERE memory_id = ?",
                [(hit_at, record.memory_id) for record in result],
            )
            self.conn.commit()
            for record in result:
                record.use_count += 1
                record.last_hit_at = hit_at
        log(f"memory search: query={query!r}, hits={len(result)}", DEBUG)
        return result

    def count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM memories").fetchone()
        return int(row[0])


def _normalize_ids(items: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        memory_id = str(item).strip()
        if memory_id and memory_id not in seen:
            seen.add(memory_id)
            result.append(memory_id)
    return result


def _load_json_list(raw: object) -> list[str]:
    try:
        data = json.loads(str(raw)) if raw else []
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    return [str(item) for item in data if str(item).strip()]
