from __future__ import annotations
from abc import ABC, abstractmethod
from research.adapters.base import Signal


class Evaluator(ABC):
    @abstractmethod
    def evaluate(self, signal: Signal) -> dict | None: ...
