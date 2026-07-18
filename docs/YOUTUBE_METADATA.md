# YouTube Metadata

## Title

Aeternus Market Intelligence — OpenAI Build Week Demo

## Description

Aeternus Market Intelligence turns a market research question into a structured, evidence-grounded report. In live mode, GPT-5.6 Sol uses the OpenAI Responses API and strict function calling to coordinate deterministic tools for market data, fundamentals, technical indicators, risk, and buy-and-hold versus SMA20/SMA50 comparison.

GPT is not allowed to invent displayed financial figures. Every value is calculated by application code and rendered with a stable evidence ID, unit, currency, data date, source, and method. The report keeps bull and bear cases, conflicting signals, uncertainty, limitations, and a disclaimer visible.

The video also demonstrates a reliable Fixed Demo path: a clearly labeled synthetic `AET-DEMO` scenario fixed through June 30, 2026. It requires no API key and explicitly says when GPT was not called.

Codex was used to audit and extend the existing Flask application, implement the isolated research boundary and interface, strengthen automated tests and Windows packaging, and produce reviewer documentation and reproducible submission media.

Repository: https://github.com/shibaraven/aeternus-market-intelligence

For research and educational purposes only. This application does not execute trades or provide personalized investment advice. Historical and simulated performance does not guarantee future results.

## Chapters

00:00 Aeternus Market Intelligence
00:07 The research problem and workflow
00:26 Live GPT-5.6 Sol result
00:43 Strict tool calls and evidence IDs
01:00 Reliable Fixed Demo Mode
01:16 Evidence report and risk
01:26 Buy-and-hold vs. SMA20/SMA50
01:34 Cases, conflicts, and uncertainty
01:50 Codex, tests, packaging, and architecture
02:21 Limitations and disclaimer

Update these timestamps from the final encoded MP4 if editing changes a boundary by more than one second.

## Technology list

- OpenAI Responses API and GPT-5.6 Sol
- Strict function calling and Pydantic structured output
- Python, Flask, pandas, NumPy, and yfinance
- Native HTML, CSS, and JavaScript
- pytest and PyInstaller
- Playwright, Windows local TTS, and FFmpeg

## Suggested thumbnail

`docs/devpost/gallery/01-cover.png`

## Upload settings

- Video: `submission-artifacts/Aeternus_OpenAI_Build_Week_Demo.mp4`
- Captions: upload `submission-artifacts/audio/aeternus_voiceover.srt` as English
- Video language: English
- Category: Science & Technology
- Audience: not made for kids
- Visibility: Public, but select **Publish** only after the user gives final confirmation

## Suggested tags

OpenAI Build Week, GPT-5.6, OpenAI Responses API, AI agent, function calling, structured outputs, market intelligence, evidence grounded AI, Flask, Python, deterministic analytics, backtesting, Codex
