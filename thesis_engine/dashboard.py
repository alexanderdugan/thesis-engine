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

st.markdown("""
<style>
.overdue { color: #ff4b4b; font-weight: bold; }
.on-track { color: #21c354; }
.metric-card { background: #1e1e1e; border-radius: 8px; padding: 1rem; }
</style>
""", unsafe_allow_html=True)

page = st.sidebar.radio(
    "Navigate",
    ["Positions", "New Trade", "Performance", "Thesis Journal", "Research"],
    index=0,
)

@st.cache_data(ttl=60)
def _market_status():
    return AlpacaClient().get_market_status()

_mkt = _market_status()
if _mkt["is_open"]:
    st.sidebar.success("Market open")
else:
    from datetime import datetime, timezone as _tz
    next_open_dt = datetime.fromisoformat(_mkt["next_open"])
    next_open_str = next_open_dt.strftime("%a %b %-d, %-I:%M %p ET")
    st.sidebar.warning(f"Market closed · opens {next_open_str}")

# ─── POSITIONS ────────────────────────────────────────────────────────────────
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
                pl = pos.get('unrealized_pl') or 0
                plpc = (pos.get('unrealized_plpc') or 0) * 100
                header = (
                    f"{'🔴 ' if overdue else ''}{symbol}  —  "
                    f"{'▲' if pl >= 0 else '▼'} ${pl:+,.2f}  ({plpc:+.2f}%)"
                )

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
                    st.info("OPG order submitted — this position will fill at the next market open and update automatically on sync.")

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

# ─── NEW TRADE ────────────────────────────────────────────────────────────────
elif page == "New Trade":
    st.title("New Trade")
    if _mkt["is_open"]:
        st.caption("Market is open — order will fill immediately.")
    else:
        from datetime import datetime as _dt2
        next_open = _dt2.fromisoformat(_mkt["next_open"]).strftime("%a %b %-d, %-I:%M %p ET")
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
                    from datetime import datetime as _dt
                    next_open = _dt.fromisoformat(result["next_open"]).strftime("%a %b %-d, %-I:%M %p ET")
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

# ─── PERFORMANCE ──────────────────────────────────────────────────────────────
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
                f"{summary['portfolio_cumulative']:+.2f}%" if summary['portfolio_cumulative'] is not None else "—",
            )
            m3.metric(
                "SPY",
                f"{summary['spy_cumulative']:+.2f}%" if summary['spy_cumulative'] is not None else "—",
            )
            m4.metric(
                "QQQ",
                f"{summary['qqq_cumulative']:+.2f}%" if summary['qqq_cumulative'] is not None else "—",
            )
            m5.metric(
                "Alpha vs SPY",
                f"{summary['alpha_vs_spy']:+.2f}%" if summary['alpha_vs_spy'] is not None else "—",
            )

        st.subheader("Cumulative Return")
        df = pd.DataFrame(history)
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df["date"], y=df["portfolio_return_cumulative"],
            name="Portfolio", line=dict(color="#00d4aa", width=2),
        ))
        fig.add_trace(go.Scatter(
            x=df["date"], y=df["spy_return_cumulative"],
            name="SPY", line=dict(color="#636efa", width=2, dash="dot"),
        ))
        fig.add_trace(go.Scatter(
            x=df["date"], y=df["qqq_return_cumulative"],
            name="QQQ", line=dict(color="#ef553b", width=2, dash="dot"),
        ))
        fig.add_hline(y=0, line_color="gray", line_dash="dash", opacity=0.4)
        fig.update_layout(
            yaxis_title="Cumulative Return (%)",
            xaxis_title="Date",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            height=400,
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

# ─── THESIS JOURNAL ───────────────────────────────────────────────────────────
elif page == "Thesis Journal":
    st.title("Thesis Journal")

    col_filter, col_search = st.columns([1, 3])
    status_filter = col_filter.selectbox("Status", ["All", "Open", "Closed"], index=0)
    search = col_search.text_input("Search by symbol or thesis keyword", placeholder="NVDA, AI, rates...")

    status_arg = None if status_filter == "All" else status_filter.lower()
    theses = list_theses(status=status_arg)

    if search:
        q = search.lower()
        theses = [
            t for t in theses
            if q in t["symbol"].lower() or q in (t.get("thesis_text") or "").lower()
        ]

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

# ─── RESEARCH ─────────────────────────────────────────────────────────────────
elif page == "Research":
    import hashlib
    import json as _json
    from datetime import datetime as _dt2, timezone as _tz2
    from research.evaluator import get_evaluator
    from research.adapters.base import Signal as _Signal
    from thesis_engine.config import USE_MOCK_EVALUATOR

    st.title("Research Signals")
    evaluator_label = "mock evaluator" if USE_MOCK_EVALUATOR else "Claude claude-sonnet-4-6"
    st.caption(f"SEC EDGAR + financial news RSS, evaluated for argument quality ({evaluator_label}).")

    # ── Manual paste-in ──────────────────────────────────────────────────────
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
                                 (paste_content.strip())[:300],
                                 _json.dumps(signal.metadata), signal.fetched_at),
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
