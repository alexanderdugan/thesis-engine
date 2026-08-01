from __future__ import annotations
import re
import logging
from datetime import datetime, timezone, timedelta

import feedparser

logger = logging.getLogger(__name__)

_LOOKBACK_DAYS = 3

MACRO_FEEDS = [
    ("BBC Business",     "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("CNBC Economy",     "https://www.cnbc.com/id/20910258/device/rss/rss.html"),
    ("MarketWatch",      "https://feeds.marketwatch.com/marketwatch/topstories/"),
    ("Dow Jones",        "https://feeds.content.dowjones.io/public/rss/RSSMarketsMain"),
    ("NPR Business",     "https://feeds.npr.org/1006/rss.xml"),
    ("Guardian Business","https://www.theguardian.com/uk/business/rss"),
    ("FT Markets",       "https://www.ft.com/markets?format=rss"),
]


def _parse_date(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return None


def fetch_macro_news(max_per_feed: int = 15) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=_LOOKBACK_DAYS)
    fetched_at = datetime.now(timezone.utc).isoformat()
    items: list[dict] = []

    for feed_name, feed_url in MACRO_FEEDS:
        try:
            feed = feedparser.parse(feed_url, request_headers={"User-Agent": "thesis-engine/1.0"})
        except Exception as e:
            logger.warning(f"Failed to fetch {feed_name}: {e}")
            continue

        count = 0
        for entry in feed.entries:
            if count >= max_per_feed:
                break
            pub = _parse_date(entry)
            if pub and pub < cutoff:
                continue

            title = (entry.get("title") or "").strip()
            raw_summary = entry.get("summary") or entry.get("description") or ""
            summary = re.sub(r"<[^>]+>", " ", raw_summary).strip()
            link = entry.get("link") or ""
            guid = entry.get("id") or link

            if not title or not guid:
                continue

            items.append({
                "raw_id": guid,
                "source": feed_name,
                "title": title,
                "summary": summary[:600] if summary else None,
                "url": link,
                "published_at": pub.isoformat() if pub else None,
                "fetched_at": fetched_at,
            })
            count += 1

    return items
