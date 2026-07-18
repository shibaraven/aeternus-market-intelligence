# Validation Report

Validation date: 2026-07-18 (Asia/Tokyo)

Branch: `build-week-2026`

Environment: Windows, Python 3.11.9

## Outcome

The source application, fixed Demo research workflow, deterministic live-data tool boundary, automated suite, and PyInstaller Windows package passed. The frozen executable was launched and exercised over HTTP, producing seven completed tool steps and 34 traceable demo evidence records.

A real OpenAI request was not executed because `OPENAI_API_KEY` was not present in the validation environment. The Responses function-call loop and typed parse path were exercised with a protocol-compatible fake client. Live-key acceptance remains an explicit manual submission step.

## Commands executed and observed results

### Dependency installation and integrity

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m pip install pyinstaller==6.21.0
.\.venv\Scripts\python.exe -m pip check
```

Observed: clean Python 3.11 environment installed the pinned runtime successfully; PyInstaller 6.21.0 installed; `No broken requirements found.`

### Automated tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Observed:

```text
..................                                                       [100%]
18 passed in 1.06s
```

Coverage includes:

- symbol, suffix, market, period, question, and hostile-character validation
- deterministic/fixed-date demo data
- SMA, EMA/MACD, volume-ratio indicator definitions
- geometric risk return, annualization, and drawdown
- compounded backtest return, trades, assumptions, and period
- request-scoped tools and evidence lookup
- missing provider currency fallback
- missing and malformed price data
- Pydantic parsing with missing-field rejection
- invalid evidence IDs/categories and fabricated numerical-claim rejection
- missing OpenAI key
- Responses tool calls, original `call_id` outputs, structured parse, reasoning, and `store=False` with a fake client
- Demo API, disclaimer, invalid JSON/symbol, key non-disclosure, homepage, and legacy health route

### Clean-clone rehearsal

A separate clone of `build-week-2026` was created under ignored build storage. That clone received its own new virtual environment, installed `backend/requirements-dev.txt`, and ran its own suite:

```powershell
git clone --no-local --branch build-week-2026 . <clean-target>
py -3.11 -m venv <clean-target>\.venv
<clean-target>\.venv\Scripts\python.exe -m pip install `
  -r <clean-target>\backend\requirements-dev.txt
<clean-target>\.venv\Scripts\python.exe -m pytest
```

Observed: `18 passed in 3.47s`. This confirms tracked files alone contain the code, UI, tests, documentation, and declared dependencies needed by the automated workflow.

### Python and browser-script syntax

```powershell
.\.venv\Scripts\python.exe -m compileall -q backend tests
node -e "/* parse every inline script from frontend/index.html with new Function */"
```

Observed: Python compilation exited 0; `inline scripts parsed: 1`. The repository has no configured formatter or linter, so no formatter/linter result is claimed.

### Source HTTP smoke test

The source server was launched with background tasks disabled, then these endpoints were requested:

```text
GET  /api/health
GET  /api/research/config
GET  /api/research/symbols?market=demo
POST /api/research/run       (fixed demo)
POST /api/research/run       (live mode without a key)
GET  /
```

Observed: health, configuration, symbols, homepage, and Demo returned HTTP 200; live mode without a key returned the expected HTTP 503 `missing_api_key`; an invalid market suffix returned HTTP 400. The configuration response exposed only an `openai_configured` boolean, not a key.

### Real public-data tool smoke test

The request-scoped deterministic tools were executed against `7203.T`/Japan/`3mo` through the existing yfinance provider, without calling GPT.

Observed on 2026-07-18:

```text
calls: 4
observations: 62
period: 2026-04-17 to 2026-07-17
evidence records: 27
source: Yahoo Finance via yfinance
```

The tested tools were price history, technical indicators, risk metrics, and strategy comparison. This confirms the live provider/tool boundary; provider availability can change independently.

### Windows package build

```powershell
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean `
  --distpath dist --workpath build_temp AeternusMarketIntelligence.spec
```

Observed: PyInstaller 6.21.0 completed successfully and created:

```text
dist\AeternusMarketIntelligence\AeternusMarketIntelligence.exe
```

### Frozen executable smoke test

The packaged executable was started hidden with `AETERNUS_NO_BROWSER=1` and `AETERNUS_DISABLE_BACKGROUND_TASKS=1`. Its `/api/health` and fixed `/api/research/run` endpoints were exercised.

Observed:

```text
health: ok
source: Aeternus deterministic synthetic generator v1
gpt_used: false
synthesis_mode: deterministic_demo_fallback
analysis period: 2025-07-14 to 2026-06-30
tool steps: 7
evidence records: 34
disclaimer present: true
```

The exact executable process was then stopped. Generated `dist/` and `build_temp/` content remains Git-ignored.

### Diff and repository safety checks

```powershell
git diff --check
git grep -I -n -E "<credential patterns>"
git ls-files | rg "<forbidden generated/private paths>"
```

Observed: no whitespace errors, no high-confidence OpenAI/GitHub/AWS/private-key credential pattern, and no tracked database, runtime data, `.env`, virtual environment, or build output. `.env.example` contains only blank/reference values. Test strings are synthetic and not valid credentials.

## Remaining warnings

1. **Real GPT acceptance:** no OpenAI key was available, so one real Responses API request could not be validated. Configure a key and follow `JUDGE_TESTING_GUIDE.md` before recording an optional live segment.
2. **Visual browser automation:** the bundled in-app browser-control runtime failed during setup with `Cannot redefine property: process`. HTTP, DOM-content, and JavaScript syntax checks passed, but the final responsive visual pass should be completed manually using the judge guide.
3. **PyInstaller analysis:** the build emits warnings for optional/platform-specific imports from pandas, OpenAI, Pydantic, and related packages. The Windows executable started and completed the Demo route, so these warnings were nonblocking in the tested target.
4. **External data:** Yahoo Finance can be delayed, incomplete, rate-limited, or unavailable. The fixed demo is the reliable offline-data evaluation path after installation.

## Known limitations

- Fundamentals exposed by the baseline provider do not include complete filing-period provenance; missing values remain absent.
- Live research supports Taiwan `.TW`, Japan `.T`, and Shanghai `.SS` symbols and the periods listed by the API.
- The Build Week comparison models buy-and-hold and one SMA20/SMA50 long/cash strategy, not optimization or prediction.
- Costs are modeled as stated, but taxes, separate dividends, slippage beyond the selected basis points, and market impact are not modeled.
- Historical and synthetic results do not imply future performance.
- The local application has no login or CSRF layer and must not be exposed to an untrusted network.
- The original Ollama chat is separate from the evidence-grounded GPT workflow.

## Exact startup procedure

### Recommended judge path

```powershell
git clone --branch build-week-2026 https://github.com/shibaraven/aeternus-market-intelligence.git
cd aeternus-market-intelligence
start.bat
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000), select **AI Research**, keep **Fixed Demo**, and select **Run AI Research**.

### Manual source path

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe backend\main.py
```

### Live GPT path

```powershell
$env:OPENAI_API_KEY = "your-key-in-this-shell-only"
$env:OPENAI_MODEL = "gpt-5.6-sol"
.\.venv\Scripts\python.exe backend\main.py
```

## Manual verification checklist

- [ ] Open AI Research at desktop and mobile widths.
- [ ] Run Fixed Demo and confirm synthetic/GPT-not-used labels.
- [ ] Expand evidence methods and inspect timeline, conflicts, uncertainties, and disclaimer.
- [ ] Re-run and confirm analytical values are stable.
- [ ] With a private shell key, run one live GPT request and confirm `gpt_used: true` and the configured model.
- [ ] Confirm the key never appears in the page, network response, console, recording, or committed files.
- [ ] Build or download the portable folder and run the same fixed demo on the target Windows version.
