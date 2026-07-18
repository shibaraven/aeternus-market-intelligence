# Validation Report

Validation date: 2026-07-19 (Asia/Tokyo)

Branch: `build-week-2026`

Environment: Windows, Python 3.11.9

## Outcome

The source application, Fixed Demo workflow, deterministic live-data boundary, automated suite, PyInstaller Windows package, genuine GPT-5.6 Sol run, submission media, and judge package passed. The frozen executable produced seven completed tool steps and 34 traceable demo evidence records. The live OpenAI run returned `gpt-5.6-sol`, completed all seven required tools, and produced 37 evidence records that all passed structured-output and numerical-traceability validation.

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
18 passed in 1.34s
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

Observed: Python compilation exited 0; `inline scripts parsed: 6`. The repository has no configured formatter or linter, so no formatter/linter result is claimed.

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

### Genuine GPT-5.6 Sol validation

```powershell
.\.venv\Scripts\python.exe scripts\run_live_gpt_validation.py
```

Observed on 2026-07-19:

```text
requested model:              gpt-5.6-sol
actual API model:             gpt-5.6-sol
reasoning effort:             medium
required tools completed:     7 of 7
tool events:                  7
evidence records:             37
referenced evidence records:  37
structured output:            PASS
numerical traceability:       PASS
```

The run used the real OpenAI Responses API. No fallback model was used. The committed record is sanitized; the full recording input remains Git-ignored.

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
visible Evidence ID markup: true
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

1. **PyInstaller analysis:** the build emits warnings for optional/platform-specific imports from pandas, OpenAI, Pydantic, and related packages. The Windows executable started and completed the Demo route, so these warnings were nonblocking in the tested target.
2. **External data:** Yahoo Finance can be delayed, incomplete, rate-limited, or unavailable. The Fixed Demo is the reliable offline-data evaluation path after installation.
3. **Publishing boundary:** YouTube publishing and the final Devpost submission remain user-confirmed account actions; no publication is claimed by this technical report.

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

- [x] Open AI Research at a 1920×1080 desktop viewport using automated browser control.
- [x] Run Fixed Demo and confirm synthetic/GPT-not-used labels.
- [x] Inspect evidence IDs, methods, timeline, conflicts, uncertainties, and disclaimer.
- [x] Re-run and confirm 7 tools, 34 evidence records, and stable fixed-demo values.
- [x] With a private shell key, run one live GPT request and confirm `gpt_used: true` and the configured model.
- [x] Confirm the key never appears in the page, response artifact, console, recording, or committed files.
- [x] Build the portable folder and run the same fixed demo on the current Windows target.

## Submission-finalization checks (2026-07-19 JST)

The current uncommitted submission work was revalidated after adding visible evidence IDs and fail-closed media tooling:

```text
pytest:                         18 passed in 1.34s
compileall:                     PASS (backend, scripts, tests)
pip check:                      No broken requirements found
frontend inline JavaScript:    6 scripts parsed successfully
Playwright package audit:      0 vulnerabilities
credential-pattern scan:       PASS
Fixed Demo source route:       7 tools / 34 evidence / GPT false
Windows packaged Fixed Demo:   7 tools / 34 evidence / GPT false
voiceover:                      PCM WAV, 48 kHz mono, 140.795 seconds
voiceover measured level:       mean -16.2 dB / peak -1.5 dB
live GPT validation:           PASS — gpt-5.6-sol / 7 tools / 37 evidence
raw browser recording:         PASS — 1920×1080 / 139.240 seconds
gallery:                       PASS — 6 of 6 PNGs / 1800×1200 / below 5 MB
final MP4:                     PASS — 156.240 seconds / H.264 / AAC / 13,847,868 bytes
final audio:                   PASS — -16.4 LUFS / true peak -1.4 dBFS
judge ZIP:                     PASS — 15 files / below 35 MB
submission readiness:          PASS — no failed checks
```

The final post-commit clean clone, tag, merge, and push remain required before technical completion. YouTube and Devpost publication remain explicitly user-confirmed manual actions.

### Current-worktree clean-snapshot rehearsal

After the submission scripts and gallery changes were added, `scripts/validate_clean_snapshot.ps1` cloned commit `aaaa162`, applied the current intended tracked and untracked changes into a new ignored directory, created a completely fresh Python 3.11 virtual environment, and installed only the documented dependency files. It also ran `npm ci` from the committed recorder lockfile.

Observed on 2026-07-19:

```text
fresh-venv pytest:              18 passed in 3.51s
fresh-venv pip check:           PASS
npm audit:                      0 vulnerabilities
Playwright Chromium launch:     PASS
source app without API key:     PASS
source Fixed Demo:              7 tools / 34 evidence / GPT false
fresh PyInstaller build:        PASS
packaged Fixed Demo:            7 tools / 34 evidence / GPT false
packaged Evidence ID markup:    visible
snapshot secret scan:           PASS
packaged executable size:       18,361,552 bytes
```

This rehearsal validated the patched worktree before the live GPT and media gates completed; it was superseded by the exact-commit clone below.

### Final exact-commit clean clone

After the implementation and post-commit validation fix were committed, `scripts/validate_clean_snapshot.ps1` cloned commit `ef81c99` into a new directory. The source worktree had no tracked or untracked patch to apply, so every product, dependency, and packaging result below came from the committed tree alone.

Observed on 2026-07-19:

```text
fresh dependency installation: PASS (backend/requirements-dev.txt)
fresh-venv pip check:           PASS
npm ci / npm audit:             PASS / 0 vulnerabilities
Playwright Chromium launch:     PASS
fresh-venv pytest:              18 passed in 3.50s
source app without API key:     PASS
source Fixed Demo:              7 tools / 34 evidence / GPT false
fresh PyInstaller build:        PASS
packaged Fixed Demo:            7 tools / 34 evidence / GPT false
packaged Evidence ID markup:    visible
snapshot secret scan:           PASS
packaged executable size:       18,361,682 bytes
```

This is the final clean-clone product validation. The follow-up documentation commit records these observed results and does not change application code, dependencies, packaging, or tests.
