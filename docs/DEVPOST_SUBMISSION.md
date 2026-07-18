# Devpost Submission Copy

## Project name

Aeternus Market Intelligence

## Elevator pitch

A local-first market research workspace where GPT-5.6 coordinates deterministic analytical tools and every displayed financial figure stays traceable to a dated evidence record.

## Inspiration

Investment research is usually split across price charts, company facts, risk calculators, and backtest screens. General-purpose AI can compress that material, but a polished answer is not enough when a reviewer cannot inspect where a number came from. We wanted an AI workflow that could reason across the evidence without becoming the source of the evidence.

## What it does

Aeternus Market Intelligence lets a user select a market, symbol, period, and research question. In live mode, GPT-5.6 Sol uses the OpenAI Responses API to call strict, request-scoped tools for symbol validation, profile and price history, fundamentals, technical indicators, risk, and buy-and-hold versus SMA20/SMA50 comparison. The final structured synthesis cites stable evidence IDs; the server resolves those IDs into cards containing value, unit, currency, data date, source, and calculation method.

The report presents technical, fundamental, backtest, and risk views together with bull and bear cases, conflicting signals, uncertainty, follow-up questions, limitations, and a financial disclaimer. The application does not execute trades.

For a reliable credential-free judge path, Fixed Demo Mode uses a visibly labeled synthetic `AET-DEMO` dataset fixed through June 30, 2026. It runs the same deterministic analytical boundary, requires no API key or live market-data request, and explicitly reports `GPT not called` when using the fallback.

## What existed before Build Week

Before Build Week, the repository already provided a local Flask/JavaScript market dashboard with multi-market watchlists, quotes, OHLCV charts, technical indicators, legacy backtests, risk analysis, comparisons, scanners, anomaly views, heatmaps, fundamentals, RSS news, reports, exports, alerts, a trade journal, portfolio analytics, and optional local Ollama chat.

## What was added during Build Week

During Build Week, we added:

- a GPT-5.6 Sol research agent using the OpenAI Responses API;
- strict function calling across nine deterministic research capabilities;
- Pydantic-validated structured synthesis with unknown fields forbidden;
- evidence IDs, dates, units, currencies, sources, methodologies, and tool execution timeline;
- fail-closed validation for unknown citations and untraceable numerical claims;
- correctly compounded buy-and-hold and SMA20/SMA50 results with next-session execution and stated costs;
- a dedicated AI Research interface with cases, conflicts, uncertainty, warnings, and errors;
- a fixed synthetic demo that requires no credential;
- automated unit and API tests, Windows PyInstaller packaging updates, reviewer documentation, and reproducible submission-media scripts.

## How it was built

The browser SPA calls a loopback-only Flask API. The API validates and locks each request to one market, symbol, and period. `ResearchToolbox` retrieves or generates data once, performs all calculations in Python, and writes a deduplicated evidence ledger. In live mode, `GPTResearchAgent` sends strict function schemas to `gpt-5.6-sol` through Responses, executes returned calls under their original call IDs, and then parses a typed final response. The server validates evidence categories, citations, and numerical traceability before attaching authoritative metadata and rendering the report.

The stack includes Python, Flask, OpenAI's Python SDK, Pydantic, pandas, NumPy, yfinance, SQLite, native HTML/CSS/JavaScript, pytest, PyInstaller, Playwright, Windows local text-to-speech, and FFmpeg.

## Challenges

The hardest boundary was preventing fluent model output from becoming the system of record for financial figures. We separated qualitative synthesis from deterministic calculations, designed stable evidence IDs, rejected unmatched numbers, and kept the model inside a bounded tool loop. We also had to preserve a large pre-existing application, correct compound-return and signal-timing details, package the expanded dependency graph for Windows, and provide a judge path that stays honest without a credential or reliable network.

## Accomplishments

- Preserved the existing product while adding an isolated evidence-grounded agent boundary.
- Made every displayed research number attributable to deterministic code and a dated evidence record.
- Exposed conflicts, limitations, and uncertainty as first-class report output.
- Built a repeatable synthetic demo instead of disguising mock data as live data.
- Added automated tests and validated both source and frozen Windows application paths.
- Added fail-closed live-validation and recording scripts that refuse to fabricate GPT proof.

## What we learned

Tool calling is most trustworthy when the model has a narrow role: decide what evidence to request, compare results, and explain them. Application code should continue to own validation, calculations, provenance, and policy-sensitive metadata. We also learned that a deterministic fallback is not merely a backup; when labeled clearly, it is a stronger review and debugging surface.

## What's next

Next steps are richer filing-period provenance for fundamentals, additional benchmark strategies, walk-forward analysis, configurable transaction-cost assumptions, more provider adapters, saved local research sessions, and broader accessibility review. Any future forecasting feature will retain the same evidence and uncertainty boundary.

## Built with

`openai-api`, `gpt-5.6-sol`, `responses-api`, `function-calling`, `structured-outputs`, `python`, `flask`, `pydantic`, `pandas`, `numpy`, `yfinance`, `javascript`, `pytest`, `pyinstaller`, `playwright`, `ffmpeg`

## Category

Primary: **AI Agents / Productivity**
Secondary: **Developer Tools / Financial Research**

## Repository

https://github.com/shibaraven/aeternus-market-intelligence

## Judge testing instructions

1. Clone the repository and run `start.bat` on Windows or `./start.sh` on macOS/Linux.
2. Open `http://127.0.0.1:5000` and select **AI Research**.
3. Keep **Synthetic Demo**, `AET-DEMO`, **1 year**, and the prefilled question.
4. Clear **Use GPT-5.6 synthesis** if an API key happens to be configured, then select **Run AI Research**.
5. Confirm `SYNTHETIC DEMO`, `Deterministic fallback · GPT not called`, the seven-step completed timeline, evidence IDs, 2026-06-30 data date, technical/fundamental/backtest/risk sections, cases, conflicts, uncertainties, and disclaimer.
6. Optional live mode: set `OPENAI_API_KEY` only in the server process, restart, select **Live public data**, and use a supported market/symbol pair. Never enter a key in the browser.
7. Run `python -m pytest` from the documented virtual environment for the automated suite.

Detailed steps and expected results are in `docs/JUDGE_TESTING_GUIDE.md` and `docs/VALIDATION_REPORT.md`.

## Financial disclaimer

Aeternus Market Intelligence is for research and educational purposes only. It does not execute trades, provide personalized investment advice, guarantee outcomes, or guarantee returns. Historical and simulated performance does not guarantee future results. Market data may be delayed, incomplete, or inaccurate. Verify important information independently and consult a qualified professional where appropriate.
