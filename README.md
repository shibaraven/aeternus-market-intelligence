# Aeternus Market Intelligence

## Overview

Aeternus Market Intelligence is a local-first, browser-based market research workspace for Taiwan, Japan, and Shanghai equities. The Build Week edition adds an evidence-grounded GPT-5.6 research agent to the existing Flask application without replacing its charts, portfolio, alert, journal, scanner, report, or local Ollama features.

Users choose a market and symbol, ask a research question, and receive a typed report whose technical, fundamental, risk, and backtest claims link to deterministic evidence records. A fixed synthetic Demo Mode lets reviewers complete the workflow without an OpenAI key or live market-data connection.

> Research and educational use only. The application does not execute trades, provide personalized investment advice, guarantee outcomes, or guarantee returns.

## Problem

Market research often separates price charts, company data, risk statistics, and strategy tests into disconnected screens. General-purpose model answers can also sound precise without showing where a number came from. This project keeps calculations in testable application tools and gives GPT-5.6 the narrower job of planning, coordinating tools, comparing results, and explaining traceable evidence—including conflicts and uncertainty.

## Key Features

Existing before Build Week:

- Multi-market watchlists, quotes, daily and intraday OHLCV charts
- SMA, EMA, MACD, RSI, Bollinger Bands, stochastic, Williams %R, OBV, support, and resistance
- Legacy strategy backtests, risk analysis, comparison, scanning, anomaly detection, and heatmaps
- Fundamentals, RSS news, reports, Excel/PDF export, alerts, trade journal, and portfolio analytics
- Optional local Ollama chat and a four-language responsive interface

Added during Build Week:

- GPT-5.6 Sol research agent using the OpenAI Responses API and structured function calling
- Nine deterministic research capabilities covering symbols, profiles, prices, fundamentals, indicators, risk, backtests, comparisons, and supporting evidence
- Strongly typed final synthesis and validation that rejects untraceable numerical claims
- Evidence IDs, dates, currencies, units, methodologies, source labels, and tool timeline
- Correctly compounded buy-and-hold versus SMA20/SMA50 comparison with next-session execution and stated costs
- Dedicated AI Research UI with status, bull/bear cases, conflicts, uncertainties, warnings, and errors
- Fixed, visibly synthetic Demo Mode that needs no private credential
- Automated unit and API integration tests plus reproducible dependency pins

## Architecture

```text
Browser SPA (frontend/index.html)
        │ same-origin JSON
        ▼
Flask API (backend/app.py)
        │
        ├── Existing services: yfinance, RSS, SQLite, Ollama
        │
        └── Research boundary
            ├── research_agent.py
            │   └── OpenAI Responses API / GPT-5.6 Sol (live mode)
            └── research_tools.py
                ├── validation and evidence ledger
                ├── technical and risk calculations
                ├── buy-and-hold / SMA20-SMA50 comparison
                └── fixed synthetic provider (demo mode)
```

All displayed financial numbers originate in deterministic tools. GPT receives tool outputs, returns qualitative structured fields with evidence IDs, and the server resolves those IDs into evidence cards. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for boundaries and request flow.

## Technology Stack

- Python 3.11–3.13
- Flask 3.1.3 and Flask-CORS 6.0.2
- OpenAI Python SDK 2.46.0 and Pydantic 2.13.4
- pandas 3.0.3, NumPy 2.4.4, yfinance 1.3.0
- SQLite and openpyxl
- Native HTML, CSS, and JavaScript
- Committed browser libraries: Lightweight Charts, Chart.js, SortableJS, html2canvas, and jsPDF
- pytest 9.0.2 and PyInstaller 6.21.0

## Prerequisites

- Python 3.11, 3.12, or 3.13 with `venv` and `pip`
- A modern browser
- Internet access for installing Python packages; live equity data also depends on Yahoo Finance
- Optional: an OpenAI API key for live GPT research
- Optional: Ollama on `localhost:11434` for the separate legacy local-chat feature

Demo Mode does not need an OpenAI key or market-data connection after dependencies are installed.

## Installation

Clone the Build Week branch:

```bash
git clone --branch build-week-2026 https://github.com/shibaraven/aeternus-market-intelligence.git
cd aeternus-market-intelligence
```

Quick install and launch:

```bat
start.bat
```

```bash
chmod +x start.sh
./start.sh
```

Manual installation on Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Manual installation on macOS/Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
```

## Configuration

The application reads configuration from the server process environment. `.env.example` is a reference; the application intentionally does not load a repository `.env` file automatically.

| Variable | Purpose | Default |
| --- | --- | --- |
| `OPENAI_API_KEY` | Server-side credential for live GPT research | unset |
| `OPENAI_MODEL` | Swappable Responses API model | `gpt-5.6-sol` |
| `OPENAI_REASONING_EFFORT` | `none`, `low`, `medium`, `high`, `xhigh`, or `max` | `medium` |
| `AETERNUS_DATA` | Writable database/report directory | `<project>/data` |
| `AETERNUS_FRONTEND` | Frontend asset directory | `<project>/frontend` |
| `AETERNUS_NO_BROWSER` | Set to `1` for noninteractive/server checks | unset |
| `AETERNUS_DISABLE_BACKGROUND_TASKS` | Set to `1` for isolated tests | unset |

PowerShell live-mode example:

```powershell
$env:OPENAI_API_KEY = "your-key-in-your-shell-only"
$env:OPENAI_MODEL = "gpt-5.6-sol"
.\.venv\Scripts\python.exe backend\main.py
```

Never put a real key in source code, browser storage, a committed file, or a request body.

## Running the Application

Start from source:

```powershell
.\.venv\Scripts\python.exe backend\main.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000), then select **AI Research** in the header or mobile menu. The launcher binds to loopback only.

Build the Windows portable folder:

```bat
build.bat
```

Run `dist\AeternusMarketIntelligence\AeternusMarketIntelligence.exe`. Copy the entire output folder when moving it to another Windows computer.

## Demo Mode

Demo Mode is the recommended first evaluation path:

1. Open **AI Research**.
2. Keep **Fixed Demo** selected.
3. Keep `AET-DEMO`, `1 year`, and the prefilled question.
4. Select **Run AI Research**.
5. Inspect the seven-step tool timeline, evidence cards, comparison, risk, conflicts, and disclaimer.

Every demo price, company value, and result is synthetic, generated deterministically, and fixed through **2026-06-30**. The UI labels it `SYNTHETIC DEMO`; it is not current market data and GPT is not used in the credential-free fallback. Repeated requests produce the same analytical values.

See [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) for the under-three-minute narration.

## Reproducing Submission Media

Submission tooling is isolated under `scripts/`; generated audio, recordings, videos, and judge ZIPs stay ignored under `submission-artifacts/`.

```powershell
cd scripts
npm install
cd ..
.\.venv\Scripts\python.exe scripts\run_live_gpt_validation.py
node scripts\record_build_week_demo.js
powershell -ExecutionPolicy Bypass -File scripts\generate_voiceover.ps1
powershell -ExecutionPolicy Bypass -File scripts\build_devpost_gallery.ps1
powershell -ExecutionPolicy Bypass -File scripts\render_final_video.ps1
powershell -ExecutionPolicy Bypass -File scripts\build_judge_package.ps1
```

The live validator must succeed before recording: the recorder accepts only its sanitized GPT-5.6 Sol report and otherwise fails closed. The workflow never records a terminal or browser profile. See [docs/DEMO_SHOT_LIST.md](docs/DEMO_SHOT_LIST.md), [docs/DEVPOST_SUBMISSION.md](docs/DEVPOST_SUBMISSION.md), and [docs/FINAL_SUBMISSION_CHECKLIST.md](docs/FINAL_SUBMISSION_CHECKLIST.md).

## Testing

Install development dependencies and run the suite:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
```

The tests cover request and symbol validation, deterministic demo output, indicators, risk, compounded backtests, tool scope, unavailable data, typed model parsing, evidence enforcement, missing keys, the mocked Responses tool loop, research API behavior, disclaimer presence, and legacy health/UI availability.

See [docs/VALIDATION_REPORT.md](docs/VALIDATION_REPORT.md) for commands and observed results.

## How GPT-5.6 Is Used

Live mode uses configurable `gpt-5.6-sol` through the OpenAI Responses API. GPT plans the investigation, calls strict deterministic functions, receives outputs under the original function `call_id`, compares evidence, and returns a Pydantic-validated synthesis. The server—not GPT—adds symbol metadata, dates, currency, full evidence objects, assumptions, warnings, and the disclaimer.

Controls against invented figures include:

- strict JSON schemas for every tool
- request-scoped symbol, market, and period enforcement
- typed structured output with extra fields forbidden
- evidence-ID and evidence-category validation
- rejection of model-authored numerical claims that cannot be matched to tool evidence
- `store=False` on live Responses API calls

Official implementation references are linked in [docs/BUILD_WEEK.md](docs/BUILD_WEEK.md).

## How Codex Was Used

Codex audited the repository before architecture changes, mapped the existing Flask/JavaScript/SQLite system, implemented the isolated research layer and UI, added tests and documentation, corrected the Build Week comparison math, updated PyInstaller packaging, and ran source and packaged validation. The pre-existing application was extended rather than replaced. Human review remains responsible for Devpost content, real-key acceptance testing, product claims, and financial/legal suitability.

## Build Week Additions

The additions are intentionally isolated:

- `backend/research_tools.py`: deterministic calculations, tool schemas, evidence ledger, and synthetic demo
- `backend/research_agent.py`: GPT Responses orchestration, typed synthesis, and evidence validation
- `/api/research/config`, `/api/research/symbols`, `/api/research/run`: safe server API boundary
- AI Research page in `frontend/index.html`
- `tests/`: unit and integration coverage
- `docs/`: audit, design, demo, judge, and validation material
- pinned runtime/development requirements and updated PyInstaller specification

Detailed scope and tradeoffs are in [docs/BUILD_WEEK.md](docs/BUILD_WEEK.md).

## Security and Data Handling

- The OpenAI key remains server-side and is never returned by the configuration endpoint.
- Live GPT mode sends the user's question, selected symbol context, instructions, and deterministic tool outputs to the OpenAI API. Demo fallback sends nothing to OpenAI.
- Responses requests use `store=False`; provider-side handling is still governed by the applicable OpenAI terms and account settings.
- CORS for API routes is restricted to local loopback origins, and the launcher binds to `127.0.0.1`.
- Dynamic research content is HTML-escaped before insertion into the page.
- Runtime SQLite data can contain watchlists, alerts, journal entries, and notes; `data/`, databases, `.env*`, builds, and virtual environments are Git-ignored.
- This is a local single-user application without authentication or CSRF tokens. Do not expose it to an untrusted network.

## Known Limitations

- Live prices and fundamentals depend on unofficial Yahoo Finance behavior and may be delayed, incomplete, or unavailable.
- Fundamental fields do not include complete filing-period provenance; unavailable fields remain unavailable rather than being filled by GPT.
- The research comparison covers buy-and-hold and one SMA20/SMA50 long/cash rule; it is not an optimizer or forecast.
- Backtests omit taxes, separate dividend cash flows, and market-impact modeling; transaction costs are stated in the result.
- The synthetic demo is useful for workflow evaluation, not for conclusions about a real security.
- No live OpenAI call is performed by the automated suite; the tool loop is tested with a protocol-compatible fake client so tests require no secret or network.
- Existing legacy routes retain some baseline assumptions described in `docs/REPOSITORY_AUDIT.md`; Build Week accuracy guarantees apply to the isolated research tools, not every legacy metric.

## Financial Disclaimer

Aeternus Market Intelligence is for research and educational purposes only. It does not execute trades, provide personalized investment advice, guarantee outcomes, or guarantee returns. Historical and simulated performance does not guarantee future results. Market data may be delayed, incomplete, or inaccurate. Verify important information independently and consult a qualified professional where appropriate.

Repository: [github.com/shibaraven/aeternus-market-intelligence](https://github.com/shibaraven/aeternus-market-intelligence)
