from research.evaluator.base import Evaluator
from research.evaluator.mock import MockEvaluator
from research.evaluator.claude import ClaudeEvaluator
from thesis_engine.config import USE_MOCK_EVALUATOR


def get_evaluator() -> Evaluator:
    if USE_MOCK_EVALUATOR:
        return MockEvaluator()
    return ClaudeEvaluator()
