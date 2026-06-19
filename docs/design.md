# 系统设计

## 总体结构

系统由四类 Agent 和三个共享基础设施组成：

- PlannerAgent：负责任务拆解、能力握手和协作路径规划。
- RetrieverAgent：负责事实证据读取、共享记忆检索和记忆审计。
- ExecutorAgent：负责确定性工具执行和数值计算。
- SummarizerAgent：负责汇总证据、生成结论并写入共享记忆。
- ProtocolMessage：结构化通信协议。
- VectorState：Agent 间传递的非文本语义状态。
- SharedMemory：JSONL 持久化共享记忆库。

## 协议化通信

纯文本模式会把任务背景、推理过程、证据和结论全部写成自然语言传递。结构化模式只传递 `sender`、`receiver`、`action`、`params`、`result` 和 `capability`。详细语义通过状态向量和共享记忆引用承载，避免长文本重复解析。

## 非文本状态传递

`VectorState` 使用 64 维哈希语义向量表示当前任务、规划结果、检索证据和执行结果。结构化模式中每个 Agent 输出结果时同步传递向量状态，接收方可以直接用于语义检索和证据聚合。

## 共享记忆

`MemoryUnit` 包含 `memory_id`、`source_agent`、`created_at`、`task_topic`、`summary`、`tags`、`evidence`、`vector` 和 `metadata`。`metadata.memory_group` 用于标注记忆所属任务组，`expected_memory_groups` 用于评估检索是否命中正确历史经验。

## 渐进式与自适应记忆读取

记忆读取分为三个阶段：

1. 关键词读取：快速查找与任务问题词项重合的记忆。
2. 标签读取：用任务标签收缩候选范围。
3. 语义读取：用向量余弦相似度补召回。

本轮新增置信门控：每一阶段都会计算当前 `confidence`，并记录 `stage_audit`。如果当前命中满足阈值，RetrieverAgent 会提前停止后续阶段，并输出 `early_stop`、`stages_skipped`、`decision` 等审计信息。该机制让“按需读取文档/技能”具备可解释记录。

## 真实大模型接入

`LLMMultiAgentRuntime` 接入服务器本地 HuggingFace/ModelScope 模型。当前实验使用 Qwen3-8B，在 2 号 GPU 上运行 Planner 和 Summarizer，Retriever 和 Executor 保持结构化工具链。Planner prompt 中包含记忆评估和渐进式记忆审计，真实模型可以看到当前记忆是否可信以及是否已经早停。
