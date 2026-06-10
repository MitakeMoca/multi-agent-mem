from __future__ import annotations

from dataclasses import dataclass
import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Iterable

from .vectors import cosine, embed_text, pack_vector, unpack_vector


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

    def to_dict(self) -> dict[str, object]:
        return {
            "memory_id": self.memory_id,
            "source_agent": self.source_agent,
            "created_at": self.created_at,
            "topic": self.topic,
            "summary": self.summary,
            "tags": self.tags,
            "evidence": self.evidence,
            "strategy": self.strategy,
            "score": round(self.score, 4),
        }


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
                vector_blob BLOB NOT NULL
            )
            """
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

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
    ) -> MemoryRecord:
        memory_id = uuid.uuid4().hex[:12]
        created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        tags_list = sorted(set(t.strip().lower() for t in tags if t.strip()))
        vector = embed_text(" ".join([topic, summary, evidence, strategy, " ".join(tags_list)]))
        self.conn.execute(
            """
            INSERT INTO memories
            (memory_id, source_agent, created_at, topic, summary, tags_json, evidence, strategy, vector_blob)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ),
        )
        self.conn.commit()
        return MemoryRecord(memory_id, source_agent, created_at, topic, summary, tags_list, evidence, strategy)

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
            SELECT memory_id, source_agent, created_at, topic, summary, tags_json, evidence, strategy, vector_blob
            FROM memories
            """
        ).fetchall()
        records: list[MemoryRecord] = []
        query_lower = query.lower()
        for row in rows:
            row_tags = json.loads(row[5])
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
                    )
                )
        records.sort(key=lambda r: r.score, reverse=True)
        return records[:top_k]

    def count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) FROM memories").fetchone()
        return int(row[0])
