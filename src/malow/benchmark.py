"""对比实验执行与指标汇总。"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from statistics import mean
from typing import Dict, Iterable, List
import csv
import json
import shutil

from .runtime import MultiAgentRuntime, TaskTrace
from .tasks import build_tasks


def run_benchmark(rounds: int, out_dir: Path) -> Dict[str, object]:
    out_dir.mkdir(parents=True, exist_ok=True)
    for sub in ["text", "structured"]:
        path = out_dir / sub
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)

    traces: List[TaskTrace] = []
    for mode in ["text", "structured"]:
        runtime = MultiAgentRuntime(out_dir / mode / "memory.jsonl", mode=mode)
        for task in build_tasks(rounds):
            traces.append(runtime.run_task(task))

    summary = summarize(traces)
    write_outputs(out_dir, traces, summary)
    return summary


def summarize(traces: Iterable[TaskTrace]) -> Dict[str, object]:
    by_mode: Dict[str, List[Dict[str, object]]] = {}
    for trace in traces:
        by_mode.setdefault(trace.mode, []).append(trace.metrics)

    modes: Dict[str, Dict[str, float]] = {}
    for mode, rows in by_mode.items():
        modes[mode] = {
            "tasks": float(len(rows)),
            "message_count": float(sum(int(r["message_count"]) for r in rows)),
            "text_chars": float(sum(int(r["text_chars"]) for r in rows)),
            "state_transfer_count": float(sum(int(r["state_transfer_count"]) for r in rows)),
            "state_bytes": float(sum(int(r["state_bytes"]) for r in rows)),
            "memory_queries": float(sum(int(r["memory_queries"]) for r in rows)),
            "memory_query_hits": float(sum(int(r["memory_query_hits"]) for r in rows)),
            "memory_hits": float(sum(int(r["memory_hits"]) for r in rows)),
            "memory_eval_count": float(sum(int(r["memory_eval_count"]) for r in rows)),
            "memory_relevant_hits": float(sum(float(r["memory_relevant_hits"]) for r in rows)),
            "progressive_stage_reads": float(sum(int(r["progressive_stage_reads"]) for r in rows)),
            "adaptive_stage_skips": float(sum(int(r["adaptive_stage_skips"]) for r in rows)),
            "adaptive_early_stops": float(sum(int(r["adaptive_early_stops"]) for r in rows)),
            "memory_confidence_sum": float(sum(float(r["memory_confidence_sum"]) for r in rows)),
            "memory_confidence_count": float(sum(int(r["memory_confidence_count"]) for r in rows)),
            "lifecycle_memory_hits": float(sum(int(r.get("lifecycle_memory_hits", 0)) for r in rows)),
            "linked_memory_hits": float(sum(int(r.get("linked_memory_hits", 0)) for r in rows)),
            "processing_cost_ms": float(sum(float(r["processing_cost_ms"]) for r in rows)),
            "elapsed_ms": float(sum(float(r["elapsed_ms"]) for r in rows)),
            "estimated_total_ms": float(sum(float(r["estimated_total_ms"]) for r in rows)),
            "avg_elapsed_ms": float(mean(float(r["elapsed_ms"]) for r in rows)),
            "avg_estimated_total_ms": float(mean(float(r["estimated_total_ms"]) for r in rows)),
        }
        queries = modes[mode]["memory_queries"]
        modes[mode]["memory_hit_rate"] = modes[mode]["memory_query_hits"] / queries if queries else 0.0
        eval_count = modes[mode]["memory_eval_count"]
        modes[mode]["memory_precision_at_k"] = (
            sum(float(r["memory_precision_at_k"]) for r in rows) / eval_count if eval_count else 0.0
        )
        modes[mode]["memory_recall_at_k"] = (
            sum(float(r["memory_recall_at_k"]) for r in rows) / eval_count if eval_count else 0.0
        )
        modes[mode]["memory_mrr"] = sum(float(r["memory_mrr"]) for r in rows) / eval_count if eval_count else 0.0
        modes[mode]["memory_ndcg"] = sum(float(r["memory_ndcg"]) for r in rows) / eval_count if eval_count else 0.0
        confidence_count = modes[mode]["memory_confidence_count"]
        modes[mode]["avg_memory_confidence"] = (
            modes[mode]["memory_confidence_sum"] / confidence_count if confidence_count else 0.0
        )
        stage_reads = modes[mode]["progressive_stage_reads"]
        stage_skips = modes[mode]["adaptive_stage_skips"]
        modes[mode]["adaptive_skip_rate"] = stage_skips / (stage_reads + stage_skips) if stage_reads + stage_skips else 0.0

    text = modes.get("text", {})
    structured = modes.get("structured", {})
    text_chars = float(text.get("text_chars", 0.0))
    struct_chars = float(structured.get("text_chars", 0.0))
    text_time = float(text.get("elapsed_ms", 0.0))
    struct_time = float(structured.get("elapsed_ms", 0.0))
    text_estimated = float(text.get("estimated_total_ms", 0.0))
    struct_estimated = float(structured.get("estimated_total_ms", 0.0))
    comparison = {
        "char_reduction_rate": (text_chars - struct_chars) / text_chars if text_chars else 0.0,
        "wall_time_reduction_rate": (text_time - struct_time) / text_time if text_time else 0.0,
        "estimated_total_time_reduction_rate": (text_estimated - struct_estimated) / text_estimated if text_estimated else 0.0,
        "structured_state_transfers": structured.get("state_transfer_count", 0.0),
        "structured_state_bytes": structured.get("state_bytes", 0.0),
        "memory_hit_rate": structured.get("memory_hit_rate", 0.0),
        "memory_precision_at_k": structured.get("memory_precision_at_k", 0.0),
        "memory_recall_at_k": structured.get("memory_recall_at_k", 0.0),
        "memory_mrr": structured.get("memory_mrr", 0.0),
        "memory_ndcg": structured.get("memory_ndcg", 0.0),
        "progressive_stage_reads": structured.get("progressive_stage_reads", 0.0),
        "adaptive_stage_skips": structured.get("adaptive_stage_skips", 0.0),
        "adaptive_early_stops": structured.get("adaptive_early_stops", 0.0),
        "avg_memory_confidence": structured.get("avg_memory_confidence", 0.0),
        "adaptive_skip_rate": structured.get("adaptive_skip_rate", 0.0),
        "lifecycle_memory_hits": structured.get("lifecycle_memory_hits", 0.0),
        "linked_memory_hits": structured.get("linked_memory_hits", 0.0),
    }
    return {"modes": modes, "comparison": comparison}


def write_outputs(out_dir: Path, traces: List[TaskTrace], summary: Dict[str, object]) -> None:
    with (out_dir / "metrics.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    with (out_dir / "traces.jsonl").open("w", encoding="utf-8") as f:
        for trace in traces:
            f.write(json.dumps(asdict(trace), ensure_ascii=False) + "\n")

    csv_path = out_dir / "metrics.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["metric", "text", "structured", "comparison"])
        modes = summary["modes"]
        comp = summary["comparison"]
        keys = [
            "message_count",
            "text_chars",
            "state_transfer_count",
            "state_bytes",
            "memory_queries",
            "memory_query_hits",
            "memory_hits",
            "memory_hit_rate",
            "memory_eval_count",
            "memory_relevant_hits",
            "memory_precision_at_k",
            "memory_recall_at_k",
            "memory_mrr",
            "memory_ndcg",
            "progressive_stage_reads",
            "adaptive_stage_skips",
            "adaptive_early_stops",
            "avg_memory_confidence",
            "adaptive_skip_rate",
            "lifecycle_memory_hits",
            "linked_memory_hits",
            "processing_cost_ms",
            "elapsed_ms",
            "estimated_total_ms",
            "avg_elapsed_ms",
            "avg_estimated_total_ms",
        ]
        for key in keys:
            writer.writerow([key, modes["text"].get(key, ""), modes["structured"].get(key, ""), ""])
        for key, val in comp.items():
            writer.writerow([key, "", "", val])
