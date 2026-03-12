from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from monitor_core import AnalysisResult, MarketSnapshot, MonitorConfig, MonitorState


@dataclass
class GaugeView:
    score_text: str
    tone: str
    label: str
    progress: float


@dataclass
class DecisionView:
    title: str
    subtitle: str
    tone: str
    badge: str


@dataclass
class BannerView:
    tone: str
    title: str
    message: str


@dataclass
class StateView:
    last_buy_text: str
    cooldown_text: str
    rc_text: str
    weight_text: str
    mode_text: str


@dataclass
class MetricView:
    label: str
    value: str
    emphasis: str = "normal"


@dataclass
class FactorCardView:
    title: str
    score_text: str
    detail: str
    tone: str


@dataclass
class StatusPillView:
    label: str
    value: str
    tone: str


@dataclass
class ReportHistoryItemView:
    filename: str
    path: str
    title: str
    subtitle: str
    tone: str


@dataclass
class DashboardView:
    gauge: GaugeView
    decision: DecisionView
    state: StateView
    analysis_time_text: str
    metrics: list[MetricView] = field(default_factory=list)
    status_pills: list[StatusPillView] = field(default_factory=list)
    factors: list[FactorCardView] = field(default_factory=list)
    report_history: list[ReportHistoryItemView] = field(default_factory=list)
    banner: BannerView | None = None
    quick_action_enabled: bool = True
    action_block_reason: str = ""


def build_dashboard_view(
    snapshot: MarketSnapshot,
    result: AnalysisResult,
    config: MonitorConfig,
    state: MonitorState,
    report_history: list[ReportHistoryItemView] | None = None,
) -> DashboardView:
    tone = _tone_for_result(result)
    gauge = GaugeView(
        score_text="N/A" if result.gfi is None else f"{result.gfi:.1f}",
        tone=tone,
        label=_gauge_label(result.gfi),
        progress=0.0 if result.gfi is None else max(0.0, min(1.0, result.gfi / 100)),
    )
    decision = DecisionView(
        title=_strip_icon(result.action_label),
        subtitle=result.detail,
        tone=tone,
        badge=result.mode,
    )
    state_view = StateView(
        last_buy_text=_format_last_buy(state),
        cooldown_text=_format_cooldown(result, config, state),
        rc_text=f"{result.rc * 100:.1f}%",
        weight_text=f"{config.portfolio_gold_weight * 100:.1f}%",
        mode_text=result.mode,
    )
    metrics = [
        MetricView("RC 风险", state_view.rc_text, "strong" if result.rc > 0.18 else "normal"),
        MetricView("黄金仓位", state_view.weight_text),
        MetricView("上次买入", state_view.last_buy_text),
        MetricView("冷却状态", state_view.cooldown_text, "strong" if "冷却中" in state_view.cooldown_text else "normal"),
    ]
    factors = [
        FactorCardView(
            title=factor.name,
            score_text="N/A" if factor.score is None else str(factor.score),
            detail=factor.description,
            tone="muted" if not factor.available else _tone_for_factor(factor.score),
        )
        for factor in result.factors
    ]
    banner = None
    if result.missing_critical_fields:
        detail = f"本次不提供交易建议，缺失字段：{', '.join(result.missing_critical_fields)}"
        if snapshot.data_notes:
            detail = f"{detail}。数据源说明：{'；'.join(snapshot.data_notes)}"
        banner = BannerView(
            tone="blocked",
            title="关键数据不足",
            message=detail,
        )
    elif snapshot.data_notes:
        banner = BannerView(
            tone="watch",
            title="已切换备用数据源",
            message="；".join(snapshot.data_notes),
        )
    quick_action_enabled = result.action_code not in {"NO_DECISION", "WAIT_COOLDOWN"}
    action_block_reason = _action_block_reason(result)
    status_pills = [
        StatusPillView("执行状态", _execution_value(result.action_code), tone),
        StatusPillView("数据状态", "数据完整" if banner is None else "有缺失", "bull" if banner is None else "blocked"),
        StatusPillView("分析模式", result.mode, "neutral"),
    ]
    return DashboardView(
        gauge=gauge,
        decision=decision,
        state=state_view,
        analysis_time_text=result.as_of.strftime("%Y-%m-%d %H:%M"),
        metrics=metrics,
        status_pills=status_pills,
        factors=factors,
        report_history=report_history or [],
        banner=banner,
        quick_action_enabled=quick_action_enabled,
        action_block_reason=action_block_reason,
    )


def build_report_history(reports_dir: str | Path, limit: int = 5) -> list[ReportHistoryItemView]:
    report_path = Path(reports_dir)
    if not report_path.exists():
        return []

    items = []
    for path in sorted(report_path.glob("*.txt"), reverse=True)[:limit]:
        parts = path.stem.split("_")
        mode = parts[2] if len(parts) > 2 else "未知"
        gfi = parts[-1] if len(parts) > 3 else "NA"
        action = " ".join(parts[3:-1]) if len(parts) > 4 else (parts[3] if len(parts) > 3 else "未知")
        subtitle = f"{parts[0]} {parts[1]}" if len(parts) > 1 else path.stem
        tone = _history_tone(action)
        items.append(
            ReportHistoryItemView(
                filename=path.name,
                path=str(path),
                title=f"{mode} / {action} / {gfi}",
                subtitle=subtitle,
                tone=tone,
            )
        )
    return items


def filter_report_history(
    history: list[ReportHistoryItemView],
    mode_filter: str,
) -> list[ReportHistoryItemView]:
    if mode_filter == "全部":
        return history
    prefix = f"{mode_filter} / "
    return [item for item in history if item.title.startswith(prefix)]


def load_report_content(report_path: str | Path) -> str:
    path = Path(report_path)
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return f"无法读取报告: {path}"


def _tone_for_result(result: AnalysisResult) -> str:
    if result.action_code in {"STRONG_BUY", "ADD_ON", "DCA"}:
        return "bull"
    if result.action_code in {"NO_DECISION", "STOP", "REDUCE"}:
        return "blocked"
    if result.action_code in {"WAIT_COOLDOWN", "WAIT_STABILIZE", "HOLD", "MONITOR_ONLY"}:
        return "watch"
    return "neutral"


def _tone_for_factor(score: int | None) -> str:
    if score is None:
        return "muted"
    if score >= 70:
        return "bull"
    if score >= 40:
        return "watch"
    return "blocked"


def _gauge_label(gfi: float | None) -> str:
    if gfi is None:
        return "数据不足"
    if gfi >= 70:
        return "偏强"
    if gfi >= 50:
        return "可建仓"
    if gfi >= 30:
        return "观望"
    return "暂停"


def _strip_icon(action_label: str) -> str:
    if " " in action_label:
        return action_label.split(" ", 1)[1]
    return action_label


def _format_last_buy(state: MonitorState) -> str:
    if state.last_buy_at is None:
        return "未记录"
    return state.last_buy_at.strftime("%Y-%m-%d %H:%M")


def _format_cooldown(result: AnalysisResult, config: MonitorConfig, state: MonitorState) -> str:
    if result.action_code == "WAIT_COOLDOWN":
        days_since = int(result.metadata.get("days_since_buy", 0))
        remaining = max(config.min_add_cooldown_days - days_since, 0)
        return f"冷却中，还需 {remaining} 天"
    if state.last_buy_at is None:
        return "未开始"
    return "可操作"


def _execution_value(action_code: str) -> str:
    if action_code in {"STRONG_BUY", "DCA", "ADD_ON"}:
        return "可执行"
    if action_code in {"WAIT_COOLDOWN", "WAIT_STABILIZE", "HOLD", "MONITOR_ONLY"}:
        return "先等待"
    if action_code in {"NO_DECISION", "STOP", "REDUCE"}:
        return "禁止执行"
    return "待运行"


def _history_tone(action: str) -> str:
    if action in {"STRONG_BUY", "ADD_ON", "DCA"}:
        return "bull"
    if action in {"NO_DECISION", "STOP", "REDUCE"}:
        return "blocked"
    return "watch"


def _action_block_reason(result: AnalysisResult) -> str:
    if result.action_code == "NO_DECISION":
        return "关键数据缺失，禁止依据系统建议执行交易。"
    if result.action_code == "WAIT_COOLDOWN":
        return "冷却期未结束，今天不要追加买入。"
    if result.action_code in {"STOP", "REDUCE"}:
        return "当前环境偏弱，系统不支持继续加仓。"
    return ""
