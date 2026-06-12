import sqlite3
from thesis_engine.config import DB_PATH


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS positions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                alpaca_order_id TEXT NOT NULL,
                symbol          TEXT NOT NULL,
                qty             INTEGER NOT NULL,
                entry_price     REAL NOT NULL,
                status          TEXT NOT NULL DEFAULT 'open',
                opened_at       TEXT NOT NULL,
                closed_at       TEXT,
                exit_price      REAL
            );

            CREATE TABLE IF NOT EXISTS theses (
                id                     INTEGER PRIMARY KEY AUTOINCREMENT,
                position_id            INTEGER NOT NULL REFERENCES positions(id),
                symbol                 TEXT NOT NULL,
                thesis_text            TEXT NOT NULL,
                expected_timeline      TEXT NOT NULL,
                falsification_criteria TEXT NOT NULL,
                conviction             INTEGER NOT NULL,
                outcome_notes          TEXT,
                created_at             TEXT NOT NULL,
                updated_at             TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS daily_snapshots (
                id                          INTEGER PRIMARY KEY AUTOINCREMENT,
                date                        TEXT NOT NULL UNIQUE,
                portfolio_value             REAL NOT NULL,
                cash                        REAL NOT NULL,
                portfolio_return_daily      REAL,
                portfolio_return_cumulative REAL,
                spy_price                   REAL NOT NULL,
                spy_return_daily            REAL,
                spy_return_cumulative       REAL,
                qqq_price                   REAL NOT NULL,
                qqq_return_daily            REAL,
                qqq_return_cumulative       REAL,
                created_at                  TEXT NOT NULL
            );
        """)
