# 演示视频脚本

本文件用于录制演示视频。建议视频长度 3 到 5 分钟。

## 1. 开场

展示项目目录：

```bash
cd /data1/code/wqx/multi-agent-mem
find . -maxdepth 2 -type f | sort
```

说明本系统完成低开销通信、非文本状态传递和共享记忆复用三项机制。

## 2. 展示系统结构

```bash
sed -n '1,220p' docs/system_design.md
```

重点说明 4 个 Agent、结构化协议、状态交换模块和 SQLite 共享记忆。

## 3. 运行测试

```bash
python3 -m unittest discover -s tests
```

说明测试覆盖向量状态包、共享记忆检索、结构化运行时和 10 轮 benchmark。

## 4. 运行实验

```bash
python3 scripts/run_benchmark.py --rounds 10 --output artifacts/benchmark.json
python3 scripts/run_pursuit_demo.py --episodes 16 --output artifacts/pursuit_transfer.json
python3 scripts/run_org_benchmark.py --episodes 16 --output artifacts/org_benchmark_suite.json
python3 scripts/run_official_mpe.py --episodes 4 --max-cycles 25 --output artifacts/official_mpe.json
```

说明实验同时运行纯文本模式、结构化模式、围堵组织记忆迁移实验、多场景组织记忆 benchmark suite，以及官方 MPE simple_spread 验证。

## 5. 查看结果

```bash
python3 - <<'PY'
import json
data = json.load(open('artifacts/benchmark.json', encoding='utf-8'))
print(json.dumps({
    'text_total': data['text_total'],
    'structured_total': data['structured_total'],
    'comparison': data['comparison'],
}, ensure_ascii=False, indent=2))
PY
```

重点说明：

- 文本字符和估算 token 节省约 63%。
- 结构化模式完成 10 次非文本状态传递。
- 共享记忆在连续任务中被命中和复用。
- 两个追捕者围堵一个逃逸者时，组织记忆把左右夹击分工迁移给新追捕者。
- 组织记忆迁移让平均围堵步数降低 16.05%，并将轨迹经验压缩为 76 bytes。
- 多场景 suite 覆盖追捕围堵、协同导航覆盖、接力运输，平均任务步数降低 46.33%，平均存储压缩 99.89%。
- 官方 `mpe2.simple_spread_v3` 中，组织记忆策略相对随机策略平均奖励提升 25.30%。

## 6. 收尾

展示实验报告：

```bash
sed -n '1,220p' docs/experiment_report.md
```

说明当前版本已经可在通用 Linux 服务器复现，后续可在 openEuler 24.03-LTS-SP3 上做最终验证。
