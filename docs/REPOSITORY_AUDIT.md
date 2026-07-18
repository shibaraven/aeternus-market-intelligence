# Repository Audit

Audit date: 2026-07-18

Branch: `build-week-2026`
Baseline commit: `a570c8318c5c534f6e2244a2a99aa31c4bf7b029`

## Executive summary

Aeternus Market Intelligence is a local-first Python web application. The repository does **not** contain C#, ASP.NET Core, Node.js application code, or multiple backend projects. Its current implementation is a Flask API, one large browser-side HTML/CSS/JavaScript application, SQLite persistence, Yahoo Finance market data through `yfinance`, RSS news, optional local Ollama chat, and a PyInstaller Windows packaging path.

The smallest safe Build Week approach is additive:

1. Keep all existing routes and UI workflows working.
2. Add a testable deterministic research-tool module beside the existing application.
3. Add a thin GPT-5.6 Responses API orchestrator that may only cite numbers returned by those tools.
4. Add a dedicated AI Research page instead of replacing the existing Ollama chat.
5. Add an explicitly synthetic, fixed-date Demo Mode that does not require market-data or OpenAI credentials.
6. Add automated tests around the new deterministic layer and response validation.
7. Update packaging, startup configuration, security guidance, and judge documentation.

## Actual application architecture

```text
Browser
└── frontend/index.html
    ├── Native HTML/CSS/JavaScript SPA
    ├── Lightweight Charts, Chart.js, SortableJS
    ├── html2canvas and jsPDF
    └── Calls same-origin /api/* routes

Flask process
├── backend/main.py                 source/frozen launcher
└── backend/app.py                  API, analytics, persistence, schedulers
    ├── yfinance                    Yahoo Finance price/profile data
    ├── urllib + RSS XML            Yahoo/Google news feeds
    ├── SQLite                      watchlists, journal, alerts
    ├── openpyxl                    Excel exports
    └── localhost:11434             optional Ollama chat proxy

Runtime data
└── data/
    ├── aeternus_market_intelligence.db
    └── reports/YYYY-WNN.json
```

The browser and API are served by the same Flask process at `http://127.0.0.1:5000` when launched through `backend/main.py`. Direct execution of `backend/app.py` binds to `0.0.0.0`; the documented launcher binds to loopback.

## Frameworks and observed versions

The dependency file is currently unpinned. Versions below are the installed versions observed in the existing working Python 3.11.9 environment, not reproducible locks:

| Component | Observed version / source |
| --- | --- |
| Python | 3.11.9 in the available working venv; launch scripts prefer 3.12/3.13 |
| Flask | 3.1.3 |
| flask-cors | 6.0.2 |
| yfinance | 1.3.0 |
| pandas | 3.0.3 |
| NumPy | 2.4.4 |
| requests | 2.34.0 |
| openpyxl | 3.1.5 |
| curl-cffi | 0.15.0 |
| lxml | 6.1.0 |
| Beautiful Soup | 4.14.3 |
| peewee | 4.0.5 (declared but no active application usage found) |
| Lightweight Charts | 4.1.3 download URL |
| Chart.js | 4.4.0 download URL |
| html2canvas | 1.4.1 download URL |
| SortableJS | 1.15.0 download URL |
| jsPDF | 2.5.1 download URL |
| PyInstaller | Used by `build.bat`; not installed in the audited working venv |

No OpenAI Python SDK or Pydantic dependency is present at baseline.

## Main modules and entry points

### `backend/main.py`

- Detects normal versus PyInstaller-frozen execution.
- Selects writable data and bundled frontend paths.
- Applies SSL certificate environment workarounds for frozen mode.
- Imports the Flask application, opens a browser, and serves on loopback port 5000.

### `backend/app.py`

- Contains 77 top-level Python functions and 39 Flask routes in one module.
- Initializes SQLite at import time.
- Starts a weekly-report timer and an alert-checking daemon thread at import time.
- Contains market-data retrieval, analytics, routes, reports, exports, news, and Ollama integration.

### `frontend/index.html`

- A 7,000+ line SPA with embedded CSS and JavaScript.
- Contains 184 named JavaScript functions.
- Uses no frontend build system and loads five committed vendor bundles.

### Packaging

- `AeternusMarketIntelligence.spec` packages `backend/main.py`, `backend/app.py`, and the frontend.
- `build.bat` installs dependencies and PyInstaller, then writes a portable folder under `dist/AeternusMarketIntelligence/`.

## Existing stock-data functionality

- Default watchlists for Taiwan (`.TW`), Japan (`.T`), and Shanghai (`.SS`).
- SQLite-backed custom watchlists and ordering.
- Daily history through `yfinance.Ticker(symbol).history(period=...)` with a five-minute in-memory cache and retries.
- Intraday 5-minute, 15-minute, and 60-minute history with a two-minute cache.
- Quote, daily change, volume, and historical OHLCV output.
- `Ticker.info` fundamentals/profile retrieval.
- Market benchmarks: Taiwan Weighted Index, Nikkei 225, and Shanghai Composite.
- No paid financial-data credential is required, but the data path depends on Yahoo Finance availability and behavior.

The baseline accepts almost any non-empty symbol string. It does not consistently validate market suffixes, periods, units, currency, or whether the requested symbol belongs to the selected market.

## Existing technical indicators

`compute_indicators` and `_build_indicators` calculate:

- SMA 5/10/20/50/120 (depending on caller)
- EMA 12/26
- MACD, signal, and histogram
- RSI 14
- Bollinger Bands 20/2
- Stochastic K/D
- Williams %R
- On-balance volume
- Rolling support/resistance
- Volume ratio and volume-spike anomaly flags

The signal engine combines RSI, MACD, moving-average, Bollinger, K/D, volume, support, and resistance rules into a score and legacy recommendation label.

## Existing financial-analysis functionality

The fundamentals route returns available Yahoo fields including P/E, EPS, dividend yield, market capitalization, price/book, revenue, margin, ROE, debt/equity, 52-week range, sector, industry, average volume, and a truncated company description.

Limitations:

- Availability varies by symbol and Yahoo response.
- Field dates, statement periods, units, and currency are not returned.
- Missing values are generally represented as `null`, zero, `--`, or an empty dictionary depending on the path.
- These values are not currently linked to evidence IDs or a source timestamp.

## Existing backtesting functionality

The existing engine supports:

- SMA crossover with configurable short/long windows
- RSI oversold/overbought
- MACD crossover
- Bollinger breakout
- Custom AND-combinations of indicator conditions
- Entry/exit trade list, win rate, average win/loss, and chart markers

Important correctness limitation: baseline `stats.total_return` adds each trade's percentage return. That is not a compounded portfolio return and cannot be used as the Build Week strategy-comparison total return. The baseline also omits buy-and-hold comparison, equity-curve drawdown, annualized return, volatility, and transaction-cost assumptions. The research layer must calculate those metrics from a deterministic daily position/equity series while retaining the existing UI engine.

## Existing risk functionality

The `/api/risk` route calculates daily returns, annualized volatility, maximum drawdown, Sharpe ratio with a hard-coded 2% annual risk-free assumption, beta/correlation versus a market benchmark, total return, a return histogram, and cumulative-return points.

Known limitations:

- It does not return explicit start/end data dates or currency.
- Monthly returns are produced by summing daily percentage returns rather than geometrically compounding them.
- Benchmark and stock data coverage may differ; only beta/correlation align dates.
- The fixed risk-free rate and 252-day convention are not exposed in the response assumptions.

## Existing charts and UI pages

- Watchlist/sidebar and multi-language stock detail
- Candlestick/volume/technical-indicator charts
- Intraday chart
- Drawing annotations and chart-pattern overlays
- Technical-signal cards
- Fundamentals page
- Preset and custom strategy backtests
- Trade journal and portfolio views
- Portfolio allocation/P&L charts and analytics
- Market heatmap
- Multi-stock comparison
- Condition scanner
- Anomaly feed
- Risk page
- Alert manager and browser notifications
- RSS news and sentiment analysis
- Multi-timeframe resonance
- Pattern recognition
- Weekly reports
- Excel and PDF export
- Responsive/mobile controls, keyboard shortcuts, layout customization, themes, and four UI languages
- Optional Ollama chat embedded in the technical-analysis tab

## Existing AI behavior

The existing AI feature is a proxy to a user-selected local Ollama model. The browser fetches history and technical signals, renders them into a client-generated system prompt, and posts the prompt plus recent chat history to `/api/ai/chat`.

It is not an evidence-grounded agent:

- There is no GPT-5.6 or OpenAI SDK integration.
- The model cannot call deterministic application tools.
- Output is unstructured prose.
- Numerical statements are not checked against tool outputs.
- There are no evidence IDs, data dates, conflict analysis, or typed report parsing.
- The endpoint accepts a browser-supplied system prompt.
- Model text is rendered with `innerHTML` after minimal Markdown replacement and without robust HTML escaping.

The Build Week research workflow should therefore be a separate, typed route and page. The existing Ollama chat can remain as a legacy optional feature.

## Startup, build, and verification commands

Windows source launch:

```bat
start.bat
```

macOS/Linux source launch:

```bash
chmod +x start.sh
./start.sh
```

Manual source launch:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/python backend/main.py
```

Windows package build:

```bat
build.bat
```

At baseline there is no automated test suite, formatter configuration, linter configuration, CI workflow, or lock file.

## Missing dependencies and broken or weak components

- OpenAI SDK and typed response-model dependencies are missing.
- No tests exist.
- Requirements are unpinned, so clean-clone installs are not reproducible.
- PyInstaller is installed only by `build.bat` and was absent from the audited venv.
- Startup scripts install packages on every launch.
- The package spec must be updated when new modules and SDK dependencies are added.
- Scheduler and SQLite initialization occur at import time, adding test side effects.
- Upstream Yahoo/RSS failures can make large parts of the application unavailable.
- Existing backtest return semantics are insufficient for investment-strategy comparison.
- Existing error responses often expose raw exception text.
- No clean-clone or judge workflow has been documented or verified yet.

## Security and data-handling audit

### Confirmed protections

- No API key, private key, `.env`, database, build output, virtual environment, or Python cache is tracked in the baseline commit.
- `.gitignore` excludes `.env*`, databases, runtime data, virtual environments, caches, and build output.
- The normal launcher binds to `127.0.0.1`.
- Weekly-report file retrieval validates a strict filename pattern.

### Risks and recommended treatment

- Flask-CORS is enabled globally without an origin restriction. This should be limited or removed for same-origin local use.
- Local mutation routes have no authentication or CSRF protection. Loopback binding reduces but does not eliminate local-browser attack exposure.
- Direct `backend/app.py` execution binds to all interfaces.
- Browser-rendered AI text uses unsafe `innerHTML`; the new research renderer must escape all model and evidence strings.
- User-provided stock names/codes are interpolated into several HTML templates and should be escaped.
- Raw upstream exception messages are returned to clients in several routes.
- The OpenAI key must remain server-side in `OPENAI_API_KEY`; it must never be accepted from or returned to the browser.
- Research requests may contain user questions and symbol context. Documentation must disclose that live GPT mode sends that content and deterministic tool output to the OpenAI API.
- SQLite can contain personal watchlists, trades, alerts, and notes and must remain untracked.

Repository scans at audit time found no tracked secrets or forbidden generated/private files.

## Official OpenAI implementation constraints

The Build Week integration will use the Responses API because OpenAI recommends it for new reasoning and tool-calling workflows. The configured default is the explicit `gpt-5.6-sol` model, with reasoning effort set intentionally. Function results must be returned with their original `call_id`, and the final report must use Structured Outputs rather than free-form JSON.

References:

- [GPT-5.6 model guidance](https://developers.openai.com/api/docs/guides/model-guidance?model=gpt-5.6)
- [Responses API migration guide](https://developers.openai.com/api/docs/guides/migrate-to-responses)
- [Function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)

## Smallest safe Build Week implementation plan

1. Add `backend/research_tools.py` with strict request validation, evidence records, a deterministic synthetic demo provider, technical/fundamental/risk tools, and mathematically correct buy-and-hold/SMA comparison.
2. Add `backend/research_agent.py` with provider abstraction, OpenAI Responses tool loop, typed structured report, tool timeline, numeric-evidence validation, missing-key behavior, and configurable model/reasoning settings.
3. Add `/api/research/config`, `/api/research/symbols`, and `/api/research/run` without changing existing route contracts.
4. Add a dedicated AI Research page in the existing SPA, with live/demo status and evidence-first report cards.
5. Preserve the Ollama chat as a separately labeled legacy feature.
6. Add pytest unit/integration tests using deterministic frames and mocked OpenAI responses; tests must not require network or an API key.
7. Update requirements, PyInstaller configuration, startup scripts, README, and all required Build Week documents.
8. Run unit, integration, syntax, HTTP, secret, package-build, and manual browser checks before final submission.

This plan adds one isolated research boundary instead of rewriting the existing 39 routes or 184 frontend functions.
