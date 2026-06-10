from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mam.agents import build_tasks
from mam.benchmark import run_benchmark
from mam.memory import SharedMemory
from mam.org_benchmarks import run_organization_benchmark_suite
from mam.official_mpe import run_official_mpe_benchmark
from mam.pursuit import run_pursuit_transfer_experiment, train_organization_memory
from mam.runtime import MultiAgentRuntime
from mam.vectors import embed_text, pack_vector


class CoreTest(unittest.TestCase):
    def test_vector_is_non_empty_and_packable(self) -> None:
        vector = embed_text("结构化协议和共享记忆")
        self.assertEqual(len(vector), 64)
        self.assertEqual(len(pack_vector(vector)), 256)

    def test_memory_search_by_tag_and_semantic_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory = SharedMemory(Path(tmp) / "mem.sqlite")
            memory.add("summarizer", "共享记忆", "SQLite 保存记忆单元", ["memory", "sqlite"], "evidence", "strategy")
            hits = memory.search("如何复用共享记忆", ["memory"])
            memory.close()
        self.assertGreaterEqual(len(hits), 1)
        self.assertEqual(hits[0].source_agent, "summarizer")

    def test_structured_runtime_runs_one_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = MultiAgentRuntime(Path(tmp) / "mem.sqlite", "structured")
            result = runtime.run_task(build_tasks(1)[0])
            runtime.close()
        self.assertEqual(result["mode"], "structured")
        self.assertGreater(result["metrics"]["state_transfers"], 0)

    def test_benchmark_covers_ten_rounds(self) -> None:
        report = run_benchmark(10)
        self.assertEqual(report["rounds"], 10)
        self.assertEqual(report["requirements_covered"]["related_task_groups"], 2)
        self.assertGreater(report["comparison"]["char_saving_rate"], 0.0)

    def test_pursuit_organization_memory_is_compact(self) -> None:
        memory, states = train_organization_memory(episodes=4)
        self.assertEqual(memory.role_names, ("left-flanker", "right-flanker"))
        self.assertGreater(len(states), 0)
        self.assertLess(memory.compressed_bytes(), len(states) * 28)

    def test_pursuit_transfer_improves_capture_steps(self) -> None:
        report = run_pursuit_transfer_experiment(eval_episodes=6)
        self.assertEqual(report["shared_memory_transfer"]["source_agent"], "organization-miner")
        self.assertEqual(
            report["shared_memory_transfer"]["stored_memory_id"],
            report["shared_memory_transfer"]["retrieved_memory_id"],
        )
        self.assertGreater(report["storage"]["storage_reduction"], 0.9)
        self.assertGreaterEqual(report["memory_transfer"]["success_rate"], report["cold_start"]["success_rate"])
        self.assertGreater(report["improvement"]["capture_step_reduction"], 0.05)

    def test_organization_benchmark_suite_has_multiple_scenarios(self) -> None:
        report = run_organization_benchmark_suite(eval_episodes=6)
        self.assertEqual(report["scenario_count"], 3)
        self.assertEqual(report["shared_memory_records"], 3)
        self.assertGreater(report["aggregate"]["avg_step_reduction"], 0.05)
        self.assertGreater(report["aggregate"]["avg_storage_reduction"], 0.9)
        scenarios = {item["scenario"]: item for item in report["scenarios"]}
        self.assertIn("pursuit_flank", scenarios)
        self.assertIn("cooperative_navigation", scenarios)
        self.assertIn("relay_transport", scenarios)

    def test_official_mpe_adapter_reports_status(self) -> None:
        report = run_official_mpe_benchmark(episodes=1, max_cycles=2)
        self.assertIn(report["status"], {"ok", "unavailable"})


if __name__ == "__main__":
    unittest.main()
