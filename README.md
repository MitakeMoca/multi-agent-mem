# 面向多智能体协作的低开销通信、状态传递与自适应共享记忆原型

本项目实现课程大作业赛题要求的可运行原型。系统支持纯文本协作模式、结构化协议协作模式和真实大模型协作模式，在相同连续任务上统计通信字符开销、非文本状态传递次数、共享记忆命中率、记忆 Precision@K/Recall@K/MRR/NDCG、置信门控自适应读取指标和任务耗时。

## 目录

- `src/malow/`: 多 Agent 运行时、协议、状态交换、共享记忆和评测代码。
- `scripts/run_experiment.py`: 运行 10 轮连续任务对比实验。
- `scripts/run_llm_experiment.py`: 接入服务器本地大模型运行真实多 Agent 任务。
- `scripts/build_report_docx.py`: 将最新实验指标写入 Word 报告。
- `scripts/make_demo_video.py`: 根据实验指标生成演示视频。
- `docs/innovation_summary.md`: 创新点总结。
- `results/`: 实验输出目录。

## 快速运行

```bash
cd /data2/wqx/multi_agent_low_overhead
CUDA_VISIBLE_DEVICES=2 /data2/wqx/conda_envs/malow/bin/python scripts/run_experiment.py --rounds 10 --out results/server_run_gpu2_adaptive_memory
CUDA_VISIBLE_DEVICES=2 /home/omnisky/anaconda3/bin/python scripts/run_llm_experiment.py --model_path /home/omnisky/.cache/modelscope/hub/models/Qwen/Qwen3-8B --rounds 2 --out results/llm_qwen3_gpu2
```

输出文件：

- `results/server_run_gpu2_adaptive_memory/metrics.json`: 最新汇总指标。
- `results/server_run_gpu2_adaptive_memory/metrics.csv`: 便于表格展示的指标。
- `results/server_run_gpu2_adaptive_memory/traces.jsonl`: 每轮任务轨迹和记忆审计过程。
- `results/llm_qwen3_gpu2/traces.jsonl`: Qwen3-8B 真实模型执行轨迹。

最新 2 号 GPU 主实验中，结构化协议模式相比纯文本模式减少文本通信字符开销 56.31%，估计端到端处理耗时减少 72.72%；自适应记忆触发早停 4 次，跳过 4 个读取阶段，阶段跳过率 13.33%，并保持 Recall@K 100.00%、MRR 0.933、NDCG 0.950。

## 设计摘要

系统包含 4 个 Agent：

- PlannerAgent：任务拆解和协议握手。
- RetrieverAgent：按需读取任务事实和历史记忆。
- ExecutorAgent：执行轻量工具和数值计算。
- SummarizerAgent：汇总证据、生成结论并写入共享记忆。

结构化模式使用 `ProtocolMessage` 传递动作、参数、结果和能力描述。非文本状态通过固定维度语义向量 `VectorState` 在 Agent 间传递，接收方直接用于语义检索和证据聚合。

共享记忆采用 JSONL 持久化，每条记忆包含 ID、来源 Agent、创建时间、任务主题、摘要、标签、证据和向量。记忆读取从关键词、标签、语义向量三阶段渐进执行，并新增置信门控：每一阶段都会计算记忆置信度，若已经达到阈值，Agent 会提前停止后续读取。实验额外统计自适应早停次数、跳过阶段数、平均记忆置信度和阶段跳过率，用于说明“读到足够证据就停止”的按需记忆机制。
