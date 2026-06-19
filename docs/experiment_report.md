# 实验报告

## 实验环境

- 服务器路径：`/data2/wqx/multi_agent_low_overhead`
- 环境目录：`/data2/wqx/conda_envs/malow`
- Python：3.10.20
- GPU：通过 `CUDA_VISIBLE_DEVICES=2` 指定 2 号 GPU
- 真实模型：Qwen3-8B，路径 `/home/omnisky/.cache/modelscope/hub/models/Qwen/Qwen3-8B`

## 运行命令

```bash
cd /data2/wqx/multi_agent_low_overhead
CUDA_VISIBLE_DEVICES=2 /data2/wqx/conda_envs/malow/bin/python scripts/run_experiment.py --rounds 10 --out results/server_run_gpu2_adaptive_memory
CUDA_VISIBLE_DEVICES=2 /home/omnisky/anaconda3/bin/python scripts/run_llm_experiment.py --model_path /home/omnisky/.cache/modelscope/hub/models/Qwen/Qwen3-8B --rounds 2 --out results/llm_qwen3_gpu2
```

## 任务设计

实验包含 10 轮连续任务，覆盖五组相关场景：

- openEuler 软件源镜像优化与复用
- 国产数据库索引调优与复用
- WPS 文档批处理转换与复用
- TongWeb 中间件日志诊断与复用
- 国产基础软件安全基线检查与复用

## 新增创新点：置信门控自适应记忆

原系统已经支持关键词、标签、语义向量三阶段渐进式读取。本轮进一步加入置信门控：每个阶段结束后计算记忆置信度，如果当前命中已经足够可靠，就提前停止后续读取。系统会记录：

- `adaptive_early_stops`：触发早停的任务次数。
- `adaptive_stage_skips`：因为早停而跳过的读取阶段数。
- `avg_memory_confidence`：平均记忆置信度。
- `adaptive_skip_rate`：跳过阶段占全部计划读取阶段的比例。

这样可以把“Agent 根据自身需要读取文档”从概念变成可审计、可量化的行为。

## 前沿论文方法对比

本项目的设计与近年多 Agent 和记忆型 Agent 研究有直接对应关系。

- CAMEL、MetaGPT、AutoGen 和 AgentVerse 说明，多 Agent 系统通常需要明确角色分工、通信协议和协作流程。本文采用 Planner、Retriever、Executor、Summarizer 四类 Agent，并用 `ProtocolMessage` 固化动作、参数、结果和能力描述，重点解决自然语言长上下文通信开销大的问题。
- Generative Agents、Reflexion、Voyager 和 CoALA 说明，Agent 需要长期记忆、反思经验、技能库和结构化动作空间。本文把任务摘要、证据链、收益计算和复用历史写入 `SharedMemory`，并用 `VectorState` 承载中间语义状态。
- MemGPT、Mem0、A-MEM、MemOS 和 MIRIX 说明，前沿记忆机制正在从普通 RAG 检索转向分层记忆、图记忆、生命周期管理和分类型记忆池。本文当前实现的是轻量可复现版本：关键词、标签、语义三阶段读取，加上置信门控和 `stage_audit`；同时已经为 `MemoryUnit` 增加 `memory_type`、`version`、`status`、`use_count`、`last_hit_at`、`parent_memory_id` 和 `linked_memory_ids` 等轻量元数据。后续可以把这些字段扩展成完整记忆图谱、记忆版本管理和 procedural / episodic / semantic 等分类型检索策略。
- AgentBench 和 AI Agents That Matter 强调 Agent 评测不应只看任务成功率，还要看成本、复现性和评估设置。本文因此同时统计通信字符数、状态字节数、端到端估计耗时、Precision@K、Recall@K、MRR、NDCG、阶段跳过率和平均记忆置信度。

因此，本项目吸收前沿工作的方式不是直接复刻某一个系统，而是把其中最适合课程原型落地的部分抽象为“低开销协议 + 可评估记忆 + 可审计读取决策”。

## 最新实验结果

最新服务器结果以 `results/server_run_gpu2_adaptive_memory/metrics.json` 为准。

| 指标 | 纯文本协作 | 结构化协议协作 |
| --- | ---: | ---: |
| 连续任务轮数 | 10 | 10 |
| Agent 消息数 | 50 | 50 |
| 文本通信字符开销 | 11736 | 5127 |
| 非文本状态传递次数 | 0 | 50 |
| 非文本状态数据规模 | 0 B | 12800 B |
| 共享记忆命中率 | 90.00% | 90.00% |
| 记忆 Precision@K | 50.00% | 50.00% |
| 记忆 Recall@K | 100.00% | 100.00% |
| 记忆 MRR | 0.933 | 0.933 |
| 记忆 NDCG | 0.950 | 0.950 |
| 实际读取阶段数 | 26 | 26 |
| 自适应早停次数 | 4 | 4 |
| 跳过读取阶段数 | 4 | 4 |
| 平均记忆置信度 | 0.504 | 0.502 |
| 阶段跳过率 | 13.33% | 13.33% |
| 估计端到端处理耗时 | 181.673 ms | 49.553 ms |

结构化协议模式相比纯文本模式减少文本通信字符开销 56.31%，估计端到端处理耗时减少 72.72%。新增的置信门控自适应记忆在不降低 Recall@K、MRR 和 NDCG 的前提下，触发早停 4 次，跳过 4 个读取阶段。

当前代码还补充了轻量记忆生命周期和动态链接字段。`memory_type` 表示记忆类型，`version` 和 `status` 表示生命周期状态，`use_count` 和 `last_hit_at` 记录复用热度，`parent_memory_id` 和 `linked_memory_ids` 记录记忆之间的复用链路。这部分用于支撑报告中对 A-MEM、MemOS 和 MIRIX 的方法吸收。

Qwen3-8B 真实模型实验在 2 号 GPU 上完成 2 轮任务，第二轮复用任务命中 `os` 组记忆，Precision@K、Recall@K、MRR 和 NDCG 均为 100.00%。真实模型轨迹中已经包含 `memory_audit`，Planner 可以看到记忆置信度和阶段决策。

## 结论

结构化协议能显著减少 Agent 间长文本传递，`VectorState` 可作为中间语义状态直接交换，共享记忆能够在连续任务中复用历史经验。新增的置信门控自适应记忆进一步说明，Agent 不必固定读满所有阶段，而是可以在证据足够时停止读取，从而提升记忆机制的可解释性和工程可控性。
