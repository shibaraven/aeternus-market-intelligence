"""Run one sanitized, genuine GPT-5.6 Sol Build Week validation.

The script reads OPENAI_API_KEY only from the process environment. It never
prints or persists the credential, request headers, or provider client state.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.setdefault("AETERNUS_DISABLE_BACKGROUND_TASKS", "1")
os.environ.setdefault("AETERNUS_FRONTEND", str(ROOT / "frontend"))
os.environ.setdefault("AETERNUS_DATA", str(ROOT / "data"))

from openai import OpenAI  # noqa: E402

from app import get_df, get_fundamentals  # noqa: E402
from research_agent import (  # noqa: E402
    GPTResearchAgent,
    ResearchAgentError,
    configured_model,
    configured_reasoning_effort,
)
from research_tools import ResearchToolbox, validate_research_request  # noqa: E402


QUESTION = (
    "Analyze the technical trend, available fundamental evidence, risk, and the "
    "conflict between buy-and-hold and the SMA20/SMA50 strategy. Show evidence "
    "IDs and uncertainty. Do not provide a guaranteed investment recommendation."
)
EXPECTED_TOOL_NAMES = {
    "search_symbol",
    "get_symbol_profile",
    "get_price_history",
    "get_financial_data",
    "calculate_technical_indicators",
    "calculate_risk_metrics",
    "compare_strategy_results",
}
REQUIRED_FIELDS = {
    "symbol",
    "market",
    "currency",
    "analysis_period",
    "data_as_of",
    "executive_summary",
    "technical_view",
    "fundamental_view",
    "backtest_view",
    "risk_view",
    "bull_case",
    "bear_case",
    "conflicting_signals",
    "uncertainties",
    "questions_for_further_research",
    "tool_timeline",
    "evidence_catalog",
    "disclaimer",
}


class TrackingResponses:
    """Delegate Responses calls while retaining only returned model IDs."""

    def __init__(self, responses: Any) -> None:
        self._responses = responses
        self.models: list[str] = []

    def _record_model(self, response: Any) -> Any:
        model = getattr(response, "model", None)
        if isinstance(model, str) and model:
            self.models.append(model)
        return response

    def create(self, **kwargs: Any) -> Any:
        return self._record_model(self._responses.create(**kwargs))

    def parse(self, **kwargs: Any) -> Any:
        return self._record_model(self._responses.parse(**kwargs))


class TrackingClient:
    def __init__(self, client: OpenAI) -> None:
        self.responses = TrackingResponses(client.responses)


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _is_gpt_5_6_sol(model: str) -> bool:
    return model == "gpt-5.6-sol" or model.startswith("gpt-5.6-sol-")


def _validate_report(report: dict[str, Any], response_models: list[str]) -> dict[str, Any]:
    missing_fields = sorted(REQUIRED_FIELDS - set(report))
    if missing_fields:
        raise RuntimeError("Missing report fields: " + ", ".join(missing_fields))
    if report.get("gpt_used") is not True:
        raise RuntimeError("The report did not confirm GPT usage.")
    if not response_models:
        raise RuntimeError("The API response did not expose an actual model ID.")
    if any(not _is_gpt_5_6_sol(model) for model in response_models):
        raise RuntimeError("The API returned a model outside the GPT-5.6 Sol family.")

    timeline = report["tool_timeline"]
    completed_tools = {
        event["tool"] for event in timeline if event.get("status") == "completed"
    }
    missing_tools = sorted(EXPECTED_TOOL_NAMES - completed_tools)
    if missing_tools:
        raise RuntimeError("Missing completed tools: " + ", ".join(missing_tools))

    catalog = report["evidence_catalog"]
    catalog_ids = {item["id"] for item in catalog}
    referenced_ids: set[str] = set()
    for section_name in (
        "technical_view",
        "fundamental_view",
        "backtest_view",
        "risk_view",
    ):
        evidence = report[section_name].get("evidence") or []
        if not evidence:
            raise RuntimeError(f"{section_name} did not cite evidence.")
        referenced_ids.update(item["id"] for item in evidence)
    unknown = sorted(referenced_ids - catalog_ids)
    if unknown:
        raise RuntimeError("Structured output cited unknown evidence: " + ", ".join(unknown))

    if not report.get("currency") or not report.get("data_as_of"):
        raise RuntimeError("Currency or data-as-of metadata is missing.")
    if "does not execute trades" not in report["disclaimer"]:
        raise RuntimeError("The required financial disclaimer is missing.")

    return {
        "completed_tools": sorted(completed_tools),
        "evidence_count": len(catalog),
        "referenced_evidence_count": len(referenced_ids),
    }


def _sanitized_report(report: dict[str, Any]) -> dict[str, Any]:
    sanitized = json.loads(json.dumps(report, ensure_ascii=False))
    for event in sanitized.get("tool_timeline", []):
        event.pop("call_id", None)
    return sanitized


def _write_validation_markdown(
    report: dict[str, Any],
    response_models: list[str],
    verification: dict[str, Any],
    started_at: datetime,
    completed_at: datetime,
) -> Path:
    warnings = report.get("warnings") or []
    warning_lines = "\n".join(f"- {warning}" for warning in warnings)
    if not warning_lines:
        warning_lines = "- No additional provider or report warnings were returned."
    tool_lines = "\n".join(f"- `{tool}`" for tool in verification["completed_tools"])
    models = ", ".join(f"`{model}`" for model in response_models)
    period = report["analysis_period"]
    period_text = f"{period['start']} to {period['end']}"
    document = f"""# Live GPT-5.6 Sol Validation

## Result

**PASS** — one genuine OpenAI Responses API run completed with structured output and deterministic numerical traceability.

| Field | Observed value |
| --- | --- |
| Started | {started_at.isoformat()} |
| Completed | {completed_at.isoformat()} |
| Requested model | `gpt-5.6-sol` |
| Model ID(s) returned by the API | {models} |
| Symbol | `{report['symbol']}` |
| Market | `{report['market']}` |
| Period | `{period_text}` |
| Data as of | `{report['data_as_of']}` |
| Evidence records | {verification['evidence_count']} |
| Referenced evidence records | {verification['referenced_evidence_count']} |
| Structured-output validation | PASS |
| Numerical traceability validation | PASS |
| Credential disclosure check | PASS — no credential or request header is stored in this record |

## Research question

{QUESTION}

## Completed tools

{tool_lines}

## Warnings

{warning_lines}

## Validation boundary

The script used the real OpenAI client, the repository's Responses API tool loop, strict function schemas, the production structured-output parser, and the deterministic research toolbox. It rejected non-GPT-5.6-Sol model IDs, unknown evidence citations, missing evidence categories, and untraceable numerical output. The sanitized report used for the recording is ignored by Git at `submission-artifacts/raw/live-gpt-report.json`.
"""
    path = ROOT / "docs" / "LIVE_GPT_VALIDATION.md"
    path.write_text(document, encoding="utf-8")
    return path


def _write_failure_markdown(
    exc: Exception,
    started_at: datetime,
    completed_at: datetime,
    response_models: list[str],
) -> Path:
    status_code = getattr(exc, "status_code", None)
    provider_type = getattr(exc, "type", None)
    provider_code = getattr(exc, "code", None)
    is_provider_error = status_code is not None
    failure_kind = "provider gate" if is_provider_error else "validation gate"
    failure_summary = (
        "the provider rejected the request before a validated model result was returned"
        if is_provider_error
        else "the real model run returned, but the repository's fail-closed validation rejected its output"
    )
    actual_models = ", ".join(f"`{model}`" for model in _unique(response_models)) or "Not available"
    validation_detail = (
        str(exc).replace("|", "\\|").replace("\r", " ").replace("\n", " ")
        if isinstance(exc, ResearchAgentError)
        else "Not exposed"
    )
    document = f"""# Live GPT-5.6 Sol Validation

## Result

**FAIL — {failure_kind}.** The credential was available and the script used the real OpenAI Responses API client, but {failure_summary}. No fallback model was used and no successful live result is claimed.

| Field | Observed value |
| --- | --- |
| Attempt started | {started_at.isoformat()} |
| Attempt ended | {completed_at.isoformat()} |
| Requested model | `gpt-5.6-sol` |
| Test symbol | `7203.T` |
| Market | Japan |
| Period | 1 year |
| API path | Real OpenAI Responses API client |
| Error class | `{type(exc).__name__}` |
| Provider HTTP status | `{status_code}` |
| Provider error type | `{provider_type}` |
| Provider error code | `{provider_code}` |
| Actual model returned | {actual_models} |
| Internal validation detail | {validation_detail} |
| Final validated tool timeline | Not retained because the run failed closed |
| Structured-output validation | Failed or did not complete |
| Numerical traceability validation | Failed or did not complete |
| Credential disclosure check | PASS — no key, request header, or credential was printed or stored |

## Research question

{QUESTION}

## Next action

Resolve the recorded gate, then run:

```powershell
.\\.venv\\Scripts\\python.exe scripts\\run_live_gpt_validation.py
```

On success the script replaces this file with a sanitized PASS record and creates the ignored live report needed by the fail-closed demo recorder. Do not paste an API key into documentation, chat, source, or the browser.
"""
    path = ROOT / "docs" / "LIVE_GPT_VALIDATION.md"
    path.write_text(document, encoding="utf-8")
    return path


def main() -> int:
    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        print(json.dumps({"pass": False, "error": "OPENAI_API_KEY is unavailable."}))
        return 2

    requested_model = configured_model()
    if requested_model != "gpt-5.6-sol":
        print(
            json.dumps(
                {
                    "pass": False,
                    "error": "OPENAI_MODEL must be exactly gpt-5.6-sol for this validation.",
                }
            )
        )
        return 2

    request_data = validate_research_request(
        "7203.T",
        "japan",
        "1y",
        QUESTION,
        False,
    )
    toolbox = ResearchToolbox(
        request_data,
        history_loader=get_df,
        profile_loader=get_fundamentals,
    )
    raw_client = OpenAI(api_key=api_key, timeout=300.0, max_retries=2)
    tracking_client = TrackingClient(raw_client)
    started_at = datetime.now(timezone.utc)

    try:
        report = GPTResearchAgent(
            client=tracking_client,
            model=requested_model,
            reasoning_effort=configured_reasoning_effort(),
            max_tool_rounds=12,
        ).run(request_data, toolbox)
        response_models = _unique(tracking_client.responses.models)
        verification = _validate_report(report, response_models)
    except Exception as exc:  # Keep provider details and headers out of stdout.
        _write_failure_markdown(
            exc,
            started_at,
            datetime.now(timezone.utc),
            tracking_client.responses.models,
        )
        validation_error = str(exc) if isinstance(exc, ResearchAgentError) else None
        print(
            json.dumps(
                {
                    "pass": False,
                    "error_type": type(exc).__name__,
                    "status_code": getattr(exc, "status_code", None),
                    "provider_error_type": getattr(exc, "type", None),
                    "provider_error_code": getattr(exc, "code", None),
                    "provider_error_param": getattr(exc, "param", None),
                    "validation_error": validation_error,
                }
            )
        )
        return 1

    completed_at = datetime.now(timezone.utc)
    report["requested_model"] = requested_model
    report["model"] = response_models[-1]
    report["api_response_models"] = response_models
    report["live_validation"] = {
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "structured_output_valid": True,
        "numerical_traceability_valid": True,
    }

    artifact_dir = ROOT / "submission-artifacts" / "raw"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    report_path = artifact_dir / "live-gpt-report.json"
    report_path.write_text(
        json.dumps(_sanitized_report(report), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    validation_doc_path = _write_validation_markdown(
        report,
        response_models,
        verification,
        started_at,
        completed_at,
    )

    summary = {
        "pass": True,
        "requested_model": requested_model,
        "actual_models": response_models,
        "reasoning_effort": configured_reasoning_effort(),
        "symbol": report["symbol"],
        "market": report["market"],
        "currency": report["currency"],
        "analysis_period": report["analysis_period"],
        "data_as_of": report["data_as_of"],
        "tools": verification["completed_tools"],
        "tool_events": len(report["tool_timeline"]),
        "evidence_count": verification["evidence_count"],
        "referenced_evidence_count": verification["referenced_evidence_count"],
        "structured_output_valid": True,
        "numerical_traceability_valid": True,
        "artifact": str(report_path.relative_to(ROOT)).replace("\\", "/"),
        "validation_document": str(validation_doc_path.relative_to(ROOT)).replace("\\", "/"),
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
