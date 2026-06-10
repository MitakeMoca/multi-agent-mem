# 交付清单

## 已完成

- 完整源码：`src/mam`
- 实验入口：`scripts/run_benchmark.py`
- 围堵组织记忆实验入口：`scripts/run_pursuit_demo.py`
- 多场景组织记忆 benchmark 入口：`scripts/run_org_benchmark.py`
- 官方 MPE benchmark 入口：`scripts/run_official_mpe.py`
- 单元测试：`tests/test_core.py`
- 系统设计文档：`docs/system_design.md`
- 部署文档：`docs/deployment.md`
- 实验报告：`docs/experiment_report.md`
- 演示视频脚本：`docs/demo_script.md`
- 演示视频：`artifacts/demo.mp4`
- 服务器实验结果：`artifacts/benchmark.json`
- 领域词汇与决策记录：`CONTEXT.md`, `docs/adr/0001-standard-library-reproducible-prototype.md`

## 作业要求覆盖

| 要求 | 状态 | 证据 |
| --- | --- | --- |
| 不少于 3 个 Agent | 已完成 | Planner、Retriever、Tool、Summarizer |
| 结构化通信协议 | 已完成 | `src/mam/protocol.py` |
| 纯文本与结构化模式对比 | 已完成 | `src/mam/runtime.py`, `artifacts/benchmark.json` |
| 非文本状态传递 | 已完成 | `src/mam/vectors.py`, `src/mam/state_exchange.py` |
| 共享记忆模块 | 已完成 | `src/mam/memory.py` |
| 组织记忆迁移创新实验 | 已完成 | `src/mam/pursuit.py`, `artifacts/pursuit_transfer.json` |
| 多场景组织记忆 benchmark | 已完成 | `src/mam/org_benchmarks.py`, `artifacts/org_benchmark_suite.json` |
| 官方 MPE benchmark | 已完成 | `src/mam/official_mpe.py`, `artifacts/official_mpe.json` |
| MADDPG-like 压缩策略存储 | 已完成 | `src/mam/pursuit.py` 中共享 actor 基和角色 adapter |
| 2 组关联连续任务 | 已完成 | `build_tasks()` |
| 不少于 10 轮连续任务 | 已完成 | `python3 scripts/run_benchmark.py --rounds 10` |
| 性能对比数据 | 已完成 | `docs/experiment_report.md`, `artifacts/benchmark.json` |
| 部署文档 | 已完成 | `docs/deployment.md` |
| 演示视频 | 已完成基础版 | `artifacts/demo.mp4`，脚本见 `docs/demo_script.md` |
| openEuler 24.03-LTS-SP3 | 暂缓 | 用户要求先不管，当前在 Hangzhou-A5000 通用 Linux 上验证 |

## 服务器验证命令

```bash
cd /data1/code/wqx/multi-agent-mem
python3 -m unittest discover -s tests
python3 scripts/run_benchmark.py --rounds 10 --output artifacts/benchmark.json
python3 scripts/run_pursuit_demo.py --episodes 16 --output artifacts/pursuit_transfer.json
python3 scripts/run_org_benchmark.py --episodes 16 --output artifacts/org_benchmark_suite.json
python3 scripts/run_official_mpe.py --episodes 4 --max-cycles 25 --output artifacts/official_mpe.json
```
