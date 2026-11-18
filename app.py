"""PeerLens: compare two companies in plain English. Run with:  streamlit run app.py"""
from __future__ import annotations

import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import ai as ai_mod
from core.analysis import base_100, compute_metrics, correlation, scorecard, verdict
from core.data import PERIODS, load_company, load_prices, search_companies
from core.excel import build_memo, memo_filename

st.set_page_config(page_title="PeerLens · Compare two companies", page_icon="📊", layout="wide",
                   initial_sidebar_state="collapsed")

COLOR_A, COLOR_B = "#2563EB", "#EA580C"
SYMBOLS = {"EUR": "€", "USD": "$", "GBP": "£", "GBp": "£", "JPY": "¥", "INR": "₹", "CHF": "CHF ", "CNY": "¥",
           "HKD": "HK$", "CAD": "C$", "AUD": "A$"}

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"], .stMarkdown, button, input, textarea { font-family: 'Inter', sans-serif !important; }
#MainMenu, footer, header [data-testid="stToolbar"] { visibility: hidden; }
.block-container { padding-top: 2rem; max-width: 1180px; }
.hero h1 { font-size: 2.4rem; font-weight: 800; letter-spacing: -0.03em; color: #0F172A; margin: 0 0 .3rem; }
.hero p { font-size: 1.08rem; color: #475569; max-width: 760px; margin: 0; line-height: 1.55; }
.step { font-size: .78rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: #2563EB;
        margin: 1.4rem 0 .4rem; }
.card { background: #fff; border: 1px solid #E2E8F0; border-radius: 16px; padding: 1.2rem 1.35rem;
        box-shadow: 0 1px 2px rgba(15,23,42,.04); height: 100%; }
.verdict { border-radius: 20px; padding: 1.6rem 1.8rem; color: #fff;
           background: linear-gradient(135deg, #0F172A 0%, #1E3A8A 100%); }
.verdict .kicker { font-size: .8rem; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; opacity: .75; }
.verdict h2 { font-size: 1.9rem; font-weight: 800; margin: .3rem 0 .4rem; letter-spacing: -.02em; color: #fff; }
.verdict p { margin: 0; opacity: .9; font-size: 1rem; }
.bar { display: flex; height: 12px; border-radius: 999px; overflow: hidden; margin: 1rem 0 .45rem;
       background: rgba(255,255,255,.15); }
.bar span { display: block; height: 100%; }
.legend { display: flex; justify-content: space-between; font-size: .9rem; font-weight: 600; }
.money .label { color: #64748B; font-size: .9rem; margin-bottom: .2rem; }
.money .value { font-size: 2.1rem; font-weight: 800; letter-spacing: -.02em; }
.money .delta { font-size: .95rem; font-weight: 600; }
.dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; }
table.score { width: 100%; border-collapse: separate; border-spacing: 0; font-size: .95rem; }
table.score th { text-align: left; color: #64748B; font-weight: 600; font-size: .8rem; text-transform: uppercase;
                 letter-spacing: .05em; padding: .6rem .7rem; border-bottom: 1px solid #E2E8F0; }
table.score th, table.score td { border-left: none !important; border-right: none !important; border-top: none !important; }
table.score td { padding: .75rem .7rem; border-bottom: 1px solid #F1F5F9; vertical-align: middle; }
table.score td.q { color: #64748B; font-size: .85rem; }
table.score td.v { font-variant-numeric: tabular-nums; font-weight: 600; white-space: nowrap; }
td.win { background: #F0FDF4; color: #166534 !important; border-radius: 8px; }
td.win::after { content: " ✓"; }
.insight { min-height: 150px; }
@media (max-width: 640px) {
  table.score td.q, table.score th:nth-child(2) { display: none; }
  .hero h1 { font-size: 1.8rem; } .verdict h2 { font-size: 1.5rem; } .money .value { font-size: 1.7rem; }
}
.insight h4 { margin: 0 0 .4rem; font-size: 1rem; }
.insight p { margin: 0; color: #334155; line-height: 1.55; }
.news a { color: #0F172A; font-weight: 600; text-decoration: none; line-height: 1.4; }
.news a:hover { color: #2563EB; text-decoration: underline; }
.news .meta { color: #94A3B8; font-size: .8rem; margin: .15rem 0 .9rem; }
.pill { display: inline-block; padding: .15rem .6rem; border-radius: 999px; font-size: .78rem; font-weight: 700; }
.small { color: #64748B; font-size: .85rem; }
div[data-testid="stDownloadButton"] button, div[data-testid="stButton"] button[kind="primary"] {
    border-radius: 12px; font-weight: 700; padding: .7rem 1.2rem; font-size: 1rem; }
</style>
""",
    unsafe_allow_html=True,
)


# ---------- cached data access (1 hour) ----------
@st.cache_data(ttl=3600, show_spinner=False)
def cached_search(q: str):
    return search_companies(q)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_company(t: str):
    return load_company(t)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_prices(tickers: tuple, period: str):
    return load_prices(list(tickers), period)


def money(v: float, cur: str) -> str:
    sym = SYMBOLS.get(cur, "")
    return f"{sym}{v:,.0f}" if sym else f"{v:,.0f} {cur}"


def safe_url(u) -> str:
    """Only allow normal web links (blocks javascript: and other unsafe schemes)."""
    u = str(u or "")
    return u if u.startswith(("https://", "http://")) else "#"


def esc(s) -> str:
    return html.escape(str(s or ""))


# ---------- header ----------
st.markdown(
    """<div class="hero"><h1>📊 Compare two companies</h1>
    <p>Pick any two listed companies. We pull up to <b>10 years of live market data</b>, read the
    <b>latest news</b>, and show you in plain English which one looks stronger on the numbers. Then download the
    full Excel memo in one click.</p></div>""",
    unsafe_allow_html=True,
)


def company_picker(col, label: str, default: str, key: str):
    with col:
        q = st.text_input(label, value=default, key=f"{key}_q",
                          placeholder="Type a name or ticker, e.g. Apple, LVMH, BNP.PA")
        matches = cached_search(q) if q else []
        if not matches:
            if q:
                st.caption("No company found. Try another spelling or the stock ticker.")
            return None
        opts = {f"{m['name']}  ·  {m['ticker']}" + (f"  ·  {m['exchange']}" if m["exchange"] else ""): m["ticker"]
                for m in matches}
        choice = st.selectbox("Pick the right one", list(opts), key=f"{key}_pick", label_visibility="collapsed")
        return opts[choice]


st.markdown('<div class="step">Step 1 · Choose two companies</div>', unsafe_allow_html=True)
c1, c2 = st.columns(2, gap="large")
ticker_a = company_picker(c1, "First company", "BNP Paribas", "a")
ticker_b = company_picker(c2, "Second company", "Societe Generale", "b")

st.markdown('<div class="step">Step 2 · How far back should we look?</div>', unsafe_allow_html=True)
period_label = st.segmented_control("Period", list(PERIODS), default="10 years", label_visibility="collapsed") or "10 years"
with st.expander("➕ Add your own news headlines (optional)"):
    extra = st.text_area("One headline per line. We already fetch the latest news automatically.",
                         placeholder="e.g. BNP Paribas announces €1bn share buyback", height=90)

go_btn = st.button("Compare now  →", type="primary", width="stretch",
                   disabled=not (ticker_a and ticker_b))
if ticker_a and ticker_b and ticker_a == ticker_b:
    st.warning("You picked the same company twice. Choose two different ones.")
    go_btn = False

# ---------- run analysis ----------
if go_btn:
    try:
        with st.status("Working on it…", expanded=True) as status:
            st.write("🔎 Looking up both companies…")
            a, b = cached_company(ticker_a), cached_company(ticker_b)
            st.write(f"📈 Downloading {period_label.lower()} of daily prices…")
            prices = cached_prices((ticker_a, ticker_b), PERIODS[period_label])
            ma, mb = compute_metrics(prices[ticker_a]), compute_metrics(prices[ticker_b])
            corr = correlation(prices)
            st.write("📰 Reading the latest news with AI…")
            extra_news = [h.strip() for h in (extra or "").splitlines() if h.strip()]
            prompt = ai_mod.build_prompt(a, b, ma, mb, period_label, prices.index[0].strftime("%d %b %Y"),
                                         prices.index[-1].strftime("%d %b %Y"), corr, extra_news)
            summary = ai_mod.summarise(a, b, ma, mb, prompt)
            checks = scorecard(a, b, ma, mb, summary.news_tone if summary.used_ai else None)
            leader, wa, wb_, _ = verdict(checks)
            st.write("📄 Preparing your Excel memo…")
            b100 = base_100(prices)
            xlsx = build_memo(a, b, ma, mb, prices, b100, checks, leader, (wa, wb_), corr, summary, period_label)
            status.update(label="Done! Scroll down for your results.", state="complete", expanded=False)
        st.session_state["result"] = dict(a=a, b=b, ma=ma, mb=mb, prices=prices, b100=b100, corr=corr,
                                          summary=summary, checks=checks, leader=leader, wins=(wa, wb_),
                                          xlsx=xlsx, period=period_label)
    except Exception as e:
        st.error(f"Sorry, something went wrong while fetching the data: {e}")

res = st.session_state.get("result")
if not res:
    st.markdown('<div class="card" style="margin-top:1rem;text-align:center">'
                '👆 Click <b>Compare now</b>. Your results and the <b>📥 Download Excel memo</b> button '
                'will appear here in about 10 seconds.</div>'
                '<p class="small" style="margin-top:1rem">Tip: you can type a company name in any language '
                'Yahoo Finance knows, or a ticker like <b>AAPL</b>, <b>MC.PA</b> or <b>7203.T</b>.</p>',
                unsafe_allow_html=True)
    st.stop()

a, b, ma, mb = res["a"], res["b"], res["ma"], res["mb"]
prices, b100, summary, checks = res["prices"], res["b100"], res["summary"], res["checks"]
leader, (wa, wb_) = res["leader"], res["wins"]
start, end = prices.index[0], prices.index[-1]
st.divider()

# ---------- 1. verdict ----------
lead_co = {"A": a, "B": b}.get(leader)
counted = max(wa + wb_, 1)
left, right = st.columns([2.2, 1], gap="large")
with left:
    headline = (f"{esc(lead_co.short)} looks stronger on the numbers" if lead_co
                else "It's a tie: both have their strengths")
    st.markdown(
        f"""<div class="verdict"><div class="kicker">Our data-based verdict · {esc(res['period'])}</div>
        <h2>{headline}</h2>
        <p>{esc(summary.plain_summary)}</p>
        <div class="bar"><span style="width:{wa / counted * 100:.0f}%;background:{COLOR_A}"></span>
        <span style="width:{wb_ / counted * 100:.0f}%;background:{COLOR_B}"></span></div>
        <div class="legend"><span>{esc(a.short)}: {wa} wins</span><span>{esc(b.short)}: {wb_} wins</span></div>
        </div>""",
        unsafe_allow_html=True,
    )
with right:
    st.markdown(
        f"""<div class="card"><b>📥 Your Excel memo is ready</b>
        <p class="small" style="margin:.4rem 0 .9rem">Includes the chart, all figures, the head-to-head checks,
        the AI summary, the latest news and the exact AI prompt (for audit).</p></div>""",
        unsafe_allow_html=True,
    )
    st.download_button("⬇  Download Excel memo", data=res["xlsx"], file_name=memo_filename(a, b),
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       type="primary", width="stretch", on_click="ignore")
st.caption("⚠️ This is an educational comparison of past data, not financial advice. Past performance does not "
           "guarantee future results. Do your own research or talk to a licensed advisor before investing.")

# ---------- 2. what would 1,000 have become ----------
st.markdown(f'<div class="step">If you had invested 1,000 on {start:%d %b %Y}</div>', unsafe_allow_html=True)
m1, m2 = st.columns(2, gap="large")
for col, co, m, color in ((m1, a, ma, COLOR_A), (m2, b, mb, COLOR_B)):
    with col:
        up = m.total_return >= 0
        st.markdown(
            f"""<div class="card money"><div class="label"><span class="dot" style="background:{color}"></span>
            {esc(co.short)} <span class="small">({esc(co.ticker)})</span></div>
            <div class="value">{money(m.value_of_1000, co.currency)}</div>
            <div class="delta" style="color:{'#16A34A' if up else '#DC2626'}">{'▲' if up else '▼'}
            {m.total_return:+.1%} in total · {m.cagr:+.1%} per year on average</div></div>""",
            unsafe_allow_html=True,
        )
if a.currency and b.currency and a.currency != b.currency:
    st.caption(f"Note: each stock is measured in its own currency ({a.currency} vs {b.currency}).")

# ---------- 3. chart ----------
st.markdown('<div class="step">How the two share prices moved</div>', unsafe_allow_html=True)
view = st.segmented_control("Chart view", ["Growth of 100", "Share price"], default="Growth of 100",
                            label_visibility="collapsed") or "Growth of 100"
data = b100 if view == "Growth of 100" else prices
fig = go.Figure()
for tk, co, color in ((a.ticker, a, COLOR_A), (b.ticker, b, COLOR_B)):
    fig.add_trace(go.Scatter(x=data.index, y=data[tk], name=f"{co.short} ({tk})", mode="lines",
                             line=dict(color=color, width=2.2),
                             hovertemplate="%{x|%d %b %Y}<br><b>%{y:,.2f}</b><extra>" + tk + "</extra>"))
if view == "Growth of 100":
    fig.add_hline(y=100, line_dash="dot", line_color="#94A3B8",
                  annotation_text="starting value", annotation_position="bottom left")
fig.update_layout(height=450, margin=dict(l=10, r=10, t=40, b=10), hovermode="x unified",
                  plot_bgcolor="white", paper_bgcolor="white", font=dict(family="Inter", size=13),
                  legend=dict(orientation="h", y=1.12, x=1, xanchor="right"),
                  yaxis=dict(gridcolor="#F1F5F9", title=None),
                  xaxis=dict(gridcolor="#F1F5F9", rangeselector=dict(x=0, y=1.12, bgcolor="#F1F5F9", buttons=[
                      dict(count=1, label="1Y", step="year", stepmode="backward"),
                      dict(count=3, label="3Y", step="year", stepmode="backward"),
                      dict(count=5, label="5Y", step="year", stepmode="backward"),
                      dict(step="all", label="All")]), type="date"))
st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
st.caption("“Growth of 100” shows what 100 invested at the start would be worth on each day "
           "(dividends reinvested, splits adjusted). It makes two very different share prices easy to compare.")

# ---------- 4. scorecard ----------
st.markdown('<div class="step">Head-to-head checks</div>', unsafe_allow_html=True)
rows = []
for c in checks:
    ca = "v win" if c.winner == "A" else "v"
    cb = "v win" if c.winner == "B" else "v"
    rows.append(f"<tr><td><b>{esc(c.label)}</b></td><td class='q'>{esc(c.question)}</td>"
                f"<td class='{ca}'>{esc(c.a_value)}</td><td class='{cb}'>{esc(c.b_value)}</td></tr>")
st.markdown(
    f"""<div class="card"><table class="score"><thead><tr><th>Check</th><th>What it means</th>
    <th><span class="dot" style="background:{COLOR_A}"></span>{esc(a.ticker)}</th>
    <th><span class="dot" style="background:{COLOR_B}"></span>{esc(b.ticker)}</th></tr></thead>
    <tbody>{''.join(rows)}</tbody></table></div>""",
    unsafe_allow_html=True,
)

# ---------- 5. AI insights ----------
st.markdown('<div class="step">What the news and numbers say</div>', unsafe_allow_html=True)
if not summary.used_ai:
    if summary.error:
        why = ai_mod.REASONS.get(summary.error, "Gemini didn't respond")
        st.warning(f"The AI summary didn't run because {why}. "
                   "Showing an automatic summary from the numbers instead.")
        if summary.error_detail:
            st.caption(f"For the app owner: {summary.error_detail}")
    else:
        st.info("The AI summary is off because no Gemini API key is set. "
                "Showing an automatic summary from the numbers instead.")
i1, i2, i3 = st.columns(3, gap="medium")
for col, icon, title, text, tint in (
    (i1, "✅", "Good news", summary.positive, "#F0FDF4"),
    (i2, "⚠️", "Bad news", summary.negative, "#FEF2F2"),
    (i3, "👀", "Risks to watch", summary.risks, "#FFFBEB"),
):
    with col:
        st.markdown(f'<div class="card insight" style="background:{tint}"><h4>{icon} {title}</h4>'
                    f'<p>{esc(text)}</p></div>', unsafe_allow_html=True)

# ---------- 6. latest news ----------
st.markdown('<div class="step">Latest news</div>', unsafe_allow_html=True)
TONE = {"positive": ("#DCFCE7", "#166534"), "negative": ("#FEE2E2", "#991B1B"), "neutral": ("#F1F5F9", "#475569")}
n1, n2 = st.columns(2, gap="large")
for col, co, key, color in ((n1, a, "A", COLOR_A), (n2, b, "B", COLOR_B)):
    with col:
        tone = str(summary.news_tone.get(key) or "").lower() if summary.used_ai else ""
        pill = ""
        if tone in TONE:
            bg, fg = TONE[tone]
            pill = f'<span class="pill" style="background:{bg};color:{fg}">News mood: {tone}</span>'
        items = "".join(
            f'<div><a href="{esc(safe_url(n["url"]))}" target="_blank" rel="noopener noreferrer">{esc(n["title"])}</a>'
            f'<div class="meta">{esc(n["source"])}{" · " + n["date"].strftime("%d %b %Y") if n["date"] else ""}'
            f'</div></div>'
            for n in co.news
        ) or '<p class="small">No recent headlines found.</p>'
        st.markdown(f'<div class="card news"><div style="display:flex;justify-content:space-between;'
                    f'align-items:center;margin-bottom:.8rem"><b><span class="dot" style="background:{color}">'
                    f'</span>{esc(co.short)}</b>{pill}</div>{items}</div>', unsafe_allow_html=True)

# ---------- 7. details ----------
st.markdown('<div class="step">More details</div>', unsafe_allow_html=True)
with st.expander("🏢 What do these companies do?"):
    for co in (a, b):
        st.markdown(f"**{co.name}** · {co.sector} · {co.industry}")
        st.write(co.summary[:900] + ("…" if len(co.summary) > 900 else "") if co.summary else "No description available.")
with st.expander("🔬 For analysts: all figures"):
    def f(v, kind):
        if v is None:
            return "n/a"
        return {"pct": f"{v:.2%}", "x": f"{v:.2f}", "p": f"{v:,.2f}", "bn": f"{v / 1e9:,.2f}"}[kind]
    table = pd.DataFrame({
        "Metric": ["Market cap (bn)", "Trailing P/E", "Forward P/E", "Price / Book", "Return on equity",
                   "Profit margin", "Revenue growth", "Dividend yield", "Beta", "Start price", "End price",
                   "Total return", "Average yearly return", "Last 12 months", "Annual volatility", "Max drawdown",
                   "Return per unit of risk"],
        a.ticker: [f(a.market_cap, "bn"), f(a.pe, "x"), f(a.forward_pe, "x"), f(a.pb, "x"), f(a.roe, "pct"),
                   f(a.profit_margin, "pct"), f(a.revenue_growth, "pct"), f(a.dividend_yield, "pct"), f(a.beta, "x"),
                   f(ma.start_price, "p"), f(ma.end_price, "p"), f(ma.total_return, "pct"), f(ma.cagr, "pct"),
                   f(ma.one_year_return, "pct"), f(ma.volatility, "pct"), f(ma.max_drawdown, "pct"),
                   f(ma.return_per_risk, "x")],
        b.ticker: [f(b.market_cap, "bn"), f(b.pe, "x"), f(b.forward_pe, "x"), f(b.pb, "x"), f(b.roe, "pct"),
                   f(b.profit_margin, "pct"), f(b.revenue_growth, "pct"), f(b.dividend_yield, "pct"), f(b.beta, "x"),
                   f(mb.start_price, "p"), f(mb.end_price, "p"), f(mb.total_return, "pct"), f(mb.cagr, "pct"),
                   f(mb.one_year_return, "pct"), f(mb.volatility, "pct"), f(mb.max_drawdown, "pct"),
                   f(mb.return_per_risk, "x")],
    })
    st.dataframe(table, hide_index=True, width="stretch")
    st.caption(f"Correlation of daily returns: {res['corr']:.2f} · {len(prices):,} common trading days · "
               f"{start:%d %b %Y} to {end:%d %b %Y}")
with st.expander("🧾 Audit: exact text sent to the AI"):
    st.caption(f"Model: {summary.model or 'not connected'}. The AI only receives these pre-computed figures "
               "and headlines; it never calculates anything.")
    st.code(summary.prompt, language=None)

st.markdown('<p class="small" style="text-align:center;margin-top:2rem">Data: Yahoo Finance (may be delayed). '
            'AI text: Google Gemini. Built for learning, not investment advice.</p>', unsafe_allow_html=True)
