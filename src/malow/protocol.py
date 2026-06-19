"""结构化通信协议定义。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List
import json
import time
import uuid


@dataclass
class Capability:
    """Agent 能力描述。"""

    agent: str
    actions: List[str]
    input_schema: Dict[str, str]
    output_schema: Dict[str, str]


@dataclass
class ProtocolMessage:
    """Agent 间传递的高密度结构化消息。"""

    sender: str
    receiver: str
    action: str
    params: Dict[str, Any] = field(default_factory=dict)
    result: Dict[str, Any] = field(default_factory=dict)
    capability: Dict[str, Any] = field(default_factory=dict)
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: float = field(default_factory=time.time)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, separators=(",", ":"))

    def size_chars(self) -> int:
        return len(self.to_json())


def text_message(sender: str, receiver: str, content: str) -> Dict[str, Any]:
    """构造纯文本模式消息。"""

    return {
        "sender": sender,
        "receiver": receiver,
        "content": content,
        "timestamp": time.time(),
    }


def text_size_chars(message: Dict[str, Any]) -> int:
    return len(json.dumps(message, ensure_ascii=False))
