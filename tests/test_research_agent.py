import json
from types import SimpleNamespace

import pytest

from research_agent import (
    GPTResearchAgent,
    MissingOpenAIKey,
    ResearchOutputError,
    ResearchSectionDraft,
    ResearchSynthesis,
    parse_synthesis,
    run_deterministic_demo,
    validate_numerical_claims,
)
from research_tools import (
    DEMO_SCENARIO,
    DEMO_SYMBOL,
    DISCLAIMER,
    ResearchToolbox,
    deterministic_demo_tool_sequence,
    validate_research_request,
)


def request_data():
    return validate_research_request(
        DEMO_SYMBOL,
        "demo",
        "1y",
        DEMO_SCENARIO,
        True,
    )


def valid_synthesis():
    return ResearchSynthesis(
        executive_summary="The long trend is positive while recent momentum is weak.",
        technical_view=ResearchSectionDraft(
            assessment="Recent momentum conflicts with the longer trend.",
            evidence_ids=["technical.close", "technical.sma50"],
        ),
        fundamental_view=ResearchSectionDraft(
            assessment="The company fields are synthetic scenario inputs.",
            evidence_ids=["fundamental.pe_ratio"],
        ),
        backtest_view=ResearchSectionDraft(
            assessment="The passive comparison had stronger historical performance.",
            evidence_ids=["backtest.buy_and_hold.total_return_pct"],
        ),
        risk_view=ResearchSectionDraft(
            assessment="The tested path includes a meaningful historical drawdown.",
            evidence_ids=["risk.max_drawdown_pct"],
        ),
        bull_case=["The full-period trend is positive."],
        bear_case=["Recent momentum is weak."],
        conflicting_signals=["Long-term performance conflicts with recent momentum."],
        uncertainties=["The dataset is synthetic."],
        questions_for_further_research=["Would another period change the conclusion?"],
    )


def test_structured_response_parsing_rejects_missing_fields():
    parsed = parse_synthesis(valid_synthesis().model_dump())
    assert parsed.technical_view.evidence_ids == ["technical.close", "technical.sma50"]
    with pytest.raises(ResearchOutputError, match="Structured research response is invalid"):
        parse_synthesis({"executive_summary": "Incomplete"})


def test_fabricated_numerical_evidence_is_rejected():
    toolbox = ResearchToolbox(request_data())
    deterministic_demo_tool_sequence(toolbox)
    synthesis = valid_synthesis()
    synthesis.executive_summary = "The model invents a 999.9 percent return."
    with pytest.raises(ResearchOutputError, match="999.9"):
        validate_numerical_claims(synthesis, toolbox)


def test_missing_api_key_behavior(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(MissingOpenAIKey, match="OPENAI_API_KEY"):
        GPTResearchAgent()


class FakeResponses:
    def __init__(self, synthesis):
        self.synthesis = synthesis
        self.create_count = 0
        self.create_requests = []
        self.parse_requests = []

    def create(self, **kwargs):
        self.create_requests.append(kwargs)
        self.create_count += 1
        if self.create_count == 1:
            common = {"symbol": DEMO_SYMBOL, "market": "demo"}
            period = {**common, "period": "1y"}
            calls = [
                ("search_symbol", {"query": DEMO_SYMBOL, "market": "demo"}),
                ("get_symbol_profile", common),
                ("get_price_history", period),
                ("get_financial_data", common),
                ("calculate_technical_indicators", period),
                ("calculate_risk_metrics", period),
                ("compare_strategy_results", {**period, "transaction_cost_bps": 10.0}),
            ]
            output = [
                SimpleNamespace(
                    type="function_call",
                    name=name,
                    arguments=json.dumps(arguments),
                    call_id=f"call_{index}",
                )
                for index, (name, arguments) in enumerate(calls, start=1)
            ]
            return SimpleNamespace(output=output)
        return SimpleNamespace(output=[])

    def parse(self, **kwargs):
        self.parse_requests.append(kwargs)
        return SimpleNamespace(output_parsed=self.synthesis, output_text="")


class FakeClient:
    def __init__(self, synthesis):
        self.responses = FakeResponses(synthesis)


def test_gpt_agent_coordinates_tools_and_hydrates_only_known_evidence():
    fake = FakeClient(valid_synthesis())
    agent = GPTResearchAgent(client=fake, model="gpt-5.6-sol", reasoning_effort="medium")
    toolbox = ResearchToolbox(request_data())
    report = agent.run(request_data(), toolbox)

    assert report["gpt_used"] is True
    assert report["model"] == "gpt-5.6-sol"
    assert len(report["tool_timeline"]) == 7
    assert {item["tool"] for item in report["tool_timeline"]} >= {
        "calculate_technical_indicators",
        "calculate_risk_metrics",
        "compare_strategy_results",
    }
    assert report["technical_view"]["evidence"][0]["id"] == "technical.close"
    assert fake.responses.create_requests[0]["store"] is False
    assert fake.responses.create_requests[0]["reasoning"] == {"effort": "medium"}
    assert fake.responses.parse_requests[0]["text_format"] is ResearchSynthesis


def test_demo_report_has_disclaimer_and_explicit_non_gpt_label():
    toolbox = ResearchToolbox(request_data())
    report = run_deterministic_demo(request_data(), toolbox)
    assert report["gpt_used"] is False
    assert report["data_mode"] == "synthetic_demo"
    assert report["data_as_of"] == "2026-06-30"
    assert report["disclaimer"] == DISCLAIMER
    assert "does not execute trades" in report["disclaimer"]
    assert "does not guarantee outcomes" in report["disclaimer"]
