from datetime import datetime, timezone

from thesis_engine.database import get_conn
from thesis_engine.alpaca_client import AlpacaClient
from thesis_engine.thesis_journal import create_thesis

_client = AlpacaClient()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def open_position(
    symbol: str,
    qty: int,
    thesis_text: str,
    expected_timeline: str,
    falsification_criteria: str,
    conviction: int,
) -> dict:
    symbol = symbol.upper().strip()

    # Guard: no concurrent positions in same symbol
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM positions WHERE symbol = ? AND status = 'open'",
            (symbol,),
        ).fetchone()
    if existing:
        raise ValueError(f"An open position in {symbol} already exists. Close it before opening a new one.")

    # 1. Place order with Alpaca (before any DB writes)
    order = _client.place_market_order(symbol, qty)
    fill = _client.poll_order_until_filled(order["order_id"])

    # 2. Write position + thesis atomically
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO positions
                (alpaca_order_id, symbol, qty, entry_price, status, opened_at)
            VALUES (?, ?, ?, ?, 'open', ?)
            """,
            (fill["order_id"], symbol, fill["filled_qty"], fill["filled_avg_price"], _now()),
        )
        position_id = cur.lastrowid
        create_thesis(
            conn,
            position_id=position_id,
            symbol=symbol,
            thesis_text=thesis_text,
            expected_timeline=expected_timeline,
            falsification_criteria=falsification_criteria,
            conviction=conviction,
        )

    return {"position_id": position_id, "fill": fill}


def close_position(symbol: str, outcome_notes: str) -> dict:
    symbol = symbol.upper().strip()

    with get_conn() as conn:
        pos_row = conn.execute(
            "SELECT * FROM positions WHERE symbol = ? AND status = 'open'",
            (symbol,),
        ).fetchone()
    if not pos_row:
        raise ValueError(f"No open position found for {symbol}")

    pos = dict(pos_row)

    # 1. Close with Alpaca
    _client.close_position(symbol)
    exit_price = _client.poll_position_closed(symbol)

    # 2. Update DB
    now = _now()
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE positions
            SET status = 'closed', exit_price = ?, closed_at = ?
            WHERE id = ?
            """,
            (exit_price, now, pos["id"]),
        )
        thesis_row = conn.execute(
            "SELECT id FROM theses WHERE position_id = ?", (pos["id"],)
        ).fetchone()
        if thesis_row:
            conn.execute(
                "UPDATE theses SET outcome_notes = ?, updated_at = ? WHERE id = ?",
                (outcome_notes, now, thesis_row["id"]),
            )

    return {"symbol": symbol, "exit_price": exit_price}


def sync_positions() -> tuple[list[dict], str]:
    """Reconcile DB open positions with live Alpaca data. Returns (positions, last_synced_iso)."""
    alpaca_positions = {p["symbol"]: p for p in _client.get_open_positions()}

    with get_conn() as conn:
        db_rows = conn.execute(
            """
            SELECT p.*, t.thesis_text, t.expected_timeline, t.falsification_criteria,
                   t.conviction, t.id as thesis_id
            FROM positions p
            LEFT JOIN theses t ON t.position_id = p.id
            WHERE p.status = 'open'
            ORDER BY p.opened_at DESC
            """
        ).fetchall()

    results = []
    for row in db_rows:
        pos = dict(row)
        live = alpaca_positions.get(pos["symbol"])
        if live:
            pos["current_price"] = live["current_price"]
            pos["unrealized_pl"] = live["unrealized_pl"]
            pos["unrealized_plpc"] = live["unrealized_plpc"]
        else:
            pos["current_price"] = pos["entry_price"]
            pos["unrealized_pl"] = 0.0
            pos["unrealized_plpc"] = 0.0
        results.append(pos)

    last_synced = _now()
    return results, last_synced


def list_open_positions() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT p.*, t.thesis_text, t.expected_timeline, t.falsification_criteria,
                   t.conviction, t.id as thesis_id
            FROM positions p
            LEFT JOIN theses t ON t.position_id = p.id
            WHERE p.status = 'open'
            ORDER BY p.opened_at DESC
            """
        ).fetchall()
    return [dict(r) for r in rows]
