from __future__ import annotations

from datetime import datetime, timedelta

from monitor_core import AnalysisResult, FactorResult, MarketSnapshot, MonitorConfig, MonitorState
from monitor_dashboard import (
    ReportHistoryItemView,
    build_dashboard_view,
    build_report_history,
    filter_report_history,
    load_report_content,
)


def make_snapshot():
    return MarketSnapshot(
        as_of=datetime(2026, 3, 12, 8, 50),
        gold_price=2950.0,
        shanghai_gold=690.0,
        etf_price=6.12,
        etf_sma20=6.00,
        etf_sma60=5.88,
        gold_24h_change_pct=-3.4,
    )


def make_result(**overrides):
    base = {
        "mode": "盘前",
        "as_of": datetime(2026, 3, 12, 8, 50),
        "action_code": "STRONG_BUY",
        "action_label": "🟢 强烈买入",
        "detail": "环境偏强，可按计划增加 1.5% 仓位。",
        "gfi": 87.5,
        "rc": 0.15,
        "factors": [
            FactorResult("真实利率", 100, 0.25, "负实利率", True),
            FactorResult("ETF资金趋势", None, 0.0, "未配置资金流数据", False),
        ],
        "missing_critical_fields": [],
        "triggered": False,
        "metadata": {},
    }
    base.update(overrides)
    return AnalysisResult(**base)


def test_dashboard_view_maps_high_conviction_result_to_visual_summary():
    view = build_dashboard_view(
        snapshot=make_snapshot(),
        result=make_result(),
        config=MonitorConfig(),
        state=MonitorState(last_buy_at=datetime(2026, 3, 1, 9, 0)),
    )

    assert view.gauge.score_text == "87.5"
    assert view.gauge.tone == "bull"
    assert view.decision.title == "强烈买入"
    assert "增加 1.5% 仓位" in view.decision.subtitle
    assert view.analysis_time_text == "2026-03-12 08:50"
    assert [pill.value for pill in view.status_pills] == ["可执行", "数据完整", "盘前"]


def test_dashboard_view_marks_missing_critical_data_as_blocking_warning():
    view = build_dashboard_view(
        snapshot=make_snapshot(),
        result=make_result(
            action_code="NO_DECISION",
            action_label="⚪ 数据不足",
            detail="关键数据缺失，停止出买卖建议，等待下一次完整抓取。",
            gfi=None,
            missing_critical_fields=["tips_10y", "etf_trend"],
        ),
        config=MonitorConfig(),
        state=MonitorState(),
    )

    assert view.banner is not None
    assert view.banner.tone == "blocked"
    assert "tips_10y" in view.banner.message
    assert view.gauge.score_text == "N/A"
    assert view.status_pills[0].value == "禁止执行"
    assert "关键数据缺失" in view.action_block_reason


def test_dashboard_view_surfaces_source_fallback_notes_without_blocking():
    snapshot = make_snapshot()
    snapshot.data_notes = ["FRED 超时，核心 CPI 已切换到 BLS 官方 API 备用数据。"]
    view = build_dashboard_view(
        snapshot=snapshot,
        result=make_result(),
        config=MonitorConfig(),
        state=MonitorState(),
    )

    assert view.banner is not None
    assert view.banner.tone == "watch"
    assert "BLS" in view.banner.message


def test_dashboard_view_exposes_cooldown_and_remaining_days():
    snapshot = make_snapshot()
    view = build_dashboard_view(
        snapshot=snapshot,
        result=make_result(
            mode="盘中",
            action_code="WAIT_COOLDOWN",
            action_label="🟡 冷却期未结束",
            detail="已触发回调，但距上次买入仅 1 天，未达到 3 天冷却期。",
            triggered=True,
            metadata={"days_since_buy": 1},
        ),
        config=MonitorConfig(min_add_cooldown_days=3, portfolio_gold_weight=0.22),
        state=MonitorState(last_buy_at=snapshot.as_of - timedelta(days=1)),
    )

    assert view.state.cooldown_text == "冷却中，还需 2 天"
    assert view.state.weight_text == "22.0%"
    assert view.quick_action_enabled is False
    assert view.status_pills[0].value == "先等待"


def test_report_history_returns_latest_reports_first(tmp_path):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    files = [
        reports_dir / "20260310_0850_盘前_DCA_GFI61.txt",
        reports_dir / "20260312_1330_盘中_ADD_ON_GFI87.txt",
        reports_dir / "20260311_0850_盘前_HOLD_GFI48.txt",
    ]
    for path in files:
        path.write_text("report", encoding="utf-8")

    history = build_report_history(reports_dir, limit=2)

    assert [item.filename for item in history] == [
        "20260312_1330_盘中_ADD_ON_GFI87.txt",
        "20260311_0850_盘前_HOLD_GFI48.txt",
    ]
    assert history[0].title == "盘中 / ADD ON / GFI87"


def test_load_report_content_returns_text_and_fallback(tmp_path):
    report = tmp_path / "20260312_0850_盘前_STRONG_BUY_GFI87.txt"
    report.write_text("hello report", encoding="utf-8")

    assert load_report_content(report) == "hello report"
    assert "无法读取" in load_report_content(tmp_path / "missing.txt")


def test_filter_report_history_by_mode():
    history = [
        ReportHistoryItemView(
            filename="20260312_0850_盘前_STRONG_BUY_GFI87.txt",
            path="/tmp/20260312_0850_盘前_STRONG_BUY_GFI87.txt",
            title="盘前 / STRONG BUY / GFI87",
            subtitle="20260312 0850",
            tone="bull",
        ),
        ReportHistoryItemView(
            filename="20260312_1330_盘中_ADD_ON_GFI87.txt",
            path="/tmp/20260312_1330_盘中_ADD_ON_GFI87.txt",
            title="盘中 / ADD ON / GFI87",
            subtitle="20260312 1330",
            tone="bull",
        ),
    ]

    assert [item.filename for item in filter_report_history(history, "盘前")] == [
        "20260312_0850_盘前_STRONG_BUY_GFI87.txt"
    ]
    assert [item.filename for item in filter_report_history(history, "盘中")] == [
        "20260312_1330_盘中_ADD_ON_GFI87.txt"
    ]
    assert len(filter_report_history(history, "全部")) == 2
