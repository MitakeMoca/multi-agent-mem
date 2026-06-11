from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mam.agents import build_tasks, ToolAgent
from mam.benchmark import run_benchmark
from mam.geom import add, sub, mul, norm, unit, clamp, distance, rotate
from mam.memory import MemoryRecord, SharedMemory
from mam.org_benchmarks import run_organization_benchmark_suite
from mam.official_mpe import run_official_mpe_benchmark
from mam.protocol import parse_text_payload
from mam.pursuit import run_pursuit_transfer_experiment, train_organization_memory
from mam.runtime import MultiAgentRuntime
from mam.state_exchange import StateExchange
from mam.vectors import cosine, embed_text, pack_vector


class CoreTest(unittest.TestCase):

    def test_vector_is_non_empty_and_packable(self) -> None:
        v = embed_text('结构化协议和共享记忆')
        self.assertEqual(len(v), 64)
        self.assertEqual(len(pack_vector(v)), 256)

    def test_memory_search_by_tag_and_semantic_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory = SharedMemory(Path(tmp) / 'mem.sqlite')
            memory.add('summarizer', '共享记忆', 'SQLite 保存记忆单元', ['memory', 'sqlite'], 'evidence', 'strategy')
            hits = memory.search('如何复用共享记忆', ['memory'])
            memory.close()
        self.assertGreaterEqual(len(hits), 1)
        self.assertEqual(hits[0].source_agent, 'summarizer')

    def test_structured_runtime_runs_one_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = MultiAgentRuntime(Path(tmp) / 'mem.sqlite', 'structured')
            result = runtime.run_task(build_tasks(1)[0])
            runtime.close()
        self.assertEqual(result['mode'], 'structured')
        self.assertGreater(result['metrics']['state_transfers'], 0)

    def test_benchmark_covers_ten_rounds(self) -> None:
        report = run_benchmark(10)
        self.assertEqual(report['rounds'], 10)
        self.assertEqual(report['requirements_covered']['related_task_groups'], 2)
        self.assertGreater(report['comparison']['char_saving_rate'], 0.0)

    def test_pursuit_organization_memory_is_compact(self) -> None:
        memory, states = train_organization_memory(episodes=4)
        self.assertEqual(memory.role_names, ('left-flanker', 'right-flanker'))
        self.assertGreater(len(states), 0)
        self.assertLess(memory.compressed_bytes(), len(states) * 28)

    def test_pursuit_transfer_improves_capture_steps(self) -> None:
        report = run_pursuit_transfer_experiment(eval_episodes=6)
        self.assertEqual(report['shared_memory_transfer']['source_agent'], 'organization-miner')
        self.assertEqual(
            report['shared_memory_transfer']['stored_memory_id'],
            report['shared_memory_transfer']['retrieved_memory_id'],
        )
        self.assertGreater(report['storage']['storage_reduction'], 0.9)
        self.assertGreaterEqual(report['memory_transfer']['success_rate'], report['cold_start']['success_rate'])
        self.assertGreater(report['improvement']['capture_step_reduction'], 0.05)

    def test_organization_benchmark_suite_has_multiple_scenarios(self) -> None:
        report = run_organization_benchmark_suite(eval_episodes=6)
        self.assertEqual(report['scenario_count'], 3)
        self.assertEqual(report['shared_memory_records'], 3)
        self.assertGreater(report['aggregate']['avg_step_reduction'], 0.05)
        self.assertGreater(report['aggregate']['avg_storage_reduction'], 0.9)
        scenarios = {item['scenario']: item for item in report['scenarios']}
        self.assertIn('pursuit_flank', scenarios)
        self.assertIn('cooperative_navigation', scenarios)
        self.assertIn('relay_transport', scenarios)

    def test_official_mpe_adapter_reports_status(self) -> None:
        report = run_official_mpe_benchmark(episodes=1, max_cycles=2)
        self.assertIn(report['status'], {'ok', 'unavailable'})

    def test_cosine_edge_cases(self) -> None:
        self.assertEqual(cosine([], []), 0.0)
        self.assertEqual(cosine([1.0], []), 0.0)
        self.assertEqual(cosine([1.0], [1.0, 2.0]), 0.0)
        zero_vec = [0.0] * 64
        self.assertEqual(cosine(zero_vec, embed_text('hello')), 0.0)

    def test_state_exchange_get_missing_raises(self) -> None:
        exchange = StateExchange()
        with self.assertRaises(LookupError) as ctx:
            exchange.get('nonexistent')
        self.assertIn('nonexistent', str(ctx.exception))

    def test_state_exchange_publish_and_get(self) -> None:
        from mam.vectors import StatePacket
        packet = StatePacket('s1', 'test-topic', embed_text('test'), 'planner')
        exchange = StateExchange()
        byte_size = exchange.publish(packet)
        self.assertEqual(byte_size, packet.byte_size)
        retrieved = exchange.get('s1')
        self.assertEqual(retrieved.state_id, 's1')
        self.assertEqual(retrieved.topic, 'test-topic')

    def test_memory_search_with_missing_tags_json(self) -> None:
        import sqlite3
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / 'corrupt.sqlite'
            conn = sqlite3.connect(str(db_path))
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute(
                'CREATE TABLE IF NOT EXISTS memories ('
                'memory_id, source_agent, created_at, topic, summary, '
                'tags_json, evidence, strategy, vector_blob)'
            )
            conn.execute(
                'INSERT INTO memories VALUES (?,?,?,?,?,?,?,?,?)',
                ('mid1', 'test', '2024-01-01', 'topic', 'summary',
                 'not-valid-json', 'ev', 'str', pack_vector(embed_text('test topic summary ev str'))),
            )
            conn.commit()
            conn.close()
            memory = SharedMemory(db_path)
            hits = memory.search('topic summary', tags=(), top_k=3)
            memory.close()
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].memory_id, 'mid1')

    def test_memory_record_to_dict_with_without_score(self) -> None:
        record = MemoryRecord(
            'mid1', 'summarizer', '2024-01-01', 'topic', 'summary',
            ['tag1'], 'evidence', 'strategy', score=0.42,
        )
        d_no_score = record.to_dict()
        self.assertNotIn('score', d_no_score)
        d_with_score = record.to_dict(include_score=True)
        self.assertIn('score', d_with_score)
        self.assertEqual(d_with_score['score'], 0.42)

    def test_codeact_basic_expressions(self) -> None:
        tool = ToolAgent()
        self.assertEqual(tool.run_codeact('abs(-5)'), 5)
        self.assertEqual(tool.run_codeact('min(1, 2, 3)'), 1)
        self.assertEqual(tool.run_codeact('max(1, 2, 3)'), 3)
        self.assertEqual(tool.run_codeact('sum([1, 2, 3])'), 6)
        self.assertEqual(tool.run_codeact('round(3.7)'), 4)
        self.assertEqual(tool.run_codeact('len([1,2,3])'), 3)
        self.assertEqual(tool.run_codeact('min(max(1, 3), 2)'), 2)
        self.assertEqual(tool.run_codeact('abs(round(-3.8))'), 4)

    def test_codeact_forbidden_builtins_blocked(self) -> None:
        tool = ToolAgent()
        with self.assertRaises((NameError, AttributeError)):
            tool.run_codeact("__import__('os').system('echo pwned')")

    def test_text_mode_runtime_runs_one_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime = MultiAgentRuntime(Path(tmp) / 'text_mem.sqlite', 'text')
            result = runtime.run_task(build_tasks(1)[0])
            runtime.close()
        self.assertEqual(result['mode'], 'text')
        self.assertEqual(result['metrics']['state_transfers'], 0)

    def test_runtime_context_manager(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with MultiAgentRuntime(Path(tmp) / 'ctx.sqlite', 'structured') as runtime:
                result = runtime.run_task(build_tasks(1)[0])
            self.assertEqual(result['mode'], 'structured')

    def test_parse_text_payload(self) -> None:
        result = parse_text_payload('agent 和 protocol 和 memory 状态交换')
        self.assertIn('word_count', result)
        self.assertGreater(result['word_count'], 0)
        self.assertIn('keyword_hits', result)
        self.assertIn('fingerprint', result)
        self.assertEqual(len(result['fingerprint']), 32)
        empty_result = parse_text_payload('')
        self.assertEqual(empty_result['word_count'], 0)
        self.assertEqual(empty_result['keyword_hits'], 0)

    def test_geom_utilities(self) -> None:
        a: tuple[float, float] = (3.0, 4.0)
        b: tuple[float, float] = (1.0, 2.0)
        self.assertEqual(add(a, b), (4.0, 6.0))
        self.assertEqual(sub(a, b), (2.0, 2.0))
        self.assertEqual(mul(a, 2.0), (6.0, 8.0))
        self.assertEqual(norm(a), 5.0)
        self.assertEqual(unit(a), (0.6, 0.8))
        clamped = clamp(a, 3.0)
        self.assertAlmostEqual(clamped[0], 1.8, places=5)
        self.assertAlmostEqual(clamped[1], 2.4, places=5)
        self.assertAlmostEqual(distance(a, b), 2.828, places=3)
        rotated = rotate((1.0, 0.0), 3.14159)
        self.assertLess(rotated[0], -0.99)
        zero = (0.0, 0.0)
        self.assertEqual(unit(zero), (1.0, 0.0))
        self.assertEqual(norm(zero), 0.0)

    def test_metrics_merge(self) -> None:
        from mam.protocol import Metrics
        a = Metrics(message_count=5, text_chars=100, memory_queries=2, memory_hits=1, elapsed_ms=10.0)
        b = Metrics(message_count=3, text_chars=60, memory_queries=1, memory_hits=1, elapsed_ms=5.0)
        a.merge(b)
        self.assertEqual(a.message_count, 8)
        self.assertEqual(a.text_chars, 160)
        self.assertEqual(a.memory_queries, 3)
        self.assertEqual(a.memory_hits, 2)
        self.assertEqual(a.elapsed_ms, 15.0)

    def test_metrics_to_dict(self) -> None:
        from mam.protocol import Metrics
        m = Metrics(message_count=10, text_chars=500, state_transfers=3, state_bytes=256,
                    memory_queries=5, memory_hits=2, memory_hit_queries=1, elapsed_ms=42.0)
        d = m.to_dict()
        self.assertEqual(d['message_count'], 10)
        self.assertEqual(d['text_chars'], 500)
        self.assertEqual(d['memory_hit_rate'], 0.2)
        self.assertEqual(d['memory_avg_hits_per_query'], 0.4)
        self.assertEqual(d['elapsed_ms'], 42.0)
        m2 = Metrics()
        self.assertEqual(m2.to_dict()['memory_hit_rate'], 0.0)

    def test_shared_memory_count_and_clear(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory = SharedMemory(Path(tmp) / 'cnt.sqlite')
            self.assertEqual(memory.count(), 0)
            memory.add('test', 'topic1', 'summary1', ['tag1'], 'ev', 'str')
            self.assertEqual(memory.count(), 1)
            memory.add('test', 'topic2', 'summary2', ['tag2'], 'ev', 'str')
            self.assertEqual(memory.count(), 2)
            memory.clear()
            self.assertEqual(memory.count(), 0)
            memory.close()

    def test_shared_memory_context_manager_with_exception(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                with SharedMemory(Path(tmp) / 'exc.sqlite') as memory:
                    memory.add('test', 't', 's', ['t'], 'e', 's')
                    raise ValueError('simulated error')
            except ValueError:
                pass
            with SharedMemory(Path(tmp) / 'exc.sqlite') as memory:
                self.assertEqual(memory.count(), 1)

    def test_state_exchange_count(self) -> None:
        from mam.vectors import StatePacket
        exchange = StateExchange()
        self.assertEqual(exchange.count(), 0)
        exchange.publish(StatePacket('a', 'topic', embed_text('x'), 'planner'))
        self.assertEqual(exchange.count(), 1)
        exchange.publish(StatePacket('b', 'topic', embed_text('y'), 'planner'))
        self.assertEqual(exchange.count(), 2)

    def test_state_exchange_overwrite_silent(self) -> None:
        from mam.vectors import StatePacket
        exchange = StateExchange()
        p1 = StatePacket('s1', 'topic', embed_text('x'), 'planner')
        p2 = StatePacket('s1', 'topic', embed_text('y'), 'planner')
        exchange.publish(p1)
        exchange.publish(p2)
        self.assertEqual(exchange.count(), 1)
        self.assertEqual(exchange.get('s1').origin_agent, 'planner')

    def test_codeact_nested_expressions(self) -> None:
        tool = ToolAgent()
        self.assertEqual(tool.run_codeact('abs(sum([-1, 2, -3]))'), 2)
        self.assertEqual(tool.run_codeact('max(min([1, 2]), 3)'), 3)
        self.assertEqual(tool.run_codeact('round(sum([1.5, 2.5]))'), 4)

    def test_approx_tokens(self) -> None:
        from mam.protocol import approx_tokens
        self.assertEqual(approx_tokens(''), 0)
        self.assertGreaterEqual(approx_tokens('a'), 1)
        self.assertGreaterEqual(approx_tokens('hello world'), 3)

    def test_embed_text_deterministic(self) -> None:
        v1 = embed_text('确定性测试')
        v2 = embed_text('确定性测试')
        self.assertEqual(v1, v2)
        self.assertEqual(len(v1), 64)
        v3 = embed_text('')
        self.assertEqual(len(v3), 64)
        self.assertEqual(v3, [0.0] * 64)

    def test_pursuit_environment_captured_condition(self) -> None:
        from mam.pursuit import PursuitEnvironment, ColdStartPolicy
        env = PursuitEnvironment(seed=0)
        metrics, _ = env.run_episode(ColdStartPolicy(), seed=0)
        self.assertIsInstance(metrics.capture_steps, int)
        self.assertGreaterEqual(metrics.capture_steps, 1)
        self.assertGreaterEqual(metrics.role_switches, 0)
        self.assertGreaterEqual(metrics.min_closure, 0.0)


if __name__ == '__main__':
    unittest.main()
