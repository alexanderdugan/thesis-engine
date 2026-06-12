from __future__ import annotations
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

    # Guard: no concurrent positions in same symbol (open or pending)
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM positions WHERE symbol = ? AND status IN ('open', 'pending')",
            (symbol,),
        ).fetchone()
    if existing:
        raise ValueError(f"A position in {symbol} already exists. Close or cancel it first.")

    market = _client.get_market_status()
    is_open = market["is_open"]

    order = _client.place_market_order(symbol, qty, opg=not is_open)

    if is_open:
        fill = _client.poll_order_until_filled(order["order_id"])
        entry_price = fill["filled_avg_price"]
        filled_qty = fill["filled_qty"]
        db_status = "open"
    else:
        # OPG order — will fill at next market open
        fill = None
        entry_price = 0.0
        filled_qty = qty
        db_status = "pending"

    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO positions
                (alpaca_order_id, symbol, qty, entry_price, status, opened_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (order["order_id"], symbol, filled_qty, entry_price, db_status, _now()),
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

    return {
        "position_id": position_id,
        "fill": fill,
        "market_open": is_open,
        "next_open": market["next_open"] if not is_open else None,
    }


def close_position(symbol: str, outcome_notes: str) -> dict:
    symbol = symbol.upper().strip()

    with get_conn() as conn:
        pos_row = conn.execute(
            "SELECT * FROM positions WHERE symbol = ? AND status = 'open'",
            (symbol,),
        ).fetchone()
    if not pos_row:
        raise ValueError(f"No filled open position found for {symbol}. Pending orders must fill before closing.")

    pos = dict(pos_row)

    _client.close_position(symbol)
    exit_price = _client.poll_position_closed(symbol)

    now = _now()
    with get_conn() as conn:
        conn.execute(
            "UPDATE positions SET status = 'closed', exit_price = ?, closed_at = ? WHERE id = ?",
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
    """Reconcile DB positions with live Alpaca data. Promotes pending→open on fill."""
    alpaca_positions = {p["symbol"]: p for p in _client.get_open_positions()}

    with get_conn() as conn:
        db_rows = conn.execute(
            """
            SELECT p.*, t.thesis_text, t.expected_timeline, t.falsification_criteria,
                   t.conviction, t.id as thesis_id
            FROM positions p
            LEFT JOIN theses t ON t.position_id = p.id
            WHERE p.status IN ('open', 'pending')
            ORDER BY p.opened_at DESC
            """
        ).fetchall()

    results = []
    for row in db_rows:
        pos = dict(row)

        if pos["status"] == "pending":
            order_info = _client.get_order(pos["alpaca_order_id"])
            if order_info["filled"]:
                # Promote to open with real fill data
                with get_conn() as conn:
                    conn.execute(
                        """
                        UPDATE positions
                        SET status = 'open', entry_price = ?, opened_at = ?
                        WHERE id = ?
                        """,
                        (order_info["filled_avg_price"], order_info["filled_at"], pos["id"]),
                    )
                pos["status"] = "open"
                pos["entry_price"] = order_info["filled_avg_price"]
            elif order_info["rejected"]:
                with get_conn() as conn:
                    conn.execute(
                        "UPDATE positions SET status = 'rejected' WHERE id = ?",
                        (pos["id"],),
                    )
                continue  # drop from results
            else:
                pos["current_price"] = None
                pos["unrealized_pl"] = None
                pos["unrealized_plpc"] = None
                results.append(pos)
                continue

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
            WHERE p.status IN ('open', 'pending')
            ORDER BY p.opened_at DESC
            """
        ).fetchall()
    return [dict(r) for r in rows]
