from __future__ import annotations
import json
import logging

from thesis_engine.database import init_db, get_conn
from research.adapters.base import Signal
from research.adapters.edgar import EdgarAdapter
from research.adapters.rss import RssAdapter
# from research.adapters.reddit import RedditAdapter  # uncomment to enable

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

ADAPTER_REGISTRY = [
    EdgarAdapter(),
    RssAdapter(),
    # RedditAdapter(),
]


def _insert_signal(conn, signal: Signal) -> int | None:
    """Insert signal, ignore on duplicate. Returns new row id or None if duplicate."""
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO signals
            (source, raw_id, ticker, title, summary, url, timestamp,
             raw_content, metadata, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            signal.source, signal.raw_id, signal.ticker, signal.title,
            signal.summary, signal.url, signal.timestamp, signal.raw_content,
            json.dumps(signal.metadata), signal.fetched_at,
        ),
    )
    return cur.lastrowid if cur.rowcount else None


def _get_unevaluated(conn) -> list[dict]:
    rows = conn.execute(
        """
        SELECT s.* FROM signals s
        LEFT JOIN evaluations e ON e.signal_id = s.id
        WHERE e.id IS NULL
        ORDER BY s.timestamp DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]


def run_pipeline() -> dict:
    init_db()

    stats = {"fetched": 0, "new": 0, "evaluated": 0, "worth_reading": 0, "errors": 0}

    # 1. Fetch from all active adapters
    all_signals: list[Signal] = []
    for adapter in ADAPTER_REGISTRY:
        name = type(adapter).__name__
        try:
            signals = adapter.fetch()
            logger.info(f"{name}: fetched {len(signals)} items")
            all_signals.extend(signals)
            stats["fetched"] += len(signals)
        except Exception as e:
            logger.error(f"{name} fetch failed: {e}")
            stats["errors"] += 1

    # 2. Dedup insert
    with get_conn() as conn:
        for signal in all_signals:
            new_id = _insert_signal(conn, signal)
            if new_id:
                stats["new"] += 1

    # 3. Evaluate unevaluated signals
    # Import here to avoid loading anthropic if API key not set
    from research.evaluator import evaluate

    with get_conn() as conn:
        unevaluated = _get_unevaluated(conn)

    logger.info(f"Evaluating {len(unevaluated)} new signal(s)...")

    for row in unevaluated:
        signal = Signal(
            source=row["source"],
            raw_id=row["raw_id"],
            ticker=row["ticker"],
            title=row["title"],
            summary=row["summary"],
            url=row["url"],
            timestamp=row["timestamp"],
            raw_content=row["raw_content"],
            metadata=json.loads(row["metadata"] or "{}"),
            fetched_at=row["fetched_at"],
        )

        result = evaluate(signal)
        if result is None:
            stats["errors"] += 1
            continue

        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO evaluations
                    (signal_id, quality_score, has_falsifiable_thesis, cites_evidence,
                     acknowledges_risk, is_business_focused, central_claim,
                     one_line_summary, verdict, evaluated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    result.get("quality_score"),
                    int(bool(result.get("has_falsifiable_thesis"))),
                    int(bool(result.get("cites_evidence"))),
                    int(bool(result.get("acknowledges_risk"))),
                    int(bool(result.get("is_business_focused"))),
                    result.get("central_claim"),
                    result.get("one_line_summary"),
                    result.get("verdict"),
                    result["evaluated_at"],
                ),
            )
            # Truncate raw_content to short excerpt — it's transient
            conn.execute(
                "UPDATE signals SET raw_content = ? WHERE id = ?",
                ((row["raw_content"] or "")[:300] or None, row["id"]),
            )

        stats["evaluated"] += 1
        if result.get("verdict") == "worth_reading":
            stats["worth_reading"] += 1
            logger.info(f"  ★ [{result.get('quality_score')}] {row['title'][:70]}")

    return stats
