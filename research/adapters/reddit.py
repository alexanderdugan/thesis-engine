from __future__ import annotations
import logging

from research.adapters.base import Signal, SourceAdapter

logger = logging.getLogger(__name__)


class RedditAdapter(SourceAdapter):
    """Stub — not yet implemented. Requires PRAW credentials (client ID + secret).
    To activate: install praw, add REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET to .env,
    implement fetch(), and uncomment in pipeline.ADAPTER_REGISTRY.
    """

    def fetch(self) -> list[Signal]:
        logger.info("RedditAdapter disabled — pending credentials (see reddit.py)")
        return []
