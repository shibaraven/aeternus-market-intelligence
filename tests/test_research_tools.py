import math

import numpy as np
import pandas as pd
import pytest

from research_tools import (
    DEMO_SCENARIO,
    DEMO_SYMBOL,
    ResearchDataUnavailable,
    ResearchToolbox,
    ResearchValidationError,
    calculate_indicator_frame,
    calculate_risk_snapshot,
    compare_backtest_strategies,
    deterministic_demo_tool_sequence,
    generate_demo_history,
    validate_research_request,
)


def make_growth_frame(rows=120, daily_return=0.01):
    index = pd.bdate_range("2025-01-02", periods=rows)
    close = 100 * np.power(1 + daily_return, np.arange(rows))
    return pd.DataFrame(
        {
            "Open": close,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": np.full(rows, 1_000_000),
        },
        index=index,
    )


def demo_request(period="1y"):
    return validate_research_request(
        DEMO_SYMBOL,
        "demo",
        period,
        DEMO_SCENARIO,
        True,
    )


def test_symbol_and_market_validation():
    request_data = validate_research_request(
        "7203.t",
        "japan",
        "1y",
        "Assess technical, fundamental, risk, and historical strategy evidence.",
    )
    assert request_data.symbol == "7203.T"
    assert request_data.market == "japan"

    with pytest.raises(ResearchValidationError, match="suffix"):
        validate_research_request(
            "7203.TW",
            "japan",
            "1y",
            "Assess technical, fundamental, risk, and historical strategy evidence.",
        )
    with pytest.raises(ResearchValidationError, match="unsupported characters"):
        validate_research_request(
            "7203.T<script>",
            "japan",
            "1y",
            "Assess technical, fundamental, risk, and historical strategy evidence.",
        )
    with pytest.raises(ResearchValidationError, match="at least 12"):
        validate_research_request("7203.T", "japan", "1y", "Too short")


def test_demo_history_is_deterministic_and_fixed_date():
    first = generate_demo_history("1y")
    second = generate_demo_history("1y")
    pd.testing.assert_frame_equal(first, second)
    assert len(first) == 252
    assert first.index[-1].strftime("%Y-%m-%d") == "2026-06-30"
    assert first.attrs["data_mode"] == "synthetic_demo"


def test_indicator_calculations_match_definitions():
    frame = make_growth_frame()
    result = calculate_indicator_frame(frame)
    assert result["SMA20"].iloc[-1] == pytest.approx(frame["Close"].tail(20).mean())
    assert result["SMA50"].iloc[-1] == pytest.approx(frame["Close"].tail(50).mean())
    assert result["MACD"].iloc[-1] == pytest.approx(
        result["EMA12"].iloc[-1] - result["EMA26"].iloc[-1]
    )
    assert result["VOLUME_RATIO20"].iloc[-1] == pytest.approx(1.0)


def test_risk_metrics_are_geometric_and_dated():
    frame = make_growth_frame(daily_return=0.002)
    risk = calculate_risk_snapshot(frame, source="unit-test")
    expected_total = (frame["Close"].iloc[-1] / frame["Close"].iloc[0] - 1) * 100
    assert risk["metrics"]["total_return_pct"] == pytest.approx(expected_total, abs=0.01)
    assert risk["metrics"]["max_drawdown_pct"] == pytest.approx(0.0)
    assert risk["analysis_period"]["start"] == frame.index[0].strftime("%Y-%m-%d")
    assert risk["analysis_period"]["end"] == frame.index[-1].strftime("%Y-%m-%d")
    assert math.isfinite(risk["metrics"]["annualized_return_pct"])


def test_backtest_buy_and_hold_uses_compounded_returns():
    frame = make_growth_frame(rows=160, daily_return=0.004)
    comparison = compare_backtest_strategies(
        frame,
        source="unit-test",
        transaction_cost_bps=0,
    )
    buy_hold = comparison["strategies"]["buy_and_hold"]
    expected = (frame["Close"].iloc[-1] / frame["Close"].iloc[0] - 1) * 100
    assert buy_hold["total_return_pct"] == pytest.approx(expected, abs=0.01)
    assert buy_hold["number_of_trades"] == 1
    assert comparison["strategies"]["sma20_sma50"]["number_of_trades"] >= 1
    assert comparison["assumptions"]["transaction_cost_bps_per_position_change"] == 0
    assert comparison["analysis_period"]["start"] == frame.index[0].strftime("%Y-%m-%d")


def test_tool_argument_scope_validation_and_evidence_ledger():
    toolbox = ResearchToolbox(demo_request())
    with pytest.raises(ResearchValidationError, match="selected research symbol"):
        toolbox.execute(
            "calculate_risk_metrics",
            {"symbol": "2330.TW", "market": "demo", "period": "1y"},
        )

    calls = deterministic_demo_tool_sequence(toolbox)
    assert len(calls) == 7
    assert len(toolbox.evidence_ledger) >= 30
    evidence = toolbox.execute(
        "get_supporting_evidence",
        {"evidence_ids": ["technical.close", "risk.max_drawdown_pct"]},
    )
    assert [item["id"] for item in evidence["evidence"]] == [
        "technical.close",
        "risk.max_drawdown_pct",
    ]


def test_live_profile_keeps_canonical_currency_when_provider_value_is_missing():
    request_data = validate_research_request(
        "7203.T",
        "japan",
        "1y",
        "Assess technical, fundamental, risk, and historical strategy evidence.",
    )
    toolbox = ResearchToolbox(
        request_data,
        profile_loader=lambda symbol: {"long_name": "Example", "currency": None},
    )
    result = toolbox.execute(
        "get_symbol_profile",
        {"symbol": "7203.T", "market": "japan"},
    )
    assert result["profile"]["currency"] == "JPY"


def test_unavailable_or_invalid_price_data_is_rejected():
    live_request = validate_research_request(
        "7203.T",
        "japan",
        "1y",
        "Assess technical, fundamental, risk, and historical strategy evidence.",
    )
    toolbox = ResearchToolbox(live_request, history_loader=lambda symbol, period: None)
    with pytest.raises(ResearchDataUnavailable, match="No price history"):
        toolbox.execute(
            "get_price_history",
            {"symbol": "7203.T", "market": "japan", "period": "1y"},
        )
    broken = pd.DataFrame({"Close": [1] * 40}, index=pd.bdate_range("2025-01-01", periods=40))
    toolbox = ResearchToolbox(live_request, history_loader=lambda symbol, period: broken)
    with pytest.raises(ResearchDataUnavailable, match="missing columns"):
        toolbox.execute(
            "calculate_technical_indicators",
            {"symbol": "7203.T", "market": "japan", "period": "1y"},
        )
