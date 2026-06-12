from __future__ import annotations
import sqlite3
from datetime import datetime, timezone

from thesis_engine.database import get_conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_thesis(
    conn: sqlite3.Connection,
    position_id: int,
    symbol: str,
    thesis_text: str,
    expected_timeline: str,
    falsification_criteria: str,
    conviction: int,
) -> int:
    now = _now()
    cur = conn.execute(
        """
        INSERT INTO theses
            (position_id, symbol, thesis_text, expected_timeline,
             falsification_criteria, conviction, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (position_id, symbol, thesis_text, expected_timeline,
         falsification_criteria, conviction, now, now),
    )
    return cur.lastrowid


def get_thesis_for_position(position_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM theses WHERE position_id = ?", (position_id,)
        ).fetchone()
    return dict(row) if row else None


def update_outcome(thesis_id: int, outcome_notes: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE theses SET outcome_notes = ?, updated_at = ? WHERE id = ?",
            (outcome_notes, _now(), thesis_id),
        )


def list_theses(status: str | None = None) -> list[dict]:
    query = """
        SELECT t.*, p.status as position_status, p.entry_price,
               p.exit_price, p.opened_at, p.closed_at, p.qty
        FROM theses t
        JOIN positions p ON p.id = t.position_id
    """
    params: list = []
    if status:
        query += " WHERE p.status = ?"
        params.append(status)
    query += " ORDER BY t.created_at DESC"
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]
