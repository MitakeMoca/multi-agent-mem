#!/usr/bin/env python3
"""探测远端 Python 环境和本地模型。"""

from __future__ import annotations

from pathlib import Path
import importlib.util
import json
import os
import sys


def main() -> int:
    mods = ["torch", "transformers", "accelerate", "sentence_transformers", "modelscope", "peft"]
    info = {
        "executable": sys.executable,
        "python": sys.version.split()[0],
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES", ""),
        "modules": {m: importlib.util.find_spec(m) is not None for m in mods},
        "models": [],
    }
    for root in ["/data2/wqx/models", "/home/omnisky/wqx/models", "/data2/wqx", "/home/omnisky"]:
        base = Path(root)
        if not base.exists():
            continue
        for cfg in list(base.glob("**/config.json"))[:80]:
            model_dir = cfg.parent
            has_weight = any(model_dir.glob("*.safetensors")) or any(model_dir.glob("pytorch_model*.bin"))
            info["models"].append({"path": str(model_dir), "has_weight": has_weight})
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
