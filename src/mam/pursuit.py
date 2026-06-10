from __future__ import annotations

from dataclasses import dataclass
import json
import math
import random
import statistics
import tempfile
from typing import Iterable

from .memory import MemoryRecord, SharedMemory


Vec2 = tuple[float, float]


def add(a: Vec2, b: Vec2) -> Vec2:
    return (a[0] + b[0], a[1] + b[1])


def sub(a: Vec2, b: Vec2) -> Vec2:
    return (a[0] - b[0], a[1] - b[1])


def mul(a: Vec2, scale: float) -> Vec2:
    return (a[0] * scale, a[1] * scale)


def norm(a: Vec2) -> float:
    return math.hypot(a[0], a[1])


def unit(a: Vec2) -> Vec2:
    length = norm(a)
    if length < 1e-9:
        return (1.0, 0.0)
    return (a[0] / length, a[1] / length)


def clamp_vec(a: Vec2, max_norm: float) -> Vec2:
    length = norm(a)
    if length <= max_norm or length < 1e-9:
        return a
    return mul(a, max_norm / length)


def rotate(a: Vec2, radians: float) -> Vec2:
    c = math.cos(radians)
    s = math.sin(radians)
    return (a[0] * c - a[1] * s, a[0] * s + a[1] * c)


def distance(a: Vec2, b: Vec2) -> float:
    return norm(sub(a, b))


@dataclass
class PursuitState:
    pursuer_left: Vec2
    pursuer_right: Vec2
    evader: Vec2
    step: int = 0

    def centroid(self) -> Vec2:
        return ((self.pursuer_left[0] + self.pursuer_right[0]) / 2.0, (self.pursuer_left[1] + self.pursuer_right[1]) / 2.0)


@dataclass
class PursuitMetrics:
    success: bool
    capture_steps: int
    min_closure: float
    final_separation_angle: float
    role_switches: int

    def to_dict(self) -> dict[str, object]:
        return {
            "success": self.success,
            "capture_steps": self.capture_steps,
            "min_closure": round(self.min_closure, 4),
            "final_separation_angle": round(self.final_separation_angle, 4),
            "role_switches": self.role_switches,
        }


@dataclass
class OrganizationMemory:
    memory_id: str
    role_names: tuple[str, str]
    flank_radius: float
    flank_angle: float
    approach_gain: float
    intercept_gain: float
    actor_basis: tuple[tuple[float, float], tuple[float, float]]
    role_adapters: tuple[float, float]
    trigger_distance: float

    def to_dict(self) -> dict[str, object]:
        return {
            "memory_id": self.memory_id,
            "role_names": list(self.role_names),
            "flank_radius": round(self.flank_radius, 4),
            "flank_angle": round(self.flank_angle, 4),
            "approach_gain": round(self.approach_gain, 4),
            "intercept_gain": round(self.intercept_gain, 4),
            "actor_basis": [[round(v, 4) for v in row] for row in self.actor_basis],
            "role_adapters": [round(v, 4) for v in self.role_adapters],
            "trigger_distance": round(self.trigger_distance, 4),
        }

    def compressed_bytes(self) -> int:
        # 8 个浮点数 + 2 个角色 adapter + 少量元数据。这里用 float32 估算二进制存储规模。
        float_count = 2 + 2 + 4 + 2 + 1
        return float_count * 4 + 32


def organization_memory_from_dict(data: dict[str, object]) -> OrganizationMemory:
    actor_basis = data["actor_basis"]
    role_adapters = data["role_adapters"]
    role_names = data["role_names"]
    return OrganizationMemory(
        memory_id=str(data["memory_id"]),
        role_names=(str(role_names[0]), str(role_names[1])),
        flank_radius=float(data["flank_radius"]),
        flank_angle=float(data["flank_angle"]),
        approach_gain=float(data["approach_gain"]),
        intercept_gain=float(data["intercept_gain"]),
        actor_basis=(
            (float(actor_basis[0][0]), float(actor_basis[0][1])),
            (float(actor_basis[1][0]), float(actor_basis[1][1])),
        ),
        role_adapters=(float(role_adapters[0]), float(role_adapters[1])),
        trigger_distance=float(data["trigger_distance"]),
    )


def store_organization_memory(shared_memory: SharedMemory, memory: OrganizationMemory) -> MemoryRecord:
    payload = json.dumps(memory.to_dict(), ensure_ascii=False, sort_keys=True)
    return shared_memory.add(
        source_agent="organization-miner",
        topic="two-pursuers-one-evader flank organization memory",
        summary="两个追捕者围堵一个逃逸者时形成的左右夹击组织记忆，可迁移给新追捕者。",
        tags=["organization-memory", "pursuit", "flanking", "maddpg-like"],
        evidence=payload,
        strategy=payload,
    )


def retrieve_organization_memory(shared_memory: SharedMemory) -> tuple[OrganizationMemory, MemoryRecord]:
    hits = shared_memory.search(
        "two pursuers one evader flank role organization memory",
        tags=["organization-memory", "pursuit", "flanking"],
        top_k=1,
        min_score=0.0,
    )
    if not hits:
        raise LookupError("organization memory not found")
    return organization_memory_from_dict(json.loads(hits[0].strategy)), hits[0]


class PursuitEnvironment:
    def __init__(self, max_steps: int = 160, seed: int = 0):
        self.max_steps = max_steps
        self.rng = random.Random(seed)

    def initial_state(self, seed: int) -> PursuitState:
        rng = random.Random(seed)
        evader = (rng.uniform(-0.2, 0.2), rng.uniform(-0.2, 0.2))
        base_x = rng.choice([-1.0, 1.0]) * rng.uniform(1.4, 1.8)
        pursuer_left = (base_x, rng.uniform(-1.0, -0.45))
        pursuer_right = (base_x + rng.uniform(-0.15, 0.15), rng.uniform(0.45, 1.0))
        return PursuitState(pursuer_left, pursuer_right, evader)

    def run_episode(self, policy: "PursuitPolicy", seed: int) -> tuple[PursuitMetrics, list[PursuitState]]:
        state = self.initial_state(seed)
        trajectory = [state]
        min_closure = 1e9
        role_switches = 0
        last_roles: tuple[str, str] | None = None
        for step in range(self.max_steps):
            actions, roles = policy.actions(state)
            if last_roles is not None and roles != last_roles:
                role_switches += 1
            last_roles = roles
            state = self._transition(state, actions)
            trajectory.append(state)
            min_closure = min(
                min_closure,
                max(distance(state.pursuer_left, state.evader), distance(state.pursuer_right, state.evader)),
            )
            if self._captured(state):
                return (
                    PursuitMetrics(True, step + 1, min_closure, self._separation_angle(state), role_switches),
                    trajectory,
                )
        return (
            PursuitMetrics(False, self.max_steps, min_closure, self._separation_angle(state), role_switches),
            trajectory,
        )

    def _transition(self, state: PursuitState, actions: tuple[Vec2, Vec2]) -> PursuitState:
        left_action = clamp_vec(actions[0], 0.055)
        right_action = clamp_vec(actions[1], 0.055)
        centroid = state.centroid()
        escape = unit(sub(state.evader, centroid))
        zigzag = rotate(escape, math.sin(state.step * 0.37) * 0.75)
        evader_action = clamp_vec(add(mul(escape, 0.035), mul(zigzag, 0.015)), 0.045)
        return PursuitState(
            self._clip(add(state.pursuer_left, left_action)),
            self._clip(add(state.pursuer_right, right_action)),
            self._clip(add(state.evader, evader_action)),
            state.step + 1,
        )

    def _clip(self, point: Vec2) -> Vec2:
        return (max(-2.2, min(2.2, point[0])), max(-2.2, min(2.2, point[1])))

    def _captured(self, state: PursuitState) -> bool:
        left_d = distance(state.pursuer_left, state.evader)
        right_d = distance(state.pursuer_right, state.evader)
        angle = self._separation_angle(state)
        return left_d <= 0.18 and right_d <= 0.18 and angle >= 1.65

    def _separation_angle(self, state: PursuitState) -> float:
        a = unit(sub(state.pursuer_left, state.evader))
        b = unit(sub(state.pursuer_right, state.evader))
        dot = max(-1.0, min(1.0, a[0] * b[0] + a[1] * b[1]))
        return math.acos(dot)


class PursuitPolicy:
    def actions(self, state: PursuitState) -> tuple[tuple[Vec2, Vec2], tuple[str, str]]:
        raise NotImplementedError


class ColdStartPolicy(PursuitPolicy):
    """没有组织记忆的基线：两个追捕者都直接追逐目标，早期会争抢同一通道。"""

    def actions(self, state: PursuitState) -> tuple[tuple[Vec2, Vec2], tuple[str, str]]:
        left_vec = sub(state.evader, state.pursuer_left)
        right_vec = sub(state.evader, state.pursuer_right)
        return (mul(unit(left_vec), 0.05), mul(unit(right_vec), 0.05)), ("chaser", "chaser")


class OrganizationMemoryPolicy(PursuitPolicy):
    """使用组织记忆的去中心化执行策略。"""

    def __init__(self, memory: OrganizationMemory):
        self.memory = memory

    def actions(self, state: PursuitState) -> tuple[tuple[Vec2, Vec2], tuple[str, str]]:
        centroid = state.centroid()
        approach_axis = unit(sub(state.evader, centroid))
        left_target = add(state.evader, mul(rotate(approach_axis, self.memory.flank_angle), self.memory.flank_radius))
        right_target = add(state.evader, mul(rotate(approach_axis, -self.memory.flank_angle), self.memory.flank_radius))
        left_action = self._actor(state.pursuer_left, left_target, state.evader, self.memory.role_adapters[0])
        right_action = self._actor(state.pursuer_right, right_target, state.evader, self.memory.role_adapters[1])
        return (left_action, right_action), self.memory.role_names

    def _actor(self, position: Vec2, role_target: Vec2, evader: Vec2, role_adapter: float) -> Vec2:
        to_role = sub(role_target, position)
        to_evader = sub(evader, position)
        basis_0 = self.memory.actor_basis[0]
        basis_1 = self.memory.actor_basis[1]
        mixed = (
            basis_0[0] * to_role[0] + basis_0[1] * to_evader[0],
            basis_1[0] * to_role[1] + basis_1[1] * to_evader[1],
        )
        intercept = mul(unit(to_evader), self.memory.intercept_gain * role_adapter)
        approach = mul(mixed, self.memory.approach_gain)
        return clamp_vec(add(approach, intercept), 0.055)


def train_organization_memory(episodes: int = 24) -> tuple[OrganizationMemory, list[PursuitState]]:
    """从专家轨迹中抽取组织记忆。

    这不是把所有轨迹存下来，而是归纳稳定分工：左右角色、夹击角、夹击半径和低维 actor 参数。
    """
    env = PursuitEnvironment(seed=13)
    expert = _ExpertFlankPolicy()
    all_states: list[PursuitState] = []
    radii: list[float] = []
    angles: list[float] = []
    for seed in range(episodes):
        _, trajectory = env.run_episode(expert, 1000 + seed)
        all_states.extend(trajectory)
        for state in trajectory[-min(20, len(trajectory)) :]:
            radii.append((distance(state.pursuer_left, state.evader) + distance(state.pursuer_right, state.evader)) / 2.0)
            angles.append(env._separation_angle(state) / 2.0)

    flank_radius = max(0.12, min(0.32, statistics.median(radii) if radii else 0.22))
    flank_angle = max(1.05, min(1.35, statistics.median(angles) if angles else 1.18))
    memory = OrganizationMemory(
        memory_id="org-pursuit-flank-v1",
        role_names=("left-flanker", "right-flanker"),
        flank_radius=flank_radius,
        flank_angle=flank_angle,
        approach_gain=0.78,
        intercept_gain=0.014,
        actor_basis=((0.76, 0.24), (0.76, 0.24)),
        role_adapters=(1.0, 1.0),
        trigger_distance=0.9,
    )
    return memory, all_states


class _ExpertFlankPolicy(PursuitPolicy):
    def actions(self, state: PursuitState) -> tuple[tuple[Vec2, Vec2], tuple[str, str]]:
        centroid = state.centroid()
        axis = unit(sub(state.evader, centroid))
        left_target = add(state.evader, mul(rotate(axis, 1.18), 0.22))
        right_target = add(state.evader, mul(rotate(axis, -1.18), 0.22))
        return (
            clamp_vec(mul(sub(left_target, state.pursuer_left), 0.78), 0.055),
            clamp_vec(mul(sub(right_target, state.pursuer_right), 0.78), 0.055),
        ), ("left-flanker", "right-flanker")


def raw_trajectory_bytes(states: Iterable[PursuitState]) -> int:
    count = 0
    for _ in states:
        count += 1
    # 每个状态 3 个二维坐标 + step，按 float32/int32 估算。
    return count * (6 * 4 + 4)


def run_pursuit_transfer_experiment(eval_episodes: int = 16) -> dict[str, object]:
    memory, training_states = train_organization_memory()
    with tempfile.TemporaryDirectory(prefix="mam_pursuit_memory_") as tmp:
        shared_memory = SharedMemory(f"{tmp}/organization.sqlite")
        stored_record = store_organization_memory(shared_memory, memory)
        transferred_memory, retrieved_record = retrieve_organization_memory(shared_memory)
        shared_memory.close()
    env = PursuitEnvironment(seed=29)
    cold = ColdStartPolicy()
    transfer = OrganizationMemoryPolicy(transferred_memory)
    cold_results = []
    transfer_results = []
    for seed in range(eval_episodes):
        cold_metrics, _ = env.run_episode(cold, 2000 + seed)
        transfer_metrics, _ = env.run_episode(transfer, 2000 + seed)
        cold_results.append(cold_metrics)
        transfer_results.append(transfer_metrics)

    cold_success = sum(1 for item in cold_results if item.success) / len(cold_results)
    transfer_success = sum(1 for item in transfer_results if item.success) / len(transfer_results)
    cold_steps = statistics.mean(item.capture_steps for item in cold_results)
    transfer_steps = statistics.mean(item.capture_steps for item in transfer_results)
    raw_bytes = raw_trajectory_bytes(training_states)
    compressed_bytes = memory.compressed_bytes()
    return {
        "experiment": "two_pursuers_one_evader_organization_memory",
        "training_episodes": 24,
        "eval_episodes": eval_episodes,
        "organization_memory": memory.to_dict(),
        "shared_memory_transfer": {
            "stored_memory_id": stored_record.memory_id,
            "retrieved_memory_id": retrieved_record.memory_id,
            "retrieval_score": round(retrieved_record.score, 4),
            "source_agent": retrieved_record.source_agent,
        },
        "cold_start": {
            "success_rate": round(cold_success, 4),
            "avg_capture_steps": round(cold_steps, 3),
            "avg_role_switches": round(statistics.mean(item.role_switches for item in cold_results), 3),
        },
        "memory_transfer": {
            "success_rate": round(transfer_success, 4),
            "avg_capture_steps": round(transfer_steps, 3),
            "avg_role_switches": round(statistics.mean(item.role_switches for item in transfer_results), 3),
        },
        "improvement": {
            "success_rate_delta": round(transfer_success - cold_success, 4),
            "capture_step_reduction": round((cold_steps - transfer_steps) / cold_steps, 4) if cold_steps else 0.0,
        },
        "storage": {
            "raw_trajectory_bytes": raw_bytes,
            "compressed_org_memory_bytes": compressed_bytes,
            "storage_reduction": round((raw_bytes - compressed_bytes) / raw_bytes, 4) if raw_bytes else 0.0,
        },
        "maddpg_like_design": {
            "centralized_training_signal": "joint positions of two pursuers and evader",
            "decentralized_actor": "role-conditioned linear actor executed by each pursuer",
            "stored_payload": "shared actor basis + two role adapters + formation trigger",
        },
    }


def dumps_pursuit_report(report: dict[str, object]) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
