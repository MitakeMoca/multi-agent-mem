from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mam.pursuit import dumps_pursuit_report, run_pursuit_transfer_experiment


def main() -> None:
    parser = argparse.ArgumentParser(description="运行两个追捕者围堵一个逃逸者的组织记忆迁移实验")
    parser.add_argument("--episodes", type=int, default=16, help="评测 episode 数，默认 16")
    parser.add_argument("--output", default="artifacts/pursuit_transfer.json", help="实验 JSON 输出路径")
    args = parser.parse_args()

    report = run_pursuit_transfer_experiment(eval_episodes=args.episodes)
    out = ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(dumps_pursuit_report(report), encoding="utf-8")

    print("围堵组织记忆迁移实验完成")
    print(f"冷启动平均围堵步数: {report['cold_start']['avg_capture_steps']}")
    print(f"记忆迁移平均围堵步数: {report['memory_transfer']['avg_capture_steps']}")
    print(f"围堵步数降低: {report['improvement']['capture_step_reduction']:.2%}")
    print(f"组织记忆压缩率: {report['storage']['storage_reduction']:.2%}")
    print(f"组织记忆检索分数: {report['shared_memory_transfer']['retrieval_score']}")
    print(f"结果文件: {out}")


if __name__ == "__main__":
    main()
