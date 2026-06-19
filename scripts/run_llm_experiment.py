#!/usr/bin/env python3
"""真实大模型多 Agent 实验。"""

from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from malow.llm_runtime import LLMMultiAgentRuntime
from malow.tasks import build_tasks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_path", type=str, required=True)
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--out", type=Path, default=ROOT / "results" / "llm_latest")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    runtime = LLMMultiAgentRuntime(args.out / "memory.jsonl", args.model_path)
    traces = []
    for task in build_tasks(args.rounds):
        traces.append(runtime.run_task(task))
    with (args.out / "metrics.json").open("w", encoding="utf-8") as f:
        json.dump({"traces": [t.metrics for t in traces]}, f, ensure_ascii=False, indent=2)
    with (args.out / "traces.jsonl").open("w", encoding="utf-8") as f:
        for trace in traces:
            f.write(json.dumps({"task_id": trace.task_id, "messages": trace.messages, "metrics": trace.metrics}, ensure_ascii=False) + "\n")
    print(json.dumps({"out": str(args.out), "tasks": len(traces)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
