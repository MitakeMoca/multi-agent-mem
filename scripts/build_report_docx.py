#!/usr/bin/env python3
"""用标准库生成课程大作业 DOCX 报告。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape
import argparse
import json
import shutil
import zipfile

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_HEADER = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'


def fmt_pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def fmt_num(x: float) -> str:
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return f"{x:.3f}"


def p(text: str, style: str | None = None, bold: bool = False) -> str:
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    rpr = "<w:rPr><w:b/></w:rPr>" if bold else ""
    return f'<w:p>{ppr}<w:r>{rpr}<w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>'


def bullet(text: str) -> str:
    return p("- " + text)


def cell(text: str, bold: bool = False) -> str:
    rpr = "<w:rPr><w:b/></w:rPr>" if bold else ""
    return (
        '<w:tc><w:tcPr><w:tcW w:w="2400" w:type="dxa"/></w:tcPr>'
        f'<w:p><w:r>{rpr}<w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p></w:tc>'
    )


def table(rows: list[list[str]]) -> str:
    out = [
        "<w:tbl>",
        '<w:tblPr><w:tblW w:w="0" w:type="auto"/>'
        '<w:tblBorders><w:top w:val="single" w:sz="6" w:space="0" w:color="808080"/>'
        '<w:left w:val="single" w:sz="6" w:space="0" w:color="808080"/>'
        '<w:bottom w:val="single" w:sz="6" w:space="0" w:color="808080"/>'
        '<w:right w:val="single" w:sz="6" w:space="0" w:color="808080"/>'
        '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="B0B0B0"/>'
        '<w:insideV w:val="single" w:sz="4" w:space="0" w:color="B0B0B0"/></w:tblBorders></w:tblPr>',
    ]
    for i, row in enumerate(rows):
        out.append("<w:tr>")
        for item in row:
            out.append(cell(item, bold=(i == 0)))
        out.append("</w:tr>")
    out.append("</w:tbl>")
    return "".join(out)


def avg_llm_metric(traces: list[dict], key: str) -> float:
    rows = [t for t in traces if t.get("expected_groups")]
    if not rows:
        return 0.0
    return sum(float(t.get(key, 0.0)) for t in rows) / len(rows)


def make_body(metrics: dict) -> str:
    modes = metrics["modes"]
    text = modes["text"]
    structured = modes["structured"]
    comp = metrics["comparison"]
    llm_metrics = metrics.get("_llm", {})
    llm_traces = llm_metrics.get("traces", []) if isinstance(llm_metrics, dict) else []
    llm_task_count = len(llm_traces)
    llm_avg_elapsed = sum(float(t.get("elapsed_ms", 0.0)) for t in llm_traces) / llm_task_count if llm_task_count else 0.0

    metric_rows = [
        ["指标", "纯文本协作", "结构化协议协作"],
        ["连续任务轮数", fmt_num(text["tasks"]), fmt_num(structured["tasks"])],
        ["Agent 消息数", fmt_num(text["message_count"]), fmt_num(structured["message_count"])],
        ["文本通信字符开销", fmt_num(text["text_chars"]), fmt_num(structured["text_chars"])],
        ["非文本状态传递次数", fmt_num(text["state_transfer_count"]), fmt_num(structured["state_transfer_count"])],
        ["非文本状态数据规模", f"{fmt_num(text['state_bytes'])} B", f"{fmt_num(structured['state_bytes'])} B"],
        ["共享记忆命中率", fmt_pct(text["memory_hit_rate"]), fmt_pct(structured["memory_hit_rate"])],
        ["记忆 Precision@K", fmt_pct(text["memory_precision_at_k"]), fmt_pct(structured["memory_precision_at_k"])],
        ["记忆 Recall@K", fmt_pct(text["memory_recall_at_k"]), fmt_pct(structured["memory_recall_at_k"])],
        ["记忆 MRR", fmt_num(text["memory_mrr"]), fmt_num(structured["memory_mrr"])],
        ["记忆 NDCG", fmt_num(text["memory_ndcg"]), fmt_num(structured["memory_ndcg"])],
        ["实际读取阶段数", fmt_num(text["progressive_stage_reads"]), fmt_num(structured["progressive_stage_reads"])],
        ["自适应早停次数", fmt_num(text["adaptive_early_stops"]), fmt_num(structured["adaptive_early_stops"])],
        ["跳过读取阶段数", fmt_num(text["adaptive_stage_skips"]), fmt_num(structured["adaptive_stage_skips"])],
        ["平均记忆置信度", fmt_num(text["avg_memory_confidence"]), fmt_num(structured["avg_memory_confidence"])],
        ["阶段跳过率", fmt_pct(text["adaptive_skip_rate"]), fmt_pct(structured["adaptive_skip_rate"])],
        ["生命周期字段命中记忆数", fmt_num(text.get("lifecycle_memory_hits", 0.0)), fmt_num(structured.get("lifecycle_memory_hits", 0.0))],
        ["动态链接字段命中记忆数", fmt_num(text.get("linked_memory_hits", 0.0)), fmt_num(structured.get("linked_memory_hits", 0.0))],
        ["估计端到端处理耗时", f"{text['estimated_total_ms']:.3f} ms", f"{structured['estimated_total_ms']:.3f} ms"],
    ]

    llm_rows = [
        ["指标", "Qwen3-8B 多 Agent 实验"],
        ["运行 GPU", "2 号 GPU"],
        ["模型路径", "/home/omnisky/.cache/modelscope/hub/models/Qwen/Qwen3-8B"],
        ["任务轮数", fmt_num(float(llm_task_count))],
        ["平均单任务耗时", f"{llm_avg_elapsed:.3f} ms"],
        ["复用任务 Precision@K", fmt_pct(avg_llm_metric(llm_traces, "memory_precision_at_k"))],
        ["复用任务 Recall@K", fmt_pct(avg_llm_metric(llm_traces, "memory_recall_at_k"))],
        ["复用任务记忆置信度", fmt_num(avg_llm_metric(llm_traces, "memory_confidence"))],
        ["复用任务跳过阶段数", fmt_num(avg_llm_metric(llm_traces, "adaptive_stage_skips"))],
    ]

    files_rows = [
        ["文件", "作用"],
        ["src/malow/protocol.py", "定义结构化消息、动作、参数、结果和能力描述。"],
        ["src/malow/state.py", "实现哈希语义向量、余弦相似度和向量状态大小估算。"],
        ["src/malow/memory.py", "实现共享记忆、渐进式读取、置信门控和检索精准度评估。"],
        ["src/malow/agents.py", "实现规划、检索、执行、总结四类 Agent。"],
        ["src/malow/runtime.py", "实现纯文本模式和结构化协议模式的统一调度与指标采集。"],
        ["src/malow/llm_runtime.py", "实现真实大模型驱动的规划与总结 Agent，并传入记忆审计信息。"],
        ["src/malow/benchmark.py", "运行连续任务并输出 JSON/CSV/轨迹。"],
        ["scripts/run_llm_experiment.py", "用服务器本地大模型运行真实多 Agent 任务。"],
    ]

    literature_rows = [
        ["论文", "可借鉴方法", "本文对应设计"],
        ["Generative Agents (arXiv:2304.03442)", "记忆流、反思、规划支撑长时行为。", "共享记忆保存任务摘要、证据链和复用经验。"],
        ["Reflexion (arXiv:2303.11366)", "把失败反馈写入语言记忆供后续任务复用。", "可扩展 failure reflection 记忆，记录错误检索和低置信度任务。"],
        ["MemGPT (arXiv:2310.08560)", "借鉴操作系统分层记忆管理突破上下文限制。", "渐进式读取和置信门控可视为轻量记忆调度。"],
        ["Mem0 (arXiv:2504.19413)", "动态抽取、合并、检索长期记忆，并关注延迟和 token 成本。", "同时评估记忆命中质量、通信字符数和处理耗时。"],
        ["A-MEM (arXiv:2502.12110)", "为记忆建立动态索引、链接和演化机制。", "后续可增加 memory_links 和 link_type，形成经验图谱。"],
        ["MemOS (arXiv:2507.03724)", "把记忆视为可表示、调度、演化和版本化的系统资源。", "后续可增加 version、status、use_count、last_hit_at 等生命周期字段。"],
        ["MIRIX (arXiv:2507.07957)", "将记忆划分为 Core、Episodic、Semantic、Procedural、Resource 等类型。", "后续可增加 memory_type，并为不同记忆类型设置不同检索策略。"],
        ["AI Agents That Matter (arXiv:2407.01502)", "强调 Agent 评测要同时关注准确率、成本和可复现性。", "报告同时给出 Precision@K、Recall@K、MRR、NDCG、通信开销和阶段跳过率。"],
    ]

    parts = [
        p("国产基础软件技术与应用大作业报告", "Title", True),
        p("题目：一种面向多智能体协作的低开销通信、状态传递与自适应共享记忆机制"),
        p("学生：SY2521121 吴奇宣"),
        p(f"完成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}"),
        p("一、项目概述", "Heading1", True),
        p(
            "本项目围绕多 Agent 协作系统中的通信开销、状态传递和共享记忆复用问题，"
            "实现了一套可运行的轻量原型。系统在同一批连续任务上同时支持纯文本协作模式、"
            "结构化协议协作模式和真实大模型协作模式，并统计通信开销、状态传递、记忆检索质量、"
            "自适应读取效率和任务耗时。"
        ),
        p("二、需求覆盖情况", "Heading1", True),
        bullet("不少于 3 个 Agent：系统实现 Planner、Retriever、Executor、Summarizer 四个 Agent。"),
        bullet("结构化通信协议：ProtocolMessage 包含 sender、receiver、action、params、result、capability 等字段，并支持握手与能力发现。"),
        bullet("双模式对比：同一任务集分别运行 text 和 structured 两种模式。"),
        bullet("非文本中间状态：VectorState 使用 64 维语义向量在 Agent 间传递，结构化模式共传递 50 次，规模 12800 B。"),
        bullet("共享记忆：MemoryUnit 包含 memory_id、source_agent、created_at、task_topic、summary、tags、evidence、vector 和 metadata。"),
        bullet("记忆检索评估：为复用任务标注 expected_memory_groups，并用 Precision@K、Recall@K、MRR、NDCG 评估精准度。"),
        bullet("渐进式记忆：RetrieverAgent 按关键词、标签、语义相似度分阶段读取记忆。"),
        bullet("自适应记忆：每个阶段计算记忆置信度，证据足够时提前停止，并记录早停、跳过阶段和审计原因。"),
        bullet("真实模型执行：在服务器 2 号 GPU 上接入 Qwen3-8B，运行真实模型驱动的规划与总结 Agent。"),
        p("三、核心创新点", "Heading1", True),
        bullet("创新点 1：协议化协作与向量状态解耦。系统把 Agent 协作拆成结构化动作、紧凑参数、结果引用和 VectorState，使通信层不再依赖冗长自然语言上下文。"),
        bullet("创新点 2：可评估的共享记忆。每个连续任务标注 expected_memory_groups，检索结果不只看命中率，还用 Precision@K、Recall@K、MRR、NDCG 评估是否命中正确历史经验。"),
        bullet("创新点 3：渐进式记忆读取。RetrieverAgent 先按关键词快速筛选，再按标签收缩范围，最后用语义向量补充召回，更接近 Agent 按需读取文档和技能的过程。"),
        bullet("创新点 4：置信门控的自适应记忆。每个读取阶段输出 stage_audit，记录命中数、最高分、命中组、置信度和 continue/stop 决策；当置信度达标时提前停止后续读取。"),
        bullet("创新点 5：确定性实验与真实模型实验统一。轻量路径保证可复现的通信机制对比，Qwen3-8B 路径验证多分工流程可以接入实际大模型执行。"),
        bullet("创新点 6：面向国产基础软件的连续任务链。任务按 openEuler、数据库、WPS、TongWeb、安全基线五组初始任务和复用任务构造，能检验跨任务记忆沉淀和复用。"),
        p("四、前沿论文对比与方法吸收", "Heading1", True),
        p(
            "本项目吸收了近期多 Agent 和记忆型 Agent 研究中的关键思想，但没有直接复刻某一个系统。"
            "多 Agent 方向的 CAMEL、MetaGPT、AutoGen 和 AgentVerse 说明角色分工、通信协议和协作流程是基础；"
            "记忆型 Agent 方向的 Generative Agents、Reflexion、MemGPT、Mem0、A-MEM、MemOS 和 MIRIX 说明长期记忆正在从普通向量检索转向反思、图链接、生命周期管理和分类型记忆；"
            "AgentBench 和 AI Agents That Matter 则说明评测应同时关注任务效果、开销和可复现性。"
        ),
        table(literature_rows),
        p(
            "因此，本文把前沿方法抽象为三个可落地设计：第一，用结构化协议降低多 Agent 间自然语言长上下文传递；"
            "第二，用共享记忆、渐进式读取和置信门控实现可审计记忆复用；第三，用检索质量和通信成本共同评价系统，而不是只报告任务是否完成。"
            "后续可以沿着 A-MEM、MemOS 和 MIRIX 的思路继续扩展记忆图谱、生命周期管理和分类型记忆池。"
        ),
        p("五、系统架构设计", "Heading1", True),
        p(
            "系统由多 Agent 运行时、协议调度模块、状态交换模块、共享记忆存储与检索模块、评测模块组成。"
            "运行时负责任务分发、握手、能力发现、模式切换和指标采集；协议层将长上下文收敛为动作短码、参数、结果摘要和记忆引用；"
            "状态交换模块生成固定维度语义向量；共享记忆模块将摘要、证据链和策略沉淀为可检索单元。"
        ),
        p("六、核心实现", "Heading1", True),
        table(files_rows),
        p("七、部署与运行", "Heading1", True),
        p("服务器工作目录为 /data2/wqx/multi_agent_low_overhead，环境目录为 /data2/wqx/conda_envs/malow。主实验和真实模型实验均使用 CUDA_VISIBLE_DEVICES=2。"),
        p("主实验命令：CUDA_VISIBLE_DEVICES=2 /data2/wqx/conda_envs/malow/bin/python scripts/run_experiment.py --rounds 10 --out results/server_run_gpu2_adaptive_memory"),
        p("真实模型实验命令：CUDA_VISIBLE_DEVICES=2 /home/omnisky/anaconda3/bin/python scripts/run_llm_experiment.py --model_path /home/omnisky/.cache/modelscope/hub/models/Qwen/Qwen3-8B --rounds 2 --out results/llm_qwen3_gpu2"),
        p("八、实验结果", "Heading1", True),
        table(metric_rows),
        p(
            f"服务器实验结果显示，结构化协议模式的文本通信字符数从 {fmt_num(text['text_chars'])} 降至 {fmt_num(structured['text_chars'])}，"
            f"降低 {fmt_pct(comp['char_reduction_rate'])}；结构化模式完成 {fmt_num(comp['structured_state_transfers'])} 次非文本状态传递，"
            f"状态总规模为 {fmt_num(comp['structured_state_bytes'])} B。共享记忆命中率为 {fmt_pct(comp['memory_hit_rate'])}，"
            f"Recall@K 为 {fmt_pct(comp['memory_recall_at_k'])}，MRR 为 {fmt_num(comp['memory_mrr'])}，NDCG 为 {fmt_num(comp['memory_ndcg'])}。"
        ),
        p(
            f"新增自适应记忆机制后，结构化模式实际读取 {fmt_num(comp['progressive_stage_reads'])} 个阶段，"
            f"触发早停 {fmt_num(comp['adaptive_early_stops'])} 次，跳过 {fmt_num(comp['adaptive_stage_skips'])} 个阶段，"
            f"平均记忆置信度为 {fmt_num(comp['avg_memory_confidence'])}，阶段跳过率为 {fmt_pct(comp['adaptive_skip_rate'])}。"
            "这说明 Agent 可以在证据足够时停止继续读取，而不是固定读满全部阶段。"
        ),
        p(
            f"为吸收 A-MEM、MemOS 和 MIRIX 等工作中关于记忆链接、生命周期和分类型管理的思想，"
            f"系统为 MemoryUnit 增加了 memory_type、version、status、use_count、last_hit_at、parent_memory_id 和 linked_memory_ids 等字段。"
            f"本次结果中结构化模式命中带生命周期字段的记忆 {fmt_num(comp.get('lifecycle_memory_hits', 0.0))} 次，"
            f"命中带动态链接字段的记忆 {fmt_num(comp.get('linked_memory_hits', 0.0))} 次。"
        ),
        p(
            f"按通信解析和状态重建成本估计，端到端处理耗时从 {text['estimated_total_ms']:.3f} ms 降至 {structured['estimated_total_ms']:.3f} ms，"
            f"降低 {fmt_pct(comp['estimated_total_time_reduction_rate'])}。"
        ),
        p("九、真实大模型实验", "Heading1", True),
        table(llm_rows),
        p(
            "真实模型实验使用服务器本地 Qwen3-8B，在 2 号 GPU 上运行 2 轮任务。"
            "Planner 和 Summarizer 由大模型生成，Retriever 使用带置信门控的渐进式记忆读取，Executor 负责确定性计算。"
            "第二个复用任务成功命中 os 组历史记忆，并在轨迹中记录 memory_audit。"
        ),
        p("十、结论", "Heading1", True),
        p(
            "本项目完成了一个面向多 Agent 协作的低开销通信、非文本状态传递与自适应共享记忆复用原型。"
            "新增的置信门控机制把“Agent 按需读取文档或技能”变成可审计、可量化的过程，进一步增强了系统创新性和工程可控性。"
        ),
    ]
    return "".join(parts)


def replace_document_xml(docx_path: Path, out_path: Path, body_xml: str) -> None:
    with zipfile.ZipFile(docx_path, "r") as zin:
        names = zin.namelist()
        old_doc = zin.read("word/document.xml").decode("utf-8")
        start = old_doc.find("<w:sectPr")
        end = old_doc.rfind("</w:body>")
        if start == -1 or end == -1:
            raise RuntimeError("无法在 document.xml 中定位 sectPr/body")
        sect_pr = old_doc[start:end]
        new_doc = (
            XML_HEADER
            + f'<w:document xmlns:w="{W_NS}" '
            + 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            + 'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
            + 'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
            + "<w:body>"
            + body_xml
            + sect_pr
            + "</w:body></w:document>"
        )
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zout:
            for name in names:
                data = zin.read(name)
                if name == "word/document.xml":
                    data = new_doc.encode("utf-8")
                zout.writestr(name, data)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docx", type=Path, required=True)
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--llm-metrics", type=Path, default=None)
    args = parser.parse_args()

    metrics = json.loads(args.metrics.read_text(encoding="utf-8"))
    if args.llm_metrics and args.llm_metrics.exists():
        metrics["_llm"] = json.loads(args.llm_metrics.read_text(encoding="utf-8"))
    backup = args.docx.with_suffix(args.docx.suffix + ".bak")
    if not backup.exists():
        shutil.copy2(args.docx, backup)
    tmp = args.docx.with_suffix(".tmp.docx")
    replace_document_xml(args.docx, tmp, make_body(metrics))
    shutil.move(str(tmp), str(args.docx))
    print(f"written: {args.docx}")
    print(f"backup: {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
