from __future__ import annotations
import json
import logging
from datetime import datetime, timezone

import anthropic

from thesis_engine.config import ANTHROPIC_API_KEY
from research.adapters.base import Signal
from research.evaluator.base import Evaluator

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a rigorous financial research analyst evaluating whether a piece of content is worth reading for a tech-growth investor.

You will receive a content item (SEC filing excerpt, news article, or pasted text) and must evaluate it against these criteria. Return STRICT JSON only — no markdown, no preamble, no explanation outside the JSON object.

## Quality signals (raise score):
- Makes a FALSIFIABLE claim: a specific thesis with a timeline or measurable outcome, not vague predictions
- Cites REAL evidence: revenue figures, product metrics, contracts, guidance, filings data — not sentiment or vibes
- Acknowledges the BEAR CASE or material risks — real analysis argues against itself
- Reasoning is about the BUSINESS and its technology or fundamentals, not stock price movements or chart patterns
- Relevant to genuine technological growth or disruption (AI, cloud, semiconductors, enterprise software, platforms)

## Red flags (lower score):
- Hype language: "moon", "can't lose", "guaranteed", rockets, excessive exclamation points
- Cites position size as argument: "YOLO'd my savings", "I'm all-in so it must be good"
- Pure technical analysis or chart-reading with no business thesis
- Artificial urgency: "buy before Monday", "last chance" — real theses don't expire in 48 hours
- No risks mentioned at all
- Purely macroeconomic takes with no company-specific content

## Output schema (JSON only):
{
  "quality_score": <integer 0-100>,
  "has_falsifiable_thesis": <boolean>,
  "cites_evidence": <boolean>,
  "acknowledges_risk": <boolean>,
  "is_business_focused": <boolean>,
  "bear_case": "<the strongest counter-argument or risk to the thesis argued in this content, ≤2 sentences>",
  "central_claim": "<the single main factual or analytical claim in plain language, ≤2 sentences>",
  "one_line_summary": "<what this content argues, ≤15 words>",
  "verdict": "<'worth_reading' if quality_score >= 60, else 'skip'>"
}"""


class ClaudeEvaluator(Evaluator):
    def evaluate(self, signal: Signal) -> dict | None:
        if not ANTHROPIC_API_KEY:
            logger.error("ANTHROPIC_API_KEY not set — cannot evaluate signals")
            return None

        content_parts = []
        if signal.title:
            content_parts.append(f"Title: {signal.title}")
        if signal.summary:
            content_parts.append(f"Summary: {signal.summary}")
        if signal.raw_content:
            content_parts.append(f"Content:\n{signal.raw_content[:2000]}")

        if not content_parts:
            return None

        user_message = "\n\n".join(content_parts) + "\n\nReturn JSON only."

        try:
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1000,
                system=[
                    {
                        "type": "text",
                        "text": _SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_message}],
            )
            raw = response.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            result = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse evaluation JSON for {signal.raw_id}: {e}")
            return None
        except anthropic.APIError as e:
            logger.error(f"Anthropic API error evaluating {signal.raw_id}: {e}")
            return None

        result["evaluated_at"] = datetime.now(timezone.utc).isoformat()
        return result
