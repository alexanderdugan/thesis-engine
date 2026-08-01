import json
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date, datetime, timezone

from thesis_engine.database import init_db
from thesis_engine.config import CONVICTION_LABELS
from thesis_engine.positions import open_position, close_position, sync_positions
from thesis_engine.alpaca_client import AlpacaClient
from thesis_engine.thesis_journal import list_theses
from thesis_engine.performance import take_snapshot, get_performance_history, get_summary
from thesis_engine.database import get_conn

init_db()

st.set_page_config(page_title="Thesis Engine", layout="wide", page_icon="📈")

# ── Global styles ──────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Sidebar */
[data-testid="stSidebar"] {
    background: #0d1320 !important;
    border-right: 1px solid rgba(255,255,255,0.06);
}
[data-testid="stSidebar"] .stRadio label {
    font-size: 0.9rem;
    letter-spacing: 0.01em;
}

/* Metric cards */
[data-testid="stMetric"] {
    background: #111827;
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px;
    padding: 1rem 1.25rem !important;
}
[data-testid="stMetricLabel"] > div {
    font-size: 0.7rem !important;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #64748b !important;
}
[data-testid="stMetricValue"] {
    font-size: 1.35rem !important;
    font-weight: 700;
    color: #f1f5f9 !important;
}

/* Expanders */
[data-testid="stExpander"] {
    background: #111827;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 12px !important;
    margin-bottom: 0.6rem;
}
[data-testid="stExpander"] summary {
    font-weight: 600;
    font-size: 0.95rem;
}

/* Primary button */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #10b981 0%, #059669 100%) !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    letter-spacing: 0.01em;
    padding: 0.45rem 1.2rem !important;
    transition: opacity 0.15s;
}
.stButton > button[kind="primary"]:hover { opacity: 0.88; }

/* Secondary button */
.stButton > button[kind="secondary"] {
    background: #1e293b !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    border-radius: 8px !important;
    color: #cbd5e1 !important;
    font-weight: 500 !important;
}

/* Alerts */
.stSuccess { background: rgba(16,185,129,0.1) !important; border-left: 3px solid #10b981; border-radius: 0 8px 8px 0; }
.stWarning { background: rgba(245,158,11,0.1) !important; border-left: 3px solid #f59e0b; border-radius: 0 8px 8px 0; }
.stError   { background: rgba(239,68,68,0.1)  !important; border-left: 3px solid #ef4444; border-radius: 0 8px 8px 0; }
.stInfo    { background: rgba(99,102,241,0.1) !important; border-left: 3px solid #6366f1; border-radius: 0 8px 8px 0; }

/* Forms */
[data-testid="stForm"] {
    background: #111827;
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px;
    padding: 1.5rem !important;
}

/* Inputs */
input, textarea, select {
    background: #0d1117 !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    border-radius: 8px !important;
    color: #e2e8f0 !important;
}

/* Selectbox */
[data-baseweb="select"] > div {
    background: #0d1117 !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    border-radius: 8px !important;
}

/* Divider */
hr { border-color: rgba(255,255,255,0.06) !important; margin: 1.5rem 0; }

/* Caption / small text */
.stCaption { color: #64748b !important; }

/* Page title */
h1 { font-weight: 800 !important; letter-spacing: -0.02em; }
h2 { font-weight: 700 !important; letter-spacing: -0.01em; }
h3 { font-weight: 600 !important; }

/* Positive / negative P&L helper classes */
.pnl-pos { color: #10b981; font-weight: 700; }
.pnl-neg { color: #ef4444; font-weight: 700; }

/* Industry badge */
.badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 600;
    margin: 2px 3px;
}
.badge-pos  { background: rgba(16,185,129,0.15); color: #10b981; border: 1px solid rgba(16,185,129,0.3); }
.badge-neg  { background: rgba(239,68,68,0.15);  color: #ef4444; border: 1px solid rgba(239,68,68,0.3); }
.badge-mix  { background: rgba(245,158,11,0.15); color: #f59e0b; border: 1px solid rgba(245,158,11,0.3); }
.badge-theme{ background: rgba(99,102,241,0.15); color: #818cf8; border: 1px solid rgba(99,102,241,0.3); }
</style>
""", unsafe_allow_html=True)

# ── Sidebar ────────────────────────────────────────────────────────────────────
st.sidebar.markdown("## 📈 Thesis Engine")

page = st.sidebar.radio(
    "Navigate",
    ["Positions", "New Trade", "Performance", "Thesis Journal", "Research", "Economy", "Market"],
    index=0,
)

@st.cache_data(ttl=60)
def _market_status():
    return AlpacaClient().get_market_status()

_mkt = _market_status()
if _mkt["is_open"]:
    st.sidebar.success("Market open")
else:
    next_open_dt = datetime.fromisoformat(_mkt["next_open"])
    next_open_str = next_open_dt.strftime("%a %b %-d, %-I:%M %p ET")
    st.sidebar.warning(f"Market closed · opens {next_open_str}")

st.sidebar.divider()
st.sidebar.caption("Paper trading via Alpaca · Phase 3")

# ── POSITIONS ─────────────────────────────────────────────────────────────────
if page == "Positions":
    st.title("Open Positions")

    with st.spinner("Syncing with Alpaca..."):
        positions, last_synced = sync_positions()

    synced_dt = datetime.fromisoformat(last_synced)
    delta = (datetime.now(timezone.utc) - synced_dt).seconds
    st.caption(f"Last synced {delta}s ago")

    if not positions:
        st.info("No open positions. Go to **New Trade** to place your first position.")
    else:
        today = date.today()

        for pos in positions:
            symbol = pos["symbol"]
            is_pending = pos["status"] == "pending"
            timeline_date = date.fromisoformat(pos["expected_timeline"]) if pos.get("expected_timeline") else None
            days_left = (timeline_date - today).days if timeline_date else None
            overdue = days_left is not None and days_left < 0 and not is_pending

            if is_pending:
                header = f"⏳ {symbol}  —  Pending (fills at market open)"
            else:
                pl = pos.get("unrealized_pl") or 0
                plpc = (pos.get("unrealized_plpc") or 0) * 100
                arrow = "▲" if pl >= 0 else "▼"
                header = f"{'🔴 ' if overdue else ''}{symbol}  —  {arrow} ${pl:+,.2f}  ({plpc:+.2f}%)"

            with st.expander(header, expanded=True):
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Shares", pos["qty"])
                col2.metric("Entry", "Pending" if is_pending else f"${pos['entry_price']:.2f}")
                col3.metric("Current", "—" if is_pending else f"${pos.get('current_price', pos['entry_price']):.2f}")
                if days_left is not None:
                    label = f"{'OVERDUE ' if overdue else ''}Timeline"
                    col4.metric(label, f"{abs(days_left)}d {'past' if overdue else 'left'}")
                else:
                    col4.metric("Timeline", "—")

                if is_pending:
                    st.info("OPG order submitted — fills at next market open.")

                st.markdown(f"**Thesis:** {pos.get('thesis_text', '—')}")
                st.markdown(f"**Falsification:** {pos.get('falsification_criteria', '—')}")
                conviction = pos.get("conviction")
                if conviction:
                    st.markdown(f"**Conviction:** {conviction}/5 — {CONVICTION_LABELS.get(conviction, '')}")

                if not is_pending:
                    st.divider()
                    st.markdown("**Close this position**")
                    with st.form(key=f"close_{symbol}"):
                        outcome = st.text_area(
                            "Outcome notes (required) — how did the thesis play out?",
                            key=f"outcome_{symbol}",
                            height=100,
                        )
                        submitted = st.form_submit_button(f"Close {symbol}")
                        if submitted:
                            if not outcome.strip():
                                st.error("Outcome notes are required before closing.")
                            else:
                                try:
                                    with st.spinner(f"Closing {symbol}..."):
                                        result = close_position(symbol, outcome.strip())
                                    st.success(f"Closed {symbol} at ${result['exit_price']:.2f}")
                                    st.rerun()
                                except Exception as e:
                                    st.error(str(e))

# ── NEW TRADE ─────────────────────────────────────────────────────────────────
elif page == "New Trade":
    st.title("New Trade")
    if _mkt["is_open"]:
        st.caption("Market is open — order will fill immediately.")
    else:
        next_open = datetime.fromisoformat(_mkt["next_open"]).strftime("%a %b %-d, %-I:%M %p ET")
        st.caption(f"Market is closed — order will be submitted as OPG and fill at next open ({next_open}).")

    with st.form("new_trade_form"):
        st.subheader("Order")
        col1, col2 = st.columns(2)
        symbol = col1.text_input("Symbol", placeholder="e.g. AAPL").upper().strip()
        qty = col2.number_input("Shares (whole)", min_value=1, step=1, value=1)

        st.subheader("Thesis")
        thesis_text = st.text_area(
            "Why are you entering this trade?",
            height=120,
            placeholder="Describe the core thesis — the asymmetry, catalyst, or edge you're betting on.",
        )
        col3, col4 = st.columns(2)
        expected_timeline = col3.date_input(
            "Expected timeline (target review/exit date)",
            value=date.today(),
            min_value=date.today(),
        )
        conviction = col4.selectbox(
            "Conviction",
            options=list(CONVICTION_LABELS.keys()),
            format_func=lambda k: f"{k} — {CONVICTION_LABELS[k]}",
            index=2,
        )
        falsification_criteria = st.text_area(
            "Falsification criteria — what would prove you wrong and force an exit?",
            height=100,
            placeholder="e.g. 'Revenue growth falls below 15% YoY' or 'Stock breaks below $X support'",
        )
        submitted = st.form_submit_button("Place Order & Record Thesis", type="primary")

    if submitted:
        errors = []
        if not symbol:
            errors.append("Symbol is required.")
        if not thesis_text.strip():
            errors.append("Thesis text is required.")
        if not falsification_criteria.strip():
            errors.append("Falsification criteria is required.")

        if errors:
            for e in errors:
                st.error(e)
        else:
            try:
                with st.spinner(f"Placing order for {qty} share(s) of {symbol}..."):
                    result = open_position(
                        symbol=symbol,
                        qty=int(qty),
                        thesis_text=thesis_text.strip(),
                        expected_timeline=expected_timeline.isoformat(),
                        falsification_criteria=falsification_criteria.strip(),
                        conviction=conviction,
                    )
                if result["market_open"]:
                    fill = result["fill"]
                    st.success(
                        f"Order filled: {fill['filled_qty']} share(s) of {symbol} "
                        f"@ ${fill['filled_avg_price']:.2f}. Thesis recorded."
                    )
                    st.balloons()
                else:
                    next_open = datetime.fromisoformat(result["next_open"]).strftime("%a %b %-d, %-I:%M %p ET")
                    st.warning(
                        f"Market is closed. OPG order queued for {symbol} ({qty} share(s)) — "
                        f"will fill at market open ({next_open}). Thesis recorded."
                    )
            except ValueError as e:
                st.error(str(e))
            except TimeoutError as e:
                st.error(f"Order timed out: {e}")
            except Exception as e:
                st.error(f"Error: {e}")

# ── PERFORMANCE ───────────────────────────────────────────────────────────────
elif page == "Performance":
    st.title("Performance")

    col_btn, col_spacer = st.columns([1, 5])
    with col_btn:
        if st.button("Take Snapshot", type="primary"):
            with st.spinner("Taking snapshot..."):
                result = take_snapshot()
            if result["status"] == "skipped":
                st.warning(f"Skipped: {result['reason']}")
            else:
                st.success(f"Snapshot recorded for {result['date']}")
                if result.get("warning"):
                    st.warning(result["warning"])
                st.rerun()

    history = get_performance_history()
    summary = get_summary()

    if not history:
        st.info("No snapshots yet. Click **Take Snapshot** after market close to start tracking performance.")
    else:
        if summary:
            st.subheader("Summary")
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Portfolio Value", f"${summary['portfolio_value']:,.2f}")
            m2.metric(
                "Portfolio Return",
                f"{summary['portfolio_cumulative']:+.2f}%" if summary["portfolio_cumulative"] is not None else "—",
            )
            m3.metric("SPY", f"{summary['spy_cumulative']:+.2f}%" if summary["spy_cumulative"] is not None else "—")
            m4.metric("QQQ", f"{summary['qqq_cumulative']:+.2f}%" if summary["qqq_cumulative"] is not None else "—")
            m5.metric(
                "Alpha vs SPY",
                f"{summary['alpha_vs_spy']:+.2f}%" if summary["alpha_vs_spy"] is not None else "—",
            )

        st.subheader("Cumulative Return")
        df = pd.DataFrame(history)
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df["date"], y=df["portfolio_return_cumulative"],
            name="Portfolio", line=dict(color="#10b981", width=2.5),
        ))
        fig.add_trace(go.Scatter(
            x=df["date"], y=df["spy_return_cumulative"],
            name="SPY", line=dict(color="#6366f1", width=2, dash="dot"),
        ))
        fig.add_trace(go.Scatter(
            x=df["date"], y=df["qqq_return_cumulative"],
            name="QQQ", line=dict(color="#f59e0b", width=2, dash="dot"),
        ))
        fig.add_hline(y=0, line_color="rgba(255,255,255,0.15)", line_dash="dash")
        fig.update_layout(
            yaxis_title="Cumulative Return (%)",
            xaxis_title="Date",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#94a3b8"),
            xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
            yaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
            height=420,
        )
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("Raw snapshot data"):
            st.dataframe(
                df[["date", "portfolio_value", "cash",
                    "portfolio_return_daily", "portfolio_return_cumulative",
                    "spy_price", "spy_return_cumulative",
                    "qqq_price", "qqq_return_cumulative"]],
                use_container_width=True,
            )

# ── THESIS JOURNAL ────────────────────────────────────────────────────────────
elif page == "Thesis Journal":
    st.title("Thesis Journal")

    col_filter, col_search = st.columns([1, 3])
    status_filter = col_filter.selectbox("Status", ["All", "Open", "Closed"], index=0)
    search = col_search.text_input("Search by symbol or thesis keyword", placeholder="NVDA, AI, rates...")

    status_arg = None if status_filter == "All" else status_filter.lower()
    theses = list_theses(status=status_arg)

    if search:
        q = search.lower()
        theses = [t for t in theses if q in t["symbol"].lower() or q in (t.get("thesis_text") or "").lower()]

    if not theses:
        st.info("No theses found.")
    else:
        st.caption(f"{len(theses)} thesis record(s)")
        for t in theses:
            is_closed = t["position_status"] == "closed"
            pnl = None
            if is_closed and t.get("exit_price") and t.get("entry_price"):
                pnl = (t["exit_price"] - t["entry_price"]) * t["qty"]

            header = f"{'✅' if is_closed else '🟢'} {t['symbol']}"
            if pnl is not None:
                header += f"  —  {'▲' if pnl >= 0 else '▼'} ${pnl:+,.2f}"

            with st.expander(header):
                col1, col2, col3 = st.columns(3)
                col1.metric("Conviction", f"{t['conviction']}/5 — {CONVICTION_LABELS.get(t['conviction'], '')}")
                col2.metric("Timeline", t.get("expected_timeline", "—"))
                col3.metric("Status", t["position_status"].capitalize())

                if is_closed and t.get("entry_price") and t.get("exit_price"):
                    c1, c2 = st.columns(2)
                    c1.metric("Entry", f"${t['entry_price']:.2f}")
                    c2.metric("Exit", f"${t['exit_price']:.2f}")

                st.markdown(f"**Thesis:** {t.get('thesis_text', '—')}")
                st.markdown(f"**Falsification:** {t.get('falsification_criteria', '—')}")

                if is_closed:
                    st.markdown(f"**Outcome:** {t.get('outcome_notes') or '_No notes recorded_'}")

                opened = t.get("opened_at", "")[:10]
                closed = t.get("closed_at", "")
                closed_str = f"  →  Closed {closed[:10]}" if closed else ""
                st.caption(f"Opened {opened}{closed_str}")

# ── RESEARCH ──────────────────────────────────────────────────────────────────
elif page == "Research":
    import hashlib
    from datetime import datetime as _dt2, timezone as _tz2
    from research.evaluator import get_evaluator
    from research.adapters.base import Signal as _Signal
    from thesis_engine.config import USE_MOCK_EVALUATOR

    st.title("Research Signals")
    evaluator_label = "mock evaluator" if USE_MOCK_EVALUATOR else "Claude claude-sonnet-4-6"
    st.caption(f"SEC EDGAR + financial news RSS, evaluated for argument quality ({evaluator_label}).")

    with st.expander("Paste & Evaluate — run any text through the evaluator", expanded=False):
        with st.form("manual_eval_form"):
            paste_content = st.text_area(
                "Paste content (Reddit post, Substack, X thread, anything)",
                height=200,
                placeholder="Paste the full text you want evaluated...",
            )
            col_a, col_b = st.columns(2)
            paste_ticker = col_a.text_input("Ticker (optional)", placeholder="NVDA").upper().strip()
            paste_source_note = col_b.text_input("Source note (optional)", placeholder="e.g. Reddit r/investing DD")
            submitted = st.form_submit_button("Evaluate", type="primary")

        if submitted:
            if not paste_content.strip():
                st.error("Paste some content first.")
            else:
                raw_id = hashlib.sha256(paste_content.encode()).hexdigest()[:16]
                with get_conn() as _c:
                    existing = _c.execute(
                        "SELECT s.id FROM signals s JOIN evaluations e ON e.signal_id = s.id "
                        "WHERE s.source = 'manual' AND s.raw_id = ?", (raw_id,)
                    ).fetchone()

                if existing:
                    st.info("This content has already been evaluated — see results in the list below.")
                else:
                    signal = _Signal(
                        source="manual",
                        raw_id=raw_id,
                        ticker=paste_ticker or None,
                        title=paste_source_note or "Manual paste",
                        summary=None,
                        url=None,
                        timestamp=_dt2.now(_tz2.utc).isoformat(),
                        raw_content=paste_content.strip(),
                        metadata={"source_note": paste_source_note},
                        fetched_at=_dt2.now(_tz2.utc).isoformat(),
                    )
                    with st.spinner("Evaluating..."):
                        result = get_evaluator().evaluate(signal)

                    if result is None:
                        st.error("Evaluation failed — check logs.")
                    else:
                        with get_conn() as _c:
                            cur = _c.execute(
                                """INSERT OR IGNORE INTO signals
                                   (source, raw_id, ticker, title, summary, url,
                                    timestamp, raw_content, metadata, fetched_at)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                (signal.source, signal.raw_id, signal.ticker, signal.title,
                                 signal.summary, signal.url, signal.timestamp,
                                 paste_content.strip()[:300],
                                 json.dumps(signal.metadata), signal.fetched_at),
                            )
                            sig_id = cur.lastrowid or _c.execute(
                                "SELECT id FROM signals WHERE source='manual' AND raw_id=?", (raw_id,)
                            ).fetchone()["id"]
                            _c.execute(
                                """INSERT INTO evaluations
                                   (signal_id, quality_score, has_falsifiable_thesis, cites_evidence,
                                    acknowledges_risk, is_business_focused, bear_case, central_claim,
                                    one_line_summary, verdict, evaluated_at)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                (sig_id,
                                 result.get("quality_score"),
                                 int(bool(result.get("has_falsifiable_thesis"))),
                                 int(bool(result.get("cites_evidence"))),
                                 int(bool(result.get("acknowledges_risk"))),
                                 int(bool(result.get("is_business_focused"))),
                                 result.get("bear_case"),
                                 result.get("central_claim"),
                                 result.get("one_line_summary"),
                                 result.get("verdict"),
                                 result["evaluated_at"]),
                            )

                        score = result.get("quality_score", 0)
                        verdict = result.get("verdict", "skip")
                        if verdict == "worth_reading":
                            st.success(f"Worth reading — score {score}/100")
                        else:
                            st.warning(f"Skip — score {score}/100")
                        if result.get("one_line_summary"):
                            st.markdown(f"**Summary:** {result['one_line_summary']}")
                        if result.get("bear_case"):
                            st.markdown(f"**Bear case:** {result['bear_case']}")
                        if result.get("central_claim"):
                            st.markdown(f"**Central claim:** {result['central_claim']}")
                        st.rerun()

    st.divider()

    col_f1, col_f2, col_f3 = st.columns([2, 2, 1])
    ticker_filter = col_f1.text_input("Filter by ticker", placeholder="NVDA").upper().strip()
    source_filter = col_f2.selectbox("Source", ["All", "edgar", "rss"], index=0)
    worth_only = col_f3.checkbox("Worth reading only", value=True)

    query = """
        SELECT s.id, s.source, s.ticker, s.title, s.url, s.timestamp, s.raw_content,
               e.quality_score, e.has_falsifiable_thesis, e.cites_evidence,
               e.acknowledges_risk, e.is_business_focused,
               e.bear_case, e.central_claim, e.one_line_summary, e.verdict, e.evaluated_at
        FROM signals s
        LEFT JOIN evaluations e ON e.signal_id = s.id
        WHERE 1=1
    """
    params = []
    if worth_only:
        query += " AND e.verdict = 'worth_reading'"
    if ticker_filter:
        query += " AND s.ticker = ?"
        params.append(ticker_filter)
    if source_filter != "All":
        query += " AND s.source = ?"
        params.append(source_filter)
    query += " ORDER BY e.quality_score DESC, s.timestamp DESC LIMIT 100"

    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(query, params).fetchall()]

    if not rows:
        if worth_only:
            st.info("No worth-reading signals yet. Run `python scripts/run_pipeline.py` to fetch and evaluate content.")
        else:
            st.info("No signals found. Run `python scripts/run_pipeline.py` to populate.")
    else:
        st.caption(f"{len(rows)} signal(s)")
        for r in rows:
            score = r.get("quality_score")
            verdict = r.get("verdict") or "unevaluated"
            ticker_badge = f"**{r['ticker']}** · " if r.get("ticker") else ""
            source_label = r["source"].upper()
            summary = r.get("one_line_summary") or r.get("title", "")[:80]

            score_color = "🟢" if (score or 0) >= 75 else "🟡" if (score or 0) >= 50 else "🔴"
            header = f"{score_color} [{source_label}] {ticker_badge}{summary}"
            if score is not None:
                header += f"  —  score {score}/100"

            with st.expander(header):
                c1, c2, c3, c4, c5 = st.columns(5)
                c1.metric("Score", score if score is not None else "—")
                c2.metric("Falsifiable", "✓" if r.get("has_falsifiable_thesis") else "✗")
                c3.metric("Evidence", "✓" if r.get("cites_evidence") else "✗")
                c4.metric("Risk noted", "✓" if r.get("acknowledges_risk") else "✗")
                c5.metric("Business", "✓" if r.get("is_business_focused") else "✗")

                if r.get("bear_case"):
                    st.markdown(f"**Bear case:** {r['bear_case']}")
                if r.get("central_claim"):
                    st.markdown(f"**Central claim:** {r['central_claim']}")

                st.markdown(f"**Title:** {r['title']}")
                ts = (r.get("timestamp") or "")[:10]
                st.caption(f"Source: {source_label}  ·  {ts}  ·  [Open original]({r['url']})")

# ── ECONOMY (Phase 3) ─────────────────────────────────────────────────────────
elif page == "Economy":
    from research.macro.fetcher import fetch_macro_news
    from research.macro.analyzer import analyze_macro_event
    from thesis_engine.config import ANTHROPIC_API_KEY as _ANTHROPIC_KEY

    st.title("Global Economy")
    st.caption(
        "Live geopolitical and economic news, analyzed by AI to show which industries are affected "
        "and what it means for your portfolio — in plain English."
    )

    _key_missing = not _ANTHROPIC_KEY or _ANTHROPIC_KEY.startswith("your_")
    if _key_missing:
        st.error(
            "**Anthropic API key not configured.** "
            "Add `ANTHROPIC_API_KEY=sk-ant-...` to your `.env` file and restart the app. "
            "Without it the Economy analyzer cannot run."
        )

    col_refresh, col_filter, col_min_score = st.columns([1, 2, 2])

    with col_refresh:
        do_refresh = st.button("Refresh News", type="primary", disabled=_key_missing)

    theme_options = ["All Themes", "Trade War", "Interest Rates", "Geopolitical Risk", "Fed Policy",
                     "Inflation", "Energy Markets", "Currency", "Labor Market",
                     "Government Spending", "Regulation", "Corporate Earnings",
                     "Supply Chain", "Housing"]
    theme_filter = col_filter.selectbox("Theme", theme_options, index=0)
    min_score = col_min_score.slider("Minimum relevance score", 0, 100, 40, step=5)

    if do_refresh:
        with st.spinner("Fetching latest news..."):
            items = fetch_macro_news()

        if not items:
            st.warning("No articles returned from news feeds. The feeds may be temporarily unavailable.")
        else:
            with get_conn() as conn:
                existing_ids = {
                    row[0] for row in conn.execute("SELECT raw_id FROM macro_events").fetchall()
                }

            new_items = [it for it in items if it["raw_id"] not in existing_ids]
            st.caption(f"Found {len(items)} articles · {len(new_items)} new")

            if new_items:
                progress = st.progress(0, text="Analyzing with Claude...")
                analyzed = 0
                _api_error_shown = False
                for i, item in enumerate(new_items):
                    result = analyze_macro_event(item)
                    if result is None and not _api_error_shown:
                        st.error(
                            "Analysis failed on first article — likely an invalid Anthropic API key or API error. "
                            "Check your `.env` file and the terminal logs."
                        )
                        _api_error_shown = True
                    if result:
                        with get_conn() as conn:
                            conn.execute(
                                """INSERT OR IGNORE INTO macro_events
                                   (raw_id, source, title, url, published_at, fetched_at,
                                    plain_summary, investor_takeaway, macro_theme,
                                    relevance_score, affected_industries, analyzed_at)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                (
                                    item["raw_id"], item["source"], item["title"],
                                    item.get("url"), item.get("published_at"), item["fetched_at"],
                                    result.get("plain_summary"),
                                    result.get("investor_takeaway"),
                                    result.get("macro_theme"),
                                    result.get("relevance_score"),
                                    json.dumps(result.get("affected_industries", [])),
                                    result["analyzed_at"],
                                ),
                            )
                        analyzed += 1
                    progress.progress((i + 1) / len(new_items), text=f"Analyzed {i+1}/{len(new_items)}...")

                progress.empty()
                if analyzed > 0:
                    st.success(f"Added {analyzed} new events to the economy feed.")
                    st.rerun()
                elif not _api_error_shown:
                    st.warning("No events were successfully analyzed.")
            else:
                st.info("No new articles since last refresh.")

    # ── FRED numeric indicators ────────────────────────────────────────────────
    from research.macro.fred import get_latest_indicators, refresh_macro_indicators
    from thesis_engine.config import FRED_API_KEY as _FRED_KEY

    st.subheader("Economic Indicators")
    if not _FRED_KEY:
        st.info(
            "Add `FRED_API_KEY=` to `.env` (free at fred.stlouisfed.org) to enable "
            "real-time CPI, interest rate, unemployment, and Treasury yield data."
        )
    else:
        fred_col_refresh, fred_col_spacer = st.columns([1, 5])
        if fred_col_refresh.button("Refresh Indicators", key="fred_refresh"):
            with st.spinner("Fetching from FRED..."):
                fred_result = refresh_macro_indicators()
            st.success(f"Updated {fred_result['ok']} observations across {fred_result['series']} series.")
            st.rerun()

        indicators = get_latest_indicators()
        if not indicators:
            st.info("No indicator data yet — click **Refresh Indicators** to pull from FRED.")
        else:
            ind_cols = st.columns(len(indicators))
            for col, ind in zip(ind_cols, indicators):
                val = ind["latest_value"]
                history = ind["history"]
                prev = history[-2]["value"] if len(history) >= 2 else None
                delta = f"{val - prev:+.2f}" if prev is not None else None
                col.metric(
                    ind["series_name"],
                    f"{val:.2f}%",
                    delta,
                    help=f"As of {ind['latest_date']} · FRED {ind['series_id']}",
                )

            with st.expander("Trend charts", expanded=False):
                for ind in indicators:
                    history = ind["history"]
                    if len(history) < 2:
                        continue
                    hdf = pd.DataFrame(history)
                    fig = go.Figure(go.Scatter(
                        x=hdf["date"], y=hdf["value"],
                        mode="lines+markers",
                        line=dict(color="#6366f1", width=2),
                        marker=dict(size=5),
                        name=ind["series_name"],
                    ))
                    fig.update_layout(
                        title=ind["series_name"],
                        height=200,
                        margin=dict(l=0, r=0, t=30, b=0),
                        plot_bgcolor="rgba(0,0,0,0)",
                        paper_bgcolor="rgba(0,0,0,0)",
                        font=dict(color="#94a3b8", size=11),
                        xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
                        yaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
                        showlegend=False,
                    )
                    st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.subheader("Macro News")

    # Load from DB
    query = "SELECT * FROM macro_events WHERE analyzed_at IS NOT NULL"
    params: list = []
    if theme_filter != "All Themes":
        query += " AND macro_theme = ?"
        params.append(theme_filter)
    if min_score > 0:
        query += " AND relevance_score >= ?"
        params.append(min_score)
    query += " ORDER BY relevance_score DESC, published_at DESC LIMIT 60"

    with get_conn() as conn:
        rows = [dict(r) for r in conn.execute(query, params).fetchall()]

    if not rows:
        st.info("No economy data yet — click **Refresh News** to pull the latest articles and analyze them.")
    else:
        st.caption(f"{len(rows)} events")
        st.divider()

        for r in rows:
            score = r.get("relevance_score") or 0
            theme = r.get("macro_theme") or "—"
            score_icon = "🔴" if score >= 75 else "🟡" if score >= 50 else "⚪"

            header = f"{score_icon} {r['title']}"

            with st.expander(header, expanded=False):
                # Score + theme + source row
                mc1, mc2, mc3 = st.columns([1, 2, 2])
                mc1.metric("Relevance", f"{score}/100")
                mc2.metric("Theme", theme)
                mc3.metric("Source", r.get("source", "—"))

                # Plain summary
                if r.get("plain_summary"):
                    st.markdown(f"**What happened:** {r['plain_summary']}")

                # Industry impact badges
                industries_raw = r.get("affected_industries")
                if industries_raw:
                    try:
                        industries = json.loads(industries_raw) if isinstance(industries_raw, str) else industries_raw
                        if industries:
                            badge_html = ""
                            for ind in industries:
                                impact = ind.get("impact", "mixed").lower()
                                cls = "badge-pos" if impact == "positive" else "badge-neg" if impact == "negative" else "badge-mix"
                                icon = "↑" if impact == "positive" else "↓" if impact == "negative" else "~"
                                badge_html += f'<span class="badge {cls}">{icon} {ind["name"]}</span>'
                            st.markdown(
                                f'<div style="margin: 0.5rem 0">'
                                f'<span style="font-size:0.8rem;color:#64748b;margin-right:6px">Affected sectors:</span>'
                                f'{badge_html}</div>',
                                unsafe_allow_html=True,
                            )

                            # Expand detail per industry
                            with st.expander("Why these sectors?", expanded=False):
                                for ind in industries:
                                    impact = ind.get("impact", "mixed").lower()
                                    color = "#10b981" if impact == "positive" else "#ef4444" if impact == "negative" else "#f59e0b"
                                    st.markdown(
                                        f'<span style="color:{color};font-weight:600">{ind["name"]}</span> — {ind.get("reason", "—")}',
                                        unsafe_allow_html=True,
                                    )
                    except (json.JSONDecodeError, TypeError):
                        pass

                # Investor takeaway
                if r.get("investor_takeaway"):
                    st.markdown(
                        f'<div style="background:rgba(99,102,241,0.1);border-left:3px solid #6366f1;'
                        f'border-radius:0 8px 8px 0;padding:0.6rem 1rem;margin-top:0.75rem">'
                        f'<span style="font-size:0.75rem;text-transform:uppercase;letter-spacing:0.08em;color:#818cf8">Investor takeaway</span><br>'
                        f'<span style="color:#e2e8f0">{r["investor_takeaway"]}</span></div>',
                        unsafe_allow_html=True,
                    )

                pub = (r.get("published_at") or "")[:10]
                url = r.get("url")
                link_str = f'  ·  [Read article]({url})' if url else ""
                st.caption(f"{r.get('source', '')}  ·  {pub}{link_str}")

# ── MARKET ────────────────────────────────────────────────────────────────────
elif page == "Market":
    from market_data.yahoo import refresh_market_data, get_latest_snapshots
    from market_data.watchlist import get_ticker_universe

    st.title("Market Data")
    st.caption("Price and fundamentals for your watchlist and open positions, via Yahoo Finance.")

    col_refresh, col_spacer = st.columns([1, 5])
    if col_refresh.button("Refresh Market Data", type="primary"):
        tickers = get_ticker_universe()
        if not tickers:
            st.warning("No tickers in watchlist or open positions. Add tickers to EDGAR_WATCHLIST in .env.")
        else:
            with st.spinner(f"Fetching data for {len(tickers)} ticker(s)..."):
                result = refresh_market_data()
            if result["failed"] > 0:
                st.warning(f"Fetched {result['ok']}/{result['tickers']} tickers ({result['failed']} failed — check logs).")
            else:
                st.success(f"Updated {result['ok']} ticker(s).")
            st.rerun()

    universe = get_ticker_universe()
    snapshots = get_latest_snapshots(universe) if universe else []

    if not snapshots:
        st.info("No market data yet — click **Refresh Market Data** to pull prices and fundamentals.")
    else:
        st.caption(f"{len(snapshots)} ticker(s)  ·  as of {snapshots[0]['date'] if snapshots else '—'}")

        # Summary metrics row
        rows_by_ticker = {s["ticker"]: s for s in snapshots}

        # Fetch live Alpaca prices for open positions
        @st.cache_data(ttl=60)
        def _live_prices():
            from thesis_engine.alpaca_client import AlpacaClient
            from thesis_engine.positions import list_open_positions
            open_syms = [p["symbol"] for p in list_open_positions() if p["status"] == "open"]
            if not open_syms:
                return {}
            try:
                return AlpacaClient().get_latest_prices(open_syms)
            except Exception:
                return {}

        live = _live_prices()

        # Table view
        table_data = []
        for snap in snapshots:
            sym = snap["ticker"]
            close = live.get(sym) or snap.get("close")
            mc = snap.get("market_cap")
            pe = snap.get("pe_ratio")
            table_data.append({
                "Ticker": sym,
                "Price": f"${close:,.2f}" if close else "—",
                "Market Cap": f"${mc/1e9:.1f}B" if mc else "—",
                "P/E": f"{pe:.1f}" if pe else "—",
                "As of": snap.get("date", "—"),
            })

        st.dataframe(
            pd.DataFrame(table_data).set_index("Ticker"),
            use_container_width=True,
        )

        st.divider()

        # Per-ticker expanders with sparklines
        for snap in snapshots:
            sym = snap["ticker"]
            close = live.get(sym) or snap.get("close")
            mc = snap.get("market_cap")
            pe = snap.get("pe_ratio")

            header = f"**{sym}**"
            if close:
                header += f"  —  ${close:,.2f}"

            with st.expander(header, expanded=False):
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Last Price", f"${close:,.2f}" if close else "—")
                c2.metric("Market Cap", f"${mc/1e9:.1f}B" if mc else "—")
                c3.metric("P/E Ratio", f"{pe:.1f}" if pe else "—")
                c4.metric("Volume", f"{snap.get('volume') or 0:,}" if snap.get("volume") else "—")

                # Historical sparkline (last 30 days)
                with get_conn() as _c:
                    hist_rows = _c.execute(
                        "SELECT date, close FROM market_snapshots WHERE ticker=? AND close IS NOT NULL ORDER BY date DESC LIMIT 30",
                        (sym,),
                    ).fetchall()
                if len(hist_rows) >= 2:
                    hist_df = pd.DataFrame([dict(r) for r in reversed(hist_rows)])
                    fig = go.Figure(go.Scatter(
                        x=hist_df["date"], y=hist_df["close"],
                        mode="lines",
                        line=dict(color="#10b981", width=2),
                        fill="tozeroy",
                        fillcolor="rgba(16,185,129,0.08)",
                    ))
                    fig.update_layout(
                        height=160,
                        margin=dict(l=0, r=0, t=0, b=0),
                        plot_bgcolor="rgba(0,0,0,0)",
                        paper_bgcolor="rgba(0,0,0,0)",
                        font=dict(color="#94a3b8", size=10),
                        xaxis=dict(gridcolor="rgba(255,255,255,0.05)", showticklabels=False),
                        yaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
                        showlegend=False,
                    )
                    st.plotly_chart(fig, use_container_width=True)
