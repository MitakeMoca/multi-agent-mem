from __future__ import annotations

from dataclasses import dataclass, field

from .vectors import StatePacket
__all__ = ['StateExchange']



@dataclass
class StateExchange:
    """Agent 间非文本状态交换模块。"""

    packets: dict[str, StatePacket] = field(default_factory=dict)

    def publish(self, packet: StatePacket) -> int:
        self.packets[packet.state_id] = packet
        return packet.byte_size

    def get(self, state_id: str) -> StatePacket:
        if state_id not in self.packets:
            raise LookupError(f"state_id not found: {state_id}")
        return self.packets[state_id]

    def count(self) -> int:
        return len(self.packets)
