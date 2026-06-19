# 创新点总结

## 1. 结构化协议与非文本状态传递

传统多 Agent 系统通常把中间结果重新组织成长文本，再交给下一个 Agent 解析。本系统把协作内容拆成 `action`、`params`、`result`、`capability` 和 `state_ref`，并把语义状态放入 `StatePacket` 单独传递。通信层只传递高密度协议单元，语义层负责携带可复用状态，减少长文本上下文反复搬运。

## 2. 组织记忆模型

普通共享记忆多保存任务摘要、工具调用历史或日志。本系统把多 Agent 协作轨迹压缩为角色分工、协作拓扑、触发条件、共享 actor 基和角色 adapter，并存入 SQLite 共享记忆库。新 Agent 可以检索这些组织记忆，直接复用“谁负责哪里、谁和谁配合、什么时候切换策略”的协作先验。

## 3. MADDPG-like 压缩策略存储

系统借鉴集中训练、分散执行思想：组织记忆抽取阶段可以观察联合状态和完整轨迹，执行阶段每个 Agent 只使用局部角色 adapter 和共享 actor 基。这样不需要引入重型深度强化学习依赖，也避免保存完整轨迹，适合课程作业环境中的可复现实验。

## 4. 多层 Benchmark 证据

系统同时提供三类评测：通信 benchmark 用于比较纯文本模式和结构化模式的开销；官方 `mpe2.simple_spread_v3` 适配器用于验证能接入真实多智能体环境；自包含 MPE-style suite 覆盖追捕围堵、协同导航覆盖和接力运输三类组织结构。这样创新点不只停留在单个示例，而是有多场景证据支撑。

## 5. 轻量记忆生命周期与动态链接

当前版本把前沿记忆系统中的生命周期和动态链接思想压缩成标准库实现。每条 `MemoryRecord` 记录 `memory_type`、`version`、`status`、`use_count`、`last_hit_at`、`confidence`、`parent_memory_id`、`linked_memory_ids`、`link_type` 和 `evolution_reason`。检索命中会更新复用热度；Summarizer 基于历史记忆生成新记忆时，会记录父记忆和复用链路。这样共享记忆不再只是扁平文本库，而是可以被审计和继续演化的经验资源。

## 6. 与前沿论文的关系

Generative Agents、Reflexion、Voyager 和 CoALA 说明长期记忆、反思、技能库和认知架构是 Agent 能力提升的重要方向；CAMEL、MetaGPT、AutoGen 和 AgentVerse 说明多 Agent 系统需要角色分工和流程约束；MemGPT、Mem0、A-MEM、MemOS 和 MIRIX 进一步说明记忆正在从普通 RAG 检索转向可调度、可链接、可版本化和可分类型的系统资源。

本项目没有复刻这些完整系统，而是吸收其中适合作业原型落地的部分：低开销结构化协作、可迁移组织记忆、生命周期字段、动态链接字段和成本敏感评测。与 AgentBench 和 AI Agents That Matter 的评测观点一致，报告不只看任务是否完成，还同时报告字符开销、token 估算、状态字节、任务步数、存储压缩率和记忆审计指标。

## 答辩表述建议

可以把创新点概括为一句话：

> 我的系统不是简单多 Agent 工作流，而是把 Agent 间协作拆成结构化通信、非文本状态交换、组织记忆迁移和可审计记忆生命周期四层；它既能减少通信开销，也能把多 Agent 分工模式压缩成可检索、可迁移、可继续演化的共享记忆。
