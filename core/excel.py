"""Builds the downloadable Excel investment memo (in memory, no files on disk)."""
from __future__ import annotations

import io
from datetime import datetime

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import LineChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from .ai import AISummary
from .analysis import Check, Metrics
from .data import Company

NAVY = "1E293B"
BLUE = "2563EB"
ORANGE = "EA580C"
GREY = "F1F5F9"
GREEN = "DCFCE7"
THIN = Side(style="thin", color="CBD5E1")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
DISCLAIMER = ("Educational analysis only, not financial advice. Past performance does not predict future "
              "results. Figures computed in Python from Yahoo Finance data; text written by AI from those figures.")


def _header(ws, row, values, fill=NAVY):
    for i, v in enumerate(values, start=1):
        c = ws.cell(row=row, column=i, value=v)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=fill)
        c.alignment = Alignment(horizontal="center" if i > 1 else "left", vertical="center")
        c.border = BOX


def _row(ws, row, label, va, vb, fmt=None, extra=None):
    cells = [ws.cell(row=row, column=1, value=label), ws.cell(row=row, column=2, value=va),
             ws.cell(row=row, column=3, value=vb)]
    if extra is not None:
        cells.append(ws.cell(row=row, column=4, value=extra))
    cells[0].font = Font(bold=True)
    cells[0].fill = PatternFill("solid", fgColor=GREY)
    for c in cells:
        c.border = BOX
    for c in cells[1:3]:
        c.alignment = Alignment(horizontal="right")
        if fmt:
            c.number_format = fmt
    return cells


def build_memo(a: Company, b: Company, ma: Metrics, mb: Metrics, prices: pd.DataFrame, b100: pd.DataFrame,
               checks: list[Check], leader: str | None, wins: tuple[int, int], corr: float,
               ai: AISummary, period_label: str) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Memo"
    ws.sheet_view.showGridLines = False
    start, end = prices.index[0].strftime("%d %b %Y"), prices.index[-1].strftime("%d %b %Y")

    ws["A1"] = f"Investment Comparison Memo: {a.name} vs {b.name}"
    ws["A1"].font = Font(size=16, bold=True, color=NAVY)
    ws["A2"] = (f"Period: {start} – {end} ({period_label})  |  Source: Yahoo Finance  |  "
                f"Generated {datetime.now():%d %b %Y %H:%M}")
    ws["A2"].font = Font(italic=True, color="64748B")

    lead_name = {"A": a.name, "B": b.name}.get(leader)
    ws["A4"] = (f"On these checks, {lead_name} comes out ahead ({max(wins)} of {sum(wins)} checks won)."
                if lead_name else f"It's a tie on these checks ({wins[0]} each).")
    ws["A4"].font = Font(size=13, bold=True, color="166534" if lead_name else NAVY)
    ws["A5"] = DISCLAIMER
    ws["A5"].font = Font(size=9, italic=True, color="64748B")

    r = 7
    _header(ws, r, ["Key figures", a.ticker, b.ticker])
    rows = [
        ("Company", a.name, b.name, None),
        ("Sector", a.sector, b.sector, None),
        ("Currency", a.currency, b.currency, None),
        ("Market cap (bn)", (a.market_cap or 0) / 1e9 or None, (b.market_cap or 0) / 1e9 or None, "#,##0.00"),
        ("Trailing P/E", a.pe, b.pe, "0.00"),
        ("Price / Book", a.pb, b.pb, "0.00"),
        ("Return on equity", a.roe, b.roe, "0.00%"),
        ("Dividend yield", a.dividend_yield, b.dividend_yield, "0.00%"),
        ("Start price", ma.start_price, mb.start_price, "#,##0.00"),
        ("End price", ma.end_price, mb.end_price, "#,##0.00"),
        ("Total return", ma.total_return, mb.total_return, "+0.00%;-0.00%"),
        ("Average yearly return", ma.cagr, mb.cagr, "+0.00%;-0.00%"),
        ("Last 12 months", ma.one_year_return, mb.one_year_return, "+0.00%;-0.00%"),
        ("Annual volatility", ma.volatility, mb.volatility, "0.00%"),
        ("Max drawdown", ma.max_drawdown, mb.max_drawdown, "0.00%"),
        ("Return per unit of risk", ma.return_per_risk, mb.return_per_risk, "0.00"),
        ("1,000 invested becomes", ma.value_of_1000, mb.value_of_1000, "#,##0"),
    ]
    for label, va, vb, fmt in rows:
        r += 1
        _row(ws, r, label, va if va is not None else "n/a", vb if vb is not None else "n/a", fmt)
    r += 1
    _row(ws, r, "Correlation of daily returns", corr, "", "0.00")

    r += 2
    _header(ws, r, ["Head-to-head check", a.ticker, b.ticker, "Winner"])
    for c in checks:
        r += 1
        win = {"A": a.ticker, "B": b.ticker}.get(c.winner, "Tie / n/a")
        cells = _row(ws, r, c.label, c.a_value, c.b_value, extra=win)
        if c.winner in ("A", "B"):
            cells[1 if c.winner == "A" else 2].fill = PatternFill("solid", fgColor=GREEN)
        cells[3].alignment = Alignment(horizontal="center")

    r += 2
    ws.cell(row=r, column=1, value=("AI summary (Gemini: text only, all figures from Python)" if ai.used_ai
                                    else "Summary (automatic, AI not connected)")).font = Font(bold=True, size=12, color=NAVY)
    for label, text in [("In short", ai.plain_summary), ("Positive catalysts", ai.positive),
                        ("Negative developments", ai.negative), ("Key risks", ai.risks)]:
        r += 1
        ws.cell(row=r, column=1, value=label).font = Font(bold=True)
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=4)
        c = ws.cell(row=r, column=2, value=text)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[r].height = 48

    ws.column_dimensions["A"].width = 30
    for col in "BCD":
        ws.column_dimensions[col].width = 24

    # --- Base-100 sheet + native Excel chart on the memo ---
    wsb = wb.create_sheet("Base-100")
    wsp = wb.create_sheet("Price Data")
    for sheet, df, fmt in ((wsb, b100, "0.00"), (wsp, prices, "#,##0.00")):
        _header(sheet, 1, ["Date", a.ticker, b.ticker])
        for i, (dt, row) in enumerate(df.iterrows(), start=2):
            sheet.cell(row=i, column=1, value=dt.to_pydatetime()).number_format = "yyyy-mm-dd"
            sheet.cell(row=i, column=2, value=round(float(row.iloc[0]), 4)).number_format = fmt
            sheet.cell(row=i, column=3, value=round(float(row.iloc[1]), 4)).number_format = fmt
        sheet.column_dimensions["A"].width = 13
        sheet.column_dimensions["B"].width = sheet.column_dimensions["C"].width = 12
        sheet.freeze_panes = "A2"

    n = len(b100) + 1
    chart = LineChart()
    chart.title = f"Value of 100 invested: {a.ticker} vs {b.ticker}"
    chart.y_axis.title = "Value of 100 invested"
    chart.x_axis.number_format = "mmm yyyy"
    chart.x_axis.majorTimeUnit = "months"
    chart.height, chart.width = 9, 20
    chart.add_data(Reference(wsb, min_col=2, min_row=1, max_col=3, max_row=n), titles_from_data=True)
    chart.set_categories(Reference(wsb, min_col=1, min_row=2, max_row=n))
    for s, color in zip(chart.series, (BLUE, ORANGE)):
        s.graphicalProperties.line.solidFill = color
        s.graphicalProperties.line.width = 15000
        s.smooth = False
    ws.add_chart(chart, "F7")

    # --- News sheet ---
    wsn = wb.create_sheet("News")
    _header(wsn, 1, ["Company", "Date", "Headline", "Source", "Link"])
    i = 1
    for c in (a, b):
        for item in c.news:
            i += 1
            wsn.cell(row=i, column=1, value=c.ticker)
            wsn.cell(row=i, column=2, value=item["date"].strftime("%Y-%m-%d") if item["date"] else "")
            wsn.cell(row=i, column=3, value=item["title"])
            wsn.cell(row=i, column=4, value=item["source"])
            if item["url"]:
                link = wsn.cell(row=i, column=5, value="Open article")
                link.hyperlink = item["url"]
                link.font = Font(color=BLUE, underline="single")
    for col, w in zip("ABCDE", (10, 12, 90, 20, 14)):
        wsn.column_dimensions[col].width = w

    # --- Audit trail ---
    wsa = wb.create_sheet("Audit Trail")
    wsa["A1"] = "Exact prompt sent to the AI" if ai.used_ai else "Prompt prepared (AI not connected, not sent)"
    wsa["A1"].font = Font(bold=True, size=14, color=BLUE)
    wsa["A2"] = f"Model: {ai.model or 'none'}  |  Generated {datetime.now():%Y-%m-%d %H:%M}"
    wsa["A2"].font = Font(italic=True, color="64748B")
    for j, line in enumerate(ai.prompt.splitlines(), start=4):
        wsa.cell(row=j, column=1, value=line)
    wsa.column_dimensions["A"].width = 140

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def memo_filename(a: Company, b: Company) -> str:
    return f"Memo_{a.ticker}_vs_{b.ticker}_{datetime.now():%Y%m%d}.xlsx".replace("^", "")

