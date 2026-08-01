from __future__ import annotations
import logging
from datetime import datetime, timezone

import requests

from thesis_engine.config import FRED_API_KEY, FRED_SERIES
from thesis_engine.database import get_conn, init_db

logger = logging.getLogger(__name__)

_BASE = "https://api.stlouisfed.org/fred/series/observations"


def _fetch_series(series_id: str, series_name: str, limit: int = 12) -> list[dict]:
    if not FRED_API_KEY:
        return []
    try:
        resp = requests.get(
            _BASE,
            params={
                "series_id": series_id,
                "api_key": FRED_API_KEY,
                "file_type": "json",
                "sort_order": "desc",
                "limit": limit,
            },
            timeout=10,
        )
        resp.raise_for_status()
        observations = resp.json().get("observations", [])
        fetched_at = datetime.now(timezone.utc).isoformat()
        rows = []
        for obs in observations:
            val_str = obs.get("value", ".")
            if val_str == ".":
                continue
            rows.append({
                "series_id": series_id,
                "series_name": series_name,
                "date": obs["date"],
                "value": float(val_str),
                "fetched_at": fetched_at,
            })
        return rows
    except Exception as e:
        logger.warning(f"FRED fetch failed for {series_id}: {e}")
        return []


def refresh_macro_indicators() -> dict:
    init_db()
    if not FRED_API_KEY:
        logger.warning("FRED_API_KEY not set — skipping macro indicator refresh")
        return {"ok": 0, "series": 0}

    total_ok = 0
    for series_id, series_name in FRED_SERIES:
        rows = _fetch_series(series_id, series_name)
        for row in rows:
            try:
                with get_conn() as conn:
                    conn.execute(
                        """
                        INSERT INTO macro_indicators
                            (series_id, series_name, date, value, fetched_at)
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(series_id, date) DO UPDATE SET
                            value=excluded.value, fetched_at=excluded.fetched_at
                        """,
                        (row["series_id"], row["series_name"], row["date"],
                         row["value"], row["fetched_at"]),
                    )
                total_ok += 1
            except Exception as e:
                logger.warning(f"DB insert failed for {series_id}/{row['date']}: {e}")

    logger.info(f"FRED refresh: {total_ok} observations upserted across {len(FRED_SERIES)} series")
    return {"ok": total_ok, "series": len(FRED_SERIES)}


def get_latest_indicators() -> list[dict]:
    """Return the most recent value per series, with last 12 obs for sparklines."""
    with get_conn() as conn:
        series_ids = [s[0] for s in FRED_SERIES]
        results = []
        for series_id, series_name in FRED_SERIES:
            rows = conn.execute(
                """
                SELECT date, value FROM macro_indicators
                WHERE series_id = ?
                ORDER BY date DESC LIMIT 12
                """,
                (series_id,),
            ).fetchall()
            if not rows:
                continue
            history = [{"date": r["date"], "value": r["value"]} for r in rows]
            results.append({
                "series_id": series_id,
                "series_name": series_name,
                "latest_value": history[0]["value"],
                "latest_date": history[0]["date"],
                "history": list(reversed(history)),
            })
    return results
