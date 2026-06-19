# 演示说明

## 演示顺序

1. 展示项目目录：`src/`、`scripts/`、`docs/`、`results/`。
2. 展示主实验命令：

```bash
CUDA_VISIBLE_DEVICES=2 /data2/wqx/conda_envs/malow/bin/python scripts/run_experiment.py --rounds 10 --out results/server_run_gpu2_adaptive_memory
```

3. 打开 `results/server_run_gpu2_adaptive_memory/metrics.json`，说明文本通信字符开销、状态传递次数、记忆 Precision@K/Recall@K/MRR/NDCG。
4. 展示新增自适应记忆指标：`adaptive_early_stops`、`adaptive_stage_skips`、`avg_memory_confidence`、`adaptive_skip_rate`。
5. 打开 `traces.jsonl` 中 Retriever 的 `memory_audit`，说明每一阶段如何记录命中数、置信度和继续/停止决策。
6. 展示真实模型命令：

```bash
CUDA_VISIBLE_DEVICES=2 /home/omnisky/anaconda3/bin/python scripts/run_llm_experiment.py --model_path /home/omnisky/.cache/modelscope/hub/models/Qwen/Qwen3-8B --rounds 2 --out results/llm_qwen3_gpu2
```

7. 打开 `results/llm_qwen3_gpu2/traces.jsonl`，展示 Qwen3-8B Planner/Summarizer 真实输出和第二轮任务的记忆复用。

## 重点话术

本项目的核心不是简单把多个 Agent 串起来，而是把协作拆成低开销协议通信、向量状态传递、共享记忆复用和可审计的自适应读取四层。新增的置信门控机制让 Agent 可以根据当前证据质量决定是否继续读取记忆，避免固定读满所有阶段。
