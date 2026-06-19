# Multi-Agent Memory

面向多智能体协作的低开销通信、非文本状态传递与共享记忆原型系统。

本项目用于完成赛题“面向多智能体协作的低开销通信、状态传递与共享记忆机制”。系统提供两种可复现实验模式：

- `text`: 纯文本协作模式，Agent 之间以自然语言长文本传递上下文。
- `structured`: 结构化协议协作模式，Agent 之间以紧凑协议消息、向量状态包和共享记忆单元协作。

核心特性：

- 支持 Planner、Retriever、Tool、Summarizer 四类 Agent 协同运行。
- 实现握手、能力发现、动作类型、输入参数、返回结果和能力描述。
- 使用确定性哈希向量作为非文本中间状态，直接在 Agent 间传递。
- 使用 SQLite 存储共享记忆，支持关键词、标签和语义相似度检索。
- 新增记忆生命周期字段和动态链接字段，记录 `memory_type`、`version`、`status`、`use_count`、`last_hit_at`、`parent_memory_id`、`linked_memory_ids`、`link_type` 和 `evolution_reason`。
- 新增 MPE-style 多场景组织记忆 benchmark suite：追捕围堵、协同导航覆盖、接力运输。
- 新增官方 `mpe2.simple_spread_v3` 可选 benchmark 适配器；服务器已安装 `mpe2` 并完成真实环境验证。
- 从轨迹中抽取角色分工、协作拓扑、触发条件和压缩 actor 参数，并迁移给新 Agent。
- 使用 MADDPG-like 的集中训练/分散执行思想，只存储共享 actor 基、角色 adapter 和场景触发条件，避免保存完整轨迹。
- 提供 2 组关联连续任务，共 10 轮可复现实验。
- 自动统计消息次数、文本字符开销、估算 token、向量状态传递次数与规模、耗时、记忆命中率、生命周期字段命中数、动态链接字段命中数和性能提升。

## 快速运行

```bash
cd /data1/code/wqx/multi-agent-mem
python3 scripts/run_benchmark.py --rounds 10 --output artifacts/benchmark.json
python3 scripts/run_pursuit_demo.py --episodes 16 --output artifacts/pursuit_transfer.json
python3 scripts/run_org_benchmark.py --episodes 16 --output artifacts/org_benchmark_suite.json
python3 scripts/run_official_mpe.py --episodes 4 --max-cycles 25 --output artifacts/official_mpe.json
python3 -m unittest discover -s tests
```

本项目只依赖 Python 标准库，已在 Python 3.13 环境下设计。

## 前沿方法对齐

报告中将本系统与 Generative Agents、Reflexion、MemGPT、Voyager、CoALA、CAMEL、MetaGPT、AutoGen、AgentVerse、Mem0、A-MEM、MemOS、MIRIX、AgentBench 和 AI Agents That Matter 等工作进行机制级比较。当前实现不追求复刻完整长期记忆操作系统，而是把其中适合作业原型落地的部分抽象为三层机制：低开销结构化协作、可迁移组织记忆、可审计的记忆生命周期与动态链接。

## 目录

- `src/mam`: 系统源码。
- `scripts/run_benchmark.py`: 可复现实验入口。
- `tests`: 单元测试。
- `docs/system_design.md`: 系统设计文档。
- `docs/deployment.md`: 部署文档。
- `docs/experiment_report.md`: 实验报告。
- `docs/literature_review.md`: 前沿论文对比与方法吸收说明。
- `CONTEXT.md`: 项目领域词汇。
- `docs/adr`: 关键设计决策记录。
