# 部署文档

## 1. 环境要求

- Linux 或 openEuler 兼容环境。
- Python 3.10 及以上。
- 不需要安装第三方 Python 包。

当前服务器验证环境：

- Host: `Hangzhou-A5000`
- 用户: `omnisky`
- 路径: `/data1/code/wqx/multi-agent-mem`
- Python: 3.13.2
- GPU: NVIDIA RTX A5000 x4

本项目实验不依赖 GPU。

## 2. 部署步骤

```bash
cd /data1/code/wqx
ls multi-agent-mem
cd multi-agent-mem
python3 --version
```

如果需要重新运行实验：

```bash
python3 scripts/run_benchmark.py --rounds 10 --output artifacts/benchmark.json
python3 scripts/run_pursuit_demo.py --episodes 16 --output artifacts/pursuit_transfer.json
python3 scripts/run_org_benchmark.py --episodes 16 --output artifacts/org_benchmark_suite.json
python3 scripts/run_official_mpe.py --episodes 4 --max-cycles 25 --output artifacts/official_mpe.json
```

如果需要运行测试：

```bash
python3 -m unittest discover -s tests
```

## 3. 输出文件

运行 benchmark 后会生成：

- `artifacts/benchmark.json`：完整实验结果。
- `artifacts/pursuit_transfer.json`：围堵组织记忆迁移实验结果。
- `artifacts/org_benchmark_suite.json`：多场景组织记忆 benchmark suite 结果。
- `artifacts/official_mpe.json`：官方 `mpe2.simple_spread_v3` benchmark 结果。

## 3.1 官方 MPE 依赖

服务器已安装并验证：

```bash
python3 -m pip install --user mpe2
python3 scripts/run_official_mpe.py --episodes 4 --max-cycles 25 --output artifacts/official_mpe.json
```

如果评审环境没有 `mpe2`，脚本会输出 `status: unavailable` 和安装提示，不影响自包含 benchmark suite 的复现。

终端会输出：

- 连续任务轮数。
- 文本字符节省率。
- 估算 token 节省率。
- 任务耗时节省率。
- 结构化状态传递规模。

## 4. 常见问题

### 4.1 中文显示乱码

如果 PowerShell 或 SSH 终端显示中文乱码，优先检查文件本身是否为 UTF-8。实验 JSON 使用 UTF-8 写入，不影响 Python 读取和评审复现。

### 4.2 openEuler 适配

作业最终要求 openEuler 24.03-LTS-SP3。当前版本只使用 Python 标准库，理论上可直接迁移；后续需要在 openEuler 环境执行同样两条命令作为最终验收。

### 4.3 依赖安装

本项目没有第三方依赖，不需要 `pip install`。如果评审希望以包方式运行，可临时设置：

```bash
export PYTHONPATH=$PWD/src
```

脚本入口已经自动加入 `src`，正常运行不需要手动设置。
