# Architecture

## System context

```text
                                live mode only
User ──► Browser SPA ──► Flask research API ─────────► OpenAI Responses API
                │                │                         GPT-5.6 Sol
                │                │ function calls
                │                ▼
                │        ResearchToolbox
                │          ├── yfinance adapter (live)
                │          ├── synthetic provider (demo)
                │          ├── indicators and risk
                │          ├── backtest comparison
                │          └── evidence ledger
                │
                └──── existing Flask routes ──► SQLite / Yahoo / RSS / Ollama
```

The application is a single local Flask process serving a native browser SPA. The Build Week modules are additive and do not change legacy API contracts.

## Main components

### Browser

`frontend/index.html` contains the existing application and the AI Research page. The research page requests configuration and known symbols, posts a validated research request, displays progress stages, then renders the tool timeline and evidence-first report. All dynamic research strings are escaped before HTML insertion.

### Flask boundary

`backend/app.py` owns HTTP and integrates existing provider helpers:

- `GET /api/research/config` returns model name, reasoning setting, modes, markets, periods, demo metadata, and only a boolean key status.
- `GET /api/research/symbols?market=...` returns safe default symbol choices.
- `POST /api/research/run` validates the request and selects live GPT or deterministic Demo fallback.

The API caps request bodies at 128 KiB, restricts CORS to loopback origins, returns explicit failure codes, and never accepts an API key from the browser.

### Deterministic research tools

`backend/research_tools.py` has no LLM dependency. `ResearchToolbox` is instantiated per request and locks calls to one market/symbol/period. It prepares OHLCV once, calculates results, records tool events, and deduplicates evidence by stable ID.

The module provides:

- strict market, suffix, period, question, and argument validation
- live provider adapters via existing yfinance-backed functions
- deterministic synthetic OHLCV and fundamentals
- SMA/EMA/MACD/RSI/volume/support/resistance evidence
- geometric returns, annualized volatility, drawdown, and Sharpe
- compounded strategy equity and comparison metrics
- OpenAI strict function schemas

### Research agent

`backend/research_agent.py` isolates model-provider behavior. `OpenAIResearchAgent` supports constructor-injected clients for testing and environment-configured clients in production.

The live sequence is:

```text
Validate request
   │
   ▼
Responses.create(tools, reasoning, store=False)
   │
   ├── function_call(s) ──► execute in ResearchToolbox
   │                         │
   │◄── function_call_output with original call_id
   │
   └── repeat until required evidence categories are complete
   │
   ▼
Responses.parse(text_format=ResearchSynthesis, store=False)
   │
   ▼
Validate schema, citations, categories, and numeric traceability
   │
   ▼
Attach server-authored metadata and resolved evidence objects
```

The planning and synthesis instructions are separate. The agent has a bounded tool-turn limit and fails closed if the provider does not complete the contract.

## Report ownership

| Field type | Owner |
| --- | --- |
| Price, indicators, financial values, risk, backtest metrics | Deterministic tools |
| Evidence IDs, dates, units, source, methodology | Deterministic tools/server |
| Assessment prose, bull/bear cases, conflicts, uncertainty, questions | GPT in live mode; fixed templates in fallback |
| Symbol, market, currency, period, data mode, model, warnings, disclaimer | Server |

This boundary prevents model output from becoming the system of record for financial figures.

## Data modes

### Live GPT

The server retrieves provider data, sends the research question and tool results to OpenAI, and returns a validated report. Missing provider fields stay missing. The OpenAI key is read only from the server environment.

### Fixed Demo

The server generates the same synthetic dataset for every matching period. No Yahoo or OpenAI call is needed in fallback mode. The fixed data date and multiple visible labels prevent confusion with current data.

## Persistence and privacy

Research reports are returned to the browser and are not persisted by the new routes. Existing SQLite persistence remains responsible for user watchlists, journal entries, alerts, and related local features. Live Responses calls set `store=False`; selected context still leaves the machine to reach OpenAI and is subject to provider terms.

## Failure behavior

| Condition | Behavior |
| --- | --- |
| Invalid JSON/symbol/market/period/question | HTTP 400 |
| Valid symbol with unavailable history | HTTP 404 |
| Live mode without OpenAI key | HTTP 503 with Demo Mode guidance |
| Provider/agent failure | HTTP 502 without returning a secret |
| Invalid structured output or evidence citation | Fail closed; no report rendered |
| Demo without key or provider | Deterministic fallback succeeds |

## Packaging

`backend/main.py` selects source versus PyInstaller paths, creates a writable data directory, configures certificates in frozen mode, serves on `127.0.0.1`, and optionally opens the browser. `AeternusMarketIntelligence.spec` includes the frontend, research modules, OpenAI SDK, Pydantic, and existing runtime dependencies.
