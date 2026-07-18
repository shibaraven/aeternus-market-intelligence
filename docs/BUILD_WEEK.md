# OpenAI Build Week 2026

## Submission summary

The Build Week edition turns the existing Aeternus market dashboard into an evidence-grounded research agent. It preserves the original Flask application and adds a narrow research boundary in which deterministic code owns every financial number while GPT-5.6 owns planning, tool coordination, comparison, and qualitative synthesis.

## Before and after

| Area | Before Build Week | Build Week addition |
| --- | --- | --- |
| AI | Optional free-form local Ollama chat | GPT-5.6 Responses agent with typed output and evidence references |
| Analysis | Metrics distributed across legacy routes | Request-scoped research tools with dates, units, currency, source, and methodology |
| Backtest | Trade-return percentages summed in the legacy engine | Separately implemented compounded buy/hold and SMA20/SMA50 equity curves |
| Risk | Legacy page without a complete evidence contract | Deterministic total/annualized return, volatility, drawdown, and Sharpe evidence |
| UI | Charts and analytical pages | Dedicated AI Research experience and tool timeline |
| Demo | Dependent on public providers | Fixed synthetic scenario through 2026-06-30 |
| Quality | No automated suite | Unit/API integration tests and packaged-app smoke validation |

The legacy backtest and risk routes remain available to avoid breaking existing workflows. The new research tools correct the calculations required for this submission at an isolated boundary.

## Agent contract

The live agent uses the configurable model `gpt-5.6-sol` and an intentional reasoning effort. It can call these strict functions:

1. `search_symbol`
2. `get_symbol_profile`
3. `get_price_history`
4. `get_financial_data`
5. `calculate_technical_indicators`
6. `calculate_risk_metrics`
7. `run_strategy_backtest`
8. `compare_strategy_results`
9. `get_supporting_evidence`

The selected market, symbol, and period are validated before the model runs and enforced again on every tool call. A tool cannot silently switch the scope.

The orchestration loop returns each function result using the originating `call_id`. GPT then produces `ResearchSynthesis`, a Pydantic model with extra fields forbidden. The server checks cited evidence IDs and categories, rejects untraceable numerical prose, and resolves IDs to complete evidence records. Server-authored fields include symbol, market, currency, dates, source labels, warnings, assumptions, and disclaimer.

## Numerical evidence design

Each evidence object includes:

- stable `id`
- category
- human-readable label
- numeric or textual value
- unit/currency
- `as_of` date
- source
- calculation methodology

Model prose is not trusted as a source of numerical facts. A response with an unknown citation, a technical section citing nontechnical evidence, missing required structure, or an unmatched numeric claim fails closed with an API error.

## Backtest assumptions

The research comparison uses daily close-to-close returns:

- Buy and hold: long from the first executable session
- SMA strategy: long when SMA20 is greater than SMA50, otherwise cash
- The signal is shifted one session to avoid same-close look-ahead
- Equity is compounded from daily net returns
- Default transaction cost is 10 basis points per position change
- Annualization uses 252 sessions
- Maximum drawdown uses equity divided by its running peak
- Win rate counts profitable completed trades; open trades are identified separately

The response states the period, cost assumption, omissions, historical-performance warning, overfitting warning, data-quality warning, and survivorship-bias caveat.

## Demo design

`AET-DEMO` is a generated, deterministic OHLCV series and company profile. It uses no random source, no provider credential, and a fixed last date of 2026-06-30. The demo is intentionally labeled synthetic in the mode selector, banner, metadata, evidence source, warnings, and report badge.

If no OpenAI key is present, Demo Mode uses a deterministic qualitative fallback. It still runs the same seven analytical steps and emits the same evidence contract; `gpt_used` is `false` and `synthesis_mode` is `deterministic_demo_fallback`. This is a workflow-resilience path, not a claim that GPT ran.

## OpenAI implementation references

The implementation follows current official guidance for Responses, function calls, reasoning configuration, and Structured Outputs:

- [Latest model guidance](https://developers.openai.com/api/docs/guides/model-guidance?model=gpt-5.6)
- [Migrate to the Responses API](https://developers.openai.com/api/docs/guides/migrate-to-responses)
- [Function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)

Live requests use `store=False`. The SDK and model name are configuration values rather than business-logic dependencies, so a compatible model can be substituted without changing deterministic tools.

## Codex contribution

Codex was used to perform the repository audit, identify actual technologies and baseline correctness risks, implement the research tools and orchestration, integrate the existing UI, build tests, update packaging, and create reviewer documentation. It also ran automated, HTTP, and frozen-executable checks. The work did not replace the existing product architecture or claim that generated demo data is live.

## Deliberate non-goals

- Trading, brokerage connectivity, orders, or portfolio automation
- Personalized recommendations or guaranteed outcomes
- GPT-generated market numbers
- Forecasting a future price
- Pretending unavailable fundamentals exist
- Rewriting all legacy analytics during a scoped Build Week change

## Reviewer entry points

- Start here: [`README.md`](../README.md)
- Architecture: [`ARCHITECTURE.md`](ARCHITECTURE.md)
- Repository baseline: [`REPOSITORY_AUDIT.md`](REPOSITORY_AUDIT.md)
- Under-three-minute narration: [`DEMO_SCRIPT.md`](DEMO_SCRIPT.md)
- Exact judge workflow: [`JUDGE_TESTING_GUIDE.md`](JUDGE_TESTING_GUIDE.md)
- Executed checks: [`VALIDATION_REPORT.md`](VALIDATION_REPORT.md)
