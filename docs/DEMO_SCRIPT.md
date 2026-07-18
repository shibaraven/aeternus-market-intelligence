# Demo Script — Under Three Minutes

Target duration: approximately 2 minutes 30 seconds. Use **Fixed Demo** so the recording is reproducible.

## 0:00–0:25 — Problem

“Investment research usually scatters charts, company facts, risk, and backtests across separate tools. A language model can summarize them, but a confident number is not useful unless we can trace it. Aeternus Market Intelligence keeps every financial calculation in deterministic code and uses GPT-5.6 to coordinate and explain the evidence.”

Show the existing dashboard briefly, then select **AI Research**.

## 0:25–0:50 — Workflow

“This is the new Build Week research page. A user selects a mode, market, symbol, period, and asks a research question. For this reliable judge path I am using `AET-DEMO`: a clearly labeled synthetic dataset fixed through June 30, 2026. It is not presented as live market data.”

Keep the preconfigured question and press **Run AI Research**.

## 0:50–1:20 — Tools and GPT-5.6

“The same research boundary exposes strict tools for symbol validation, profile and price history, fundamentals, technical indicators, risk, strategy backtests, comparison, and evidence lookup. In live mode, GPT-5.6 Sol uses the Responses API to plan and coordinate those tools. It cannot create the displayed figures. Its structured synthesis must cite real evidence IDs, and the server rejects unmatched numerical claims.”

Point to the visible progress state and seven-step tool timeline.

“This credential-free demo uses the deterministic fallback and says `GPT not used`; it does not pretend a model call happened.”

## 1:20–2:05 — Result

“The report combines technical, fundamental, backtest, and risk views. Each evidence card shows its value, unit, date, source, and method. The comparison compounds buy-and-hold and the SMA20/SMA50 rule, shifts the signal one session to avoid same-close look-ahead, and states transaction costs.”

Scroll through:

- data-as-of and analysis period
- technical and financial evidence
- buy-and-hold versus SMA20/SMA50 evidence
- risk evidence and assumptions
- bull case, bear case, and conflicting signals
- uncertainties and further questions

“There is no unexplained buy or sell instruction. Conflicts and uncertainty are first-class output.”

## 2:05–2:30 — Codex and limitations

“Codex audited the original Flask repository, preserved its working features, added this isolated agent boundary, tests, packaging, and reviewer documentation, then validated both source and frozen Windows builds. The main limitations are that live data depends on Yahoo Finance, fundamental provenance may be incomplete, backtests are historical and simplified, and the synthetic demo cannot support a real investment conclusion.”

End on the disclaimer.

“This is research and education software. It does not execute trades or guarantee outcomes.”

## Optional live-mode variation

If an OpenAI key is configured and network access is reliable, switch to **Live GPT**, choose a matching real symbol, and ask a concise question. Point out the `gpt_used: true`/model badge in the result. Keep the fixed demo as the recorded fallback and never display the key.
