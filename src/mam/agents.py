from __future__ import annotations

from dataclasses import dataclass
import json
import math
import statistics
import uuid

from .memory import MemoryRecord, SharedMemory
from .protocol import Capability
from .vectors import StatePacket, embed_text


KNOWLEDGE_BASE: list[dict[str, object]] = [
    {
        "id": "ipc_shared_memory",
        "title": "共享内存适合低延迟状态交换",
        "tags": ["ipc", "state", "shared-memory"],
        "body": "共享内存避免多次文本序列化，适合在同机多 Agent 之间交换 embedding、特征向量和短生命周期状态。",
    },
    {
        "id": "protocol_schema",
        "title": "结构化协议减少重复上下文",
        "tags": ["protocol", "overhead"],
        "body": "将消息拆分为 action、params、result、capability 和 state_ref，可以减少自然语言包装和反复解析。",
    },
    {
        "id": "sqlite_memory",
        "title": "SQLite 适合作业级共享记忆原型",
        "tags": ["memory", "sqlite"],
        "body": "SQLite 部署简单，可保存记忆元数据、证据、策略和向量 blob，适合可复现实验和离线评测。",
    },
    {
        "id": "hash_embedding",
        "title": "哈希向量提供可复现的语义近似",
        "tags": ["embedding", "state"],
        "body": "确定性哈希向量不依赖外部模型，能提供轻量语义相似度检索，便于固定实验结果。",
    },
    {
        "id": "codeact_sandbox",
        "title": "CodeAct 可通过轻量沙箱隔离执行",
        "tags": ["codeact", "sandbox", "tool"],
        "body": "LLM 生成的 Python 代码应在受限环境执行，限制内置函数、运行时间和文件访问，降低工具 Agent 风险。",
    },
    {
        "id": "benchmark_metrics",
        "title": "多 Agent 协作需要同时统计通信、状态和记忆指标",
        "tags": ["benchmark", "metrics"],
        "body": "评测应包含消息次数、字符或 token 开销、状态传递次数与规模、任务耗时、记忆命中率和性能提升。",
    },
]


@dataclass
class Task:
    task_id: str
    group: str
    topic: str
    request: str
    tags: list[str]


@dataclass
class Plan:
    objective: str
    steps: list[str]
    expected_evidence: list[str]


class BaseAgent:
    name = "base"

    def capability(self) -> Capability:
        raise NotImplementedError


class PlannerAgent(BaseAgent):
    name = "planner"

    def capability(self) -> Capability:
        return Capability(
            name=self.name,
            actions=("plan_task", "emit_state"),
            description="拆解任务目标，生成执行步骤，并输出任务语义状态包。",
        )

    def plan(self, task: Task, reused: list[MemoryRecord]) -> tuple[Plan, StatePacket]:
        steps = [
            "识别任务目标和已有记忆",
            "检索相关系统机制证据",
            "执行指标计算或策略比较",
            "生成结论并沉淀共享记忆",
        ]
        if reused:
            steps.insert(1, f"复用 {len(reused)} 条历史记忆避免重复检索")
        evidence = ["protocol_schema", "benchmark_metrics"]
        if "state" in task.tags:
            evidence.append("ipc_shared_memory")
        if "memory" in task.tags:
            evidence.append("sqlite_memory")
        if "codeact" in task.tags:
            evidence.append("codeact_sandbox")
        text = " ".join([task.topic, task.request, " ".join(task.tags), " ".join(r.summary for r in reused)])
        state = StatePacket(uuid.uuid4().hex[:10], task.topic, embed_text(text), self.name)
        return Plan(task.request, steps, evidence), state


class RetrieverAgent(BaseAgent):
    name = "retriever"

    def capability(self) -> Capability:
        return Capability(
            name=self.name,
            actions=("retrieve_knowledge", "retrieve_memory"),
            description="检索静态知识库和共享记忆，返回证据链与历史经验。",
        )

    def retrieve(self, task: Task, state: StatePacket, memory: SharedMemory) -> tuple[list[dict[str, object]], list[MemoryRecord]]:
        scored: list[tuple[float, dict[str, object]]] = []
        query_vec = state.vector
        for item in KNOWLEDGE_BASE:
            hay = " ".join([str(item["title"]), str(item["body"]), " ".join(item["tags"])])
            score = sum(a * b for a, b in zip(query_vec, embed_text(hay)))
            if set(task.tags).intersection(set(item["tags"])):
                score += 0.25
            scored.append((score, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        evidence = [item for score, item in scored[:3] if score > 0]
        memories = memory.search(task.request, task.tags, top_k=3, min_score=0.18)
        return evidence, memories


class ToolAgent(BaseAgent):
    name = "tool"

    def capability(self) -> Capability:
        return Capability(
            name=self.name,
            actions=("compute_metrics", "run_codeact"),
            description="执行轻量计算、指标汇总和受限 CodeAct 风格代码片段。",
        )

    def compute(self, task: Task, plan: Plan, evidence: list[dict[str, object]], memories: list[MemoryRecord]) -> dict[str, object]:
        base_steps = len(plan.steps) + len(evidence)
        reuse_gain = min(0.35, 0.08 * len(memories))
        complexity = 1.0 + math.log2(base_steps + 1) / 8.0
        estimated_latency = round(120.0 * complexity * (1.0 - reuse_gain), 3)
        confidence_values = [0.74 + 0.04 * len(evidence), 0.68 + 0.05 * len(memories), 0.78]
        confidence = round(min(0.98, statistics.mean(confidence_values)), 3)
        return {
            "estimated_latency_ms": estimated_latency,
            "reuse_gain": round(reuse_gain, 3),
            "confidence": confidence,
            "evidence_count": len(evidence),
            "memory_reuse_count": len(memories),
        }

    def run_codeact(self, expression: str) -> object:
        """受限执行入口，用于展示 CodeAct 扩展点。"""
        allowed = {"abs": abs, "min": min, "max": max, "sum": sum, "round": round, "len": len}
        return eval(expression, {"__builtins__": allowed}, {})


class SummarizerAgent(BaseAgent):
    name = "summarizer"

    def capability(self) -> Capability:
        return Capability(
            name=self.name,
            actions=("summarize", "write_memory"),
            description="汇总多 Agent 结果，生成结论并写入共享记忆。",
        )

    def summarize(
        self,
        task: Task,
        plan: Plan,
        evidence: list[dict[str, object]],
        memories: list[MemoryRecord],
        tool_result: dict[str, object],
        memory: SharedMemory,
    ) -> dict[str, object]:
        evidence_titles = [str(item["title"]) for item in evidence]
        reused_ids = [m.memory_id for m in memories]
        summary = (
            f"{task.topic}: 采用{len(plan.steps)}步协作流程，"
            f"命中{len(memories)}条历史记忆，证据包括{'、'.join(evidence_titles[:2])}。"
        )
        strategy = "优先传递 state_ref 和向量状态包，仅在最终总结阶段展开自然语言说明。"
        record = memory.add(
            source_agent=self.name,
            topic=task.topic,
            summary=summary,
            tags=task.tags,
            evidence=json.dumps(evidence_titles, ensure_ascii=False),
            strategy=strategy,
        )
        return {
            "task_id": task.task_id,
            "topic": task.topic,
            "summary": summary,
            "reused_memory_ids": reused_ids,
            "new_memory_id": record.memory_id,
            "tool_result": tool_result,
        }


def build_tasks(rounds: int = 10) -> list[Task]:
    seeds = [
        ("A1", "protocol-memory", "结构化协议压缩", "设计低开销 Agent 协议并比较纯文本通信开销", ["protocol", "overhead"]),
        ("A2", "protocol-memory", "能力发现与协议映射", "复用前序协议经验，补充握手和能力发现机制", ["protocol", "memory"]),
        ("A3", "protocol-memory", "共享记忆元数据", "设计记忆单元字段并支持跨 Agent 复用", ["memory", "sqlite"]),
        ("A4", "protocol-memory", "记忆命中率评估", "复用协议与记忆设计，统计连续任务命中率", ["memory", "benchmark"]),
        ("A5", "protocol-memory", "协议模式最终总结", "综合前序任务生成系统层机制结论", ["protocol", "memory", "benchmark"]),
        ("B1", "state-codeact", "非文本状态传递", "设计 embedding 状态包在 Agent 间的直接传递机制", ["state", "embedding"]),
        ("B2", "state-codeact", "共享内存交换优化", "复用状态包经验，比较共享内存和文本编码路径", ["state", "shared-memory"]),
        ("B3", "state-codeact", "CodeAct 沙箱接口", "设计轻量沙箱执行 Python 代码并回传结构化结果", ["codeact", "sandbox", "tool"]),
        ("B4", "state-codeact", "状态传递评测", "统计状态包传递次数、规模和任务时延", ["state", "benchmark"]),
        ("B5", "state-codeact", "连续任务综合验证", "复用两组历史记忆，生成完整实验结论", ["state", "memory", "benchmark"]),
    ]
    tasks = [Task(*seed) for seed in seeds]
    return tasks[:rounds]
