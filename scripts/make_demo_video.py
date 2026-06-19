#!/usr/bin/env python3
"""根据实验指标生成简短演示视频。"""

from __future__ import annotations

from pathlib import Path
import argparse
import json

import cv2
from PIL import Image, ImageDraw, ImageFont


def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def wrap(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.ImageFont, width: int) -> list[str]:
    lines: list[str] = []
    for raw in text.split("\n"):
        line = ""
        for ch in raw:
            test = line + ch
            if draw.textbbox((0, 0), test, font=fnt)[2] <= width:
                line = test
            else:
                if line:
                    lines.append(line)
                line = ch
        if line:
            lines.append(line)
    return lines


def frame(title: str, bullets: list[str], metrics: dict, w: int = 1280, h: int = 720) -> Image.Image:
    img = Image.new("RGB", (w, h), "#f7f9fb")
    draw = ImageDraw.Draw(img)
    title_font = font(42)
    body_font = font(27)
    small_font = font(21)

    draw.rectangle((0, 0, w, 86), fill="#1f4e79")
    draw.text((48, 22), title, font=title_font, fill="white")
    y = 120
    for item in bullets:
        draw.ellipse((54, y + 10, 66, y + 22), fill="#2f7d32")
        for line in wrap(draw, item, body_font, w - 145):
            draw.text((82, y), line, font=body_font, fill="#1c2630")
            y += 40
        y += 8

    comp = metrics["comparison"]
    box_y = h - 158
    draw.rounded_rectangle((48, box_y, w - 48, h - 42), radius=10, fill="#e9f2fb", outline="#9db9d3", width=2)
    summary = (
        f"通信字符降低 {comp['char_reduction_rate'] * 100:.2f}% | "
        f"估计耗时降低 {comp['estimated_total_time_reduction_rate'] * 100:.2f}% | "
        f"早停 {int(comp.get('adaptive_early_stops', 0))} 次 | "
        f"跳过阶段 {int(comp.get('adaptive_stage_skips', 0))} 个"
    )
    draw.text((72, box_y + 38), summary, font=small_font, fill="#17324d")
    return img


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    metrics = json.loads(args.metrics.read_text(encoding="utf-8"))
    comp = metrics["comparison"]
    slides = [
        (
            "多智能体低开销协作原型",
            [
                "实现 Planner、Retriever、Executor、Summarizer 四个 Agent，覆盖规划、检索、执行和总结。",
                "结构化协议只传动作、任务 ID、紧凑结果、能力摘要和记忆 ID，避免长文本反复搬运。",
            ],
        ),
        (
            "服务器与真实模型",
            [
                "主实验路径：/data2/wqx/multi_agent_low_overhead/results/server_run_gpu2_adaptive_memory",
                "主实验 GPU：CUDA_VISIBLE_DEVICES=2，2 号 GPU 为 A800 80GB。",
                "真实模型：Qwen3-8B，Planner 和 Summarizer 由真实模型生成。",
            ],
        ),
        (
            "核心创新点",
            [
                "共享记忆使用 expected_memory_groups 标注，输出 Precision@K、Recall@K、MRR、NDCG。",
                "渐进式记忆按关键词、标签、语义向量三阶段读取。",
                "新增置信门控：每阶段记录 memory_audit，证据足够时提前停止后续读取。",
            ],
        ),
        (
            "自适应记忆结果",
            [
                f"结构化模式触发早停 {int(comp.get('adaptive_early_stops', 0))} 次，跳过 {int(comp.get('adaptive_stage_skips', 0))} 个读取阶段。",
                f"平均记忆置信度 {comp.get('avg_memory_confidence', 0.0):.3f}，阶段跳过率 {comp.get('adaptive_skip_rate', 0.0) * 100:.2f}%。",
                f"记忆 Recall@K {comp['memory_recall_at_k'] * 100:.2f}%，MRR {comp['memory_mrr']:.3f}，NDCG {comp['memory_ndcg']:.3f}。",
            ],
        ),
    ]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(args.out), cv2.VideoWriter_fourcc(*"mp4v"), 1.0, (1280, 720))
    for title, bullets in slides:
        img = frame(title, bullets, metrics)
        arr = cv2.cvtColor(__import__("numpy").array(img), cv2.COLOR_RGB2BGR)
        for _ in range(4):
            writer.write(arr)
    writer.release()
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
