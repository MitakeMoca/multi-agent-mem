from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from .memory import MemoryRecord, SharedMemory


@dataclass
class OrganizationMemoryModel:
    """可迁移组织记忆的统一模型。

    它保存多 Agent 协作中的稳定分工，而不是保存完整轨迹或自然语言日志。
    """

    memory_id: str
    scenario: str
    roles: tuple[str, ...]
    coordination_graph: tuple[tuple[str, str], ...]
    trigger: dict[str, float]
    actor_basis: tuple[float, ...]
    role_adapters: tuple[tuple[float, ...], ...]
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "scenario": self.scenario,
            "roles": list(self.roles),
            "coordination_graph": [list(edge) for edge in self.coordination_graph],
            "trigger": {k: round(v, 6) for k, v in self.trigger.items()},
            "actor_basis": [round(v, 6) for v in self.actor_basis],
            "role_adapters": [[round(v, 6) for v in row] for row in self.role_adapters],
            "payload": self.payload,
        }

    def compressed_bytes(self) -> int:
        float_count = len(self.actor_basis)
        float_count += sum(len(row) for row in self.role_adapters)
        float_count += len(self.trigger)
        # 元数据按轻量二进制头估算；payload 中的规则名按短枚举处理。
        return 48 + float_count * 4 + len(self.roles) * 2 + len(self.coordination_graph) * 4


def organization_memory_from_dict(data: dict[str, Any]) -> OrganizationMemoryModel:
    return OrganizationMemoryModel(
        memory_id=str(data["memory_id"]),
        scenario=str(data["scenario"]),
        roles=tuple(str(item) for item in data["roles"]),
        coordination_graph=tuple((str(edge[0]), str(edge[1])) for edge in data["coordination_graph"]),
        trigger={str(k): float(v) for k, v in data["trigger"].items()},
        actor_basis=tuple(float(v) for v in data["actor_basis"]),
        role_adapters=tuple(tuple(float(v) for v in row) for row in data["role_adapters"]),
        payload=dict(data["payload"]),
    )


def store_organization_model(shared_memory: SharedMemory, model: OrganizationMemoryModel) -> MemoryRecord:
    payload = json.dumps(model.to_dict(), ensure_ascii=False, sort_keys=True)
    return shared_memory.add(
        source_agent="organization-miner",
        topic=f"{model.scenario} organization memory",
        summary=f"{model.scenario} 场景中的可迁移组织记忆，包含角色分工、协作拓扑和压缩 actor 参数。",
        tags=["organization-memory", model.scenario, "maddpg-like", "transfer"],
        evidence=payload,
        strategy=payload,
    )


def retrieve_organization_model(shared_memory: SharedMemory, scenario: str) -> tuple[OrganizationMemoryModel, MemoryRecord]:
    hits = shared_memory.search(
        f"{scenario} organization memory role coordination transfer",
        tags=["organization-memory", scenario],
        top_k=1,
        min_score=0.0,
    )
    if not hits:
        raise LookupError(f"organization memory not found: {scenario}")
    return organization_memory_from_dict(json.loads(hits[0].strategy)), hits[0]
