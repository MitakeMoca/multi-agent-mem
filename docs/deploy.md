# 部署与复现

## 服务器

- SSH Host：`atrust`
- 远端目录：`/data2/wqx/multi_agent_low_overhead`
- 主实验环境：`/data2/wqx/conda_envs/malow`
- 真实模型 Python：`/home/omnisky/anaconda3/bin/python`
- GPU：使用 `CUDA_VISIBLE_DEVICES=2`
- 2 号 GPU：NVIDIA A800 80GB

## 主实验

```bash
cd /data2/wqx/multi_agent_low_overhead
CUDA_VISIBLE_DEVICES=2 /data2/wqx/conda_envs/malow/bin/python scripts/run_experiment.py --rounds 10 --out results/server_run_gpu2_adaptive_memory
```

输出：

- `results/server_run_gpu2_adaptive_memory/metrics.json`
- `results/server_run_gpu2_adaptive_memory/metrics.csv`
- `results/server_run_gpu2_adaptive_memory/traces.jsonl`

## 真实大模型实验

```bash
CUDA_VISIBLE_DEVICES=2 /home/omnisky/anaconda3/bin/python scripts/run_llm_experiment.py --model_path /home/omnisky/.cache/modelscope/hub/models/Qwen/Qwen3-8B --rounds 2 --out results/llm_qwen3_gpu2
```

输出：

- `results/llm_qwen3_gpu2/metrics.json`
- `results/llm_qwen3_gpu2/traces.jsonl`
- `results/llm_qwen3_gpu2/memory.jsonl`

## 核验点

- `metrics.json` 中应包含 `adaptive_early_stops`、`adaptive_stage_skips`、`avg_memory_confidence` 和 `adaptive_skip_rate`。
- `traces.jsonl` 的 Retriever 消息中应包含 `memory_audit`。
- Qwen3-8B 实验中第二个复用任务应命中 `os` 组记忆。
