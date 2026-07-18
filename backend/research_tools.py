"""Deterministic market-research tools used by the Build Week agent.

All numerical values exposed to the language model originate in this module or
in an injected market-data provider. The module itself never calls an LLM.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

import numpy as np
import pandas as pd


DEMO_SYMBOL = "AET-DEMO"
DEMO_MARKET = "demo"
DEMO_DATA_AS_OF = "2026-06-30"
DEMO_SCENARIO = (
    "Assess whether the synthetic company's improving momentum is supported "
    "by risk and SMA crossover backtest evidence."
)

DISCLAIMER = (
    "For research and educational purposes only. This application does not "
    "execute trades, does not provide personalized investment advice, does "
    "not guarantee outcomes, and historical performance does not guarantee "
    "future results."
)

MARKET_CONFIG = {
    "taiwan": {"suffix": ".TW", "currency": "TWD", "label": "Taiwan"},
    "japan": {"suffix": ".T", "currency": "JPY", "label": "Japan"},
    "shanghai": {"suffix": ".SS", "currency": "CNY", "label": "Shanghai"},
    DEMO_MARKET: {"suffix": None, "currency": "USD", "label": "Synthetic demo"},
}

PERIOD_OBSERVATIONS = {
    "3mo": 66,
    "6mo": 132,
    "1y": 252,
    "2y": 504,
}

DEFAULT_SYMBOLS = {
    "taiwan": [
        {"symbol": "2330.TW", "name": "TSMC"},
        {"symbol": "2317.TW", "name": "Hon Hai Precision"},
        {"symbol": "2454.TW", "name": "MediaTek"},
    ],
    "japan": [
        {"symbol": "7203.T", "name": "Toyota Motor"},
        {"symbol": "6758.T", "name": "Sony Group"},
        {"symbol": "7974.T", "name": "Nintendo"},
    ],
    "shanghai": [
        {"symbol": "600519.SS", "name": "Kweichow Moutai"},
        {"symbol": "601318.SS", "name": "Ping An Insurance"},
        {"symbol": "600036.SS", "name": "China Merchants Bank"},
    ],
    DEMO_MARKET: [{"symbol": DEMO_SYMBOL, "name": "Aeternus Synthetic Industries"}],
}

TOOL_NAMES = (
    "search_symbol",
    "get_symbol_profile",
    "get_price_history",
    "get_financial_data",
    "calculate_technical_indicators",
    "calculate_risk_metrics",
    "run_strategy_backtest",
    "compare_strategy_results",
    "get_supporting_evidence",
)


class ResearchValidationError(ValueError):
    """Raised when a research or tool argument is unsafe or unsupported."""


class ResearchDataUnavailable(RuntimeError):
    """Raised when a deterministic provider cannot supply usable data."""


@dataclass(frozen=True)
class ValidatedResearchRequest:
    symbol: str
    market: str
    period: str
    question: str
    demo_mode: bool


def normalize_symbol(symbol: Any) -> str:
    if not isinstance(symbol, str):
        raise ResearchValidationError("Symbol must be a string.")
    normalized = symbol.strip().upper()
    if not normalized:
        raise ResearchValidationError("Symbol is required.")
    if len(normalized) > 20:
        raise ResearchValidationError("Symbol is too long.")
    if not re.fullmatch(r"[A-Z0-9^][A-Z0-9.^=_-]*", normalized):
        raise ResearchValidationError("Symbol contains unsupported characters.")
    return normalized


def validate_research_request(
    symbol: Any,
    market: Any,
    period: Any,
    question: Any,
    demo_mode: Any = False,
) -> ValidatedResearchRequest:
    if not isinstance(market, str):
        raise ResearchValidationError("Market must be a string.")
    normalized_market = market.strip().lower()
    if normalized_market not in MARKET_CONFIG:
        raise ResearchValidationError(f"Unsupported market: {normalized_market or '(empty)'}")

    normalized_symbol = normalize_symbol(symbol)
    requested_demo = bool(demo_mode) or normalized_market == DEMO_MARKET
    if requested_demo:
        normalized_market = DEMO_MARKET
        if normalized_symbol != DEMO_SYMBOL:
            raise ResearchValidationError(f"Demo Mode only supports {DEMO_SYMBOL}.")
    else:
        suffix = MARKET_CONFIG[normalized_market]["suffix"]
        if suffix and not normalized_symbol.endswith(suffix):
            raise ResearchValidationError(
                f"{normalized_symbol} does not match the {normalized_market} market suffix {suffix}."
            )

    if not isinstance(period, str) or period not in PERIOD_OBSERVATIONS:
        raise ResearchValidationError(
            f"Unsupported analysis period. Choose one of: {', '.join(PERIOD_OBSERVATIONS)}."
        )

    if not isinstance(question, str):
        raise ResearchValidationError("Research question must be a string.")
    normalized_question = " ".join(question.strip().split())
    if len(normalized_question) < 12:
        raise ResearchValidationError("Research question must be at least 12 characters.")
    if len(normalized_question) > 1200:
        raise ResearchValidationError("Research question must be 1,200 characters or fewer.")

    return ValidatedResearchRequest(
        symbol=normalized_symbol,
        market=normalized_market,
        period=period,
        question=normalized_question,
        demo_mode=requested_demo,
    )


def generate_demo_history(period: str = "1y") -> pd.DataFrame:
    """Return a deterministic, clearly synthetic OHLCV series.

    The fixed date and formula make the demo reproducible and prevent it from
    being confused with current or cached live market data.
    """
    if period not in PERIOD_OBSERVATIONS:
        raise ResearchValidationError(f"Unsupported demo period: {period}")

    rows = 520
    index = pd.bdate_range(end=DEMO_DATA_AS_OF, periods=rows)
    t = np.arange(rows, dtype=float)
    trend = 78.0 + 0.075 * t
    cycle = 4.8 * np.sin(t / 15.0) + 1.9 * np.sin(t / 4.7)
    regime = np.where(t > 390, (t - 390) * 0.025, 0.0)
    close = trend + cycle + regime
    open_ = close * (1.0 + 0.0025 * np.sin(t / 2.9))
    high = np.maximum(open_, close) * (1.008 + 0.002 * (1 + np.sin(t / 5.0)))
    low = np.minimum(open_, close) * (0.992 - 0.0015 * (1 + np.cos(t / 6.0)))
    volume = (
        920_000
        + 210_000 * (1 + np.sin(t / 11.0))
        + (t.astype(int) % 19) * 9_000
    ).astype(int)

    frame = pd.DataFrame(
        {
            "Open": np.round(open_, 4),
            "High": np.round(high, 4),
            "Low": np.round(low, 4),
            "Close": np.round(close, 4),
            "Volume": volume,
        },
        index=index,
    )
    frame.attrs.update(
        {
            "data_mode": "synthetic_demo",
            "source": "Aeternus deterministic synthetic generator v1",
            "currency": "USD",
            "data_as_of": DEMO_DATA_AS_OF,
        }
    )
    return frame.tail(PERIOD_OBSERVATIONS[period]).copy()


def prepare_history(frame: Any) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise ResearchDataUnavailable("Market-data provider did not return a DataFrame.")
    required = ["Open", "High", "Low", "Close", "Volume"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ResearchDataUnavailable(f"Price history is missing columns: {', '.join(missing)}")

    clean = frame.loc[:, required].copy()
    for column in required:
        clean[column] = pd.to_numeric(clean[column], errors="coerce")
    clean = clean.dropna(subset=["Close"]).sort_index()
    clean = clean[~clean.index.duplicated(keep="last")]
    if len(clean) < 30:
        raise ResearchDataUnavailable("At least 30 valid observations are required.")

    clean.index = pd.to_datetime(clean.index)
    if getattr(clean.index, "tz", None) is not None:
        clean.index = clean.index.tz_localize(None)
    clean.attrs.update(getattr(frame, "attrs", {}))
    return clean


def calculate_indicator_frame(frame: pd.DataFrame) -> pd.DataFrame:
    data = prepare_history(frame)
    close = data["Close"]
    volume = data["Volume"]

    data["SMA20"] = close.rolling(20).mean()
    data["SMA50"] = close.rolling(50).mean()
    data["EMA12"] = close.ewm(span=12, adjust=False).mean()
    data["EMA26"] = close.ewm(span=26, adjust=False).mean()
    data["MACD"] = data["EMA12"] - data["EMA26"]
    data["MACD_SIGNAL"] = data["MACD"].ewm(span=9, adjust=False).mean()
    delta = close.diff()
    gains = delta.clip(lower=0).rolling(14).mean()
    losses = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gains / losses.replace(0, np.nan)
    data["RSI14"] = 100 - (100 / (1 + rs))
    data["VOLUME_RATIO20"] = volume / volume.rolling(20).mean()
    data["SUPPORT20"] = close.rolling(20).min()
    data["RESISTANCE20"] = close.rolling(20).max()
    return data


def _finite(value: Any, digits: int = 4) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return round(number, digits)


def _evidence(
    evidence_id: str,
    category: str,
    label: str,
    value: Any,
    unit: str,
    as_of: str,
    source: str,
    methodology: str,
) -> dict[str, Any]:
    return {
        "id": evidence_id,
        "category": category,
        "label": label,
        "value": value,
        "unit": unit,
        "as_of": as_of,
        "source": source,
        "methodology": methodology,
    }


def calculate_technical_snapshot(
    frame: pd.DataFrame,
    *,
    source: str,
    currency: str,
) -> dict[str, Any]:
    data = calculate_indicator_frame(frame)
    latest = data.iloc[-1]
    latest_date = data.index[-1].strftime("%Y-%m-%d")

    metrics = {
        "close": _finite(latest["Close"]),
        "sma20": _finite(latest["SMA20"]),
        "sma50": _finite(latest["SMA50"]),
        "rsi14": _finite(latest["RSI14"], 2),
        "macd": _finite(latest["MACD"]),
        "macd_signal": _finite(latest["MACD_SIGNAL"]),
        "volume_ratio20": _finite(latest["VOLUME_RATIO20"], 2),
        "support20": _finite(latest["SUPPORT20"]),
        "resistance20": _finite(latest["RESISTANCE20"]),
    }
    if metrics["close"] is not None and metrics["sma50"]:
        metrics["price_vs_sma50_pct"] = round(
            (metrics["close"] / metrics["sma50"] - 1) * 100, 2
        )
    else:
        metrics["price_vs_sma50_pct"] = None

    spread = data["SMA20"] - data["SMA50"]
    direction = np.sign(spread)
    crosses = direction.ne(direction.shift(1)) & spread.notna() & spread.shift(1).notna()
    cross_rows = data.loc[crosses]
    cross_type = "none"
    cross_date = None
    if not cross_rows.empty:
        cross_date = cross_rows.index[-1].strftime("%Y-%m-%d")
        cross_type = "bullish" if spread.loc[cross_rows.index[-1]] > 0 else "bearish"

    evidence = []
    metric_specs = [
        ("close", "Latest close", currency, "Provider closing price."),
        ("sma20", "20-session simple moving average", currency, "Arithmetic mean of 20 closes."),
        ("sma50", "50-session simple moving average", currency, "Arithmetic mean of 50 closes."),
        (
            "price_vs_sma50_pct",
            "Close versus 50-session average",
            "%",
            "(latest close / SMA50 - 1) × 100.",
        ),
        ("rsi14", "14-session RSI", "index", "Simple-average 14-session RSI."),
        ("macd", "MACD", currency, "EMA12 minus EMA26."),
        ("macd_signal", "MACD signal", currency, "Nine-session EMA of MACD."),
        (
            "volume_ratio20",
            "Volume versus 20-session average",
            "ratio",
            "Latest volume divided by 20-session mean volume.",
        ),
        ("support20", "20-session support", currency, "Minimum close over 20 sessions."),
        ("resistance20", "20-session resistance", currency, "Maximum close over 20 sessions."),
    ]
    for key, label, unit, methodology in metric_specs:
        value = metrics.get(key)
        if value is not None:
            evidence.append(
                _evidence(
                    f"technical.{key}",
                    "technical",
                    label,
                    value,
                    unit,
                    latest_date,
                    source,
                    methodology,
                )
            )
    if cross_date:
        evidence.append(
            _evidence(
                "technical.latest_sma_cross",
                "technical",
                "Latest SMA20/SMA50 crossover",
                cross_type,
                "signal",
                cross_date,
                source,
                "Last sign change in SMA20 minus SMA50; no forward-looking data.",
            )
        )

    return {
        "data_as_of": latest_date,
        "metrics": metrics,
        "latest_sma_cross": {"type": cross_type, "date": cross_date},
        "evidence": evidence,
    }


def calculate_risk_snapshot(
    frame: pd.DataFrame,
    *,
    source: str,
    risk_free_rate: float = 0.02,
) -> dict[str, Any]:
    data = prepare_history(frame)
    close = data["Close"].astype(float)
    returns = close.pct_change().dropna()
    if len(returns) < 20:
        raise ResearchDataUnavailable("At least 20 returns are required for risk metrics.")

    total_return = close.iloc[-1] / close.iloc[0] - 1
    annualized_return = (1 + total_return) ** (252 / len(returns)) - 1
    annualized_volatility = returns.std(ddof=1) * math.sqrt(252)
    equity = (1 + returns).cumprod()
    equity_with_origin = pd.concat([pd.Series([1.0]), equity.reset_index(drop=True)])
    drawdown = equity_with_origin / equity_with_origin.cummax() - 1
    excess = returns - risk_free_rate / 252
    sharpe = excess.mean() / returns.std(ddof=1) * math.sqrt(252)

    start = data.index[0].strftime("%Y-%m-%d")
    end = data.index[-1].strftime("%Y-%m-%d")
    metrics = {
        "total_return_pct": round(total_return * 100, 2),
        "annualized_return_pct": round(annualized_return * 100, 2),
        "annualized_volatility_pct": round(annualized_volatility * 100, 2),
        "max_drawdown_pct": round(float(drawdown.min()) * 100, 2),
        "sharpe_ratio": round(float(sharpe), 2),
        "trading_days": int(len(returns)),
    }
    evidence = [
        _evidence(
            "risk.total_return_pct",
            "risk",
            "Total return",
            metrics["total_return_pct"],
            "%",
            end,
            source,
            "Latest close divided by first close minus one.",
        ),
        _evidence(
            "risk.annualized_return_pct",
            "risk",
            "Annualized return",
            metrics["annualized_return_pct"],
            "%",
            end,
            source,
            "Geometric annualization using 252 trading sessions.",
        ),
        _evidence(
            "risk.annualized_volatility_pct",
            "risk",
            "Annualized volatility",
            metrics["annualized_volatility_pct"],
            "%",
            end,
            source,
            "Sample standard deviation of daily returns × sqrt(252).",
        ),
        _evidence(
            "risk.max_drawdown_pct",
            "risk",
            "Maximum drawdown",
            metrics["max_drawdown_pct"],
            "%",
            end,
            source,
            "Minimum equity/rolling-peak minus one over the tested period.",
        ),
        _evidence(
            "risk.sharpe_ratio",
            "risk",
            "Sharpe ratio",
            metrics["sharpe_ratio"],
            "ratio",
            end,
            source,
            f"Daily excess return with {risk_free_rate * 100:.2f}% annual risk-free assumption, annualized by sqrt(252).",
        ),
    ]
    return {
        "analysis_period": {"start": start, "end": end},
        "metrics": metrics,
        "assumptions": {
            "trading_sessions_per_year": 252,
            "annual_risk_free_rate_pct": risk_free_rate * 100,
            "return_basis": "provider close-to-close returns",
        },
        "evidence": evidence,
    }


def _trade_statistics(
    close: pd.Series,
    exposure: pd.Series,
    transaction_cost_bps: float,
) -> dict[str, Any]:
    costs = transaction_cost_bps / 10_000
    entries: list[tuple[int, float]] = []
    trades: list[dict[str, Any]] = []
    previous = 0.0
    entry_index: int | None = None
    entry_price: float | None = None

    for index in range(1, len(exposure)):
        current = float(exposure.iloc[index])
        if current > 0 and previous <= 0:
            entry_index = index - 1
            entry_price = float(close.iloc[entry_index])
            entries.append((entry_index, entry_price))
        elif current <= 0 and previous > 0 and entry_index is not None and entry_price:
            exit_index = index - 1
            exit_price = float(close.iloc[exit_index])
            net_return = exit_price / entry_price - 1 - 2 * costs
            trades.append(
                {
                    "entry_date": close.index[entry_index].strftime("%Y-%m-%d"),
                    "exit_date": close.index[exit_index].strftime("%Y-%m-%d"),
                    "net_return_pct": round(net_return * 100, 2),
                    "open": False,
                }
            )
            entry_index = None
            entry_price = None
        previous = current

    open_position = entry_index is not None and entry_price is not None
    if open_position and entry_index is not None and entry_price:
        exit_price = float(close.iloc[-1])
        net_return = exit_price / entry_price - 1 - costs
        trades.append(
            {
                "entry_date": close.index[entry_index].strftime("%Y-%m-%d"),
                "exit_date": close.index[-1].strftime("%Y-%m-%d"),
                "net_return_pct": round(net_return * 100, 2),
                "open": True,
            }
        )

    completed = [trade for trade in trades if not trade["open"]]
    wins = [trade for trade in completed if trade["net_return_pct"] > 0]
    return {
        "number_of_trades": len(trades),
        "completed_trades": len(completed),
        "win_rate_pct": round(len(wins) / len(completed) * 100, 2) if completed else None,
        "open_position": open_position,
        "trades": trades,
    }


def _strategy_metrics(
    close: pd.Series,
    desired_position: pd.Series,
    transaction_cost_bps: float,
) -> dict[str, Any]:
    returns = close.pct_change().fillna(0.0)
    exposure = desired_position.shift(1).fillna(0.0).astype(float)
    turnover = exposure.diff().abs().fillna(abs(exposure.iloc[0]))
    costs = turnover * (transaction_cost_bps / 10_000)
    strategy_returns = exposure * returns - costs
    equity = (1 + strategy_returns).cumprod()
    equity_with_origin = pd.concat([pd.Series([1.0]), equity.reset_index(drop=True)])
    total_return = float(equity.iloc[-1] - 1)
    annualized_return = float(equity.iloc[-1] ** (252 / max(1, len(equity) - 1)) - 1)
    volatility = float(strategy_returns.iloc[1:].std(ddof=1) * math.sqrt(252))
    drawdown = equity_with_origin / equity_with_origin.cummax() - 1
    trades = _trade_statistics(close, exposure, transaction_cost_bps)

    return {
        "total_return_pct": round(total_return * 100, 2),
        "annualized_return_pct": round(annualized_return * 100, 2),
        "annualized_volatility_pct": round(volatility * 100, 2),
        "max_drawdown_pct": round(float(drawdown.min()) * 100, 2),
        **trades,
        "equity_curve": [
            {"date": index.strftime("%Y-%m-%d"), "value": round(float(value), 6)}
            for index, value in equity.items()
        ],
    }


def compare_backtest_strategies(
    frame: pd.DataFrame,
    *,
    source: str,
    short_window: int = 20,
    long_window: int = 50,
    transaction_cost_bps: float = 10.0,
) -> dict[str, Any]:
    data = prepare_history(frame)
    if not 2 <= short_window < long_window <= 250:
        raise ResearchValidationError("Backtest windows must satisfy 2 ≤ short < long ≤ 250.")
    if not 0 <= transaction_cost_bps <= 100:
        raise ResearchValidationError("Transaction cost must be between 0 and 100 basis points.")
    if len(data) <= long_window + 5:
        raise ResearchDataUnavailable("Price history is too short for the requested SMA strategy.")

    close = data["Close"].astype(float)
    buy_hold_position = pd.Series(1.0, index=close.index)
    short_average = close.rolling(short_window).mean()
    long_average = close.rolling(long_window).mean()
    sma_position = (short_average > long_average).astype(float)
    sma_position[long_average.isna()] = 0.0

    buy_hold = _strategy_metrics(close, buy_hold_position, transaction_cost_bps)
    sma_cross = _strategy_metrics(close, sma_position, transaction_cost_bps)
    start = data.index[0].strftime("%Y-%m-%d")
    end = data.index[-1].strftime("%Y-%m-%d")

    strategies = {"buy_and_hold": buy_hold, "sma20_sma50": sma_cross}
    evidence: list[dict[str, Any]] = []
    labels = {"buy_and_hold": "Buy and hold", "sma20_sma50": "SMA20/SMA50"}
    for key, result in strategies.items():
        for metric, unit, methodology in (
            (
                "total_return_pct",
                "%",
                "Compounded net daily strategy returns over the tested period.",
            ),
            (
                "annualized_return_pct",
                "%",
                "Geometric annualization of the ending equity using 252 sessions.",
            ),
            (
                "annualized_volatility_pct",
                "%",
                "Sample standard deviation of net daily strategy returns × sqrt(252).",
            ),
            (
                "max_drawdown_pct",
                "%",
                "Minimum strategy equity/rolling-peak minus one.",
            ),
            (
                "win_rate_pct",
                "%",
                "Profitable completed trades divided by completed trades.",
            ),
            (
                "number_of_trades",
                "count",
                "Long entries observed in the executed position series, including an open trade.",
            ),
        ):
            value = result.get(metric)
            if value is None:
                continue
            evidence.append(
                _evidence(
                    f"backtest.{key}.{metric}",
                    "backtest",
                    f"{labels[key]} {metric.replace('_', ' ')}",
                    value,
                    unit,
                    end,
                    source,
                    methodology,
                )
            )

    return {
        "analysis_period": {"start": start, "end": end},
        "strategies": strategies,
        "assumptions": {
            "signal_timing": "SMA signal computed at close and applied to the next session return",
            "positioning": "long-only, full notional when invested, no leverage",
            "transaction_cost_bps_per_position_change": transaction_cost_bps,
            "dividends_and_taxes": "not modeled separately; uses the provider close series",
            "survivorship_bias": "possible for a single currently selected symbol",
            "overfitting_warning": "one historical rule and one symbol do not establish future performance",
            "data_quality_warning": "provider gaps or adjustments can affect results",
        },
        "evidence": evidence,
    }


def _json_safe(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return _finite(value)
    if isinstance(value, (pd.Timestamp, date)):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def openai_tool_definitions() -> list[dict[str, Any]]:
    """Return strict Responses API function-tool definitions."""
    common = {
        "symbol": {"type": "string", "description": "Validated selected stock symbol."},
        "market": {
            "type": "string",
            "enum": list(MARKET_CONFIG),
            "description": "Validated selected market.",
        },
    }
    with_period = {
        **common,
        "period": {
            "type": "string",
            "enum": list(PERIOD_OBSERVATIONS),
            "description": "Validated analysis period.",
        },
    }

    def tool(name: str, description: str, properties: dict[str, Any], required: list[str]):
        return {
            "type": "function",
            "name": name,
            "description": description,
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        }

    return [
        tool(
            "search_symbol",
            "Validate and resolve a stock symbol in the selected market.",
            {
                "query": {"type": "string", "description": "Symbol or company search query."},
                "market": common["market"],
            },
            ["query", "market"],
        ),
        tool(
            "get_symbol_profile",
            "Get the selected symbol's deterministic provider profile and currency.",
            common,
            ["symbol", "market"],
        ),
        tool(
            "get_price_history",
            "Get dated OHLCV history and a compact price summary for the selected period.",
            with_period,
            ["symbol", "market", "period"],
        ),
        tool(
            "get_financial_data",
            "Get available fundamental fields with source and availability warnings.",
            common,
            ["symbol", "market"],
        ),
        tool(
            "calculate_technical_indicators",
            "Calculate deterministic technical indicators and dated evidence.",
            with_period,
            ["symbol", "market", "period"],
        ),
        tool(
            "calculate_risk_metrics",
            "Calculate deterministic return, volatility, drawdown, and Sharpe metrics.",
            with_period,
            ["symbol", "market", "period"],
        ),
        tool(
            "run_strategy_backtest",
            "Run either buy-and-hold or SMA20/SMA50 with explicit cost assumptions.",
            {
                **with_period,
                "strategy": {"type": "string", "enum": ["buy_and_hold", "sma20_sma50"]},
                "transaction_cost_bps": {"type": "number", "minimum": 0, "maximum": 100},
            },
            ["symbol", "market", "period", "strategy", "transaction_cost_bps"],
        ),
        tool(
            "compare_strategy_results",
            "Compare buy-and-hold with SMA20/SMA50 on the same dates and assumptions.",
            {
                **with_period,
                "transaction_cost_bps": {"type": "number", "minimum": 0, "maximum": 100},
            },
            ["symbol", "market", "period", "transaction_cost_bps"],
        ),
        tool(
            "get_supporting_evidence",
            "Retrieve exact evidence records already produced by deterministic tools.",
            {
                "evidence_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": 30,
                }
            },
            ["evidence_ids"],
        ),
    ]


class ResearchToolbox:
    """Request-scoped deterministic tools and evidence ledger."""

    def __init__(
        self,
        request_data: ValidatedResearchRequest,
        *,
        history_loader: Callable[[str, str], pd.DataFrame | None] | None = None,
        profile_loader: Callable[[str], dict[str, Any]] | None = None,
    ) -> None:
        self.request = request_data
        self.history_loader = history_loader
        self.profile_loader = profile_loader
        self.evidence_ledger: dict[str, dict[str, Any]] = {}
        self._history_cache: pd.DataFrame | None = None
        self._profile_cache: dict[str, Any] | None = None

    @property
    def source(self) -> str:
        return (
            "Aeternus deterministic synthetic generator v1"
            if self.request.demo_mode
            else "Yahoo Finance via yfinance"
        )

    @property
    def currency(self) -> str:
        profile = self._profile()
        return str(profile.get("currency") or MARKET_CONFIG[self.request.market]["currency"])

    def _history(self) -> pd.DataFrame:
        if self._history_cache is not None:
            return self._history_cache.copy()
        if self.request.demo_mode:
            raw = generate_demo_history(self.request.period)
        else:
            if self.history_loader is None:
                raise ResearchDataUnavailable("Live history provider is unavailable.")
            raw = self.history_loader(self.request.symbol, self.request.period)
            if raw is None:
                raise ResearchDataUnavailable(f"No price history is available for {self.request.symbol}.")
        self._history_cache = prepare_history(raw)
        return self._history_cache.copy()

    def _profile(self) -> dict[str, Any]:
        if self._profile_cache is not None:
            return dict(self._profile_cache)
        if self.request.demo_mode:
            self._profile_cache = {
                "symbol": DEMO_SYMBOL,
                "name": "Aeternus Synthetic Industries",
                "market": DEMO_MARKET,
                "exchange": "SIMULATED",
                "currency": "USD",
                "sector": "Synthetic diversified technology",
                "industry": "Educational simulation",
                "description": (
                    "A fictional company used only for a reproducible Build Week demonstration."
                ),
                "data_mode": "synthetic_demo",
            }
        else:
            loaded = self.profile_loader(self.request.symbol) if self.profile_loader else {}
            self._profile_cache = {
                **loaded,
                "symbol": self.request.symbol,
                "name": loaded.get("long_name") or loaded.get("name") or self.request.symbol,
                "market": self.request.market,
                "exchange": loaded.get("exchange") or "unavailable",
                "currency": loaded.get("currency")
                or MARKET_CONFIG[self.request.market]["currency"],
                "sector": loaded.get("sector") or "unavailable",
                "industry": loaded.get("industry") or "unavailable",
                "description": loaded.get("description") or "",
                "data_mode": "live_public_data",
            }
        return dict(self._profile_cache)

    def _validate_scope(self, arguments: dict[str, Any], *, period: bool = False) -> None:
        if normalize_symbol(arguments.get("symbol")) != self.request.symbol:
            raise ResearchValidationError("Tool symbol must match the selected research symbol.")
        market = str(arguments.get("market", "")).strip().lower()
        if market != self.request.market:
            raise ResearchValidationError("Tool market must match the selected research market.")
        if period and arguments.get("period") != self.request.period:
            raise ResearchValidationError("Tool period must match the selected analysis period.")

    def _record(self, result: dict[str, Any]) -> dict[str, Any]:
        for item in result.get("evidence", []):
            evidence_id = item.get("id")
            if evidence_id:
                self.evidence_ledger[evidence_id] = _json_safe(item)
        return _json_safe(result)

    def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name not in TOOL_NAMES:
            raise ResearchValidationError(f"Unknown research tool: {name}")
        if not isinstance(arguments, dict):
            raise ResearchValidationError("Tool arguments must be an object.")

        if name == "search_symbol":
            market = str(arguments.get("market", "")).strip().lower()
            if market != self.request.market:
                raise ResearchValidationError("Search market must match the selected market.")
            query = str(arguments.get("query", "")).strip().upper()
            if not query:
                raise ResearchValidationError("Search query is required.")
            matches = [
                item
                for item in DEFAULT_SYMBOLS[market]
                if query in item["symbol"].upper() or query in item["name"].upper()
            ]
            if self.request.symbol not in {item["symbol"] for item in matches}:
                matches.insert(0, {"symbol": self.request.symbol, "name": self._profile()["name"]})
            return {
                "query": query,
                "market": market,
                "matches": matches[:10],
                "selected_symbol_valid": True,
            }

        if name == "get_supporting_evidence":
            evidence_ids = arguments.get("evidence_ids")
            if not isinstance(evidence_ids, list) or not evidence_ids:
                raise ResearchValidationError("At least one evidence ID is required.")
            unknown = [item for item in evidence_ids if item not in self.evidence_ledger]
            if unknown:
                raise ResearchValidationError(f"Unknown evidence IDs: {', '.join(unknown)}")
            return {"evidence": [self.evidence_ledger[item] for item in evidence_ids]}

        needs_period = name in {
            "get_price_history",
            "calculate_technical_indicators",
            "calculate_risk_metrics",
            "run_strategy_backtest",
            "compare_strategy_results",
        }
        self._validate_scope(arguments, period=needs_period)

        if name == "get_symbol_profile":
            profile = self._profile()
            return {
                "profile": profile,
                "source": self.source,
                "warnings": (
                    ["All profile fields are synthetic and fixed for demonstration."]
                    if self.request.demo_mode
                    else ["Profile availability and reporting periods depend on Yahoo Finance."]
                ),
            }

        if name == "get_price_history":
            history = self._history()
            start = history.index[0].strftime("%Y-%m-%d")
            end = history.index[-1].strftime("%Y-%m-%d")
            result = {
                "analysis_period": {"start": start, "end": end},
                "currency": self.currency,
                "observations": len(history),
                "first_close": _finite(history["Close"].iloc[0]),
                "last_close": _finite(history["Close"].iloc[-1]),
                "recent_points": [
                    {
                        "date": index.strftime("%Y-%m-%d"),
                        "close": _finite(row["Close"]),
                        "volume": int(row["Volume"]) if pd.notna(row["Volume"]) else None,
                    }
                    for index, row in history.tail(20).iterrows()
                ],
                "source": self.source,
                "data_mode": "synthetic_demo" if self.request.demo_mode else "live_public_data",
                "evidence": [
                    _evidence(
                        "price.first_close",
                        "price",
                        "First close in analysis period",
                        _finite(history["Close"].iloc[0]),
                        self.currency,
                        start,
                        self.source,
                        "Provider closing price at the first usable observation.",
                    ),
                    _evidence(
                        "price.last_close",
                        "price",
                        "Latest close in analysis period",
                        _finite(history["Close"].iloc[-1]),
                        self.currency,
                        end,
                        self.source,
                        "Provider closing price at the last usable observation.",
                    ),
                ],
            }
            return self._record(result)

        if name == "get_financial_data":
            profile = self._profile()
            if self.request.demo_mode:
                fields = {
                    "market_cap": 12_500_000_000,
                    "pe_ratio": 22.4,
                    "revenue": 4_200_000_000,
                    "profit_margin_pct": 14.8,
                    "debt_to_equity_pct": 35.0,
                }
                warning = "All financial values are synthetic demonstration inputs, not live figures."
            else:
                fields = {
                    "market_cap": profile.get("market_cap"),
                    "pe_ratio": profile.get("pe_ratio"),
                    "revenue": profile.get("revenue"),
                    "profit_margin_pct": profile.get("profit_margin"),
                    "debt_to_equity_pct": profile.get("debt_ratio"),
                    "roe_pct": profile.get("roe"),
                    "eps": profile.get("eps"),
                    "dividend_yield_pct": profile.get("dividend_yield"),
                }
                warning = (
                    "Provider statement dates and reporting periods are unavailable in the baseline "
                    "profile response; missing fields remain null."
                )
            as_of = self._history().index[-1].strftime("%Y-%m-%d")
            evidence = []
            for key, value in fields.items():
                if value is None:
                    continue
                unit = "%" if key.endswith("_pct") else self.currency if key in {"market_cap", "revenue", "eps"} else "ratio"
                evidence.append(
                    _evidence(
                        f"fundamental.{key}",
                        "fundamental",
                        key.replace("_", " ").title(),
                        _finite(value, 4) if isinstance(value, (int, float)) else value,
                        unit,
                        as_of,
                        self.source,
                        "Latest value exposed by the selected deterministic provider; statement period unavailable."
                        if not self.request.demo_mode
                        else "Fixed synthetic value for the Build Week demonstration.",
                    )
                )
            return self._record(
                {
                    "currency": self.currency,
                    "fields": fields,
                    "reported_period": "unavailable",
                    "warning": warning,
                    "evidence": evidence,
                }
            )

        if name == "calculate_technical_indicators":
            return self._record(
                calculate_technical_snapshot(
                    self._history(), source=self.source, currency=self.currency
                )
            )

        if name == "calculate_risk_metrics":
            return self._record(calculate_risk_snapshot(self._history(), source=self.source))

        if name in {"run_strategy_backtest", "compare_strategy_results"}:
            transaction_cost_bps = float(arguments.get("transaction_cost_bps", 10.0))
            comparison = compare_backtest_strategies(
                self._history(),
                source=self.source,
                short_window=20,
                long_window=50,
                transaction_cost_bps=transaction_cost_bps,
            )
            if name == "run_strategy_backtest":
                strategy = arguments.get("strategy")
                if strategy not in {"buy_and_hold", "sma20_sma50"}:
                    raise ResearchValidationError("Unsupported backtest strategy.")
                result = {
                    "analysis_period": comparison["analysis_period"],
                    "strategy": strategy,
                    "metrics": comparison["strategies"][strategy],
                    "assumptions": comparison["assumptions"],
                    "evidence": [
                        item
                        for item in comparison["evidence"]
                        if item["id"].startswith(f"backtest.{strategy}.")
                    ],
                }
                return self._record(result)
            return self._record(comparison)

        raise ResearchValidationError(f"Research tool is not implemented: {name}")


def deterministic_demo_tool_sequence(toolbox: ResearchToolbox) -> list[dict[str, Any]]:
    """Run the complete judge demo without network or model credentials."""
    request_data = toolbox.request
    common = {"symbol": request_data.symbol, "market": request_data.market}
    with_period = {**common, "period": request_data.period}
    calls = [
        ("search_symbol", {"query": request_data.symbol, "market": request_data.market}),
        ("get_symbol_profile", common),
        ("get_price_history", with_period),
        ("get_financial_data", common),
        ("calculate_technical_indicators", with_period),
        ("calculate_risk_metrics", with_period),
        (
            "compare_strategy_results",
            {**with_period, "transaction_cost_bps": 10.0},
        ),
    ]
    return [{"name": name, "arguments": args, "result": toolbox.execute(name, args)} for name, args in calls]
