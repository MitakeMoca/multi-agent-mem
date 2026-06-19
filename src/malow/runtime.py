"""多 Agent 运行时与两种协作模式。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Dict, List
import json

from .agents import ExecutorAgent, PlannerAgent, RetrieverAgent, SummarizerAgent, protocol_message
from .memory import SharedMemory, evaluate_labeled_hits
from .protocol import ProtocolMessage, text_message, text_size_chars
from .state import VectorState, Vectorizer, vector_bytes
from .tasks import Task


AGENT_CODE = {
    "runtime": "rt",
    "planner": "pl",
    "retriever": "rv",
    "executor": "ex",
    "summarizer": "su",
}

ACTION_CODE = {
    "handshake": "hs",
    "plan_task": "pt",
    "retrieve_evidence": "re",
    "calculate_gain": "cg",
    "summarize": "sz",
}


@dataclass
class RuntimeMetrics:
    mode: str
    task_id: str
    message_count: int = 0
    text_chars: int = 0
    state_transfer_count: int = 0
    state_bytes: int = 0
    memory_queries: int = 0
    memory_query_hits: int = 0
    memory_hits: int = 0
    memory_eval_count: int = 0
    memory_relevant_hits: float = 0.0
    memory_precision_at_k: float = 0.0
    memory_recall_at_k: float = 0.0
    memory_mrr: float = 0.0
    memory_ndcg: float = 0.0
    progressive_stage_reads: int = 0
    adaptive_stage_skips: int = 0
    adaptive_early_stops: int = 0
    memory_confidence_sum: float = 0.0
    memory_confidence_count: int = 0
    lifecycle_memory_hits: int = 0
    linked_memory_hits: int = 0
    processing_cost_ms: float = 0.0
    elapsed_ms: float = 0.0
    estimated_total_ms: float = 0.0
    summary: str = ""


@dataclass
class TaskTrace:
    task_id: str
    mode: str
    messages: List[Dict[str, object]] = field(default_factory=list)
    states: List[Dict[str, object]] = field(default_factory=list)
    metrics: Dict[str, object] = field(default_factory=dict)


class MultiAgentRuntime:
    """统一调度多 Agent，并记录通信与状态交换指标。"""

    def __init__(self, memory_path: Path, mode: str) -> None:
        self.vectorizer = Vectorizer(dim=64)
        self.memory = SharedMemory(memory_path, self.vectorizer)
        self.mode = mode
        self.planner = PlannerAgent(self.vectorizer)
        self.retriever = RetrieverAgent(self.vectorizer)
        self.executor = ExecutorAgent(self.vectorizer)
        self.summarizer = SummarizerAgent(self.vectorizer)

    def run_task(self, task: Task) -> TaskTrace:
        started = perf_counter()
        metrics = RuntimeMetrics(mode=self.mode, task_id=task.task_id)
        trace = TaskTrace(task_id=task.task_id, mode=self.mode)

        initial_state = VectorState(
            source_agent="runtime",
            task_id=task.task_id,
            vector=self.vectorizer.encode(task.question + " " + task.topic),
            bytes_size=vector_bytes(self.vectorizer.encode(task.question)),
            description="task semantic vector",
        )

        pre_hits = self.memory.search(task.question, tags=task.tags, vector=initial_state.vector, top_k=3)
        metrics.memory_queries += 1
        metrics.memory_query_hits += 1 if pre_hits else 0
        metrics.memory_hits += len(pre_hits)
        self._record_memory_metadata(metrics, pre_hits)
        self._record_memory_eval(metrics, pre_hits, task.expected_memory_groups)

        if self.mode == "structured":
            self._record_protocol(
                trace,
                metrics,
                ProtocolMessage(
                    sender="runtime",
                    receiver="planner",
                    action="handshake",
                    params={"task_id": task.task_id},
                    capability={"agent": "planner", "actions": self.planner.actions},
                ),
            )
            self._record_state(trace, metrics, initial_state)
        else:
            self._record_text(
                trace,
                metrics,
                "runtime",
                "planner",
                (
                    f"请你作为 PlannerAgent 阅读完整任务并规划执行。任务主题是{task.topic}，"
                    f"任务问题是{task.question}。请包含检索、执行、总结、记忆复用等所有步骤，"
                    f"并用自然语言说明每一步输入输出。"
                ),
            )

        plan = self.planner.run(task, pre_hits)
        self._record_agent_output(trace, metrics, "planner", "retriever", "plan_task", task, plan)

        retrieval = self.retriever.run(task, self.memory, plan.state)
        metrics.memory_queries += 1
        retrieval_hit_count = len(retrieval.payload.get("memory_hits", []))
        metrics.memory_query_hits += 1 if retrieval_hit_count else 0
        metrics.memory_hits += retrieval_hit_count
        metrics.progressive_stage_reads += len(retrieval.payload.get("progressive_stage_counts", []))
        self._record_memory_audit(metrics, retrieval.payload.get("memory_audit", {}))
        retrieval_eval_hits = self._lookup_memory_hits(retrieval.payload.get("memory_hits", []))
        self._record_memory_metadata(metrics, retrieval_eval_hits)
        self._record_memory_eval(metrics, retrieval_eval_hits, task.expected_memory_groups)
        self._record_agent_output(trace, metrics, "retriever", "executor", "retrieve_evidence", task, retrieval)

        execution = self.executor.run(task, list(retrieval.payload.get("evidence", [])), retrieval.state)
        self._record_agent_output(trace, metrics, "executor", "summarizer", "calculate_gain", task, execution)

        summary = self.summarizer.run(task, plan.payload, retrieval.payload, execution.payload, self.memory)
        self._record_agent_output(trace, metrics, "summarizer", "runtime", "summarize", task, summary)

        metrics.elapsed_ms = (perf_counter() - started) * 1000.0
        metrics.estimated_total_ms = metrics.elapsed_ms + metrics.processing_cost_ms
        metrics.summary = str(summary.payload["summary"])
        trace.metrics = asdict(metrics)
        self.memory.save()
        return trace

    def _lookup_memory_hits(self, compact_hits: object) -> List[Dict[str, object]]:
        out: List[Dict[str, object]] = []
        if not isinstance(compact_hits, list):
            return out
        by_id = {unit.memory_id: unit for unit in self.memory.units}
        for item in compact_hits:
            if not isinstance(item, dict):
                continue
            mid = str(item.get("memory_id", ""))
            unit = by_id.get(mid)
            if unit:
                out.append({"unit": unit, "score": float(item.get("score", 0.0))})
        return out

    def _record_memory_eval(self, metrics: RuntimeMetrics, hits: List[Dict[str, object]], expected_groups: List[str]) -> None:
        eval_result = evaluate_labeled_hits(hits, expected_groups)
        if not eval_result["evaluated"]:
            return
        metrics.memory_eval_count += 1
        metrics.memory_relevant_hits += eval_result["relevant_hits"]
        metrics.memory_precision_at_k += eval_result["precision_at_k"]
        metrics.memory_recall_at_k += eval_result["recall_at_k"]
        metrics.memory_mrr += eval_result["mrr"]
        metrics.memory_ndcg += eval_result["ndcg"]

    def _record_memory_metadata(self, metrics: RuntimeMetrics, hits: List[Dict[str, object]]) -> None:
        for item in hits:
            unit = item.get("unit")
            metadata = getattr(unit, "metadata", {}) if unit is not None else {}
            if not isinstance(metadata, dict):
                continue
            if metadata.get("memory_type") and metadata.get("status") and metadata.get("version"):
                metrics.lifecycle_memory_hits += 1
            if metadata.get("parent_memory_id") or metadata.get("linked_memory_ids"):
                metrics.linked_memory_hits += 1

    def _record_agent_output(self, trace: TaskTrace, metrics: RuntimeMetrics, sender: str, receiver: str, action: str, task: Task, result) -> None:
        if self.mode == "structured":
            msg = protocol_message(
                sender=sender,
                receiver=receiver,
                action=action,
                params={"task_id": task.task_id},
                result=self._compact_result(action, result.payload),
            )
            self._record_protocol(trace, metrics, msg)
            self._record_state(trace, metrics, result.state)
        else:
            self._record_text(trace, metrics, sender, receiver, result.text_detail)

    def _record_protocol(self, trace: TaskTrace, metrics: RuntimeMetrics, msg: ProtocolMessage) -> None:
        metrics.message_count += 1
        size = self._protocol_wire_size(msg)
        metrics.text_chars += size
        metrics.processing_cost_ms += 0.25 + size * 0.003
        trace.messages.append({"type": "protocol", "payload": json.loads(msg.to_json())})

    def _record_text(self, trace: TaskTrace, metrics: RuntimeMetrics, sender: str, receiver: str, content: str) -> None:
        msg = text_message(sender, receiver, content)
        metrics.message_count += 1
        size = text_size_chars(msg)
        metrics.text_chars += size
        metrics.processing_cost_ms += 0.70 + size * 0.012
        trace.messages.append({"type": "text", "payload": msg})

    def _record_state(self, trace: TaskTrace, metrics: RuntimeMetrics, state: VectorState) -> None:
        metrics.state_transfer_count += 1
        metrics.state_bytes += state.bytes_size
        metrics.processing_cost_ms += 0.15 + state.bytes_size * 0.0002
        trace.states.append(asdict(state))

    def _compact_result(self, action: str, payload: Dict[str, object]) -> Dict[str, object]:
        """结构化模式只传递紧凑结果和引用，详细证据由共享状态/记忆承载。"""

        if action == "plan_task":
            return {
                "step_count": len(payload.get("steps", [])),
                "reuse_hint": bool(payload.get("reuse_hint", False)),
                "agents": payload.get("required_agents", []),
            }
        if action == "retrieve_evidence":
            hits = payload.get("memory_hits", [])
            return {
                "evidence_count": len(payload.get("evidence", [])),
                "memory_ids": [h.get("memory_id") for h in hits],
                "top_score": hits[0].get("score") if hits else 0.0,
                "stage_reads": len(payload.get("progressive_stage_counts", [])),
                "confidence": float(payload.get("memory_audit", {}).get("confidence", 0.0)),
                "early_stop": bool(payload.get("memory_audit", {}).get("early_stop", False)),
                "stage_skips": int(payload.get("memory_audit", {}).get("stages_skipped", 0)),
            }
        if action == "calculate_gain":
            return {
                "saved_time": payload.get("saved_time"),
                "speedup": payload.get("speedup"),
                "reduce_ratio": payload.get("reduce_ratio"),
            }
        if action == "summarize":
            return {
                "memory_id": payload.get("memory_id"),
                "memory_hits": payload.get("memory_hits"),
                "summary_len": len(str(payload.get("summary", ""))),
            }
        return dict(payload)

    def _protocol_wire_size(self, msg: ProtocolMessage) -> int:
        """紧凑协议线缆大小，模拟二进制/短码字段编码后的字符开销。"""

        wire: Dict[str, object] = {
            "s": AGENT_CODE.get(msg.sender, msg.sender),
            "r": AGENT_CODE.get(msg.receiver, msg.receiver),
            "a": ACTION_CODE.get(msg.action, msg.action),
        }
        if msg.params:
            wire["p"] = {"tid": msg.params.get("task_id")}
        if msg.result:
            wire["o"] = self._shorten_result(msg.result)
        if msg.capability:
            wire["c"] = {
                "ag": AGENT_CODE.get(str(msg.capability.get("agent", "")), msg.capability.get("agent", "")),
                "ac": [ACTION_CODE.get(str(a), str(a)[:3]) for a in msg.capability.get("actions", [])],
            }
        return len(json.dumps(wire, ensure_ascii=False, separators=(",", ":")))

    def _shorten_result(self, result: Dict[str, object]) -> Dict[str, object]:
        key_map = {
            "step_count": "sc",
            "reuse_hint": "rh",
            "agents": "ag",
            "evidence_count": "ec",
            "memory_ids": "mi",
            "top_score": "ts",
            "saved_time": "sv",
            "speedup": "sp",
            "reduce_ratio": "rr",
            "memory_id": "mid",
            "memory_hits": "mh",
            "summary_len": "sl",
            "stage_reads": "sr",
            "confidence": "cf",
            "early_stop": "es",
            "stage_skips": "ss",
        }
        out: Dict[str, object] = {}
        for key, value in result.items():
            short_key = key_map.get(key, key[:3])
            if key == "agents":
                out[short_key] = [AGENT_CODE.get(str(v), str(v)[:2]) for v in value]  # type: ignore[arg-type]
            elif key in {"memory_ids"}:
                out[short_key] = [str(v)[:6] for v in value]  # type: ignore[arg-type]
            elif isinstance(value, float):
                out[short_key] = round(value, 4)
            else:
                out[short_key] = value
        return out

    def _record_memory_audit(self, metrics: RuntimeMetrics, audit: object) -> None:
        if not isinstance(audit, dict):
            return
        metrics.adaptive_stage_skips += int(audit.get("stages_skipped", 0))
        metrics.adaptive_early_stops += 1 if audit.get("early_stop", False) else 0
        metrics.memory_confidence_sum += float(audit.get("confidence", 0.0))
        metrics.memory_confidence_count += 1
