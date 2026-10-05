"""Event stream emitted by the agent. The CLI and the Streamlit UI both render these."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Event:
    kind: str  # spec, memory, trial, code, thought, tool, observation, guard, dispute, reflection, lesson, done, info
    title: str
    data: dict = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {"kind": self.kind, "title": self.title, "data": self.data, "ts": self.ts}


EventSink = Callable[[Event], None]


def null_sink(_: Event) -> None:
    return None
