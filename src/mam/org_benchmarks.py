from __future__ import annotations

from dataclasses import dataclass
import json
import math
import random
import statistics
import tempfile
from typing import Callable

from .logging import log, INFO, DEBUG
from .geom import Vec2, add, sub, mul, norm, unit, clamp, distance
from .memory import SharedMemory
from .organization import OrganizationMemoryModel, retrieve_organization_model, store_organization_model
from .pursuit import run_pursuit_transfer_experiment

__all__ = ["run_organization_benchmark_suite", "ScenarioSummary", "dumps_org_suite"]


@dataclass
class ScenarioSummary:
    scenario: str
    cold_score: float
    transfer_score: float
    cold_steps: float
    transfer_steps: float
    raw_bytes: int
    compressed_bytes: int
    retrieved_memory_id: str
    retrieval_score: float

    def to_dict(self) -> dict[str, object]:
        step_reduction = (self.cold_steps - self.transfer_steps) / self.cold_steps if self.cold_steps else 0.0
        storage_reduction = (self.raw_bytes - self.compressed_bytes) / self.raw_bytes if self.raw_bytes else 0.0
        return {
            "scenario": self.scenario,
            "cold_score": round(self.cold_score, 4),
            "transfer_score": round(self.transfer_score, 4),
            "cold_steps": round(self.cold_steps, 3),
            "transfer_steps": round(self.transfer_steps, 3),
            "step_reduction": round(step_reduction, 4),
            "raw_bytes": self.raw_bytes,
            "compressed_bytes": self.compressed_bytes,
            "storage_reduction": round(storage_reduction, 4),
            "retrieved_memory_id": self.retrieved_memory_id,
            "retrieval_score": round(self.retrieval_score, 4),
        }


def run_organization_benchmark_suite(
    eval_episodes: int = 16,
    pursuit_report: dict[str, object] | None = None,
) -> dict[str, object]:
    log(f"org suite start: eval_episodes={eval_episodes}", INFO)
    with tempfile.TemporaryDirectory(prefix="mam_org_suite_") as tmp:
        memory = SharedMemory(f"{tmp}/organization_suite.sqlite")
        log("running 3 scenarios...", DEBUG)
        summaries = [
            _run_pursuit(memory, eval_episodes, pursuit_report),
            _run_navigation(memory, eval_episodes),
            _run_relay(memory, eval_episodes),
        ]
        memory_count = memory.count()
        memory.close()

    scenario_dicts = [item.to_dict() for item in summaries]
    log(f"org suite done: {len(scenario_dicts)} scenarios", INFO)
    return {
        "suite": "mpe_style_organization_memory_suite",
        "scenario_count": len(scenario_dicts),
        "shared_memory_records": memory_count,
        "scenarios": scenario_dicts,
        "aggregate": {
            "avg_step_reduction": round(statistics.mean(item["step_reduction"] for item in scenario_dicts), 4),
            "avg_storage_reduction": round(statistics.mean(item["storage_reduction"] for item in scenario_dicts), 4),
            "min_transfer_score": round(min(item["transfer_score"] for item in scenario_dicts), 4),
            "total_raw_bytes": sum(int(item["raw_bytes"]) for item in scenario_dicts),
            "total_compressed_bytes": sum(int(item["compressed_bytes"]) for item in scenario_dicts),
        },
    }


def _run_pursuit(memory: SharedMemory, eval_episodes: int, pre_report=None) -> ScenarioSummary:
    log("  running pursuit scenario...", DEBUG)
    report = pre_report if pre_report is not None else run_pursuit_transfer_experiment(eval_episodes=eval_episodes)
    model = OrganizationMemoryModel(
        memory_id="org-suite-pursuit-flank",
        scenario="pursuit_flank",
        roles=tuple(report["organization_memory"]["role_names"]),
        coordination_graph=(("left-flanker", "right-flanker"),),
        trigger={"distance": float(report["organization_memory"]["trigger_distance"])},
        actor_basis=tuple(v for row in report["organization_memory"]["actor_basis"] for v in row),
        role_adapters=(tuple(report["organization_memory"]["role_adapters"]),),
        payload={"source": "two_pursuers_one_evader", "rule": "flank-and-close"},
    )
    store_organization_model(memory, model)
    _, record = retrieve_organization_model(memory, "pursuit_flank")
    return ScenarioSummary(
        scenario="pursuit_flank",
        cold_score=float(report["cold_start"]["success_rate"]),
        transfer_score=float(report["memory_transfer"]["success_rate"]),
        cold_steps=float(report["cold_start"]["avg_capture_steps"]),
        transfer_steps=float(report["memory_transfer"]["avg_capture_steps"]),
        raw_bytes=int(report["storage"]["raw_trajectory_bytes"]),
        compressed_bytes=model.compressed_bytes(),
        retrieved_memory_id=record.memory_id,
        retrieval_score=record.score,
    )


def _run_navigation(memory: SharedMemory, eval_episodes: int) -> ScenarioSummary:
    log("  running navigation scenario...", DEBUG)
    model = OrganizationMemoryModel(
        memory_id="org-suite-navigation-roles",
        scenario="cooperative_navigation",
        roles=("left-cover", "center-cover", "right-cover"),
        coordination_graph=(("left-cover", "center-cover"), ("center-cover", "right-cover")),
        trigger={"cover_radius": 0.08, "max_speed": 0.065},
        actor_basis=(0.84, 0.16, 0.08),
        role_adapters=((-1.0, 0.0), (0.0, 0.0), (1.0, 0.0)),
        payload={"assignment_rule": "sort-agents-and-landmarks-by-x", "scenario_family": "MPE simple_spread"},
    )
    store_organization_model(memory, model)
    transferred, record = retrieve_organization_model(memory, "cooperative_navigation")
    cold_steps: list[int] = []
    transfer_steps: list[int] = []
    cold_success = 0
    transfer_success = 0
    raw_states = 0
    for idx in range(eval_episodes):
        env = _NavigationEnv(3000 + idx)
        c_success, c_steps, c_states = env.run(_cold_navigation_policy)
        t_success, t_steps, t_states = env.run(_navigation_memory_policy(transferred))
        cold_success += int(c_success)
        transfer_success += int(t_success)
        cold_steps.append(c_steps)
        transfer_steps.append(t_steps)
        raw_states += c_states + t_states
    return ScenarioSummary(
        scenario="cooperative_navigation",
        cold_score=cold_success / eval_episodes,
        transfer_score=transfer_success / eval_episodes,
        cold_steps=statistics.mean(cold_steps),
        transfer_steps=statistics.mean(transfer_steps),
        raw_bytes=raw_states * (6 * 4 + 6 * 4 + 4),
        compressed_bytes=model.compressed_bytes(),
        retrieved_memory_id=record.memory_id,
        retrieval_score=record.score,
    )


class _NavigationEnv:
    def __init__(self, seed: int, max_steps: int = 100):
        rng = random.Random(seed)
        self.max_steps = max_steps
        self.agents = [(rng.uniform(-0.2, 0.2), rng.uniform(-1.0, -0.75)) for _ in range(3)]
        xs = sorted([rng.uniform(-1.1, 1.1) for _ in range(3)])
        self.landmarks = [(xs[0], rng.uniform(0.55, 0.95)), (xs[1], rng.uniform(0.65, 1.05)), (xs[2], rng.uniform(0.55, 0.95))]

    def run(self, policy: Callable[[list[Vec2], list[Vec2]], list[Vec2]]) -> tuple[bool, int, int]:
        states = 0
        for step in range(self.max_steps):
            actions = policy(self.agents, self.landmarks)
            self.agents = [add(agent, clamp(action, 0.065)) for agent, action in zip(self.agents, actions)]
            states += 1
            if self._covered():
                return True, step + 1, states
        return False, self.max_steps, states

    def _covered(self) -> bool:
        return all(min(distance(agent, landmark) for agent in self.agents) <= 0.08 for landmark in self.landmarks)


def _cold_navigation_policy(agents: list[Vec2], landmarks: list[Vec2]) -> list[Vec2]:
    # 冷启动基线没有角色分配，多个 Agent 会被最近目标吸引，容易重复覆盖。
    return [mul(unit(sub(min(landmarks, key=lambda lm: distance(agent, lm)), agent)), 0.06) for agent in agents]


def _navigation_memory_policy(model: OrganizationMemoryModel) -> Callable[[list[Vec2], list[Vec2]], list[Vec2]]:
    def policy(agents: list[Vec2], landmarks: list[Vec2]) -> list[Vec2]:
        ordered_agents = sorted(range(len(agents)), key=lambda i: agents[i][0])
        ordered_landmarks = sorted(landmarks, key=lambda item: item[0])
        actions = [(0.0, 0.0)] * len(agents)
        for role_index, agent_index in enumerate(ordered_agents):
            target = ordered_landmarks[role_index]
            gain = model.actor_basis[0]
            actions[agent_index] = mul(sub(target, agents[agent_index]), gain)
        return actions

    return policy


def _run_relay(memory: SharedMemory, eval_episodes: int) -> ScenarioSummary:
    log("  running relay scenario...", DEBUG)
    model = OrganizationMemoryModel(
        memory_id="org-suite-relay-transport",
        scenario="relay_transport",
        roles=("front-scout", "left-carrier", "right-carrier"),
        coordination_graph=(("front-scout", "left-carrier"), ("front-scout", "right-carrier"), ("left-carrier", "right-carrier")),
        trigger={"payload_radius": 0.16, "handoff_distance": 0.42},
        actor_basis=(0.72, 0.18, 0.10),
        role_adapters=((0.18, 0.0), (-0.08, -0.10), (-0.08, 0.10)),
        payload={"transport_rule": "triangular-support", "scenario_family": "cooperative payload transport"},
    )
    store_organization_model(memory, model)
    transferred, record = retrieve_organization_model(memory, "relay_transport")
    cold_steps: list[int] = []
    transfer_steps: list[int] = []
    cold_success = 0
    transfer_success = 0
    raw_states = 0
    for idx in range(eval_episodes):
        c_success, c_steps, c_states = _run_relay_episode(4000 + idx, None)
        t_success, t_steps, t_states = _run_relay_episode(4000 + idx, transferred)
        cold_success += int(c_success)
        transfer_success += int(t_success)
        cold_steps.append(c_steps)
        transfer_steps.append(t_steps)
        raw_states += c_states + t_states
    return ScenarioSummary(
        scenario="relay_transport",
        cold_score=cold_success / eval_episodes,
        transfer_score=transfer_success / eval_episodes,
        cold_steps=statistics.mean(cold_steps),
        transfer_steps=statistics.mean(transfer_steps),
        raw_bytes=raw_states * (3 * 2 * 4 + 2 * 4 + 2 * 4 + 4),
        compressed_bytes=model.compressed_bytes(),
        retrieved_memory_id=record.memory_id,
        retrieval_score=record.score,
    )


def _run_relay_episode(seed: int, model: OrganizationMemoryModel | None, max_steps: int = 140) -> tuple[bool, int, int]:
    rng = random.Random(seed)
    payload = (rng.uniform(-1.0, -0.75), rng.uniform(-0.08, 0.08))
    goal = (rng.uniform(0.85, 1.1), rng.uniform(-0.08, 0.08))
    agents = [(payload[0] - 0.25, payload[1] + offset) for offset in (-0.16, 0.0, 0.16)]
    states = 0
    for step in range(max_steps):
        if model is None:
            target_offsets = [(0.0, 0.0), (-0.02, 0.0), (0.02, 0.0)]
            speed_scale = 0.026
        else:
            target_offsets = [tuple(row) for row in model.role_adapters]
            speed_scale = 0.043
        direction = unit(sub(goal, payload))
        desired = [add(payload, offset) for offset in target_offsets]
        agents = [add(agent, clamp(mul(sub(target, agent), 0.74), 0.06)) for agent, target in zip(agents, desired)]
        formation_error = statistics.mean(distance(agent, target) for agent, target in zip(agents, desired))
        support = max(0.35, 1.0 - formation_error * 2.6)
        payload = add(payload, mul(direction, speed_scale * support))
        states += 1
        if distance(payload, goal) <= 0.08:
            return True, step + 1, states
    return False, max_steps, states


def dumps_org_suite(report: dict[str, object]) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
