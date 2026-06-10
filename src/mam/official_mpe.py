from __future__ import annotations

import importlib
import json
import random
import statistics
from typing import Any, Callable

from .organization import OrganizationMemoryModel


def mpe_backend_status() -> dict[str, object]:
    """检查官方 MPE/MPE2 benchmark 依赖是否可用。"""
    for package in ("mpe2", "pettingzoo.mpe"):
        try:
            importlib.import_module(package)
            return {"available": True, "backend": package}
        except ModuleNotFoundError:
            continue
    return {
        "available": False,
        "backend": None,
        "reason": "mpe2 and pettingzoo.mpe are not installed",
        "install_hint": "pip install mpe2",
    }


def run_official_mpe_benchmark(episodes: int = 8, max_cycles: int = 25) -> dict[str, object]:
    """在官方 MPE/MPE2 simple_spread 上评测组织记忆先验。

    如果环境未安装，返回 unavailable 结果，不影响主 benchmark。
    """
    status = mpe_backend_status()
    if not status["available"]:
        return {"suite": "official_mpe", "status": "unavailable", "backend": status}

    module = _load_env_module("simple_spread")
    random_rewards: list[float] = []
    org_rewards: list[float] = []
    for idx in range(episodes):
        random_rewards.append(_run_episode(module, 5200 + idx, max_cycles, _random_policy))
        org_rewards.append(_run_episode(module, 5200 + idx, max_cycles, _spread_organization_policy))

    random_mean = statistics.mean(random_rewards)
    org_mean = statistics.mean(org_rewards)
    improvement = (org_mean - random_mean) / abs(random_mean) if random_mean else 0.0
    model = OrganizationMemoryModel(
        memory_id="official-mpe-simple-spread-role-prior",
        scenario="official_simple_spread",
        roles=("left-landmark-cover", "center-landmark-cover", "right-landmark-cover"),
        coordination_graph=(("left-landmark-cover", "center-landmark-cover"), ("center-landmark-cover", "right-landmark-cover")),
        trigger={"max_cycles": float(max_cycles), "target_tolerance": 0.05},
        actor_basis=(1.0, 0.0, 0.0),
        role_adapters=((-1.0, 0.0), (0.0, 0.0), (1.0, 0.0)),
        payload={"official_env": "simple_spread_v3", "backend": str(status["backend"])},
    )
    return {
        "suite": "official_mpe",
        "status": "ok",
        "backend": status["backend"],
        "environment": "simple_spread_v3",
        "episodes": episodes,
        "max_cycles": max_cycles,
        "random_policy": {
            "mean_reward": round(random_mean, 4),
            "rewards": [round(v, 4) for v in random_rewards],
        },
        "organization_memory_policy": {
            "mean_reward": round(org_mean, 4),
            "rewards": [round(v, 4) for v in org_rewards],
            "memory": model.to_dict(),
            "compressed_bytes": model.compressed_bytes(),
        },
        "improvement": {
            "reward_delta": round(org_mean - random_mean, 4),
            "relative_reward_improvement": round(improvement, 4),
        },
    }


def _load_env_module(name: str) -> Any:
    errors: list[str] = []
    for module_name in (f"mpe2.{name}_v3", f"pettingzoo.mpe.{name}_v3"):
        try:
            return importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            errors.append(str(exc))
    raise ModuleNotFoundError("; ".join(errors))


def _make_env(module: Any, max_cycles: int) -> Any:
    try:
        return module.env(max_cycles=max_cycles, continuous_actions=False)
    except TypeError:
        return module.env(max_cycles=max_cycles)


def _run_episode(module: Any, seed: int, max_cycles: int, policy: Callable[[str, Any, Any], int]) -> float:
    env = _make_env(module, max_cycles)
    env.reset(seed=seed)
    total_reward = 0.0
    for agent in env.agent_iter():
        observation, reward, termination, truncation, info = env.last()
        total_reward += float(reward)
        if termination or truncation:
            action = None
        else:
            action = policy(agent, observation, env.action_space(agent))
        env.step(action)
    env.close()
    return total_reward


def _random_policy(agent: str, observation: Any, action_space: Any) -> int:
    rng = random.Random(hash((agent, str(observation)[:32])) & 0xFFFFFFFF)
    if hasattr(action_space, "n"):
        return rng.randrange(int(action_space.n))
    return action_space.sample()


def _spread_organization_policy(agent: str, observation: Any, action_space: Any) -> int:
    if not hasattr(action_space, "n") or int(action_space.n) < 5:
        return _random_policy(agent, observation, action_space)
    values = list(observation)
    if len(values) < 10:
        return 0
    try:
        agent_index = int(agent.rsplit("_", 1)[1])
    except (IndexError, ValueError):
        agent_index = 0
    # simple_spread 的观测前 4 维通常为自身速度/位置，之后是 landmark 相对位置。
    target_index = agent_index % 3
    base = 4 + target_index * 2
    if base + 1 >= len(values):
        return 0
    dx = float(values[base])
    dy = float(values[base + 1])
    if abs(dx) < 0.05 and abs(dy) < 0.05:
        return 0
    if abs(dx) >= abs(dy):
        return 2 if dx > 0 else 1
    return 4 if dy > 0 else 3


def dumps_official_mpe(report: dict[str, object]) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
