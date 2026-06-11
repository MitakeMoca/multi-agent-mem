from __future__ import annotations

from pathlib import Path
import json
import tempfile
from typing import Any

from .agents import build_tasks
from .org_benchmarks import run_organization_benchmark_suite
from .protocol import Metrics
from .pursuit import run_pursuit_transfer_experiment
from .runtime import MultiAgentRuntime
from .logging import log, INFO, DEBUG

__all__ = ["run_benchmark", "_sum_metrics", "_improvement", "_compare"]


def run_benchmark(rounds: int, output_path: str | Path | None = None) -> dict[str, Any]:
    log(f"benchmark start: rounds={rounds}", INFO)
    tasks = build_tasks(rounds)
    log(f"tasks built: {len(tasks)} tasks", DEBUG)
    with tempfile.TemporaryDirectory(prefix="mam_benchmark_") as tmp:
        text_runtime = MultiAgentRuntime(Path(tmp) / "text.sqlite", "text")
        structured_runtime = MultiAgentRuntime(Path(tmp) / "structured.sqlite", "structured")
        try:
            log("running text mode...", INFO)
            text_results = [text_runtime.run_task(task) for task in tasks]
            log("running structured mode...", INFO)
            structured_results = [structured_runtime.run_task(task) for task in tasks]
        finally:
            text_runtime.close()
            structured_runtime.close()

    text_total = _sum_metrics(text_results)
    structured_total = _sum_metrics(structured_results)
    comparison = _compare(text_total, structured_total)
    log("running pursuit transfer...", INFO)
    pursuit_report = run_pursuit_transfer_experiment()
    log("running org benchmark suite...", INFO)
    organization_suite = run_organization_benchmark_suite(pursuit_report=pursuit_report)
    report = {
        "rounds": len(tasks),
        "task_groups": sorted(set(task.group for task in tasks)),
        "requirements_covered": {
            "agents": ["planner", "retriever", "tool", "summarizer"],
            "structured_protocol": True,
            "text_baseline": True,
            "non_text_state_transfer": True,
            "shared_memory": True,
            "related_task_groups": 2,
            "continuous_rounds": len(tasks),
        },
        "text_total": text_total.to_dict(),
        "structured_total": structured_total.to_dict(),
        "comparison": comparison,
        "pursuit_transfer": pursuit_report,
        "organization_benchmark_suite": organization_suite,
        "structured_task_results": structured_results,
        "text_task_results": text_results,
    }
    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        log(f"report written to {out}", INFO)
    log(f"benchmark done: char_saving={comparison['char_saving_rate']:.2%}, token_saving={comparison['token_saving_rate']:.2%}", INFO)
    return report


def _sum_metrics(results: list[dict[str, Any]]) -> Metrics:
    total = Metrics()
    for item in results:
        metrics = item["metrics"]
        total.message_count += metrics["message_count"]
        total.text_chars += metrics["text_chars"]
        total.estimated_tokens += metrics["estimated_tokens"]
        total.state_transfers += metrics["state_transfers"]
        total.state_bytes += metrics["state_bytes"]
        total.memory_queries += metrics["memory_queries"]
        total.memory_hits += metrics["memory_hits"]
        total.memory_hit_queries += metrics["memory_hit_queries"]
        total.elapsed_ms += metrics["elapsed_ms"]
    return total


def _improvement(baseline: float, optimized: float) -> float:
    if baseline <= 0:
        return 0.0
    return round((baseline - optimized) / baseline, 4)


def _compare(text_total: Metrics, structured_total: Metrics) -> dict[str, Any]:
    return {
        "char_saving_rate": _improvement(text_total.text_chars, structured_total.text_chars),
        "token_saving_rate": _improvement(text_total.estimated_tokens, structured_total.estimated_tokens),
        "latency_saving_rate": _improvement(text_total.elapsed_ms, structured_total.elapsed_ms),
        "memory_hit_rate_delta": round(
            (
                structured_total.memory_hit_queries / structured_total.memory_queries
                if structured_total.memory_queries
                else 0.0
            )
            - (text_total.memory_hit_queries / text_total.memory_queries if text_total.memory_queries else 0.0),
            4,
        ),
        "state_transfer_bytes": structured_total.state_bytes,
    }
