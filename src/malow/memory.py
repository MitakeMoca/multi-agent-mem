"""共享记忆存储、检索和复用。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from math import log2
from pathlib import Path
from typing import Dict, Iterable, List, Optional
import json
import uuid

from .state import Vectorizer, cosine, tokenize


@dataclass
class MemoryUnit:
    """统一记忆单元。"""

    memory_id: str
    source_agent: str
    created_at: str
    task_topic: str
    summary: str
    tags: List[str]
    evidence: List[str]
    vector: List[float]
    metadata: Dict[str, str] = field(default_factory=dict)


class SharedMemory:
    """JSONL 持久化共享记忆。"""

    def __init__(self, path: Path, vectorizer: Optional[Vectorizer] = None) -> None:
        self.path = path
        self.vectorizer = vectorizer or Vectorizer()
        self.units: List[MemoryUnit] = []
        if path.exists():
            self.load()

    def load(self) -> None:
        self.units = []
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                unit = MemoryUnit(**json.loads(line))
                self._normalize_metadata(unit)
                self.units.append(unit)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            for unit in self.units:
                f.write(json.dumps(asdict(unit), ensure_ascii=False) + "\n")

    def add(
        self,
        source_agent: str,
        task_topic: str,
        summary: str,
        tags: Iterable[str],
        evidence: Iterable[str],
        metadata: Optional[Dict[str, str]] = None,
    ) -> MemoryUnit:
        tag_list = sorted(set(tags))
        evidence_list = list(evidence)
        text = " ".join([task_topic, summary, " ".join(tag_list), " ".join(evidence_list)])
        enriched_metadata = self._enrich_metadata(metadata or {}, tag_list)
        unit = MemoryUnit(
            memory_id=uuid.uuid4().hex[:12],
            source_agent=source_agent,
            created_at=datetime.now(timezone.utc).isoformat(),
            task_topic=task_topic,
            summary=summary,
            tags=tag_list,
            evidence=evidence_list,
            vector=self.vectorizer.encode(text),
            metadata=enriched_metadata,
        )
        self.units.append(unit)
        return unit

    def _normalize_metadata(self, unit: MemoryUnit) -> None:
        """为旧记忆补齐生命周期和类型字段，保证向后兼容。"""

        defaults = {
            "memory_type": "procedural",
            "version": "1",
            "status": "active",
            "use_count": "0",
            "last_hit_at": "",
            "confidence": "",
            "parent_memory_id": "",
            "linked_memory_ids": "",
            "link_type": "",
            "evolution_reason": "",
        }
        for key, value in defaults.items():
            unit.metadata.setdefault(key, value)

    def _enrich_metadata(self, metadata: Dict[str, str], tags: List[str]) -> Dict[str, str]:
        """写入新记忆时补充类型、生命周期和轻量记忆链接。"""

        out = dict(metadata)
        now = datetime.now(timezone.utc).isoformat()
        out.setdefault("memory_type", "procedural")
        out.setdefault("version", "1")
        out.setdefault("status", "active")
        out.setdefault("use_count", "0")
        out.setdefault("last_hit_at", "")
        out.setdefault("confidence", "")

        group = out.get("memory_group", "")
        if not out.get("parent_memory_id") and group:
            parents = [u for u in self.units if u.metadata.get("memory_group") == group and u.metadata.get("status", "active") == "active"]
            if parents:
                out["parent_memory_id"] = parents[-1].memory_id

        linked = set(filter(None, out.get("linked_memory_ids", "").split(",")))
        tag_set = set(tags)
        for unit in self.units:
            if len(linked) >= 3:
                break
            if unit.memory_id == out.get("parent_memory_id"):
                continue
            if tag_set & set(unit.tags):
                linked.add(unit.memory_id)
        out["linked_memory_ids"] = ",".join(sorted(linked))
        out.setdefault("link_type", "same_group" if out.get("parent_memory_id") else "tag_overlap")
        out.setdefault("evolution_reason", "new_task_summary")
        return out

    def touch_hits(self, hits: List[Dict[str, object]]) -> None:
        """记录记忆被复用的次数和最近命中时间。"""

        now = datetime.now(timezone.utc).isoformat()
        for item in hits:
            unit = item.get("unit")
            if not isinstance(unit, MemoryUnit):
                continue
            self._normalize_metadata(unit)
            try:
                use_count = int(unit.metadata.get("use_count", "0"))
            except ValueError:
                use_count = 0
            unit.metadata["use_count"] = str(use_count + 1)
            unit.metadata["last_hit_at"] = now

    def search(
        self,
        query: str,
        tags: Optional[Iterable[str]] = None,
        vector: Optional[List[float]] = None,
        top_k: int = 3,
        group_filter: Optional[str] = None,
    ) -> List[Dict[str, object]]:
        query_terms = set(tokenize(query))
        tag_set = set(tags or [])
        query_vec = vector or self.vectorizer.encode(query)
        scored: List[Dict[str, object]] = []
        for unit in self.units:
            if group_filter and unit.metadata.get("memory_group") != group_filter:
                continue
            text_terms = set(tokenize(unit.task_topic + " " + unit.summary + " " + " ".join(unit.tags)))
            keyword_score = len(query_terms & text_terms) / max(1, len(query_terms))
            tag_score = len(tag_set & set(unit.tags)) / max(1, len(tag_set)) if tag_set else 0.0
            semantic_score = cosine(query_vec, unit.vector)
            score = 0.45 * semantic_score + 0.35 * keyword_score + 0.20 * tag_score
            if score > 0:
                scored.append({"score": score, "unit": unit})
        scored.sort(key=lambda x: float(x["score"]), reverse=True)
        result = scored[:top_k]
        self.touch_hits(result)
        return result

    def progressive_search(
        self,
        query: str,
        tags: Optional[Iterable[str]] = None,
        vector: Optional[List[float]] = None,
        stages: int = 3,
        top_k: int = 3,
        group_filter: Optional[str] = None,
        confidence_threshold: float = 0.68,
        min_confident_hits: int = 1,
        adaptive: bool = True,
    ) -> Dict[str, object]:
        """渐进式记忆读取：先关键词，再标签，再语义相似。

        每个阶段结束后都会计算当前命中的置信度。若置信度已经足够高，
        Agent 会提前停止后续读取，形成类似按需查资料的自适应记忆机制。
        """

        query_terms = set(tokenize(query))
        tag_set = set(tags or [])
        query_vec = vector or self.vectorizer.encode(query)
        stage_hits: List[List[Dict[str, object]]] = []
        seen: set[str] = set()
        stage_names = ["keyword", "tag", "semantic"]
        stage_audit: List[Dict[str, object]] = []
        max_stages = max(1, min(stages, len(stage_names)))
        merged: List[Dict[str, object]] = []
        coverage = self.evaluate_hits(query_terms, tag_set, merged)
        confidence = 0.0
        for stage in range(max_stages):
            hits: List[Dict[str, object]] = []
            for unit in self.units:
                if group_filter and unit.metadata.get("memory_group") != group_filter:
                    continue
                if unit.memory_id in seen:
                    continue
                text_terms = set(tokenize(unit.task_topic + " " + unit.summary + " " + " ".join(unit.tags)))
                if stage == 0:
                    score = len(query_terms & text_terms) / max(1, len(query_terms))
                elif stage == 1:
                    score = len(tag_set & set(unit.tags)) / max(1, len(tag_set)) if tag_set else 0.0
                else:
                    score = cosine(query_vec, unit.vector)
                if score > 0:
                    hits.append({"score": score, "unit": unit, "stage": stage_names[min(stage, 2)]})
            hits.sort(key=lambda x: float(x["score"]), reverse=True)
            trimmed = hits[:top_k]
            for item in trimmed:
                seen.add(item["unit"].memory_id)
            stage_hits.append(trimmed)
            merged = self._merge_stage_hits(stage_hits, top_k)
            coverage = self.evaluate_hits(query_terms, tag_set, merged)
            confidence = self._memory_confidence(merged, coverage)
            should_stop = (
                adaptive
                and stage + 1 < max_stages
                and len(merged) >= min_confident_hits
                and confidence >= confidence_threshold
            )
            stage_audit.append(
                {
                    "stage": stage_names[min(stage, 2)],
                    "hit_count": len(trimmed),
                    "best_score": round(float(trimmed[0]["score"]), 4) if trimmed else 0.0,
                    "top_memory_id": trimmed[0]["unit"].memory_id if trimmed else "",
                    "hit_groups": sorted(
                        {
                            str(item["unit"].metadata.get("memory_group", ""))
                            for item in trimmed
                            if item["unit"].metadata.get("memory_group", "")
                        }
                    ),
                    "confidence": round(confidence, 4),
                    "decision": "stop" if should_stop else ("finish" if stage + 1 == max_stages else "continue"),
                }
            )
            if should_stop:
                break
        stages_used = len(stage_hits)
        stages_skipped = max(0, max_stages - stages_used)
        self.touch_hits(merged)
        return {
            "hits": merged,
            "stages": stage_hits,
            "coverage": coverage,
            "audit": {
                "policy": "confidence_gated_progressive_memory",
                "threshold": confidence_threshold,
                "confidence": round(confidence, 4),
                "stages_requested": max_stages,
                "stages_used": stages_used,
                "stages_skipped": stages_skipped,
                "early_stop": stages_skipped > 0,
                "stage_audit": stage_audit,
            },
        }

    def _merge_stage_hits(self, stage_hits: List[List[Dict[str, object]]], top_k: int) -> List[Dict[str, object]]:
        merged: List[Dict[str, object]] = []
        for hits in stage_hits:
            merged.extend(hits)
        merged.sort(key=lambda x: (float(x["score"]), str(x.get("stage", ""))), reverse=True)
        return merged[:top_k]

    def _memory_confidence(self, hits: List[Dict[str, object]], coverage: Dict[str, float]) -> float:
        if not hits:
            return 0.0
        top_score = max(0.0, min(1.0, float(hits[0]["score"])))
        precision = max(0.0, min(1.0, float(coverage.get("precision_at_k", 0.0))))
        mrr = max(0.0, min(1.0, float(coverage.get("mrr", 0.0))))
        stage_diversity = len({str(item.get("stage", "")) for item in hits})
        diversity_bonus = min(0.08, 0.04 * stage_diversity)
        return min(1.0, 0.55 * top_score + 0.25 * precision + 0.20 * mrr + diversity_bonus)

    def evaluate_hits(self, query_terms: set[str], tag_set: set[str], hits: List[Dict[str, object]]) -> Dict[str, float]:
        """对当前命中结果做简单精度/召回/排序质量评估。"""

        if not hits:
            return {"precision_at_k": 0.0, "recall_at_k": 0.0, "mrr": 0.0, "ndcg": 0.0}
        relevance = []
        for item in hits:
            unit = item["unit"]
            text_terms = set(tokenize(unit.task_topic + " " + unit.summary + " " + " ".join(unit.tags)))
            rel = 0
            if query_terms & text_terms:
                rel += 1
            if tag_set & set(unit.tags):
                rel += 1
            relevance.append(rel)
        relevant_hits = sum(1 for r in relevance if r > 0)
        precision = relevant_hits / len(hits)
        recall = relevant_hits / max(1, len(self.units))
        mrr = 0.0
        for idx, rel in enumerate(relevance, start=1):
            if rel > 0:
                mrr = 1.0 / idx
                break
        dcg = 0.0
        idcg = 0.0
        for idx, rel in enumerate(relevance, start=1):
            dcg += (2**rel - 1) / log2(idx + 1)
        ideal = sorted(relevance, reverse=True)
        for idx, rel in enumerate(ideal, start=1):
            idcg += (2**rel - 1) / log2(idx + 1)
        ndcg = dcg / idcg if idcg else 0.0
        return {
            "precision_at_k": precision,
            "recall_at_k": recall,
            "mrr": mrr,
            "ndcg": ndcg,
        }


def evaluate_labeled_hits(hits: List[Dict[str, object]], expected_groups: Iterable[str]) -> Dict[str, float]:
    """用任务标注的期望记忆组评估检索精准度。"""

    expected = set(expected_groups)
    if not expected:
        return {
            "evaluated": 0.0,
            "precision_at_k": 0.0,
            "recall_at_k": 0.0,
            "mrr": 0.0,
            "ndcg": 0.0,
            "relevant_hits": 0.0,
        }
    if not hits:
        return {
            "evaluated": 1.0,
            "precision_at_k": 0.0,
            "recall_at_k": 0.0,
            "mrr": 0.0,
            "ndcg": 0.0,
            "relevant_hits": 0.0,
        }
    relevance: List[int] = []
    hit_groups = set()
    for item in hits:
        unit = item["unit"]
        group = unit.metadata.get("memory_group", "")
        is_relevant = 1 if group in expected else 0
        relevance.append(is_relevant)
        if is_relevant:
            hit_groups.add(group)
    relevant_hits = sum(relevance)
    precision = relevant_hits / len(hits)
    recall = len(hit_groups) / len(expected)
    mrr = 0.0
    for idx, rel in enumerate(relevance, start=1):
        if rel:
            mrr = 1.0 / idx
            break
    dcg = 0.0
    for idx, rel in enumerate(relevance, start=1):
        dcg += rel / log2(idx + 1)
    ideal = sorted(relevance, reverse=True)
    idcg = 0.0
    for idx, rel in enumerate(ideal, start=1):
        idcg += rel / log2(idx + 1)
    ndcg = dcg / idcg if idcg else 0.0
    return {
        "evaluated": 1.0,
        "precision_at_k": precision,
        "recall_at_k": recall,
        "mrr": mrr,
        "ndcg": ndcg,
        "relevant_hits": float(relevant_hits),
    }
