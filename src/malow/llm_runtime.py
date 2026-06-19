"""真实大模型驱动的多 Agent 运行时。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Dict, List
import json

from .agents import ExecutorAgent, PlannerAgent, RetrieverAgent, SummarizerAgent
from .llm import LocalCausalLM
from .memory import SharedMemory, evaluate_labeled_hits
from .state import VectorState, Vectorizer, vector_bytes
from .tasks import Task


@dataclass
class LLMTrace:
    task_id: str
    messages: List[Dict[str, object]] = field(default_factory=list)
    metrics: Dict[str, object] = field(default_factory=dict)


class LLMMultiAgentRuntime:
    """用真实模型执行规划与总结，保留检索和数值执行的结构化分工。"""

    def __init__(self, memory_path: Path, model_path: str) -> None:
        self.vectorizer = Vectorizer(dim=64)
        self.memory = SharedMemory(memory_path, self.vectorizer)
        self.llm = LocalCausalLM(model_path=model_path, device_map="auto", dtype="bfloat16")
        self.planner = PlannerAgent(self.vectorizer)
        self.retriever = RetrieverAgent(self.vectorizer)
        self.executor = ExecutorAgent(self.vectorizer)
        self.summarizer = SummarizerAgent(self.vectorizer)

    def run_task(self, task: Task) -> LLMTrace:
        started = perf_counter()
        trace = LLMTrace(task_id=task.task_id)
        initial_vec = self.vectorizer.encode(task.question + " " + task.topic)
        initial_state = VectorState(
            source_agent="llm_runtime",
            task_id=task.task_id,
            vector=initial_vec,
            bytes_size=vector_bytes(initial_vec),
            description="LLM task semantic state",
        )
        pre_hits = self.memory.progressive_search(task.question, tags=task.tags, vector=initial_state.vector, stages=3, top_k=3)
        pre_hit_units = [item["unit"] for item in pre_hits["hits"]]

        planner_prompt = self._planner_prompt(task, pre_hits["coverage"], pre_hits.get("audit", {}), pre_hit_units)
        planner_out = self.llm.generate_json(
            "你是规划Agent。只输出严格 JSON，不要输出多余解释。",
            planner_prompt,
            max_new_tokens=256,
        )
        plan_data = planner_out["data"] or {
            "memory_group_hint": task.memory_group,
            "expected_memory_groups": task.expected_memory_groups,
            "steps": [
                {"role": "retriever", "goal": "读取相关记忆"},
                {"role": "executor", "goal": "计算结果"},
                {"role": "summarizer", "goal": "生成结论"},
            ],
        }
        trace.messages.append({"role": "planner", "prompt": planner_prompt, "output": planner_out["result"].text, "json": plan_data})

        retrieval = self.retriever.run(task, self.memory, initial_state)
        trace.messages.append(
            {
                "role": "retriever",
                "hits": retrieval.payload.get("memory_hits", []),
                "stage_counts": retrieval.payload.get("progressive_stage_counts", []),
                "memory_audit": retrieval.payload.get("memory_audit", {}),
            }
        )

        execution = self.executor.run(task, list(retrieval.payload.get("evidence", [])), retrieval.state)
        trace.messages.append({"role": "executor", "payload": execution.payload})

        summarizer_prompt = self._summarizer_prompt(task, plan_data, retrieval.payload, execution.payload)
        summary_out = self.llm.generate_json(
            "你是总结Agent。只输出严格 JSON，不要输出多余解释。",
            summarizer_prompt,
            max_new_tokens=256,
        )
        summary_data = summary_out["data"] or {
            "summary": f"{task.topic} 完成分析。"
        }
        unit = self.memory.add(
            source_agent="llm_summarizer",
            task_topic=task.topic,
            summary=str(summary_data.get("summary", "")),
            tags=task.tags,
            evidence=list(retrieval.payload.get("evidence", [])),
            metadata={"task_id": task.task_id, "memory_group": task.memory_group, "mode": "llm"},
        )
        trace.messages.append({"role": "summarizer", "output": summary_out["result"].text, "json": summary_data, "memory_id": unit.memory_id})

        eval_result = evaluate_labeled_hits(
            self._lookup_hits([h["memory_id"] for h in retrieval.payload.get("memory_hits", [])]),
            task.expected_memory_groups,
        )
        metrics = {
            "task_id": task.task_id,
            "elapsed_ms": (perf_counter() - started) * 1000.0,
            "planner_prompt_chars": planner_out["result"].prompt_chars,
            "planner_output_chars": planner_out["result"].output_chars,
            "summary_prompt_chars": summary_out["result"].prompt_chars,
            "summary_output_chars": summary_out["result"].output_chars,
            "memory_precision_at_k": eval_result["precision_at_k"],
            "memory_recall_at_k": eval_result["recall_at_k"],
            "memory_mrr": eval_result["mrr"],
            "memory_ndcg": eval_result["ndcg"],
            "memory_confidence": float(retrieval.payload.get("memory_audit", {}).get("confidence", 0.0)),
            "adaptive_stage_skips": int(retrieval.payload.get("memory_audit", {}).get("stages_skipped", 0)),
            "adaptive_early_stop": bool(retrieval.payload.get("memory_audit", {}).get("early_stop", False)),
            "retrieved_groups": [h["memory_group"] for h in retrieval.payload.get("memory_hits", [])],
            "expected_groups": task.expected_memory_groups,
        }
        trace.metrics = metrics
        self.memory.save()
        return trace

    def _lookup_hits(self, memory_ids: List[str]) -> List[Dict[str, object]]:
        by_id = {unit.memory_id: unit for unit in self.memory.units}
        out: List[Dict[str, object]] = []
        for mid in memory_ids:
            unit = by_id.get(mid)
            if unit:
                out.append({"unit": unit, "score": 1.0})
        return out

    def _planner_prompt(self, task: Task, coverage: Dict[str, float], audit: Dict[str, object], hits: List[object]) -> str:
        snippets = []
        for unit in hits[:3]:
            snippets.append(f"- {unit.memory_id}: {unit.task_topic} | {unit.summary}")
        return (
            f"任务ID: {task.task_id}\n"
            f"任务主题: {task.topic}\n"
            f"任务问题: {task.question}\n"
            f"标签: {','.join(task.tags)}\n"
            f"历史记忆命中摘要:\n" + "\n".join(snippets) + "\n"
            f"当前记忆评估: {json.dumps(coverage, ensure_ascii=False)}\n"
            f"渐进式记忆审计: {json.dumps(audit, ensure_ascii=False)}\n"
            "请输出 JSON，字段包括 memory_group_hint, expected_memory_groups, retrieval_query, steps。"
        )

    def _summarizer_prompt(self, task: Task, plan: Dict[str, object], retrieval: Dict[str, object], execution: Dict[str, object]) -> str:
        return (
            f"任务ID: {task.task_id}\n"
            f"任务主题: {task.topic}\n"
            f"任务问题: {task.question}\n"
            f"计划: {json.dumps(plan, ensure_ascii=False)}\n"
            f"检索: {json.dumps(retrieval, ensure_ascii=False)}\n"
            f"执行: {json.dumps(execution, ensure_ascii=False)}\n"
            "请输出 JSON，字段包括 summary, reuse_note, risk_note, action_items。"
        )
