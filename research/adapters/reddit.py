from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta

from research.adapters.base import Signal, SourceAdapter
from thesis_engine.config import (
    REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT,
    REDDIT_SUBREDDITS, EDGAR_WATCHLIST,
)

logger = logging.getLogger(__name__)

_LOOKBACK_HOURS = 48
_POST_LIMIT = 50


class RedditAdapter(SourceAdapter):
    def fetch(self) -> list[Signal]:
        if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
            logger.info("RedditAdapter: REDDIT_CLIENT_ID/SECRET not set — skipping")
            return []

        try:
            import praw
        except ImportError:
            logger.error("RedditAdapter: praw not installed — run: pip install praw")
            return []

        try:
            reddit = praw.Reddit(
                client_id=REDDIT_CLIENT_ID,
                client_secret=REDDIT_CLIENT_SECRET,
                user_agent=REDDIT_USER_AGENT,
                read_only=True,
            )
        except Exception as e:
            logger.error(f"RedditAdapter: failed to initialize PRAW: {e}")
            return []

        watchlist = set(EDGAR_WATCHLIST)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=_LOOKBACK_HOURS)
        fetched_at = datetime.now(timezone.utc).isoformat()
        signals: list[Signal] = []

        for sub_name in REDDIT_SUBREDDITS:
            try:
                sub = reddit.subreddit(sub_name)
                for post in sub.new(limit=_POST_LIMIT):
                    created = datetime.fromtimestamp(post.created_utc, tz=timezone.utc)
                    if created < cutoff:
                        continue

                    text = f"{post.title} {post.selftext or ''}"
                    ticker = _find_ticker(text, watchlist)

                    excerpt = (post.selftext or "").strip()[:500]
                    raw_content = f"{post.title}. {excerpt}" if excerpt else post.title

                    signals.append(Signal(
                        source="reddit",
                        raw_id=post.id,
                        ticker=ticker,
                        title=post.title[:300],
                        summary=excerpt or None,
                        url=f"https://reddit.com{post.permalink}",
                        timestamp=created.isoformat(),
                        raw_content=raw_content[:2000],
                        metadata={
                            "subreddit": sub_name,
                            "score": post.score,
                            "num_comments": post.num_comments,
                        },
                        fetched_at=fetched_at,
                    ))
            except Exception as e:
                logger.warning(f"RedditAdapter: error fetching r/{sub_name}: {e}")

        logger.info(f"RedditAdapter: fetched {len(signals)} posts from {REDDIT_SUBREDDITS}")
        return signals


def _find_ticker(text: str, watchlist: set[str]) -> str | None:
    """Return the first watchlist ticker mentioned in the text."""
    import re
    # Match $TICK, (TICK), or bare watchlist symbol as a whole word
    pattern = re.compile(r"\$([A-Z]{1,5})\b|(?<!\w)(" + "|".join(re.escape(t) for t in sorted(watchlist, key=len, reverse=True)) + r")(?!\w)")
    m = pattern.search(text.upper())
    if m:
        return m.group(1) or m.group(2)
    return None
