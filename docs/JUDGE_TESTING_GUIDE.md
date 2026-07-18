# Judge Testing Guide

This guide has a two-minute no-secret path first, followed by optional live GPT and automated validation.

## Fastest path: fixed demo

### 1. Install and start

Requirements: Python 3.11–3.13 and internet access for the initial package installation.

Windows:

```bat
start.bat
```

macOS/Linux:

```bash
chmod +x start.sh
./start.sh
```

Wait for the browser at [http://127.0.0.1:5000](http://127.0.0.1:5000). No OpenAI key is needed.

### 2. Open the research page

Select **AI Research** in the top header. On a narrow screen, open the overflow menu and select **AI Research**.

Expected initial state:

- Mode: **Fixed Demo**
- Market: **Synthetic demo**
- Symbol: `AET-DEMO`
- Period: **1 year**
- A prefilled research question
- A visible warning that values are synthetic and fixed through `2026-06-30`

### 3. Run the scenario

Select **Run AI Research** once.

Expected result, normally within a few seconds:

- visible processing state followed by a completed report
- `SYNTHETIC DEMO` and `GPT not used` labels
- analysis dates `2025-07-14` through `2026-06-30`
- seven completed tool-timeline steps
- 34 evidence records in the evidence catalog
- technical, fundamental, backtest, and risk sections
- buy-and-hold versus SMA20/SMA50 comparison
- bull and bear cases, conflicts, uncertainties, and further questions
- evidence values with dates, units, source, and methodology
- research/education disclaimer

Re-run the same request: analytical values should be identical because the dataset has no random input. Timeline timestamps may differ.

## Expected failure path

Switch to **Live GPT** without configuring an OpenAI key, choose a live market and a suffix-valid symbol, and run. The page should show a clear missing-key error and guide you to Demo Mode; no partial fabricated report should appear.

Try a symbol with the wrong suffix, such as `7203.T` while Taiwan is selected. The API should reject it before provider or model execution.

## Optional live GPT path

Set a key only in the server shell before launch.

PowerShell:

```powershell
$env:OPENAI_API_KEY = "your-key"
$env:OPENAI_MODEL = "gpt-5.6-sol"
.\.venv\Scripts\python.exe backend\main.py
```

Bash:

```bash
export OPENAI_API_KEY="your-key"
export OPENAI_MODEL="gpt-5.6-sol"
.venv/bin/python backend/main.py
```

Then:

1. Select **Live GPT**.
2. Select Taiwan, Japan, or Shanghai.
3. Choose a provided symbol or enter one with the required suffix (`.TW`, `.T`, or `.SS`).
4. Keep `1 year` and enter a question of at least 10 characters.
5. Run and wait for provider and model calls.
6. Confirm the result identifies GPT use/model, shows real provider dates, and cites evidence cards.

Live success depends on the OpenAI account/network and Yahoo Finance availability. Never paste the key into the web page; it has no key field.

## Automated checks

From the repository root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
```

Expected result for this branch: `18 passed`.

## Windows portable build

Run:

```bat
build.bat
```

Expected executable:

```text
dist\AeternusMarketIntelligence\AeternusMarketIntelligence.exe
```

Launch it, open **AI Research**, and repeat the fixed demo. Move the whole `AeternusMarketIntelligence` folder when testing on another PC.

## What is synthetic, live, and model-authored?

| Item | Fixed Demo | Live GPT |
| --- | --- | --- |
| OHLCV and fundamentals | Deterministic synthetic values | Existing yfinance/Yahoo provider |
| Indicators, risk, backtest | Deterministic application tools | Same deterministic tools |
| Qualitative synthesis | Fixed server templates without key | GPT-5.6 structured output |
| Evidence metadata and disclaimer | Server | Server |

## Troubleshooting

- Port 5000 already used: stop the other local service and retry.
- Package install fails: verify a supported 64-bit Python and internet access, then recreate `.venv`.
- Live data is empty: use Fixed Demo; Yahoo availability is external.
- Live mode says missing key: set `OPENAI_API_KEY` in the same shell that launches the server.
- Ollama unavailable: this affects only the separate legacy chat, not AI Research Demo Mode.

For all executed checks and remaining warnings, see [`VALIDATION_REPORT.md`](VALIDATION_REPORT.md).
