from __future__ import annotations
from thesis_engine.config import EDGAR_WATCHLIST
from thesis_engine.database import get_conn


def get_ticker_universe() -> list[str]:
    """All tickers we care about: configured watchlist + symbols with open positions."""
    tickers = set(EDGAR_WATCHLIST)
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT symbol FROM positions WHERE status = 'open'"
        ).fetchall()
    for row in rows:
        tickers.add(row["symbol"])
    return sorted(tickers)
