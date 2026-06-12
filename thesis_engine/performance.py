from __future__ import annotations
from datetime import date, datetime, timezone

from thesis_engine.database import get_conn
from thesis_engine.alpaca_client import AlpacaClient

_client = AlpacaClient()
BENCHMARKS = ["SPY", "QQQ"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def take_snapshot() -> dict:
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")

    if not _client.is_trading_day(today):
        return {"status": "skipped", "reason": "not a trading day"}

    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM daily_snapshots WHERE date = ?", (today_str,)
        ).fetchone()
    if existing:
        return {"status": "skipped", "reason": "snapshot already taken today"}

    account = _client.get_account()
    prices = _client.get_latest_prices(BENCHMARKS)
    spy_price = prices.get("SPY", 0.0)
    qqq_price = prices.get("QQQ", 0.0)

    with get_conn() as conn:
        prior = conn.execute(
            "SELECT * FROM daily_snapshots ORDER BY date DESC LIMIT 1"
        ).fetchone()
        first = conn.execute(
            "SELECT * FROM daily_snapshots ORDER BY date ASC LIMIT 1"
        ).fetchone()

    portfolio_value = account["equity"]
    cash = account["cash"]

    portfolio_return_daily = None
    spy_return_daily = None
    qqq_return_daily = None

    if prior:
        prior = dict(prior)
        portfolio_return_daily = (portfolio_value - prior["portfolio_value"]) / prior["portfolio_value"] * 100
        spy_return_daily = (spy_price - prior["spy_price"]) / prior["spy_price"] * 100
        qqq_return_daily = (qqq_price - prior["qqq_price"]) / prior["qqq_price"] * 100

    portfolio_return_cumulative = None
    spy_return_cumulative = None
    qqq_return_cumulative = None
    is_first = first is None

    if first:
        first = dict(first)
        portfolio_return_cumulative = (portfolio_value - first["portfolio_value"]) / first["portfolio_value"] * 100
        spy_return_cumulative = (spy_price - first["spy_price"]) / first["spy_price"] * 100
        qqq_return_cumulative = (qqq_price - first["qqq_price"]) / first["qqq_price"] * 100
    else:
        # This is the first snapshot — set cumulative to 0
        portfolio_return_cumulative = 0.0
        spy_return_cumulative = 0.0
        qqq_return_cumulative = 0.0

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO daily_snapshots
                (date, portfolio_value, cash,
                 portfolio_return_daily, portfolio_return_cumulative,
                 spy_price, spy_return_daily, spy_return_cumulative,
                 qqq_price, qqq_return_daily, qqq_return_cumulative,
                 created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                today_str, portfolio_value, cash,
                portfolio_return_daily, portfolio_return_cumulative,
                spy_price, spy_return_daily, spy_return_cumulative,
                qqq_price, qqq_return_daily, qqq_return_cumulative,
                _now(),
            ),
        )

    return {
        "status": "ok",
        "date": today_str,
        "portfolio_value": portfolio_value,
        "is_first_snapshot": is_first,
        "warning": (
            "BASELINE LOCKED to today. Ensure capital is deployed before taking your first snapshot."
            if is_first else None
        ),
    }


def get_performance_history() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM daily_snapshots ORDER BY date ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_summary() -> dict | None:
    history = get_performance_history()
    if not history:
        return None
    latest = history[-1]
    first = history[0]
    return {
        "portfolio_cumulative": latest.get("portfolio_return_cumulative"),
        "spy_cumulative": latest.get("spy_return_cumulative"),
        "qqq_cumulative": latest.get("qqq_return_cumulative"),
        "alpha_vs_spy": (
            (latest.get("portfolio_return_cumulative") or 0)
            - (latest.get("spy_return_cumulative") or 0)
        ),
        "alpha_vs_qqq": (
            (latest.get("portfolio_return_cumulative") or 0)
            - (latest.get("qqq_return_cumulative") or 0)
        ),
        "start_date": first["date"],
        "latest_date": latest["date"],
        "portfolio_value": latest["portfolio_value"],
        "snapshot_count": len(history),
    }
