from __future__ import annotations
import json
import logging
from datetime import datetime, timezone

import anthropic

from thesis_engine.config import ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)

_SYSTEM = """You are a macro economist helping a non-technical retail investor understand how global and national events affect their stock portfolio.

Given a news headline and optional summary, return a JSON object describing the impact for everyday investors. Use plain, jargon-free English — write as if explaining to a smart friend who doesn't follow the markets.

Industries to pick from (choose only the most relevant 1–4):
Energy, Technology, Healthcare, Financials, Consumer Staples, Consumer Discretionary,
Industrials, Materials, Real Estate, Utilities, Defense, Agriculture, Retail, Transportation, Banking

Macro themes (pick one):
Trade War, Interest Rates, Geopolitical Risk, Fed Policy, Inflation, Energy Markets,
Currency, Labor Market, Government Spending, Regulation, Corporate Earnings, Supply Chain, Housing

Return STRICT JSON only — no markdown, no preamble, no trailing text.

{
  "plain_summary": "<2-3 sentences, plain English, what happened and why it matters — no jargon>",
  "affected_industries": [
    {"name": "<Industry>", "impact": "<positive|negative|mixed>", "reason": "<one sentence why, in plain English>"}
  ],
  "investor_takeaway": "<one actionable sentence for a non-expert investor>",
  "macro_theme": "<one theme from the list>",
  "relevance_score": <integer 0-100, how much this matters for a typical US stock investor>
}"""


def analyze_macro_event(item: dict) -> dict | None:
    if not ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY not set — cannot analyze macro events")
        return None

    content = f"Headline: {item['title']}"
    if item.get("summary"):
        content += f"\nSummary: {item['summary']}"
    content += "\n\nReturn JSON only."

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            system=[{"type": "text", "text": _SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": content}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.rsplit("```", 1)[0]
        result = json.loads(raw.strip())
    except json.JSONDecodeError as e:
        logger.warning(f"JSON parse error for '{item['title']}': {e}")
        return None
    except anthropic.APIError as e:
        logger.error(f"Anthropic API error for '{item['title']}': {e}")
        return None

    result["analyzed_at"] = datetime.now(timezone.utc).isoformat()
    return result
