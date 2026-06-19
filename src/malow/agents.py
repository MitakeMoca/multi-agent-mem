"""多 Agent 角色实现。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from .memory import SharedMemory
from .protocol import Capability, ProtocolMessage
from .state import VectorState, Vectorizer, vector_bytes
from .tasks import Task


@dataclass
class AgentResult:
    payload: Dict[str, object]
    state: VectorState
    text_detail: str


class BaseAgent:
    name = "base"
    actions: List[str] = []

    def __init__(self, vectorizer: Vectorizer) -> None:
        self.vectorizer = vectorizer

    def capability(self) -> Capability:
        return Capability(
            agent=self.name,
            actions=self.actions,
            input_schema={"task": "Task", "memory_hits": "list"},
            output_schema={"payload": "dict", "state": "VectorState"},
        )

    def make_state(self, task: Task, text: str) -> VectorState:
        vec = self.vectorizer.encode(text)
        return VectorState(
            source_agent=self.name,
            task_id=task.task_id,
            vector=vec,
            bytes_size=vector_bytes(vec),
            description=f"{self.name} semantic state for {task.task_id}",
        )


class PlannerAgent(BaseAgent):
    name = "planner"
    actions = ["handshake", "plan_task", "map_protocol"]

    def run(self, task: Task, memory_hits: List[Dict[str, object]]) -> AgentResult:
        reuse_hint = len(memory_hits) > 0
        steps = ["检索领域知识", "执行收益计算", "汇总结论", "写入共享记忆"]
        if reuse_hint:
            steps.insert(0, "复用历史记忆")
        text = f"任务{task.task_id}:{task.question};步骤:{'|'.join(steps)};复用={reuse_hint}"
        return AgentResult(
            payload={"steps": steps, "reuse_hint": reuse_hint, "required_agents": ["retriever", "executor", "summarizer"]},
            state=self.make_state(task, text),
            text_detail=(
                f"PlannerAgent 接收到任务：{task.question}。它需要先判断是否存在历史经验，"
                f"再安排检索、执行和总结三个阶段。规划步骤为：{'、'.join(steps)}。"
            ),
        )


class RetrieverAgent(BaseAgent):
    name = "retriever"
    actions = ["search_memory", "retrieve_evidence"]

    def run(self, task: Task, memory: SharedMemory, state: VectorState) -> AgentResult:
        progressive = memory.progressive_search(task.question, tags=task.tags, vector=state.vector, stages=3, top_k=3)
        hits = progressive["hits"]
        evidence = [
            f"{task.topic} 基线耗时 {task.facts.get('baseline_time', 0):.1f}s，优化后 {task.facts.get('optimized_time', 0):.1f}s。",
            f"任务标签：{','.join(task.tags)}。",
        ]
        reused = []
        for hit in hits:
            unit = hit["unit"]
            reused.append({
                "memory_id": unit.memory_id,
                "score": round(float(hit["score"]), 4),
                "stage": str(hit.get("stage", "mixed")),
                "memory_group": unit.metadata.get("memory_group", ""),
                "summary": unit.summary,
            })
            evidence.append(f"复用记忆 {unit.memory_id}: {unit.summary}")
        stage_counts = [len(stage_hits) for stage_hits in progressive["stages"]]
        audit = progressive.get("audit", {})
        text = f"{task.question};证据:{' '.join(evidence)}"
        return AgentResult(
            payload={
                "evidence": evidence,
                "memory_hits": reused,
                "progressive_stage_counts": stage_counts,
                "memory_audit": audit,
            },
            state=self.make_state(task, text),
            text_detail=(
                f"RetrieverAgent 围绕任务检索事实和共享记忆。检索到 {len(reused)} 条可复用记忆，"
                f"渐进式读取阶段命中数为 {stage_counts}，置信度为 {audit.get('confidence', 0.0)}，"
                f"是否早停为 {audit.get('early_stop', False)}，证据包括：{'；'.join(evidence)}"
            ),
        )


class ExecutorAgent(BaseAgent):
    name = "executor"
    actions = ["calculate_gain", "run_tool"]

    def run(self, task: Task, evidence: List[str], state: VectorState) -> AgentResult:
        baseline = float(task.facts.get("baseline_time", 0.0))
        optimized = float(task.facts.get("optimized_time", baseline))
        saved = max(0.0, baseline - optimized)
        speedup = baseline / optimized if optimized else 0.0
        reduce_ratio = saved / baseline if baseline else 0.0
        text = f"{task.topic};baseline={baseline};optimized={optimized};saved={saved};speedup={speedup};evidence={evidence}"
        return AgentResult(
            payload={
                "baseline_time": baseline,
                "optimized_time": optimized,
                "saved_time": saved,
                "speedup": round(speedup, 4),
                "reduce_ratio": round(reduce_ratio, 4),
            },
            state=self.make_state(task, text),
            text_detail=(
                f"ExecutorAgent 使用工具计算：基线耗时 {baseline:.1f}s，优化后 {optimized:.1f}s，"
                f"节省 {saved:.1f}s，速度提升 {speedup:.2f} 倍。"
            ),
        )


class SummarizerAgent(BaseAgent):
    name = "summarizer"
    actions = ["summarize", "write_memory"]

    def run(
        self,
        task: Task,
        plan: Dict[str, object],
        retrieval: Dict[str, object],
        execution: Dict[str, object],
        memory: SharedMemory,
    ) -> AgentResult:
        hits = retrieval.get("memory_hits", [])
        reduce_ratio = float(execution.get("reduce_ratio", 0.0))
        audit = retrieval.get("memory_audit", {})
        parent_memory_id = ""
        linked_memory_ids = []
        if isinstance(hits, list):
            linked_memory_ids = [str(hit.get("memory_id", "")) for hit in hits if isinstance(hit, dict) and hit.get("memory_id")]
            parent_memory_id = linked_memory_ids[0] if linked_memory_ids else ""
        summary = (
            f"{task.topic}完成协作分析，优化后耗时降低 {reduce_ratio * 100:.1f}%，"
            f"命中历史记忆 {len(hits)} 条。"
        )
        evidence = list(retrieval.get("evidence", []))
        unit = memory.add(
            source_agent=self.name,
            task_topic=task.topic,
            summary=summary,
            tags=task.tags,
            evidence=evidence,
            metadata={
                "task_id": task.task_id,
                "reuse_count": str(len(hits)),
                "memory_group": task.memory_group,
                "memory_type": "procedural",
                "status": "active",
                "version": "1",
                "confidence": str(audit.get("confidence", "")) if isinstance(audit, dict) else "",
                "parent_memory_id": parent_memory_id,
                "linked_memory_ids": ",".join(linked_memory_ids),
                "link_type": "reuse_chain" if parent_memory_id else "new_group",
                "evolution_reason": "reuse_summary" if parent_memory_id else "initial_summary",
            },
        )
        text = f"{summary};memory={unit.memory_id};plan={plan};execution={execution}"
        return AgentResult(
            payload={"summary": summary, "memory_id": unit.memory_id, "memory_hits": len(hits)},
            state=self.make_state(task, text),
            text_detail=(
                f"SummarizerAgent 汇总任务结论：{summary} 同时将摘要、证据链和策略写入共享记忆，"
                f"新记忆 ID 为 {unit.memory_id}。"
            ),
        )


def protocol_message(sender: str, receiver: str, action: str, params: Dict[str, object], result: Dict[str, object]) -> ProtocolMessage:
    return ProtocolMessage(sender=sender, receiver=receiver, action=action, params=params, result=result)
