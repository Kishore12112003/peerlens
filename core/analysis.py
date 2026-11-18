"""All the maths. Pure Python/pandas: the AI never calculates a number."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .data import Company

TRADING_DAYS = 252


@dataclass
class Metrics:
    start_price: float
    end_price: float
    total_return: float
    cagr: float
    one_year_return: float | None
    volatility: float
    max_drawdown: float
    return_per_risk: float
    value_of_1000: float


def compute_metrics(prices: pd.Series) -> Metrics:
    prices = prices.dropna()
    daily = prices.pct_change().dropna()
    years = max((prices.index[-1] - prices.index[0]).days / 365.25, 1 / 365.25)
    total = prices.iloc[-1] / prices.iloc[0] - 1
    cagr = (1 + total) ** (1 / years) - 1
    vol = float(daily.std() * np.sqrt(TRADING_DAYS))
    dd = float((prices / prices.cummax() - 1).min())
    one_year_ago = prices.index[-1] - pd.DateOffset(years=1)
    past = prices[prices.index <= one_year_ago]
    one_year = float(prices.iloc[-1] / past.iloc[-1] - 1) if len(past) and years >= 1 else None
    return Metrics(
        start_price=float(prices.iloc[0]),
        end_price=float(prices.iloc[-1]),
        total_return=float(total),
        cagr=float(cagr),
        one_year_return=one_year,
        volatility=vol,
        max_drawdown=dd,
        return_per_risk=float(cagr / vol) if vol else 0.0,
        value_of_1000=float(1000 * (1 + total)),
    )


def base_100(prices: pd.DataFrame) -> pd.DataFrame:
    return prices / prices.iloc[0] * 100


@dataclass
class Check:
    label: str          # plain-English name
    question: str       # what it means for a non-expert
    a_value: str
    b_value: str
    winner: str | None  # "A", "B" or None (tie / no data)


def _pct(v, signed=False):
    if v is None:
        return "n/a"
    return f"{v:+.1%}" if signed else f"{v:.1%}"


def _x(v):
    return "n/a" if v is None else f"{v:.1f}×"


def _pick(a, b, higher_is_better=True):
    if a is None or b is None or a == b:
        return None
    return ("A" if a > b else "B") if higher_is_better else ("A" if a < b else "B")


def scorecard(a: Company, b: Company, ma: Metrics, mb: Metrics, news_tone: dict | None = None) -> list[Check]:
    """Head-to-head checks. Each one is a simple, explainable comparison."""
    pe_a = a.pe if a.pe and a.pe > 0 else None
    pe_b = b.pe if b.pe and b.pe > 0 else None
    checks = [
        Check("Long-term growth", "Which share price grew faster per year, on average?",
              _pct(ma.cagr, True) + " / yr", _pct(mb.cagr, True) + " / yr", _pick(ma.cagr, mb.cagr)),
        Check("Last 12 months", "Which one did better over the past year?",
              _pct(ma.one_year_return, True), _pct(mb.one_year_return, True),
              _pick(ma.one_year_return, mb.one_year_return)),
        Check("Smoother ride", "Which price moved up and down less? (lower = calmer)",
              _pct(ma.volatility), _pct(mb.volatility), _pick(ma.volatility, mb.volatility, False)),
        Check("Smaller worst drop", "The biggest fall from a peak. Smaller = less painful.",
              _pct(ma.max_drawdown), _pct(mb.max_drawdown), _pick(ma.max_drawdown, mb.max_drawdown)),
        Check("Reward for the risk", "Growth earned for each unit of ups and downs (higher = better).",
              f"{ma.return_per_risk:.2f}", f"{mb.return_per_risk:.2f}",
              _pick(ma.return_per_risk, mb.return_per_risk)),
        Check("Price vs. profits", "Price/Earnings ratio. Lower = you pay less for each €1 of profit.",
              _x(pe_a), _x(pe_b), _pick(pe_a, pe_b, False)),
        Check("Profitability", "Return on equity: profit made with shareholders' money.",
              _pct(a.roe), _pct(b.roe), _pick(a.roe, b.roe)),
        Check("Dividend income", "Cash paid to shareholders each year, as % of the share price.",
              _pct(a.dividend_yield), _pct(b.dividend_yield), _pick(a.dividend_yield, b.dividend_yield)),
    ]
    if news_tone:
        score = {"positive": 1, "neutral": 0, "mixed": 0, "negative": -1}
        ta, tb = news_tone.get("A"), news_tone.get("B")
        sa, sb = score.get(str(ta).lower()), score.get(str(tb).lower())
        checks.append(Check("Recent news mood", "Is the latest news mostly good or bad? (read by AI)",
                            str(ta or "n/a").capitalize(), str(tb or "n/a").capitalize(), _pick(sa, sb)))
    return checks


def verdict(checks: list[Check]) -> tuple[str | None, int, int, int]:
    """Returns (leader 'A'/'B'/None, wins_a, wins_b, checks_counted)."""
    wa = sum(c.winner == "A" for c in checks)
    wb = sum(c.winner == "B" for c in checks)
    leader = "A" if wa > wb else "B" if wb > wa else None
    return leader, wa, wb, wa + wb


def correlation(prices: pd.DataFrame) -> float:
    r = prices.pct_change().dropna()
    return float(r.iloc[:, 0].corr(r.iloc[:, 1]))
