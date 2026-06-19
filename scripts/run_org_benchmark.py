from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mam.org_benchmarks import dumps_org_suite, run_organization_benchmark_suite


def main() -> None:
    parser = argparse.ArgumentParser(description="运行多场景组织记忆 benchmark suite")
    parser.add_argument("--episodes", type=int, default=16, help="每个场景的评测 episode 数，默认 16")
    parser.add_argument("--output", default="artifacts/org_benchmark_suite.json", help="实验 JSON 输出路径")
    args = parser.parse_args()

    report = run_organization_benchmark_suite(eval_episodes=args.episodes)
    out = ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(dumps_org_suite(report), encoding="utf-8")

    print("组织记忆 benchmark suite 完成")
    print(f"场景数: {report['scenario_count']}")
    print(f"平均任务步数降低: {report['aggregate']['avg_step_reduction']:.2%}")
    print(f"平均存储压缩率: {report['aggregate']['avg_storage_reduction']:.2%}")
    for item in report["scenarios"]:
        print(
            f"  {item['scenario']}: {item['cold_steps']} -> {item['transfer_steps']} 步, "
            f"降低 {item['step_reduction']:.2%}, 压缩 {item['storage_reduction']:.2%}"
        )
    print(f"结果文件: {out}")


if __name__ == "__main__":
    main()
