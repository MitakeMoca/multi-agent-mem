# 系统设计文档

## 1. 目标与核心创新

本系统面向规模化多智能体协作中的三个系统层问题：Agent 间通信冗余、非文本中间状态难以直接传递、协作经验难以沉淀为可迁移策略。普通共享记忆通常保存任务摘要、工具调用历史或日志，本系统进一步提出**组织记忆模型**：从多 Agent 交互轨迹中抽取角色分工、协作拓扑、触发条件和压缩 actor 参数，并将其作为可检索、可迁移、可执行的策略记忆。

核心创新点如下：

1. **组织记忆模型**：统一表示角色、协作拓扑、触发条件、共享 actor 基、角色 adapter 和场景 payload，使组织记忆成为系统模型的一部分，而不是某个任务的局部规则。
2. **真实与自包含双层 benchmark**：服务器安装 `mpe2` 后运行官方 `simple_spread_v3`，并提供自包含 MPE-style suite 覆盖追捕围堵、协同导航覆盖、接力运输三类协作结构。
3. **MADDPG-like 压缩策略存储**：训练阶段利用联合状态抽取协作结构，执行阶段每个 Agent 只使用低维角色策略；系统保存共享 actor 基和角色 adapter，而不是保存完整轨迹。
4. **双通道协作协议**：控制信息通过结构化协议传递，语义状态通过向量状态包传递，组织记忆通过共享记忆检索和 `state_ref` 间接进入下游 Agent。
5. **可审计记忆生命周期**：共享记忆记录类型、版本、状态、命中次数、最近命中时间、父记忆和动态链接，使任务记忆与组织记忆都能被后续审计和演化。

## 2. 总体架构

系统由七个模块组成：

- **多 Agent 运行时**：负责任务调度、能力握手、消息记录和两种协作模式切换。
- **协议解析与调度模块**：定义 `ProtocolMessage`，包含动作类型、输入参数、返回结果、能力描述和状态引用。
- **状态交换模块**：定义 `StatePacket` 与 `StateExchange`，用于非文本向量状态的发布和读取。
- **共享记忆存储与检索模块**：定义 `SharedMemory`，使用 SQLite 保存任务记忆与组织记忆，并维护生命周期与动态链接元数据。
- **组织记忆模型模块**：定义 `OrganizationMemoryModel`，统一表达角色、拓扑、触发条件和压缩 actor 参数。
- **组织记忆 benchmark 模块**：定义 MPE-style 的追捕围堵、协同导航覆盖和接力运输场景。
- **官方 MPE 适配模块**：可选运行 `mpe2.simple_spread_v3`，环境缺失时输出明确 fallback 状态。
- **评测模块**：执行通信 benchmark、单场景围堵实验和多场景组织记忆 suite。

执行流程如下：

```text
Multi-Agent Runtime:
Task -> Planner -> StatePacket -> Retriever -> Tool -> Summarizer -> SharedMemory

Organization Memory Suite:
Scenario trajectories -> Organization miner -> OrganizationMemoryModel
                    -> SQLite SharedMemory -> New agents retrieve memory
                    -> Decentralized actor execution -> Transfer metrics
```

## 3. 组织记忆模型

组织记忆定义在 `src/mam/organization.py` 中。它不是普通经验摘要，而是多 Agent 协作结构的压缩表示：

- `scenario`：组织记忆适用的场景族，例如 `pursuit_flank`、`cooperative_navigation`、`relay_transport`。
- `roles`：Agent 的协作角色，例如左右夹击者、中心覆盖者、前导侦察者。
- `coordination_graph`：角色之间的依赖边，描述谁和谁需要保持协同关系。
- `trigger`：触发组织策略的条件，例如覆盖半径、交接距离、最大速度。
- `actor_basis`：共享 actor 基，表示不同角色共享的低维控制结构。
- `role_adapters`：角色 adapter，表示每个 Agent 的分工偏置。
- `payload`：场景级补充信息，例如排序规则、队形规则或任务族名称。

组织记忆会被序列化为 JSON，作为 `organization-miner` 产生的记忆单元写入 SQLite。迁移阶段，新 Agent 按场景标签和语义相似度检索该记忆，再还原为可执行策略。

## 4. 共享记忆生命周期与动态链接

共享记忆定义在 `src/mam/memory.py` 中。每条 `MemoryRecord` 保存任务主题、摘要、标签、证据、策略和向量 blob，同时增加轻量生命周期字段：

- `memory_type`：记忆类型，当前普通任务记忆和组织记忆默认使用 `procedural`。
- `version`、`status`：记录记忆版本和 active/deprecated 等生命周期状态。
- `use_count`、`last_hit_at`：检索命中时自动更新，用于衡量复用热度。
- `confidence`：写入时由工具结果或组织记忆抽取过程给出。
- `parent_memory_id`、`linked_memory_ids`、`link_type`、`evolution_reason`：记录新记忆从哪些历史记忆演化而来。

Summarizer 写入新任务记忆时，会把本轮复用过的记忆 ID 写入父节点和链接列表。组织记忆写入时会标记为 `organization_pattern`。运行时额外统计 `lifecycle_memory_hits` 和 `linked_memory_hits`，用于在实验报告中审计“命中的记忆是否带有可治理元数据”和“是否形成复用链路”。

## 5. MPE-style 组织记忆 Benchmark Suite

多场景 benchmark 定义在 `src/mam/org_benchmarks.py` 中，包含三个场景：

| 场景 | 对齐的多智能体问题 | 组织记忆内容 |
| --- | --- | --- |
| `pursuit_flank` | 两个追捕者围堵一个逃逸者 | 左右夹击角色、夹击角、夹击半径、actor 参数 |
| `cooperative_navigation` | 多 Agent 覆盖多个 landmark | 按 x 坐标排序的覆盖分工、链式协作拓扑 |
| `relay_transport` | 多 Agent 接力运输载荷 | 前导侦察者与左右搬运者、三角支撑队形 |

这三个场景都遵循相同流程：先从训练轨迹或专家规则抽取组织记忆，写入共享记忆库；再让新的 Agent 检索该记忆并执行去中心化策略；最后与冷启动策略比较任务步数和存储开销。

## 6. 官方 MPE 适配器

官方 benchmark 适配器定义在 `src/mam/official_mpe.py` 中。系统优先检测 `mpe2`，可用时运行 `mpe2.simple_spread_v3`；如果环境中没有 `mpe2` 或旧版 `pettingzoo.mpe`，脚本会输出 `status: unavailable` 和安装提示。

服务器验证中，`mpe2.simple_spread_v3` 已成功运行。组织记忆策略将三名 Agent 分配到左、中、右 landmark 角色，相对随机策略平均奖励提升 25.30%。该实验用于补强真实 benchmark 证据，自包含 suite 则用于稳定复现多场景组织记忆迁移。

## 7. MADDPG-like 压缩策略

本系统没有引入重型深度强化学习框架，而是保留 MADDPG 的关键系统思想：

- **集中训练信号**：组织记忆抽取器可以观察联合状态和完整轨迹。
- **分散执行 actor**：迁移阶段每个 Agent 只读取自身观测、角色 adapter 和共享 actor 基。
- **压缩存储**：保存低维 actor 参数、角色分工和触发条件，不保存完整轨迹。

这一设计使组织记忆具备系统价值：它不仅能迁移给新 Agent，还能显著降低长期记忆的存储规模。

## 8. 结构化协作协议与状态传递

结构化消息定义在 `src/mam/protocol.py` 中，字段包括 `sender`、`receiver`、`action`、`params`、`result`、`capability` 和 `state_ref`。系统启动每个任务时执行能力握手；纯文本模式使用自然语言能力说明并解析长上下文，结构化模式使用 `capability_announce` 和紧凑参数字段。

状态包定义在 `src/mam/vectors.py` 中。Planner 使用确定性哈希 embedding 生成 64 维向量，并发布到 `StateExchange`。后续 Agent 通过 `state_ref` 读取该状态，用于检索知识、普通记忆和组织记忆。

## 9. Agent 设计

系统实现 4 类通用 Agent，满足“不少于 3 个 Agent 并覆盖 3 类角色”的要求。

| Agent | 角色 | 动作 | 输出 |
| --- | --- | --- | --- |
| Planner | 任务规划 | `plan_task`, `emit_state` | 执行计划和语义状态包 |
| Retriever | 信息检索 | `retrieve_knowledge`, `retrieve_memory` | 静态证据和历史记忆 |
| Tool | 工具执行 | `compute_metrics`, `run_codeact` | 指标、置信度、沙箱扩展点 |
| Summarizer | 总结生成 | `summarize`, `write_memory` | 任务总结和新增记忆 |

组织记忆 benchmark 中的追捕者、覆盖者和运输者可视为执行型 Agent。它们通过共享记忆检索获得角色和 actor adapter，然后分散执行。

## 10. 可复现实验入口

系统提供三个入口：

```bash
python3 scripts/run_benchmark.py --rounds 10 --output artifacts/benchmark.json
python3 scripts/run_pursuit_demo.py --episodes 16 --output artifacts/pursuit_transfer.json
python3 scripts/run_org_benchmark.py --episodes 16 --output artifacts/org_benchmark_suite.json
python3 scripts/run_official_mpe.py --episodes 4 --max-cycles 25 --output artifacts/official_mpe.json
```

`run_benchmark.py` 覆盖原始赛题要求中的通信、状态传递和共享记忆 benchmark，并包含组织记忆 suite 摘要。`run_pursuit_demo.py` 保留围堵场景的单独复现入口。`run_org_benchmark.py` 是主要组织记忆 benchmark suite。`run_official_mpe.py` 在安装 `mpe2` 时运行官方 MPE 环境。

## 11. 与作业要求对应关系

| 作业要求 | 实现位置 |
| --- | --- |
| 不少于 3 个 Agent | `src/mam/agents.py`，实现 4 个 Agent |
| 结构化通信协议 | `src/mam/protocol.py` |
| 纯文本和结构化模式对比 | `src/mam/runtime.py`, `src/mam/benchmark.py` |
| 非文本状态传递 | `src/mam/vectors.py`, `src/mam/state_exchange.py` |
| 共享记忆存储、检索、复用 | `src/mam/memory.py` |
| 记忆生命周期与动态链接 | `src/mam/memory.py`, `src/mam/runtime.py` |
| 组织记忆模型 | `src/mam/organization.py` |
| 多场景组织记忆 benchmark | `src/mam/org_benchmarks.py` |
| 官方 MPE benchmark | `src/mam/official_mpe.py` |
| MADDPG-like 压缩策略存储 | `OrganizationMemoryModel`, `role_adapters`, `actor_basis` |
| 2 组连续任务 | `build_tasks()` |
| 10 轮稳定执行 | `scripts/run_benchmark.py --rounds 10` |
| 性能统计 | `artifacts/benchmark.json`, `artifacts/org_benchmark_suite.json`, `artifacts/official_mpe.json` |
