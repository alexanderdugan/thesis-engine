from __future__ import annotations
import logging
from datetime import datetime, timezone

import yfinance as yf

from thesis_engine.database import get_conn, init_db
from market_data.watchlist import get_ticker_universe

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_ticker(symbol: str) -> dict | None:
    try:
        t = yf.Ticker(symbol)
        info = t.info or {}
        hist = t.history(period="2d")
        if hist.empty:
            logger.warning(f"yfinance: no price history for {symbol}")
            return None

        row = hist.iloc[-1]
        date = hist.index[-1].strftime("%Y-%m-%d")

        return {
            "ticker": symbol,
            "date": date,
            "open": float(row.get("Open") or 0) or None,
            "high": float(row.get("High") or 0) or None,
            "low": float(row.get("Low") or 0) or None,
            "close": float(row.get("Close") or 0) or None,
            "volume": int(row.get("Volume") or 0) or None,
            "market_cap": info.get("marketCap") or None,
            "pe_ratio": info.get("trailingPE") or None,
        }
    except Exception as e:
        logger.warning(f"yfinance fetch failed for {symbol}: {e}")
        return None


def refresh_market_data() -> dict:
    init_db()
    tickers = get_ticker_universe()
    fetched_at = _now()
    ok, failed = 0, 0

    for symbol in tickers:
        data = _fetch_ticker(symbol)
        if data is None:
            failed += 1
            continue
        try:
            with get_conn() as conn:
                conn.execute(
                    """
                    INSERT INTO market_snapshots
                        (ticker, date, open, high, low, close, volume, market_cap, pe_ratio, fetched_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(ticker, date) DO UPDATE SET
                        open=excluded.open, high=excluded.high, low=excluded.low,
                        close=excluded.close, volume=excluded.volume,
                        market_cap=excluded.market_cap, pe_ratio=excluded.pe_ratio,
                        fetched_at=excluded.fetched_at
                    """,
                    (
                        data["ticker"], data["date"], data["open"], data["high"],
                        data["low"], data["close"], data["volume"],
                        data["market_cap"], data["pe_ratio"], fetched_at,
                    ),
                )
            ok += 1
        except Exception as e:
            logger.warning(f"DB insert failed for {symbol}: {e}")
            failed += 1

    logger.info(f"market_data refresh: {ok} ok, {failed} failed out of {len(tickers)} tickers")
    return {"ok": ok, "failed": failed, "tickers": len(tickers)}


def get_latest_snapshots(tickers: list[str] | None = None) -> list[dict]:
    """Return the most recent snapshot row per ticker."""
    with get_conn() as conn:
        if tickers:
            placeholders = ",".join("?" * len(tickers))
            rows = conn.execute(
                f"""
                SELECT s.* FROM market_snapshots s
                INNER JOIN (
                    SELECT ticker, MAX(date) AS max_date
                    FROM market_snapshots
                    WHERE ticker IN ({placeholders})
                    GROUP BY ticker
                ) latest ON s.ticker = latest.ticker AND s.date = latest.max_date
                ORDER BY s.ticker
                """,
                tickers,
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT s.* FROM market_snapshots s
                INNER JOIN (
                    SELECT ticker, MAX(date) AS max_date
                    FROM market_snapshots GROUP BY ticker
                ) latest ON s.ticker = latest.ticker AND s.date = latest.max_date
                ORDER BY s.ticker
                """
            ).fetchall()
    return [dict(r) for r in rows]
