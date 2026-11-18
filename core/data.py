"""Live market data from Yahoo Finance: company search, prices, fundamentals, news."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

PERIODS = {"1 year": "1y", "3 years": "3y", "5 years": "5y", "10 years": "10y", "All history": "max"}


@dataclass
class Company:
    ticker: str
    name: str
    sector: str = "—"
    industry: str = "—"
    currency: str = ""
    exchange: str = ""
    summary: str = ""
    market_cap: float | None = None
    pe: float | None = None
    forward_pe: float | None = None
    pb: float | None = None
    dividend_yield: float | None = None  # as a fraction, e.g. 0.0677
    roe: float | None = None
    profit_margin: float | None = None
    revenue_growth: float | None = None
    beta: float | None = None
    news: list[dict] = field(default_factory=list)

    @property
    def short(self) -> str:
        """Friendly display name: 'Société Générale Société anonyme' -> 'Société Générale'."""
        drop = {"sa", "s.a.", "inc", "inc.", "corp", "corp.", "corporation", "plc", "ag", "nv", "n.v.", "se",
                "ltd", "ltd.", "limited", "société anonyme", "societe anonyme", "co.", "company", "holdings"}
        name = self.name
        for suffix in sorted(drop, key=len, reverse=True):
            if name.lower().endswith(" " + suffix):
                name = name[: -len(suffix) - 1].rstrip(" ,")
        return name or self.ticker


def search_companies(query: str, limit: int = 6) -> list[dict]:
    """Return stock matches for a name or ticker, e.g. 'apple' -> AAPL."""
    query = (query or "").strip()
    if len(query) < 2:
        return []
    try:
        quotes = yf.Search(query, max_results=limit * 2, news_count=0).quotes
    except Exception:
        quotes = []
    results = []
    for q in quotes:
        if q.get("quoteType") not in ("EQUITY", "ETF"):
            continue
        results.append(
            {
                "ticker": q.get("symbol"),
                "name": q.get("longname") or q.get("shortname") or q.get("symbol"),
                "exchange": q.get("exchDisp") or q.get("exchange") or "",
            }
        )
    # If the user typed an exact ticker that search didn't return, still offer it.
    if not results and re.fullmatch(r"[A-Za-z0-9.\-^=]{1,15}", query):
        results.append({"ticker": query.upper(), "name": query.upper(), "exchange": ""})
    return results[:limit]


def _num(v):
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _keywords(name: str, ticker: str) -> list[str]:
    """Words that a headline must contain to count as being about this company."""
    stop = {"inc", "inc.", "sa", "s.a.", "plc", "corp", "corporation", "group", "groupe", "ag", "nv",
            "se", "co", "company", "ltd", "limited", "holdings", "the", "anonyme", "société", "societe", "act.a"}
    words = [w for w in re.split(r"[\s,]+", name.lower()) if w and w not in stop and len(w) > 2]
    keys = set(words[:2])
    base = ticker.split(".")[0].lower()
    if len(base) >= 2:
        keys.add(base)
    if "société générale" in name.lower() or "societe generale" in name.lower():
        keys |= {"société générale", "societe generale", "socgen"}
    return sorted(keys)


def _clean_news(raw: list, name: str, ticker: str, limit: int = 6) -> list[dict]:
    keys = _keywords(name, ticker)
    items = []
    for item in raw or []:
        c = item.get("content", item)
        title = (c.get("title") or "").strip()
        if not title:
            continue
        text = f"{title} {c.get('summary') or ''}".lower()
        relevant = any(k in text for k in keys)
        url = (c.get("canonicalUrl") or {}).get("url") or (c.get("clickThroughUrl") or {}).get("url") or c.get("link")
        provider = (c.get("provider") or {}).get("displayName") or c.get("publisher") or ""
        when = c.get("pubDate") or c.get("displayTime")
        try:
            when = datetime.fromisoformat(when.replace("Z", "+00:00")) if isinstance(when, str) else (
                datetime.fromtimestamp(c["providerPublishTime"], tz=timezone.utc) if c.get("providerPublishTime") else None)
        except Exception:
            when = None
        items.append({"title": title, "summary": (c.get("summary") or "").strip(), "url": url,
                      "source": provider, "date": when, "relevant": relevant})
    # Keep headlines that actually mention the company first.
    items.sort(key=lambda x: (not x["relevant"], -(x["date"].timestamp() if x["date"] else 0)))
    return [i for i in items if i["relevant"]][:limit] or items[:limit]


def load_company(ticker: str) -> Company:
    t = yf.Ticker(ticker)
    try:
        info = t.info or {}
    except Exception:
        info = {}
    name = info.get("longName") or info.get("shortName") or ticker
    dy = _num(info.get("dividendYield"))
    if dy is not None:
        dy = dy / 100  # yfinance >= 0.2.50 reports this one in percent
    elif _num(info.get("trailingAnnualDividendYield")) is not None:
        dy = _num(info.get("trailingAnnualDividendYield"))
    try:
        raw_news = t.news
    except Exception:
        raw_news = []
    return Company(
        ticker=ticker.upper(),
        name=name,
        sector=info.get("sector") or "—",
        industry=info.get("industry") or "—",
        currency=info.get("currency") or info.get("financialCurrency") or "",
        exchange=info.get("fullExchangeName") or info.get("exchange") or "",
        summary=info.get("longBusinessSummary") or "",
        market_cap=_num(info.get("marketCap")),
        pe=_num(info.get("trailingPE")),
        forward_pe=_num(info.get("forwardPE")),
        pb=_num(info.get("priceToBook")),
        dividend_yield=dy,
        roe=_num(info.get("returnOnEquity")),
        profit_margin=_num(info.get("profitMargins")),
        revenue_growth=_num(info.get("revenueGrowth")),
        beta=_num(info.get("beta")),
        news=_clean_news(raw_news, name, ticker),
    )


def load_prices(tickers: list[str], period: str) -> pd.DataFrame:
    """Daily adjusted closing prices (dividends & splits accounted for), one column per ticker."""
    frames = {}
    for tk in tickers:
        h = yf.Ticker(tk).history(period=period, auto_adjust=True)
        if h.empty:
            raise ValueError(f"No price history found for {tk}. Check the ticker and try again.")
        s = h["Close"].copy()
        s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
        frames[tk] = s[~s.index.duplicated(keep="last")]
    df = pd.DataFrame(frames).dropna()  # only days where both markets traded
    if len(df) < 30:
        raise ValueError("Not enough overlapping trading days between the two companies for this period.")
    return df
