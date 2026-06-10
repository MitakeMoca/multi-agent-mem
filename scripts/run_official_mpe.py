from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mam.official_mpe import dumps_official_mpe, run_official_mpe_benchmark


def main() -> None:
    parser = argparse.ArgumentParser(description="运行官方 MPE/MPE2 simple_spread benchmark，可用时使用 mpe2")
    parser.add_argument("--episodes", type=int, default=8, help="评测 episode 数，默认 8")
    parser.add_argument("--max-cycles", type=int, default=25, help="每个 episode 最大 cycle 数，默认 25")
    parser.add_argument("--output", default="artifacts/official_mpe.json", help="实验 JSON 输出路径")
    args = parser.parse_args()

    report = run_official_mpe_benchmark(episodes=args.episodes, max_cycles=args.max_cycles)
    out = ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(dumps_official_mpe(report), encoding="utf-8")

    print("官方 MPE/MPE2 benchmark 完成")
    print(f"状态: {report['status']}")
    if report["status"] == "ok":
        print(f"后端: {report['backend']}")
        print(f"环境: {report['environment']}")
        print(f"随机策略平均奖励: {report['random_policy']['mean_reward']}")
        print(f"组织记忆策略平均奖励: {report['organization_memory_policy']['mean_reward']}")
        print(f"相对奖励提升: {report['improvement']['relative_reward_improvement']:.2%}")
    else:
        print(f"原因: {report['backend']['reason']}")
        print(f"安装提示: {report['backend']['install_hint']}")
    print(f"结果文件: {out}")


if __name__ == "__main__":
    main()
