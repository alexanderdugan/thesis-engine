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

            CREATE TABLE IF NOT EXISTS signals (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                source      TEXT NOT NULL,
                raw_id      TEXT NOT NULL,
                ticker      TEXT,
                title       TEXT NOT NULL,
                summary     TEXT,
                url         TEXT,
                timestamp   TEXT,
                raw_content TEXT,
                metadata    TEXT,
                fetched_at  TEXT NOT NULL,
                UNIQUE(source, raw_id)
            );

            CREATE TABLE IF NOT EXISTS evaluations (
                id                     INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id              INTEGER NOT NULL REFERENCES signals(id),
                quality_score          INTEGER,
                has_falsifiable_thesis INTEGER,
                cites_evidence         INTEGER,
                acknowledges_risk      INTEGER,
                is_business_focused    INTEGER,
                bear_case              TEXT,
                central_claim          TEXT,
                one_line_summary       TEXT,
                verdict                TEXT,
                evaluated_at           TEXT NOT NULL
            );
        """)

        # Migration: if evaluations table is missing bear_case, it's the old schema.
        # Drop and recreate signals + evaluations (safe — they contain no real data yet).
        cols = {row[1] for row in conn.execute("PRAGMA table_info(evaluations)").fetchall()}
        if "bear_case" not in cols:
            conn.executescript("""
                DROP TABLE IF EXISTS evaluations;
                DROP TABLE IF EXISTS signals;
                CREATE TABLE signals (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    source      TEXT NOT NULL,
                    raw_id      TEXT NOT NULL,
                    ticker      TEXT,
                    title       TEXT NOT NULL,
                    summary     TEXT,
                    url         TEXT,
                    timestamp   TEXT,
                    raw_content TEXT,
                    metadata    TEXT,
                    fetched_at  TEXT NOT NULL,
                    UNIQUE(source, raw_id)
                );
                CREATE TABLE evaluations (
                    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id              INTEGER NOT NULL REFERENCES signals(id),
                    quality_score          INTEGER,
                    has_falsifiable_thesis INTEGER,
                    cites_evidence         INTEGER,
                    acknowledges_risk      INTEGER,
                    is_business_focused    INTEGER,
                    bear_case              TEXT,
                    central_claim          TEXT,
                    one_line_summary       TEXT,
                    verdict                TEXT,
                    evaluated_at           TEXT NOT NULL
                );
            """)
