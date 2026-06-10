from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mam.benchmark import run_benchmark


def main() -> None:
    parser = argparse.ArgumentParser(description="运行多 Agent 共享记忆可复现实验")
    parser.add_argument("--rounds", type=int, default=10, help="连续任务轮数，默认 10")
    parser.add_argument("--output", default="artifacts/benchmark.json", help="实验 JSON 输出路径")
    args = parser.parse_args()

    report = run_benchmark(args.rounds, args.output)
    comparison = report["comparison"]
    print("实验完成")
    print(f"连续任务轮数: {report['rounds']}")
    print(f"文本字符节省率: {comparison['char_saving_rate']:.2%}")
    print(f"估算 token 节省率: {comparison['token_saving_rate']:.2%}")
    print(f"任务耗时节省率: {comparison['latency_saving_rate']:.2%}")
    print(f"结构化状态传递规模: {comparison['state_transfer_bytes']} bytes")
    pursuit = report["pursuit_transfer"]
    print("组织记忆迁移实验:")
    print(f"  冷启动平均围堵步数: {pursuit['cold_start']['avg_capture_steps']}")
    print(f"  记忆迁移平均围堵步数: {pursuit['memory_transfer']['avg_capture_steps']}")
    print(f"  围堵步数降低: {pursuit['improvement']['capture_step_reduction']:.2%}")
    print(f"  策略存储压缩率: {pursuit['storage']['storage_reduction']:.2%}")
    suite = report["organization_benchmark_suite"]
    print("多场景组织记忆 benchmark:")
    print(f"  场景数: {suite['scenario_count']}")
    print(f"  平均任务步数降低: {suite['aggregate']['avg_step_reduction']:.2%}")
    print(f"  平均存储压缩率: {suite['aggregate']['avg_storage_reduction']:.2%}")
    print(f"结果文件: {args.output}")


if __name__ == "__main__":
    main()
