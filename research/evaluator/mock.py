from __future__ import annotations
from datetime import datetime, timezone
from research.adapters.base import Signal
from research.evaluator.base import Evaluator


class MockEvaluator(Evaluator):
    """Returns deterministic fake scores — no API calls, free end-to-end testing."""

    def evaluate(self, signal: Signal) -> dict | None:
        score = 55 + (len(signal.raw_content or "") % 40)
        is_edgar = signal.source == "edgar"
        return {
            "quality_score": score,
            "has_falsifiable_thesis": is_edgar,
            "cites_evidence": is_edgar,
            "acknowledges_risk": is_edgar,
            "is_business_focused": True,
            "bear_case": "Mock: no real bear case generated — switch to ClaudeEvaluator for real analysis.",
            "central_claim": f"Mock claim for {signal.ticker or signal.source}: {signal.title[:80]}",
            "one_line_summary": signal.title[:60],
            "verdict": "worth_reading" if score >= 60 else "skip",
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }
