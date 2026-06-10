from __future__ import annotations

from pathlib import Path
import json
import time
from typing import Any

from .agents import PlannerAgent, RetrieverAgent, SummarizerAgent, Task, ToolAgent
from .memory import SharedMemory
from .protocol import Metrics, ProtocolMessage, TextMessage, parse_text_payload
from .state_exchange import StateExchange


class MultiAgentRuntime:
    def __init__(self, memory_path: str | Path, mode: str):
        if mode not in {"text", "structured"}:
            raise ValueError(f"unknown mode: {mode}")
        self.mode = mode
        self.memory = SharedMemory(memory_path)
        self.state_exchange = StateExchange()
        self.planner = PlannerAgent()
        self.retriever = RetrieverAgent()
        self.tool = ToolAgent()
        self.summarizer = SummarizerAgent()
        self.agents = [self.planner, self.retriever, self.tool, self.summarizer]

    def close(self) -> None:
        self.memory.close()

    def _record_text_wire(self, metrics: Metrics, wire: str) -> None:
        metrics.record_text(wire)
        if self.mode == "text":
            parse_text_payload(wire)

    def handshake(self, metrics: Metrics) -> dict[str, Any]:
        capabilities = {}
        for agent in self.agents:
            cap = agent.capability()
            capabilities[agent.name] = cap.to_dict()
            if self.mode == "structured":
                msg = ProtocolMessage(
                    sender=agent.name,
                    receiver="runtime",
                    action="capability_announce",
                    params={"agent": agent.name},
                    capability=cap.to_dict(),
                )
                self._record_text_wire(metrics, msg.to_wire())
            else:
                text = (
                    f"我是 {agent.name}。我的能力包括 {', '.join(cap.actions)}。"
                    f"能力说明: {cap.description}。请调度器在后续任务中根据这些自然语言能力描述选择我。"
                )
                self._record_text_wire(metrics, TextMessage(agent.name, "runtime", text).to_wire())
        return capabilities

    def run_task(self, task: Task) -> dict[str, Any]:
        metrics = Metrics()
        started = time.perf_counter()
        capabilities = self.handshake(metrics)

        initial_memories = self.memory.search(task.request, task.tags, top_k=2, min_score=0.2)
        metrics.memory_queries += 1
        metrics.memory_hits += len(initial_memories)
        metrics.memory_hit_queries += 1 if initial_memories else 0

        if self.mode == "structured":
            self._record_text_wire(
                metrics,
                ProtocolMessage(
                    "runtime",
                    "planner",
                    "plan_task",
                    {"task_id": task.task_id, "topic": task.topic, "tags": task.tags},
                    capability=capabilities["planner"],
                ).to_wire(),
            )
        else:
            self._record_text_wire(
                metrics,
                TextMessage(
                    "runtime",
                    "planner",
                    self._verbose_context(task, initial_memories, capabilities),
                ).to_wire(),
            )

        plan, state = self.planner.plan(task, initial_memories)
        if self.mode == "structured":
            metrics.record_state(self.state_exchange.publish(state))
            self._record_text_wire(
                metrics,
                ProtocolMessage(
                    "planner",
                    "retriever",
                    "retrieve_knowledge",
                    {"task_id": task.task_id, "state": state.as_payload(), "expected_evidence": plan.expected_evidence},
                    result={"steps": plan.steps},
                    state_ref=state.state_id,
                ).to_wire(),
            )
        else:
            self._record_text_wire(
                metrics,
                TextMessage(
                    "planner",
                    "retriever",
                    "请根据以下完整任务上下文检索资料。\n"
                    + self._verbose_context(task, initial_memories, capabilities)
                    + "\n计划步骤:\n"
                    + "\n".join(plan.steps),
                ).to_wire(),
            )

        transferred_state = self.state_exchange.get(state.state_id) if self.mode == "structured" else state
        evidence, memories = self.retriever.retrieve(task, transferred_state, self.memory)
        metrics.memory_queries += 1
        metrics.memory_hits += len(memories)
        metrics.memory_hit_queries += 1 if memories else 0

        if self.mode == "structured":
            self._record_text_wire(
                metrics,
                ProtocolMessage(
                    "retriever",
                    "tool",
                    "compute_metrics",
                    {
                        "task_id": task.task_id,
                        "evidence_ids": [item["id"] for item in evidence],
                        "memory_ids": [m.memory_id for m in memories],
                    },
                    result={"evidence_count": len(evidence), "memory_reuse_count": len(memories)},
                    state_ref=state.state_id,
                ).to_wire(),
            )
        else:
            evidence_text = json.dumps(evidence, ensure_ascii=False, indent=2)
            memory_text = json.dumps([m.to_dict() for m in memories], ensure_ascii=False, indent=2)
            self._record_text_wire(
                metrics,
                TextMessage(
                    "retriever",
                    "tool",
                    "请阅读下面的检索证据和历史记忆后计算指标。\n"
                    + self._verbose_context(task, memories, capabilities)
                    + "\n证据:\n"
                    + evidence_text
                    + "\n历史记忆:\n"
                    + memory_text,
                ).to_wire(),
            )

        tool_result = self.tool.compute(task, plan, evidence, memories)
        if self.mode == "structured":
            self._record_text_wire(
                metrics,
                ProtocolMessage(
                    "tool",
                    "summarizer",
                    "summarize",
                    {"task_id": task.task_id, "topic": task.topic},
                    result=tool_result,
                    state_ref=state.state_id,
                ).to_wire(),
            )
        else:
            self._record_text_wire(
                metrics,
                TextMessage(
                    "tool",
                    "summarizer",
                    "请基于完整上下文、证据、计划和指标生成总结。\n"
                    + self._verbose_context(task, memories, capabilities)
                    + "\n计划:"
                    + json.dumps(plan.__dict__, ensure_ascii=False)
                    + "\n指标:"
                    + json.dumps(tool_result, ensure_ascii=False),
                ).to_wire(),
            )

        summary = self.summarizer.summarize(task, plan, evidence, memories, tool_result, self.memory)
        if self.mode == "structured":
            self._record_text_wire(
                metrics,
                ProtocolMessage(
                    "summarizer",
                    "runtime",
                    "write_memory",
                    {"task_id": task.task_id},
                    result={"new_memory_id": summary["new_memory_id"], "summary": summary["summary"]},
                    state_ref=state.state_id,
                ).to_wire(),
            )
        else:
            self._record_text_wire(
                metrics,
                TextMessage(
                    "summarizer",
                    "runtime",
                    "任务已完成，以下为自然语言总结和新增记忆。\n"
                    + json.dumps(summary, ensure_ascii=False, indent=2),
                ).to_wire(),
            )

        metrics.elapsed_ms = (time.perf_counter() - started) * 1000
        return {
            "task": task.__dict__,
            "mode": self.mode,
            "summary": summary,
            "metrics": metrics.to_dict(),
        }

    def _verbose_context(self, task: Task, memories: list[Any], capabilities: dict[str, Any]) -> str:
        memory_dump = json.dumps(
            [m.to_dict() if hasattr(m, "to_dict") else str(m) for m in memories],
            ensure_ascii=False,
            indent=2,
        )
        capability_dump = json.dumps(capabilities, ensure_ascii=False, indent=2)
        return (
            f"任务编号: {task.task_id}\n"
            f"任务组: {task.group}\n"
            f"主题: {task.topic}\n"
            f"用户请求: {task.request}\n"
            f"标签: {', '.join(task.tags)}\n"
            f"可用 Agent 能力如下，需要完整阅读后再决定下一步:\n{capability_dump}\n"
            f"已知历史记忆如下，需要逐条阅读并判断是否复用:\n{memory_dump}\n"
            "请保持上下文完整，避免遗漏任何条件。"
        )
