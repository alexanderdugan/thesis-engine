from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Signal:
    source: str
    raw_id: str
    title: str
    url: str
    fetched_at: str
    ticker: str | None = None
    summary: str | None = None
    timestamp: str | None = None
    raw_content: str | None = None
    metadata: dict = field(default_factory=dict)


class SourceAdapter(ABC):
    @abstractmethod
    def fetch(self) -> list[Signal]: ...
