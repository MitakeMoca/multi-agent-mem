"""连续任务数据集。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class Task:
    task_id: str
    topic: str
    question: str
    tags: List[str]
    facts: Dict[str, float]
    memory_group: str
    expected_memory_groups: List[str]


def build_tasks(rounds: int = 10) -> List[Task]:
    """构造两组有关联性的连续任务。"""

    base = [
        Task(
            "os-01",
            "国产操作系统软件源镜像优化",
            "分析 openEuler 软件源镜像切换对下载耗时的影响，并给出优化建议。",
            ["openEuler", "软件源", "性能"],
            {"baseline_time": 128.0, "optimized_time": 74.0, "packages": 42},
            "os",
            [],
        ),
        Task(
            "os-02",
            "国产操作系统软件源镜像优化复用",
            "在第二台 openEuler 节点复用上一轮策略，估计重复分析减少的时间。",
            ["openEuler", "软件源", "复用"],
            {"baseline_time": 121.0, "optimized_time": 73.0, "packages": 42},
            "os",
            ["os"],
        ),
        Task(
            "db-01",
            "国产数据库索引调优",
            "根据查询次数和命中率分析达梦数据库索引调优收益。",
            ["数据库", "索引", "性能"],
            {"baseline_time": 94.0, "optimized_time": 49.0, "queries": 180},
            "db",
            [],
        ),
        Task(
            "db-02",
            "国产数据库索引调优复用",
            "复用上一轮索引调优经验，评估相似表结构上的收益。",
            ["数据库", "索引", "复用"],
            {"baseline_time": 102.0, "optimized_time": 55.0, "queries": 200},
            "db",
            ["db"],
        ),
        Task(
            "office-01",
            "国产办公套件批量转换",
            "规划 WPS 文档批量转 PDF 的失败重试与耗时优化方案。",
            ["办公套件", "批处理", "可靠性"],
            {"baseline_time": 240.0, "optimized_time": 171.0, "files": 60},
            "office",
            [],
        ),
        Task(
            "office-02",
            "国产办公套件批量转换复用",
            "对另一批 WPS 文档复用批量转换策略，统计复用带来的减少。",
            ["办公套件", "批处理", "复用"],
            {"baseline_time": 236.0, "optimized_time": 169.0, "files": 60},
            "office",
            ["office"],
        ),
        Task(
            "middleware-01",
            "国产中间件日志诊断",
            "分析 TongWeb 服务日志中的异常模式并生成排查流程。",
            ["中间件", "日志", "诊断"],
            {"baseline_time": 87.0, "optimized_time": 52.0, "events": 320},
            "middleware",
            [],
        ),
        Task(
            "middleware-02",
            "国产中间件日志诊断复用",
            "在相似 TongWeb 故障中复用历史排查流程，估算节省时间。",
            ["中间件", "日志", "复用"],
            {"baseline_time": 91.0, "optimized_time": 54.0, "events": 330},
            "middleware",
            ["middleware"],
        ),
        Task(
            "security-01",
            "国产基础软件安全基线检查",
            "设计面向操作系统和数据库的安全基线检查步骤。",
            ["安全", "基线", "检查"],
            {"baseline_time": 150.0, "optimized_time": 104.0, "items": 36},
            "security",
            [],
        ),
        Task(
            "security-02",
            "国产基础软件安全基线复用",
            "复用安全基线检查记忆，生成第二轮检查计划和收益估计。",
            ["安全", "基线", "复用"],
            {"baseline_time": 148.0, "optimized_time": 101.0, "items": 36},
            "security",
            ["security"],
        ),
    ]
    if rounds <= len(base):
        return base[:rounds]
    tasks = list(base)
    for i in range(len(base), rounds):
        seed = base[i % len(base)]
        tasks.append(
            Task(
                f"{seed.task_id}-r{i + 1}",
                seed.topic + "扩展",
                seed.question,
                seed.tags,
                dict(seed.facts),
                seed.memory_group,
                [seed.memory_group],
            )
        )
    return tasks
