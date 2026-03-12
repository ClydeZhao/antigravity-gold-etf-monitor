from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class MarketSnapshot:
    as_of: datetime
    gold_price: Optional[float] = None
    gold_change_pct: Optional[float] = None
    shanghai_gold: Optional[float] = None
    etf_price: Optional[float] = None
    etf_sma20: Optional[float] = None
    etf_sma60: Optional[float] = None
    tips_10y: Optional[float] = None
    core_cpi_yoy: Optional[float] = None
    dxy: Optional[float] = None
    dxy_mom: Optional[float] = None
    vix: Optional[float] = None
    gold_sma50: Optional[float] = None
    gold_sma200: Optional[float] = None
    share_trend: Optional[str] = None
    gold_24h_change_pct: Optional[float] = None
    data_notes: list[str] = field(default_factory=list)


@dataclass
class MonitorConfig:
    portfolio_gold_weight: float = 0.12
    gold_volatility: float = 0.15
    portfolio_volatility: float = 0.12
    min_add_cooldown_days: int = 3
    reports_dir: str = "reports"


@dataclass
class MonitorState:
    last_buy_at: Optional[datetime] = None


@dataclass
class FactorResult:
    name: str
    score: Optional[int]
    weight: float
    description: str
    available: bool


@dataclass
class AnalysisResult:
    mode: str
    as_of: datetime
    action_code: str
    action_label: str
    detail: str
    gfi: Optional[float]
    rc: float
    factors: list[FactorResult] = field(default_factory=list)
    missing_critical_fields: list[str] = field(default_factory=list)
    triggered: bool = False
    metadata: dict[str, object] = field(default_factory=dict)


MANDATORY_FACTOR_WEIGHTS = {
    "真实利率": 0.25,
    "核心CPI": 0.15,
    "DXY动量": 0.15,
    "VIX": 0.10,
    "黄金趋势": 0.15,
    "ETF趋势": 0.20,
}
OPTIONAL_FACTOR_WEIGHTS = {
    "ETF资金趋势": 0.10,
}


def calculate_risk_contribution(config: MonitorConfig) -> float:
    if config.portfolio_volatility <= 0:
        raise ValueError("portfolio_volatility must be positive")
    return round(
        (config.portfolio_gold_weight * config.gold_volatility) / config.portfolio_volatility,
        4,
    )


def analyze_morning(snapshot: MarketSnapshot, config: MonitorConfig) -> AnalysisResult:
    factors, missing = _build_morning_factors(snapshot)
    rc = calculate_risk_contribution(config)
    if missing:
        return AnalysisResult(
            mode="盘前",
            as_of=snapshot.as_of,
            action_code="NO_DECISION",
            action_label="⚪ 数据不足",
            detail="关键数据缺失，停止出买卖建议，等待下一次完整抓取。",
            gfi=None,
            rc=rc,
            factors=factors,
            missing_critical_fields=missing,
        )

    active_weight = sum(f.weight for f in factors if f.available)
    gfi = round(
        sum((f.score or 0) * f.weight for f in factors if f.available) / active_weight,
        1,
    )
    action_code, action_label, detail = _action_from_score(gfi, rc)
    return AnalysisResult(
        mode="盘前",
        as_of=snapshot.as_of,
        action_code=action_code,
        action_label=action_label,
        detail=detail,
        gfi=gfi,
        rc=rc,
        factors=factors,
        missing_critical_fields=[],
    )


def analyze_intraday(
    snapshot: MarketSnapshot,
    config: MonitorConfig,
    state: MonitorState,
) -> AnalysisResult:
    morning = analyze_morning(snapshot, config)
    if snapshot.gold_24h_change_pct is None:
        return AnalysisResult(
            mode="盘中",
            as_of=snapshot.as_of,
            action_code="NO_DECISION",
            action_label="⚪ 数据不足",
            detail="无法获取黄金 24h 涨跌幅，停止盘中加仓判断。",
            gfi=morning.gfi,
            rc=morning.rc,
            factors=morning.factors,
            missing_critical_fields=morning.missing_critical_fields + ["gold_24h_change_pct"],
        )

    if morning.action_code == "NO_DECISION":
        return AnalysisResult(
            mode="盘中",
            as_of=snapshot.as_of,
            action_code="NO_DECISION",
            action_label="⚪ 数据不足",
            detail="盘前关键数据不足，盘中不做额外加仓判断。",
            gfi=morning.gfi,
            rc=morning.rc,
            factors=morning.factors,
            missing_critical_fields=morning.missing_critical_fields,
            triggered=snapshot.gold_24h_change_pct <= -3,
        )

    triggered = snapshot.gold_24h_change_pct <= -3
    if not triggered:
        return AnalysisResult(
            mode="盘中",
            as_of=snapshot.as_of,
            action_code="MONITOR_ONLY",
            action_label="✅ 无异常回调",
            detail=f"24h 涨跌幅 {snapshot.gold_24h_change_pct:+.2f}%，未触发 -3% 回调阈值。",
            gfi=morning.gfi,
            rc=morning.rc,
            factors=morning.factors,
            triggered=False,
        )

    days_since_buy = None
    if state.last_buy_at is not None:
        days_since_buy = (snapshot.as_of.date() - state.last_buy_at.date()).days

    if days_since_buy is not None and days_since_buy < config.min_add_cooldown_days:
        return AnalysisResult(
            mode="盘中",
            as_of=snapshot.as_of,
            action_code="WAIT_COOLDOWN",
            action_label="🟡 冷却期未结束",
            detail=(
                f"已触发回调，但距上次买入仅 {days_since_buy} 天，"
                f"未达到 {config.min_add_cooldown_days} 天冷却期。"
            ),
            gfi=morning.gfi,
            rc=morning.rc,
            factors=morning.factors,
            triggered=True,
            metadata={"days_since_buy": days_since_buy},
        )

    if snapshot.gold_24h_change_pct < -5 and (morning.gfi or 0) >= 50:
        return AnalysisResult(
            mode="盘中",
            as_of=snapshot.as_of,
            action_code="WAIT_STABILIZE",
            action_label="⚠️ 跌幅过大",
            detail="24h 跌幅超过 5%，等待企稳后再评估，不执行回调加仓。",
            gfi=morning.gfi,
            rc=morning.rc,
            factors=morning.factors,
            triggered=True,
        )

    if -5 <= snapshot.gold_24h_change_pct <= -3 and (morning.gfi or 0) >= 50 and morning.rc <= 0.18:
        return AnalysisResult(
            mode="盘中",
            as_of=snapshot.as_of,
            action_code="ADD_ON",
            action_label="⚡ 触发回调加仓",
            detail="满足回调和 GFI 条件，可额外买入组合资金的 0.5%。",
            gfi=morning.gfi,
            rc=morning.rc,
            factors=morning.factors,
            triggered=True,
        )

    return AnalysisResult(
        mode="盘中",
        as_of=snapshot.as_of,
        action_code="HOLD",
        action_label="📊 条件不足",
        detail=f"已触发回调，但 GFI={morning.gfi:.1f} 或 RC={morning.rc:.2f} 不满足加仓条件。",
        gfi=morning.gfi,
        rc=morning.rc,
        factors=morning.factors,
        triggered=True,
    )


def render_morning_report(snapshot: MarketSnapshot, result: AnalysisResult) -> str:
    lines = _header_lines(result)
    lines.extend(_price_block(snapshot))
    if snapshot.data_notes:
        lines.append("")
        lines.append("🛰️  数据源说明")
        lines.append("─" * 62)
        for note in snapshot.data_notes:
            lines.append(f"  - {note}")
    lines.append("")
    lines.append("🧮  GFI")
    lines.append("─" * 62)
    lines.append(f"  当前值       : {result.gfi:.1f}" if result.gfi is not None else "  当前值       : N/A")
    lines.append(f"  风险贡献 RC  : {result.rc * 100:.1f}%")
    if result.missing_critical_fields:
        lines.append(f"  缺失关键字段 : {', '.join(result.missing_critical_fields)}")
    lines.append("")
    lines.append("📌  因子明细")
    lines.append("─" * 62)
    for factor in result.factors:
        score = "N/A" if factor.score is None else str(factor.score)
        weight = f"{factor.weight:.2f}"
        lines.append(f"  {factor.name:<12} 分数={score:<3} 权重={weight:<4} {factor.description}")
    lines.extend(_decision_block(result))
    return "\n".join(lines)


def render_intraday_report(snapshot: MarketSnapshot, result: AnalysisResult) -> str:
    lines = _header_lines(result)
    lines.append("🏷️  盘中监控")
    lines.append("─" * 62)
    lines.append(
        f"  黄金 24h 涨跌幅 : "
        f"{snapshot.gold_24h_change_pct:+.2f}%" if snapshot.gold_24h_change_pct is not None else "  黄金 24h 涨跌幅 : N/A"
    )
    lines.append(f"  是否触发阈值   : {'是' if result.triggered else '否'}")
    lines.append(f"  当前 GFI       : {result.gfi:.1f}" if result.gfi is not None else "  当前 GFI       : N/A")
    lines.append(f"  风险贡献 RC    : {result.rc * 100:.1f}%")
    if result.missing_critical_fields:
        lines.append(f"  缺失关键字段   : {', '.join(result.missing_critical_fields)}")
    if snapshot.data_notes:
        lines.append("  数据源说明     : " + "；".join(snapshot.data_notes))
    lines.extend(_decision_block(result))
    return "\n".join(lines)


def serialize_state(state: MonitorState) -> dict[str, object]:
    payload = asdict(state)
    if state.last_buy_at is not None:
        payload["last_buy_at"] = state.last_buy_at.isoformat()
    return payload


def _build_morning_factors(snapshot: MarketSnapshot) -> tuple[list[FactorResult], list[str]]:
    factors: list[FactorResult] = []
    missing: list[str] = []

    score, desc, available = _score_real_rate(snapshot.tips_10y)
    factors.append(FactorResult("真实利率", score, MANDATORY_FACTOR_WEIGHTS["真实利率"], desc, available))
    if not available:
        missing.append("tips_10y")

    score, desc, available = _score_core_cpi(snapshot.core_cpi_yoy)
    factors.append(FactorResult("核心CPI", score, MANDATORY_FACTOR_WEIGHTS["核心CPI"], desc, available))
    if not available:
        missing.append("core_cpi_yoy")

    score, desc, available = _score_dxy_momentum(snapshot.dxy_mom)
    factors.append(FactorResult("DXY动量", score, MANDATORY_FACTOR_WEIGHTS["DXY动量"], desc, available))
    if not available:
        missing.append("dxy_mom")

    score, desc, available = _score_vix(snapshot.vix)
    factors.append(FactorResult("VIX", score, MANDATORY_FACTOR_WEIGHTS["VIX"], desc, available))
    if not available:
        missing.append("vix")

    score, desc, available = _score_gold_trend(snapshot.gold_price, snapshot.gold_sma50, snapshot.gold_sma200)
    factors.append(FactorResult("黄金趋势", score, MANDATORY_FACTOR_WEIGHTS["黄金趋势"], desc, available))
    if not available:
        missing.append("gold_trend")

    score, desc, available = _score_etf_trend(snapshot.etf_price, snapshot.etf_sma20, snapshot.etf_sma60)
    factors.append(FactorResult("ETF趋势", score, MANDATORY_FACTOR_WEIGHTS["ETF趋势"], desc, available))
    if not available:
        missing.append("etf_trend")

    score, desc, available = _score_share_flow(snapshot.share_trend)
    factors.append(FactorResult("ETF资金趋势", score, OPTIONAL_FACTOR_WEIGHTS["ETF资金趋势"] if available else 0, desc, available))
    return factors, missing


def _action_from_score(gfi: float, rc: float) -> tuple[str, str, str]:
    if gfi < 20 and rc > 0.20:
        return "REDUCE", "🔴 减仓提示", "GFI 过低且风险贡献过高，建议降低黄金仓位。"
    if gfi < 30:
        return "STOP", "⚫ 暂停买入", "宏观和价格结构不利，停止新增仓位。"
    if gfi >= 70 and rc <= 0.15:
        return "STRONG_BUY", "🟢 强烈买入", "环境偏强，可按计划增加 1.5% 仓位。"
    if 50 <= gfi < 70 and rc <= 0.18:
        return "DCA", "🔵 逐步建仓", "条件允许，按定投节奏增加 0.5% 仓位。"
    return "HOLD", "🟡 持有 / 观望", "分数或风控约束未达标，维持现有仓位。"


def _score_real_rate(value: Optional[float]) -> tuple[Optional[int], str, bool]:
    if value is None:
        return None, "数据缺失", False
    if value < 0:
        return 100, f"{value:.2f}% 负实利率", True
    if value < 1:
        return 50, f"{value:.2f}% 低实利率", True
    return 0, f"{value:.2f}% 高实利率", True


def _score_core_cpi(value: Optional[float]) -> tuple[Optional[int], str, bool]:
    if value is None:
        return None, "数据缺失", False
    if value >= 4:
        return 100, f"{value:.2f}% 高通胀", True
    if value >= 2:
        return 50, f"{value:.2f}% 温和通胀", True
    return 0, f"{value:.2f}% 低通胀", True


def _score_dxy_momentum(value: Optional[float]) -> tuple[Optional[int], str, bool]:
    if value is None:
        return None, "数据缺失", False
    if value < -2:
        return 100, f"{value:+.2f}% 美元走弱", True
    if value <= 2:
        return 50, f"{value:+.2f}% 美元中性", True
    return 0, f"{value:+.2f}% 美元走强", True


def _score_vix(value: Optional[float]) -> tuple[Optional[int], str, bool]:
    if value is None:
        return None, "数据缺失", False
    if value >= 25:
        return 100, f"{value:.2f} 高波动", True
    if value >= 18:
        return 50, f"{value:.2f} 中等波动", True
    return 0, f"{value:.2f} 低波动", True


def _score_gold_trend(
    price: Optional[float],
    sma50: Optional[float],
    sma200: Optional[float],
) -> tuple[Optional[int], str, bool]:
    if None in (price, sma50, sma200):
        return None, "数据缺失", False
    if sma50 > sma200 and price > sma50:
        return 100, "黄金多头排列", True
    if price >= sma200:
        return 50, "黄金中性结构", True
    return 0, "黄金空头结构", True


def _score_etf_trend(
    price: Optional[float],
    sma20: Optional[float],
    sma60: Optional[float],
) -> tuple[Optional[int], str, bool]:
    if None in (price, sma20, sma60):
        return None, "数据缺失", False
    if sma20 > sma60 and price >= sma20:
        return 100, "518880 多头结构", True
    if price >= sma60:
        return 50, "518880 中性结构", True
    return 0, "518880 偏弱结构", True


def _score_share_flow(trend: Optional[str]) -> tuple[Optional[int], str, bool]:
    if trend is None:
        return None, "未配置资金流数据", False
    if trend == "连续增加":
        return 100, "连续两周净申购", True
    if trend == "连续减少":
        return 0, "连续两周净赎回", True
    return 50, "份额平稳", True


def _header_lines(result: AnalysisResult) -> list[str]:
    return [
        "=" * 62,
        f"  Antigravity 监控看板 | {result.as_of.strftime('%Y-%m-%d %H:%M:%S')}",
        f"  模式: {result.mode}",
        "=" * 62,
    ]


def _price_block(snapshot: MarketSnapshot) -> list[str]:
    return [
        "🏷️  资产价格",
        "─" * 62,
        f"  COMEX 黄金     : {'${:.2f}'.format(snapshot.gold_price) if snapshot.gold_price is not None else 'N/A'}",
        f"  上海金 Au99.99 : {'¥{:.2f}/g'.format(snapshot.shanghai_gold) if snapshot.shanghai_gold is not None else 'N/A'}",
        f"  华安黄金ETF    : {'¥{:.3f}'.format(snapshot.etf_price) if snapshot.etf_price is not None else 'N/A'}",
        f"  ETF SMA20/60   : "
        f"{'¥{:.3f}'.format(snapshot.etf_sma20) if snapshot.etf_sma20 is not None else 'N/A'} / "
        f"{'¥{:.3f}'.format(snapshot.etf_sma60) if snapshot.etf_sma60 is not None else 'N/A'}",
    ]


def _decision_block(result: AnalysisResult) -> list[str]:
    return [
        "",
        "💡  当前评级",
        "═" * 62,
        f"  当前评级  : {result.action_label}",
        f"  行动建议  : {result.detail}",
        "═" * 62,
    ]
