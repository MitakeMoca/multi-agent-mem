# 创新点总结

## 1. 协议化协作与向量状态解耦

传统多 Agent 系统通常把中间结果重新组织成长文本再交给下一个 Agent 解析。本系统把协作内容拆成 `action`、`params`、`result`、`capability` 和 `memory_id`，并把语义状态放入 `VectorState` 单独传递。通信层只传递高密度协议单元，语义层负责携带可复用状态，减少长文本上下文反复搬运。

## 2. 可评估的共享记忆机制

系统不只统计“有没有命中记忆”，而是为连续任务标注 `expected_memory_groups`，把记忆复用转化为可评估的检索问题。实验输出 Precision@K、Recall@K、MRR 和 NDCG，用于回答“记忆模式精准度如何评估”。

## 3. 渐进式记忆读取

系统实现了类似 self-hold-skill 的渐进式记忆读取：RetrieverAgent 先用关键词快速定位，再用标签收缩范围，最后用语义向量补召回。Agent 不再一次性读取全部历史，而是按任务需要逐层读取记忆。

## 4. 置信门控的自适应记忆读取

在渐进式读取基础上，系统新增记忆审计与置信门控。每个读取阶段都会记录阶段名称、命中数、最高分、命中记忆组、当前置信度和下一步决策。当置信度超过阈值时，Agent 会提前停止后续阶段，避免“为了检索而检索”。实验新增 `adaptive_early_stops`、`adaptive_stage_skips`、`avg_memory_confidence` 和 `adaptive_skip_rate`，用于量化按需读取是否真的减少了无效阶段。

这个点比普通 top-k 检索更强：它把“读哪些记忆、读到什么程度、为什么停止”变成可审计过程，更接近 Agent 自主读取文档或技能的行为。

在 2 号 GPU 最新主实验中，该机制触发早停 4 次，跳过 4 个读取阶段，平均记忆置信度为 0.502，阶段跳过率为 13.33%，同时保持 Recall@K 100.00%、MRR 0.933、NDCG 0.950。

## 5. 确定性机制实验与真实大模型实验统一

轻量运行时用于稳定复现通信和记忆机制，真实模型运行时用于验证该机制能接入大模型。当前在服务器 2 号 GPU 上接入 Qwen3-8B，Planner 和 Summarizer 由真实模型生成，Retriever 和 Executor 保持结构化工具链。真实模型实验可以验证该系统不是纯规则模拟，而是可承载实际大模型分工。

## 6. 面向国产基础软件的连续任务链

实验不是孤立问答，而是围绕 openEuler 软件源、国产数据库索引、WPS 批处理、TongWeb 日志诊断和安全基线检查构造“初始任务 + 复用任务”链。这样可以验证记忆是否真的跨任务沉淀并被后续 Agent 复用。

## 7. 对前沿记忆型 Agent 方法的吸收与扩展

近期 Agent 论文已经从“会调用工具”转向“能管理长期经验”。Generative Agents 使用记忆流、反思和规划维持长时行为一致性；Reflexion 将失败反馈写入情节记忆；MemGPT 从操作系统角度管理不同层级记忆；Mem0 强调长期记忆的延迟和 token 成本；A-MEM 进一步把记忆组织成可动态链接和演化的知识网络；MemOS 把记忆视为可调度、可版本化、可演化的系统资源；MIRIX 则将记忆划分为 Core、Episodic、Semantic、Procedural、Resource 和 Knowledge Vault 等类型。

本项目已经实现其中最适合课程原型落地的一部分：渐进式记忆读取、置信门控、记忆审计和检索指标评估。同时，为了与 A-MEM、MemOS 和 MIRIX 的方向对齐，系统为 `MemoryUnit` 增加了轻量元数据字段：`memory_type`、`version`、`status`、`use_count`、`last_hit_at`、`parent_memory_id` 和 `linked_memory_ids`。和这些前沿方法相比，本项目的差异是：不追求构建最大规模长期记忆库，而是把多 Agent 间的记忆复用过程变成可测量、可解释、可复现的机制实验。

后续可继续扩展三个创新点：

- 记忆图谱与动态链接：当前已记录 `parent_memory_id`、`linked_memory_ids`、`link_type` 和 `evolution_reason`，后续可以把这些边可视化为经验图谱。
- 记忆生命周期管理：当前已记录 `version`、`status`、`use_count`、`last_hit_at` 和 `confidence`，后续可以加入旧策略降权、错误记忆废弃和高频经验晋升规则。
- 分类型记忆池：当前已记录 `memory_type`，后续可以细分 episodic、semantic、procedural、resource 和 reflection 记忆，并为不同类型设计不同检索权重。

## 答辩表述建议

可以把创新点概括为一句话：

> 我的系统不是简单多 Agent 工作流，而是把 Agent 间协作拆成协议通信、向量状态交换和可评估共享记忆三层，并进一步实现带置信门控的自适应渐进式记忆读取；系统会记录每一阶段读到了什么、置信度是否足够、为什么继续或停止。和 MemGPT、Mem0、A-MEM、MemOS、MIRIX 等前沿记忆型 Agent 工作相比，我的原型更强调低开销、多 Agent 协作场景下的可审计记忆复用，并用 Qwen3-8B 在 2 号 GPU 上验证该机制能接入真实大模型执行多分工任务。
