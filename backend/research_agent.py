"""GPT-5.6 Responses API orchestration for evidence-grounded research."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from research_tools import (
    DISCLAIMER,
    ResearchDataUnavailable,
    ResearchToolbox,
    ResearchValidationError,
    ValidatedResearchRequest,
    deterministic_demo_tool_sequence,
    openai_tool_definitions,
)


DEFAULT_OPENAI_MODEL = "gpt-5.6-sol"
DEFAULT_REASONING_EFFORT = "medium"
ALLOWED_REASONING_EFFORTS = {"none", "low", "medium", "high", "xhigh", "max"}

REQUIRED_AGENT_TOOLS = {
    "search_symbol",
    "get_symbol_profile",
    "get_price_history",
    "get_financial_data",
    "calculate_technical_indicators",
    "calculate_risk_metrics",
    "compare_strategy_results",
}


class MissingOpenAIKey(RuntimeError):
    """Raised when a live GPT research run has no server-side API key."""


class ResearchAgentError(RuntimeError):
    """Raised when the model/tool workflow cannot produce a verified report."""


class ResearchOutputError(ResearchAgentError):
    """Raised when structured output violates the evidence contract."""


class ResearchSectionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assessment: str = Field(min_length=1, max_length=1200)
    evidence_ids: list[str] = Field(min_length=1, max_length=20)


class ResearchSynthesis(BaseModel):
    """Only qualitative fields are model-authored; metadata is server-authored."""

    model_config = ConfigDict(extra="forbid")

    executive_summary: str = Field(min_length=1, max_length=1800)
    technical_view: ResearchSectionDraft
    fundamental_view: ResearchSectionDraft
    backtest_view: ResearchSectionDraft
    risk_view: ResearchSectionDraft
    bull_case: list[str] = Field(min_length=1, max_length=8)
    bear_case: list[str] = Field(min_length=1, max_length=8)
    conflicting_signals: list[str] = Field(min_length=1, max_length=8)
    uncertainties: list[str] = Field(min_length=1, max_length=10)
    questions_for_further_research: list[str] = Field(min_length=1, max_length=8)


AGENT_INSTRUCTIONS = """You are the planning and tool-coordination stage of an
evidence-grounded stock research application. Work only on the already selected
symbol, market, and period. Validate the symbol, then call the deterministic
tools needed to inspect price history, technical indicators, available
fundamentals, risk, and the buy-and-hold versus SMA crossover comparison.

Hard rules:
- Never calculate, estimate, repair, interpolate, or invent a market number.
- Numerical facts may come only from tool output.
- Preserve dates, currency, units, period, and assumptions exactly.
- Treat missing fundamentals as unavailable; do not infer them.
- Do not recommend executing a trade and do not promise an outcome.
- Historical results must be treated as historical and uncertain.
- Continue calling tools until the required evidence categories are covered.
"""


SYNTHESIS_INSTRUCTIONS = """Produce the final qualitative synthesis using the
provided structured schema. Every evidence_ids entry must exactly match an ID
returned by a deterministic tool. Include evidence that supports each
assessment, and explain conflicts rather than hiding them.

Keep evidence categories separated: technical_view may cite only technical.*
or price.* IDs; fundamental_view only fundamental.* IDs; backtest_view only
backtest.* IDs; and risk_view only risk.* IDs. Never cross-cite an ID into a
different section even when it appears semantically related.

Do not invent or recompute numerical values. Prefer qualitative language in
narrative fields. Do not use Arabic numerals in any narrative field; the server
hydrates all cited measurements from deterministic evidence after validation.
Do not put dates, currency, symbol, market, period, model name, or disclaimer in
the output; the server supplies those authoritative fields. Do not output a
simple BUY or SELL verdict. State limitations and questions for further work.
"""


def configured_model() -> str:
    return (os.environ.get("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL).strip()


def configured_reasoning_effort() -> str:
    effort = (os.environ.get("OPENAI_REASONING_EFFORT") or DEFAULT_REASONING_EFFORT).strip().lower()
    if effort not in ALLOWED_REASONING_EFFORTS:
        raise ResearchValidationError(
            f"OPENAI_REASONING_EFFORT must be one of: {', '.join(sorted(ALLOWED_REASONING_EFFORTS))}."
        )
    return effort


def openai_is_configured() -> bool:
    return bool((os.environ.get("OPENAI_API_KEY") or "").strip())


def parse_synthesis(payload: Any) -> ResearchSynthesis:
    try:
        if isinstance(payload, ResearchSynthesis):
            return payload
        return ResearchSynthesis.model_validate(payload)
    except ValidationError as exc:
        raise ResearchOutputError(f"Structured research response is invalid: {exc}") from exc


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _event(
    sequence: int,
    tool: str,
    status: str,
    arguments: dict[str, Any],
    *,
    call_id: str | None = None,
    started_at: str | None = None,
    error: str | None = None,
    summary: str | None = None,
) -> dict[str, Any]:
    return {
        "sequence": sequence,
        "tool": tool,
        "status": status,
        "call_id": call_id,
        "arguments": arguments,
        "started_at": started_at or _utc_now(),
        "completed_at": _utc_now() if status in {"completed", "error"} else None,
        "summary": summary,
        "error": error,
    }


def _tool_output_for_model(result: dict[str, Any]) -> dict[str, Any]:
    """Remove large chart series while preserving every metric/evidence item."""
    compact = json.loads(json.dumps(result, ensure_ascii=False))
    if isinstance(compact.get("recent_points"), list):
        compact["recent_points"] = compact["recent_points"][-8:]
    strategies = compact.get("strategies")
    if isinstance(strategies, dict):
        for metrics in strategies.values():
            if isinstance(metrics, dict):
                metrics.pop("equity_curve", None)
                if isinstance(metrics.get("trades"), list):
                    metrics["trades"] = metrics["trades"][-8:]
    metrics = compact.get("metrics")
    if isinstance(metrics, dict):
        metrics.pop("equity_curve", None)
        if isinstance(metrics.get("trades"), list):
            metrics["trades"] = metrics["trades"][-8:]
    return compact


def _function_calls(output: Iterable[Any]) -> list[Any]:
    return [item for item in output if getattr(item, "type", None) == "function_call"]


def _numeric_variants(value: float) -> set[str]:
    variants = set()
    for digits in range(0, 7):
        rendered = f"{value:.{digits}f}"
        variants.add(rendered)
        variants.add(rendered.rstrip("0").rstrip("."))
    return {item for item in variants if item not in {"", "-0", "+0"}}


def _collect_allowed_numbers(toolbox: ResearchToolbox) -> set[str]:
    allowed: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, bool) or value is None:
            return
        if isinstance(value, (int, float)):
            allowed.update(_numeric_variants(float(value)))
            return
        if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            allowed.update(part.lstrip("0") or "0" for part in value.split("-"))
            allowed.add(value)
            return
        if isinstance(value, dict):
            for item in value.values():
                visit(item)
            return
        if isinstance(value, (list, tuple)):
            for item in value:
                visit(item)

    visit(list(toolbox.evidence_ledger.values()))
    return allowed


def _narrative_texts(synthesis: ResearchSynthesis) -> list[str]:
    return [
        synthesis.executive_summary,
        synthesis.technical_view.assessment,
        synthesis.fundamental_view.assessment,
        synthesis.backtest_view.assessment,
        synthesis.risk_view.assessment,
        *synthesis.bull_case,
        *synthesis.bear_case,
        *synthesis.conflicting_signals,
        *synthesis.uncertainties,
        *synthesis.questions_for_further_research,
    ]


def validate_numerical_claims(synthesis: ResearchSynthesis, toolbox: ResearchToolbox) -> None:
    """Reject model-authored numbers that cannot be traced to tool evidence."""
    allowed = _collect_allowed_numbers(toolbox)
    unsupported: list[str] = []
    pattern = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?")
    for text in _narrative_texts(synthesis):
        for match in pattern.findall(text):
            normalized = match.lstrip("+")
            if normalized not in allowed:
                unsupported.append(match)
    if unsupported:
        unique = sorted(set(unsupported))
        raise ResearchOutputError(
            "Model output contains numerical claims not found in deterministic evidence: "
            + ", ".join(unique)
        )


def _hydrate_section(
    draft: ResearchSectionDraft,
    toolbox: ResearchToolbox,
    *,
    allowed_categories: set[str],
) -> dict[str, Any]:
    records = []
    for evidence_id in draft.evidence_ids:
        record = toolbox.evidence_ledger.get(evidence_id)
        if record is None:
            raise ResearchOutputError(f"Unknown evidence ID in structured report: {evidence_id}")
        if record.get("category") not in allowed_categories:
            raise ResearchOutputError(
                f"Evidence {evidence_id} is not valid for this report section."
            )
        records.append(record)
    if not records:
        raise ResearchOutputError("Every report section must cite deterministic evidence.")
    return {"assessment": draft.assessment, "evidence": records}


def assemble_report(
    request_data: ValidatedResearchRequest,
    toolbox: ResearchToolbox,
    synthesis: ResearchSynthesis,
    timeline: list[dict[str, Any]],
    *,
    model: str | None,
    gpt_used: bool,
    synthesis_mode: str,
) -> dict[str, Any]:
    validate_numerical_claims(synthesis, toolbox)
    history = toolbox._history()  # request-scoped cached deterministic data
    start = history.index[0].strftime("%Y-%m-%d")
    end = history.index[-1].strftime("%Y-%m-%d")
    profile = toolbox._profile()

    return {
        "symbol": request_data.symbol,
        "market": request_data.market,
        "currency": toolbox.currency,
        "analysis_period": {"start": start, "end": end},
        "data_as_of": end,
        "research_question": request_data.question,
        "executive_summary": synthesis.executive_summary,
        "technical_view": _hydrate_section(
            synthesis.technical_view,
            toolbox,
            allowed_categories={"technical", "price"},
        ),
        "fundamental_view": _hydrate_section(
            synthesis.fundamental_view,
            toolbox,
            allowed_categories={"fundamental"},
        ),
        "backtest_view": _hydrate_section(
            synthesis.backtest_view,
            toolbox,
            allowed_categories={"backtest"},
        ),
        "risk_view": _hydrate_section(
            synthesis.risk_view,
            toolbox,
            allowed_categories={"risk"},
        ),
        "bull_case": synthesis.bull_case,
        "bear_case": synthesis.bear_case,
        "conflicting_signals": synthesis.conflicting_signals,
        "uncertainties": synthesis.uncertainties,
        "questions_for_further_research": synthesis.questions_for_further_research,
        "tool_timeline": timeline,
        "evidence_catalog": list(toolbox.evidence_ledger.values()),
        "data_mode": "synthetic_demo" if request_data.demo_mode else "live_public_data",
        "demo_mode": request_data.demo_mode,
        "demo_indicator": (
            "SYNTHETIC DEMO — fixed educational values, not current market data"
            if request_data.demo_mode
            else None
        ),
        "source": toolbox.source,
        "profile_name": profile.get("name") or request_data.symbol,
        "model": model,
        "gpt_used": gpt_used,
        "synthesis_mode": synthesis_mode,
        "warnings": [
            "Historical performance does not guarantee future results.",
            "Backtests may be affected by overfitting, data quality, and survivorship bias.",
            "Transaction costs are modeled as stated; taxes and slippage are not modeled separately.",
            *(
                ["Every displayed demo value is synthetic and fixed through 2026-06-30."]
                if request_data.demo_mode
                else ["Live public-data availability, adjustments, and reporting dates depend on Yahoo Finance."]
            ),
        ],
        "disclaimer": DISCLAIMER,
    }


def _demo_synthesis(toolbox: ResearchToolbox) -> ResearchSynthesis:
    technical = [key for key in toolbox.evidence_ledger if key.startswith("technical.")]
    fundamental = [key for key in toolbox.evidence_ledger if key.startswith("fundamental.")]
    backtest = [key for key in toolbox.evidence_ledger if key.startswith("backtest.")]
    risk = [key for key in toolbox.evidence_ledger if key.startswith("risk.")]

    return ResearchSynthesis(
        executive_summary=(
            "The synthetic series has a positive full-period return, while current momentum "
            "is weaker than the longer trend. The crossover strategy reduced historical "
            "drawdown but did not outperform buy and hold in this fixed scenario."
        ),
        technical_view=ResearchSectionDraft(
            assessment=(
                "Latest momentum is weak and price is below the longer moving average, "
                "which conflicts with the positive full-period trend."
            ),
            evidence_ids=technical[:8],
        ),
        fundamental_view=ResearchSectionDraft(
            assessment=(
                "The displayed fundamentals are scenario inputs only and cannot validate a real company."
            ),
            evidence_ids=fundamental[:5],
        ),
        backtest_view=ResearchSectionDraft(
            assessment=(
                "Buy and hold produced the stronger historical return, while the crossover rule "
                "showed lower drawdown in the tested synthetic period."
            ),
            evidence_ids=backtest[:10],
        ),
        risk_view=ResearchSectionDraft(
            assessment=(
                "The synthetic path experienced a material drawdown despite its positive total return."
            ),
            evidence_ids=risk[:5],
        ),
        bull_case=[
            "The full-period trend remains positive.",
            "The rule-based strategy reduced historical drawdown in this scenario.",
        ],
        bear_case=[
            "Latest momentum and moving-average evidence are weak.",
            "The crossover strategy lagged the passive comparison in historical return.",
        ],
        conflicting_signals=[
            "Positive full-period performance conflicts with weak latest technical momentum.",
            "Lower strategy drawdown conflicts with lower strategy return.",
        ],
        uncertainties=[
            "The entire dataset and company profile are synthetic.",
            "No inference from this scenario should be transferred to a real security.",
            "Taxes, slippage, and separate dividend cash flows are not modeled.",
        ],
        questions_for_further_research=[
            "Would the conclusions persist under different cost assumptions?",
            "How sensitive is the crossover result to the selected period?",
        ],
    )


def run_deterministic_demo(
    request_data: ValidatedResearchRequest,
    toolbox: ResearchToolbox,
) -> dict[str, Any]:
    if not request_data.demo_mode:
        raise ResearchValidationError("Deterministic fallback is available only in Demo Mode.")
    timeline: list[dict[str, Any]] = []
    calls = deterministic_demo_tool_sequence(toolbox)
    for sequence, call in enumerate(calls, start=1):
        timeline.append(
            _event(
                sequence,
                call["name"],
                "completed",
                call["arguments"],
                started_at=_utc_now(),
                summary=f"Produced {len(call['result'].get('evidence', []))} evidence records.",
            )
        )
    synthesis = _demo_synthesis(toolbox)
    return assemble_report(
        request_data,
        toolbox,
        synthesis,
        timeline,
        model=None,
        gpt_used=False,
        synthesis_mode="deterministic_demo_fallback",
    )


class GPTResearchAgent:
    """Request-scoped GPT-5.6 planner, tool loop, and structured synthesizer."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        api_key: str | None = None,
        model: str | None = None,
        reasoning_effort: str | None = None,
        max_tool_rounds: int = 10,
    ) -> None:
        self.model = model or configured_model()
        self.reasoning_effort = reasoning_effort or configured_reasoning_effort()
        if self.reasoning_effort not in ALLOWED_REASONING_EFFORTS:
            raise ResearchValidationError("Unsupported reasoning effort.")
        self.max_tool_rounds = max_tool_rounds

        if client is not None:
            self.client = client
        else:
            key = (api_key or os.environ.get("OPENAI_API_KEY") or "").strip()
            if not key:
                raise MissingOpenAIKey(
                    "OPENAI_API_KEY is not configured on the server. Use Demo Mode for the "
                    "credential-free deterministic walkthrough or set the environment variable."
                )
            from openai import OpenAI

            self.client = OpenAI(api_key=key, timeout=180.0, max_retries=2)

    def run(
        self,
        request_data: ValidatedResearchRequest,
        toolbox: ResearchToolbox,
    ) -> dict[str, Any]:
        tools = openai_tool_definitions()
        input_items: list[Any] = [
            {
                "role": "user",
                "content": (
                    f"Selected symbol: {request_data.symbol}\n"
                    f"Selected market: {request_data.market}\n"
                    f"Selected period: {request_data.period}\n"
                    f"Data mode: {'synthetic demo' if request_data.demo_mode else 'live public data'}\n"
                    f"Research question: {request_data.question}"
                ),
            }
        ]
        timeline: list[dict[str, Any]] = []
        completed_tools: set[str] = set()
        sequence = 0

        for round_index in range(self.max_tool_rounds):
            response = self.client.responses.create(
                model=self.model,
                instructions=AGENT_INSTRUCTIONS,
                input=input_items,
                tools=tools,
                tool_choice="required" if REQUIRED_AGENT_TOOLS - completed_tools else "auto",
                parallel_tool_calls=True,
                max_tool_calls=20,
                reasoning={"effort": self.reasoning_effort},
                include=["reasoning.encrypted_content"],
                store=False,
                max_output_tokens=3000,
            )
            output_items = list(response.output)
            input_items.extend(output_items)
            calls = _function_calls(output_items)

            if calls:
                for call in calls:
                    sequence += 1
                    started = _utc_now()
                    arguments: dict[str, Any] = {}
                    try:
                        arguments = json.loads(call.arguments)
                        if not isinstance(arguments, dict):
                            raise ResearchValidationError("Tool arguments must decode to an object.")
                        result = toolbox.execute(call.name, arguments)
                        completed_tools.add(call.name)
                        compact_result = _tool_output_for_model(result)
                        input_items.append(
                            {
                                "type": "function_call_output",
                                "call_id": call.call_id,
                                "output": json.dumps(compact_result, ensure_ascii=False),
                            }
                        )
                        timeline.append(
                            _event(
                                sequence,
                                call.name,
                                "completed",
                                arguments,
                                call_id=call.call_id,
                                started_at=started,
                                summary=f"Produced {len(result.get('evidence', []))} evidence records.",
                            )
                        )
                    except (json.JSONDecodeError, ResearchValidationError, ResearchDataUnavailable) as exc:
                        error_text = str(exc)
                        input_items.append(
                            {
                                "type": "function_call_output",
                                "call_id": call.call_id,
                                "output": json.dumps(
                                    {"error": error_text, "retryable": True}, ensure_ascii=False
                                ),
                            }
                        )
                        timeline.append(
                            _event(
                                sequence,
                                call.name,
                                "error",
                                arguments,
                                call_id=call.call_id,
                                started_at=started,
                                error=error_text,
                            )
                        )
                continue

            missing = sorted(REQUIRED_AGENT_TOOLS - completed_tools)
            if missing:
                input_items.append(
                    {
                        "role": "user",
                        "content": (
                            "The evidence workflow is incomplete. Call these required deterministic "
                            f"tools before synthesis: {', '.join(missing)}."
                        ),
                    }
                )
                continue
            break
        else:
            raise ResearchAgentError("The GPT tool workflow exceeded its tool-round limit.")

        missing = sorted(REQUIRED_AGENT_TOOLS - completed_tools)
        if missing:
            raise ResearchAgentError(
                "The GPT tool workflow ended without required evidence: " + ", ".join(missing)
            )

        available_ids = sorted(toolbox.evidence_ledger)
        input_items.append(
            {
                "role": "user",
                "content": (
                    "Create the final structured research synthesis now. Cite only these exact "
                    "evidence IDs: "
                    + ", ".join(available_ids)
                ),
            }
        )
        parsed_response = self.client.responses.parse(
            model=self.model,
            instructions=SYNTHESIS_INSTRUCTIONS,
            input=input_items,
            text_format=ResearchSynthesis,
            reasoning={"effort": self.reasoning_effort},
            include=["reasoning.encrypted_content"],
            store=False,
            max_output_tokens=5000,
        )
        if parsed_response.output_parsed is None:
            refusal = getattr(parsed_response, "output_text", "") or "No structured output returned."
            raise ResearchOutputError(f"GPT-5.6 did not return a structured report: {refusal}")
        synthesis = parse_synthesis(parsed_response.output_parsed)
        return assemble_report(
            request_data,
            toolbox,
            synthesis,
            timeline,
            model=self.model,
            gpt_used=True,
            synthesis_mode="gpt_5_6_responses_tools_and_structured_output",
        )
