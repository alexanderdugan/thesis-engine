from __future__ import annotations
import logging
import re
from datetime import datetime, timezone, timedelta

import feedparser

from thesis_engine.config import RSS_FEEDS
from research.adapters.base import Signal, SourceAdapter

logger = logging.getLogger(__name__)

_TICKER_RE = re.compile(r"\b\$([A-Z]{1,5})\b|\(([A-Z]{1,5})\)|\bNASDAQ:\s*([A-Z]{1,5})\b|\bNYSE:\s*([A-Z]{1,5})\b")
_LOOKBACK_DAYS = 7


def _extract_ticker(text: str) -> str | None:
    m = _TICKER_RE.search(text or "")
    if not m:
        return None
    return next(g for g in m.groups() if g)


def _parse_date(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RssAdapter(SourceAdapter):
    def fetch(self) -> list[Signal]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=_LOOKBACK_DAYS)
        signals: list[Signal] = []
        fetched_at = _now_iso()

        for feed_url in RSS_FEEDS:
            try:
                feed = feedparser.parse(feed_url)
                feed_name = feed.feed.get("title", feed_url)
            except Exception as e:
                logger.error(f"Failed to parse RSS feed {feed_url}: {e}")
                continue

            for entry in feed.entries:
                pub_date = _parse_date(entry)
                if pub_date and pub_date < cutoff:
                    continue

                title = entry.get("title", "").strip()
                summary = entry.get("summary", "") or entry.get("description", "")
                # Strip HTML tags from summary
                summary = re.sub(r"<[^>]+>", " ", summary).strip()
                link = entry.get("link", "")
                guid = entry.get("id", "") or link

                if not title or not link:
                    continue

                ticker = _extract_ticker(title) or _extract_ticker(summary)
                raw_content = f"{title}. {summary}"[:2000] if summary else title

                signals.append(Signal(
                    source="rss",
                    raw_id=guid,
                    ticker=ticker,
                    title=title,
                    summary=summary[:500] if summary else None,
                    url=link,
                    timestamp=pub_date.isoformat() if pub_date else None,
                    raw_content=raw_content,
                    metadata={"feed_name": feed_name, "feed_url": feed_url},
                    fetched_at=fetched_at,
                ))

        return signals
