"""Gemini reads the pre-computed facts + headlines and writes plain-English text. It never does maths."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from .analysis import Metrics
from .data import Company

DEFAULT_MODEL = "gemini-3.1-flash-lite"


@dataclass
class AISummary:
    plain_summary: str
    positive: str
    negative: str
    risks: str
    news_tone: dict = field(default_factory=dict)  # {"A": "positive", "B": "negative"}
    prompt: str = ""
    model: str = ""
    used_ai: bool = False
    error: str = ""


def _fmt(v, kind):
    if v is None:
        return "n/a"
    return {"pct": f"{v:.2%}", "spct": f"{v:+.2%}", "x": f"{v:.2f}", "bn": f"{v / 1e9:,.2f}"}[kind]


def build_prompt(a: Company, b: Company, ma: Metrics, mb: Metrics, period_label: str,
                 start: str, end: str, corr: float, extra_news: list[str]) -> str:
    def row(label, va, vb):
        return f"- {label}: {a.ticker} {va}; {b.ticker} {vb}"

    lines = [
        "You are an equity research analyst writing for a NON-EXPERT reader (a student or a first-time investor).",
        "Use ONLY the pre-computed figures and the news headlines below. Do NOT calculate, estimate or invent any",
        "number or fact. Never contradict the figures. Only use a headline for the company it is labelled with.",
        f"PERIOD: {start} to {end} ({period_label})",
        "MARKET FACTS (computed in Python from Yahoo Finance):",
        row("Company", a.name, b.name),
        row("Sector", a.sector, b.sector),
        row("Currency", a.currency, b.currency),
        row("Market cap (bn)", _fmt(a.market_cap, "bn"), _fmt(b.market_cap, "bn")),
        row("Trailing P/E", _fmt(a.pe, "x"), _fmt(b.pe, "x")),
        row("Price / Book", _fmt(a.pb, "x"), _fmt(b.pb, "x")),
        row("Return on equity", _fmt(a.roe, "pct"), _fmt(b.roe, "pct")),
        row("Dividend yield", _fmt(a.dividend_yield, "pct"), _fmt(b.dividend_yield, "pct")),
        row("Total return", _fmt(ma.total_return, "spct"), _fmt(mb.total_return, "spct")),
        row("Average yearly return", _fmt(ma.cagr, "spct"), _fmt(mb.cagr, "spct")),
        row("Last 12 months return", _fmt(ma.one_year_return, "spct"), _fmt(mb.one_year_return, "spct")),
        row("Annual volatility", _fmt(ma.volatility, "pct"), _fmt(mb.volatility, "pct")),
        row("Max drawdown", _fmt(ma.max_drawdown, "pct"), _fmt(mb.max_drawdown, "pct")),
        row("Return per unit of risk", _fmt(ma.return_per_risk, "x"), _fmt(mb.return_per_risk, "x")),
        f"- Correlation of daily returns: {corr:.2f}",
        "NEWS (latest headlines, fetched automatically from Yahoo Finance):",
    ]
    for c in (a, b):
        for n in c.news:
            lines.append(f"- [{c.ticker}] {n['title']}")
    for h in extra_news:
        lines.append(f"- [USER-PROVIDED] {h}")
    lines += [
        "TASK: Reply with JSON only, using exactly these keys:",
        '{"plain_summary": "2 sentences, simple words, who did better and why it matters",',
        ' "positive": "Positive catalysts: max 40 words, name the company concerned",',
        ' "negative": "Negative developments: max 40 words, name the company concerned",',
        ' "risks": "Key risks to watch: max 40 words, name the company concerned",',
        f' "news_tone": {{"{a.ticker}": "positive|neutral|negative", "{b.ticker}": "positive|neutral|negative"}}}}',
        "Every statement must come from one specific headline or figure above. Do not give buy/sell advice.",
    ]
    return "\n".join(lines)


def _fallback(a: Company, b: Company, ma: Metrics, mb: Metrics, prompt: str, error: str = "") -> AISummary:
    lead, lag, ml, mg = (a, b, ma, mb) if ma.total_return >= mb.total_return else (b, a, mb, ma)
    calmer = a if ma.volatility <= mb.volatility else b
    return AISummary(
        plain_summary=(f"{lead.short} grew more over this period ({ml.total_return:+.1%} vs "
                       f"{mg.total_return:+.1%} for {lag.short}). {calmer.short} had the calmer share price."),
        positive=f"{lead.short} delivered the higher total return ({ml.total_return:+.1%}).",
        negative=f"{lag.short} lagged, with a worst drop of {mg.max_drawdown:.1%} from its peak.",
        risks="AI news reading is switched off (no Gemini key), so check the latest headlines below yourself.",
        prompt=prompt, used_ai=False, error=error,
    )


def get_api_key() -> str | None:
    try:
        import streamlit as st
        key = st.secrets.get("GEMINI_API_KEY")
        if key:
            return key
    except Exception:
        pass
    return os.environ.get("GEMINI_API_KEY")


def get_model() -> str:
    try:
        import streamlit as st
        return st.secrets.get("GEMINI_MODEL", DEFAULT_MODEL)
    except Exception:
        return os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)


def summarise(a: Company, b: Company, ma: Metrics, mb: Metrics, prompt: str) -> AISummary:
    key = get_api_key()
    if not key:
        return _fallback(a, b, ma, mb, prompt)
    model = get_model()
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=key)
        resp = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.2),
        )
        data = json.loads(resp.text)
        tone = data.get("news_tone") or {}
        return AISummary(
            plain_summary=data.get("plain_summary", "").strip(),
            positive=data.get("positive", "").strip(),
            negative=data.get("negative", "").strip(),
            risks=data.get("risks", "").strip(),
            news_tone={"A": tone.get(a.ticker), "B": tone.get(b.ticker)},
            prompt=prompt, model=model, used_ai=True,
        )
    except Exception as e:  # never break the app because the AI is unavailable
        return _fallback(a, b, ma, mb, prompt, error=f"{type(e).__name__}: {e}")
