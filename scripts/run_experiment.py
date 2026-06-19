#!/usr/bin/env python3
"""运行多智能体低开销通信对比实验。"""

from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from malow.benchmark import run_benchmark


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=10, help="连续任务轮数")
    parser.add_argument("--out", type=Path, default=ROOT / "results" / "latest", help="输出目录")
    args = parser.parse_args()

    summary = run_benchmark(args.rounds, args.out)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
