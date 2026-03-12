from __future__ import annotations

from datetime import datetime, timedelta

from monitor_core import (
    MarketSnapshot,
    MonitorConfig,
    MonitorState,
    analyze_intraday,
    analyze_morning,
    calculate_risk_contribution,
)


def make_snapshot(**overrides):
    base = {
        "as_of": datetime(2026, 3, 12, 8, 50),
        "gold_price": 2950.0,
        "gold_change_pct": 0.8,
        "shanghai_gold": 690.0,
        "etf_price": 6.12,
        "etf_sma20": 6.00,
        "etf_sma60": 5.88,
        "tips_10y": -0.25,
        "core_cpi_yoy": 3.1,
        "dxy": 101.5,
        "dxy_mom": -2.8,
        "vix": 21.0,
        "gold_sma50": 2875.0,
        "gold_sma200": 2610.0,
        "share_trend": None,
        "gold_24h_change_pct": -3.4,
    }
    base.update(overrides)
    return MarketSnapshot(**base)


def test_morning_analysis_fails_closed_when_critical_data_missing():
    snapshot = make_snapshot(tips_10y=None)

    result = analyze_morning(snapshot, MonitorConfig())

    assert result.action_code == "NO_DECISION"
    assert result.gfi is None
    assert "tips_10y" in result.missing_critical_fields


def test_missing_share_trend_does_not_create_bullish_bias():
    snapshot = make_snapshot(share_trend=None)

    result = analyze_morning(snapshot, MonitorConfig())

    share_flow = next(f for f in result.factors if f.name == "ETF资金趋势")
    assert share_flow.available is False
    assert share_flow.weight == 0


def test_risk_contribution_uses_runtime_config_values():
    rc = calculate_risk_contribution(
        MonitorConfig(
            portfolio_gold_weight=0.20,
            gold_volatility=0.18,
            portfolio_volatility=0.10,
        )
    )

    assert rc == 0.36


def test_intraday_requires_buy_cooldown_before_extra_add():
    snapshot = make_snapshot()
    config = MonitorConfig(min_add_cooldown_days=3)
    state = MonitorState(last_buy_at=snapshot.as_of - timedelta(days=1))

    result = analyze_intraday(snapshot, config, state)

    assert result.action_code == "WAIT_COOLDOWN"
    assert result.triggered is True
    assert "冷却" in result.detail
