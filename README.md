# 📊 PeerLens: compare two companies in plain English

An AI-powered comparative equity analyst. Enter the stock tickers of any two listed companies (e.g. BNP.PA and GLE.PA) and the app:

1. **Pulls up to 10 years of live prices** and company fundamentals from Yahoo Finance
2. **Calculates every figure in Python**: total & yearly return, volatility, max drawdown, return per unit of risk, P/E, ROE, dividend yield, correlation
3. **Runs 8–9 head-to-head checks** and gives a data-based verdict on which company looks stronger
4. **Reads the latest news** and asks Google Gemini for three plain-English bullets: positive catalysts, negative developments, key risks (Gemini writes text only and never calculates)
5. **Exports a one-click Excel memo** with a native chart, all figures, the checks, the AI summary, the news and the exact AI prompt (audit trail)

> Educational tool. Past performance does not predict future results. Not financial advice.

## Run it on your computer

```bash
pip install -r requirements.txt
streamlit run app.py
```

Optional, to switch on the AI summary: copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`
and paste a free Gemini key from <https://aistudio.google.com/apikey>. Without a key, the app still works
and shows an automatic summary built from the numbers.

## Put it online (free, Streamlit Community Cloud)

1. Go to <https://share.streamlit.io> and sign in with GitHub
2. **Create app** → pick this repository, branch `main`, main file `app.py`
3. **Advanced settings → Secrets**, paste:
   ```toml
   GEMINI_API_KEY = "your-key"
   GEMINI_MODEL = "gemini-3.1-flash-lite"
   ```
4. **Deploy**. You get a public link like `https://your-app.streamlit.app`

## Project structure

| File | What it does |
|---|---|
| `app.py` | The web interface (Streamlit) |
| `core/data.py` | Company search, prices, fundamentals and news from Yahoo Finance |
| `core/analysis.py` | All the maths + the head-to-head scorecard |
| `core/ai.py` | Builds the audit prompt and calls Gemini (text only) |
| `core/excel.py` | Builds the downloadable Excel memo |

## Sharing tip

Share **https://peerlens.streamlit.app/?embed=true** for a clean view without the Streamlit
toolbar, creator badge and GitHub links.
