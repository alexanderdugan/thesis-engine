from __future__ import annotations
import logging

from research.adapters.base import Signal, SourceAdapter

logger = logging.getLogger(__name__)


class TwitterAdapter(SourceAdapter):
    """Stub — not yet implemented.

    Deferred: X/Twitter API no longer has a free tier (~$0.005/read).
    Also requires review of current developer agreement restrictions on
    using API data for investment/trading decisions before building.

    To activate when ready:
    - Add TWITTER_BEARER_TOKEN to .env
    - Install tweepy
    - Implement fetch() and register in pipeline.ADAPTER_REGISTRY
    """

    def fetch(self) -> list[Signal]:
        logger.info("TwitterAdapter disabled — see twitter.py for rationale")
        return []
