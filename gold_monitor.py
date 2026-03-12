#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import queue
import os
import sys
import threading
from datetime import datetime
from pathlib import Path

from monitor_core import (
    AnalysisResult,
    MarketSnapshot,
    MonitorConfig,
    MonitorState,
    analyze_intraday,
    analyze_morning,
    calculate_risk_contribution,
    render_intraday_report,
    render_morning_report,
)
from monitor_dashboard import (
    DashboardView,
    build_dashboard_view,
    build_report_history,
    filter_report_history,
    load_report_content,
)
from monitor_data import build_snapshot
from monitor_state import load_config, load_state, save_config, save_state


def prepare_tk_runtime() -> None:
    if os.environ.get("TCL_LIBRARY") and os.environ.get("TK_LIBRARY"):
        return

    candidates = []
    executable = Path(sys.executable).resolve()
    candidates.append(executable.parents[1])
    candidates.append(Path(sys.prefix))
    candidates.append(Path(sys.base_prefix))

    for root in candidates:
        tcl_dir = root / "lib" / "tcl8.6"
        tk_dir = root / "lib" / "tk8.6"
        if tcl_dir.joinpath("init.tcl").exists():
            os.environ.setdefault("TCL_LIBRARY", str(tcl_dir))
        if tk_dir.joinpath("tk.tcl").exists():
            os.environ.setdefault("TK_LIBRARY", str(tk_dir))
        if os.environ.get("TCL_LIBRARY") and os.environ.get("TK_LIBRARY"):
            return


prepare_tk_runtime()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "gui":
        return launch_gui(args.config, args.state, offline_demo=args.offline_demo, autorun=args.autorun or "")
    if args.command == "record-buy":
        when = datetime.fromisoformat(args.when) if args.when else datetime.now()
        record_buy(args.state, when)
        print(f"Recorded last buy at {when.isoformat()}")
        return 0
    if args.command == "morning":
        return run_mode("morning", args.config, args.state, args.offline_demo)
    if args.command == "intraday":
        return run_mode("intraday", args.config, args.state, args.offline_demo)

    parser.print_help()
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Antigravity 黄金 ETF 监控器")
    subparsers = parser.add_subparsers(dest="command")

    gui = subparsers.add_parser("gui", help="启动桌面界面")
    gui.add_argument("--config", default="config.json")
    gui.add_argument("--state", default="state.json")
    gui.add_argument("--offline-demo", action="store_true")
    gui.add_argument("--autorun", choices=("morning", "intraday"))

    morning = subparsers.add_parser("morning", help="执行盘前分析")
    morning.add_argument("--config", default="config.json")
    morning.add_argument("--state", default="state.json")
    morning.add_argument("--offline-demo", action="store_true")

    intraday = subparsers.add_parser("intraday", help="执行盘中监控")
    intraday.add_argument("--config", default="config.json")
    intraday.add_argument("--state", default="state.json")
    intraday.add_argument("--offline-demo", action="store_true")

    record = subparsers.add_parser("record-buy", help="记录最近一次买入时间")
    record.add_argument("--state", default="state.json")
    record.add_argument("--when", help="ISO 时间，例如 2026-03-12T10:30:00")

    return parser


def run_mode(mode: str, config_path: str, state_path: str, offline_demo: bool) -> int:
    _, _, snapshot, result, report, output = perform_analysis(mode, config_path, state_path, offline_demo)
    print(report)
    print(f"\nSaved report: {output}")
    return 0


def perform_analysis(
    mode: str,
    config_path: str,
    state_path: str,
    offline_demo: bool,
) -> tuple[MonitorConfig, MonitorState, MarketSnapshot, AnalysisResult, str, Path]:
    config = load_config(config_path)
    state = load_state(state_path)
    snapshot = build_snapshot(mode, offline_demo=offline_demo)

    if mode == "morning":
        result = analyze_morning(snapshot, config)
        report = render_morning_report(snapshot, result)
        output = save_report(report, snapshot.as_of, "盘前", result, config.reports_dir)
    else:
        result = analyze_intraday(snapshot, config, state)
        report = render_intraday_report(snapshot, result)
        output = save_report(report, snapshot.as_of, "盘中", result, config.reports_dir)

    return config, state, snapshot, result, report, output


def record_buy(state_path: str, when: datetime | None = None) -> MonitorState:
    state = load_state(state_path)
    state.last_buy_at = when or datetime.now()
    save_state(state, state_path)
    return state


def save_report(
    content: str,
    as_of: datetime,
    mode: str,
    result: AnalysisResult,
    reports_dir: str,
) -> Path:
    target_dir = Path(reports_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    suffix = "NA" if result.gfi is None else f"{int(result.gfi):02d}"
    filename = f"{as_of.strftime('%Y%m%d_%H%M')}_{mode}_{result.action_code}_GFI{suffix}.txt"
    path = target_dir / filename
    path.write_text(content, encoding="utf-8")
    return path


class MonitorGUI:
    COLORS = {
        "bg": "#07111F",
        "panel": "#0E1B2D",
        "panel_alt": "#13243A",
        "panel_soft": "#182C44",
        "text": "#F4F7FB",
        "muted": "#9DB0C6",
        "gold": "#F5C451",
        "gold_soft": "#6B551E",
        "bull": "#3ECF8E",
        "bull_soft": "#173A2C",
        "watch": "#F2B94B",
        "watch_soft": "#4C3A17",
        "blocked": "#FF7E79",
        "blocked_soft": "#4A1D1A",
        "neutral": "#7AB6FF",
        "neutral_soft": "#17314D",
        "line": "#20344C",
        "input": "#091521",
    }

    def __init__(self, root, config_path: str, state_path: str, offline_demo: bool = False, autorun: str = ""):
        self.root = root
        self.config_path = config_path
        self.state_path = state_path
        self.offline_demo = offline_demo
        self.autorun = autorun
        self.config = load_config(config_path)
        self.state = load_state(state_path)
        self.snapshot = MarketSnapshot(as_of=datetime.now())
        self.result = self._idle_result()
        self.latest_report = "点击上方按钮开始分析。"
        self.latest_report_path: Path | None = None
        self.selected_report_path: str | None = None
        self.report_filter = "全部"
        self.events: queue.Queue[dict[str, object]] = queue.Queue()
        self.factor_frames = []
        self.status_pill_frames = []
        self.history_frames = []
        self.report_filter_buttons = {}

        self.root.title("Antigravity 黄金 ETF 操作台")
        self.root.geometry("1460x980")
        self.root.minsize(1280, 820)
        self.root.configure(bg=self.COLORS["bg"])

        self._build_ui()
        self._load_config_form()
        self._render_dashboard()
        if self.autorun:
            self.root.after(250, lambda: self._start_task(self.autorun))
        self.root.after(120, self._drain_events)

    def _build_ui(self):
        import tkinter as tk

        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, weight=1)

        header = tk.Frame(self.root, bg=self.COLORS["bg"], padx=28, pady=24)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        tk.Label(
            header,
            text="Antigravity 黄金 ETF 操作台",
            font=("Avenir Next", 26, "bold"),
            fg=self.COLORS["text"],
            bg=self.COLORS["bg"],
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            header,
            text="先看结论，再看风控，再执行操作",
            font=("Avenir Next", 12),
            fg=self.COLORS["muted"],
            bg=self.COLORS["bg"],
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        self.demo_var = tk.StringVar(
            value="演示模式：当前不是实时行情，GFI 与报告内容均为示例数据"
            if self.offline_demo
            else "实时模式：将尝试抓取最新行情，若关键数据缺失则不提供交易建议"
        )

        self.clock_var = tk.StringVar(value=datetime.now().strftime("%Y-%m-%d %H:%M"))
        self.status_var = tk.StringVar(value="准备就绪")
        self.latest_analysis_var = tk.StringVar(value="最近分析: 尚未运行")
        self.banner_var = tk.StringVar(value="")
        self.action_lock_var = tk.StringVar(value="")
        self.report_path_var = tk.StringVar(value="暂无报告")

        header_side = tk.Frame(header, bg=self.COLORS["panel"], padx=14, pady=12)
        header_side.grid(row=0, column=1, rowspan=2, sticky="e")
        tk.Label(
            header_side,
            text="系统状态",
            font=("Avenir Next", 10, "bold"),
            fg=self.COLORS["gold"],
            bg=self.COLORS["panel"],
        ).pack(anchor="w")
        tk.Label(
            header_side,
            textvariable=self.status_var,
            font=("Avenir Next", 12, "bold"),
            fg=self.COLORS["text"],
            bg=self.COLORS["panel"],
        ).pack(anchor="w", pady=(4, 2))
        tk.Label(
            header_side,
            textvariable=self.clock_var,
            font=("Avenir Next", 10),
            fg=self.COLORS["muted"],
            bg=self.COLORS["panel"],
        ).pack(anchor="w")
        tk.Label(
            header_side,
            textvariable=self.latest_analysis_var,
            font=("Avenir Next", 10),
            fg=self.COLORS["muted"],
            bg=self.COLORS["panel"],
        ).pack(anchor="w", pady=(8, 0))

        if self.offline_demo:
            self.demo_notice_label = tk.Label(
                header,
                textvariable=self.demo_var,
                font=("Avenir Next", 11, "bold"),
                fg=self.COLORS["watch"],
                bg=self.COLORS["watch_soft"],
                padx=14,
                pady=10,
                justify="left",
                anchor="w",
            )
            self.demo_notice_label.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(16, 0))
        else:
            self.demo_notice_label = tk.Label(
                header,
                textvariable=self.demo_var,
                font=("Avenir Next", 10),
                fg=self.COLORS["muted"],
                bg=self.COLORS["bg"],
                justify="left",
                anchor="w",
            )
            self.demo_notice_label.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))

        main = tk.Frame(self.root, bg=self.COLORS["bg"], padx=24, pady=8)
        main.grid(row=1, column=0, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)

        summary = tk.Frame(main, bg=self.COLORS["bg"])
        summary.grid(row=0, column=0, sticky="ew")
        summary.grid_columnconfigure(0, weight=4)
        summary.grid_columnconfigure(1, weight=5)
        summary.grid_columnconfigure(2, weight=4)

        self.gauge_card = self._make_card(summary, row=0, column=0, title="今日 GFI")
        self.decision_card = self._make_card(summary, row=0, column=1, title="今日结论")
        self.state_card = self._make_card(summary, row=0, column=2, title="状态与风控")

        self.gauge_canvas = tk.Canvas(
            self.gauge_card,
            width=280,
            height=200,
            bg=self.COLORS["panel"],
            highlightthickness=0,
        )
        self.gauge_canvas.pack(padx=8, pady=(8, 2))
        self.gauge_score_var = tk.StringVar(value="N/A")
        self.gauge_label_var = tk.StringVar(value="等待分析")
        tk.Label(
            self.gauge_card,
            textvariable=self.gauge_score_var,
            font=("Avenir Next", 28, "bold"),
            fg=self.COLORS["text"],
            bg=self.COLORS["panel"],
        ).pack()
        tk.Label(
            self.gauge_card,
            textvariable=self.gauge_label_var,
            font=("Avenir Next", 11),
            fg=self.COLORS["muted"],
            bg=self.COLORS["panel"],
        ).pack(pady=(0, 10))

        self.badge_var = tk.StringVar(value="待运行")
        self.decision_title_var = tk.StringVar(value="等待分析")
        self.decision_detail_var = tk.StringVar(value="点击盘前分析或盘中监控开始。")
        self.banner_title_var = tk.StringVar(value="")
        self.decision_badge = tk.Label(
            self.decision_card,
            textvariable=self.badge_var,
            font=("Avenir Next", 10, "bold"),
            fg=self.COLORS["gold"],
            bg=self.COLORS["gold_soft"],
            padx=12,
            pady=4,
        )
        self.decision_badge.pack(anchor="w", padx=14, pady=(8, 10))
        tk.Label(
            self.decision_card,
            textvariable=self.decision_title_var,
            font=("Avenir Next", 24, "bold"),
            fg=self.COLORS["text"],
            bg=self.COLORS["panel"],
            wraplength=360,
            justify="left",
        ).pack(anchor="w", padx=14)
        tk.Label(
            self.decision_card,
            textvariable=self.decision_detail_var,
            font=("Avenir Next", 12),
            fg=self.COLORS["muted"],
            bg=self.COLORS["panel"],
            wraplength=390,
            justify="left",
        ).pack(anchor="w", padx=14, pady=(10, 12))
        self.status_pill_container = tk.Frame(self.decision_card, bg=self.COLORS["panel"])
        self.status_pill_container.pack(fill="x", padx=14, pady=(0, 12))
        self.action_lock_box = tk.Frame(self.decision_card, bg=self.COLORS["panel"])
        self.action_lock_box.pack(fill="x", padx=14, pady=(0, 10))
        self.action_lock_label = tk.Label(
            self.action_lock_box,
            textvariable=self.action_lock_var,
            font=("Avenir Next", 11, "bold"),
            fg=self.COLORS["blocked"],
            bg=self.COLORS["blocked_soft"],
            wraplength=380,
            justify="left",
            padx=12,
            pady=10,
        )
        self.action_lock_label.pack(fill="x")
        self.banner_box = tk.Frame(self.decision_card, bg=self.COLORS["panel"])
        self.banner_box.pack(fill="x", padx=14, pady=(0, 10))
        self.banner_title_label = tk.Label(
            self.banner_box,
            textvariable=self.banner_title_var,
            font=("Avenir Next", 11, "bold"),
            fg=self.COLORS["text"],
            bg=self.COLORS["blocked_soft"],
            padx=10,
            pady=6,
        )
        self.banner_title_label.pack(fill="x")
        self.banner_message_label = tk.Label(
            self.banner_box,
            textvariable=self.banner_var,
            font=("Avenir Next", 10),
            fg=self.COLORS["text"],
            bg=self.COLORS["blocked_soft"],
            wraplength=380,
            justify="left",
            padx=10,
            pady=8,
        )
        self.banner_message_label.pack(fill="x")

        self.state_grid = tk.Frame(self.state_card, bg=self.COLORS["panel"])
        self.state_grid.pack(fill="both", expand=True, padx=14, pady=10)
        self.state_metric_vars = {}
        for row, label in enumerate(("RC 风险", "黄金仓位", "上次买入", "冷却状态")):
            tk.Label(
                self.state_grid,
                text=label,
                font=("Avenir Next", 10, "bold"),
                fg=self.COLORS["muted"],
                bg=self.COLORS["panel"],
            ).grid(row=row * 2, column=0, sticky="w")
            value_var = tk.StringVar(value="--")
            tk.Label(
                self.state_grid,
                textvariable=value_var,
                font=("Avenir Next", 16, "bold"),
                fg=self.COLORS["text"],
                bg=self.COLORS["panel"],
            ).grid(row=row * 2 + 1, column=0, sticky="w", pady=(2, 10))
            self.state_metric_vars[label] = value_var

        content = tk.Frame(main, bg=self.COLORS["bg"])
        content.grid(row=1, column=0, sticky="nsew")
        content.grid_columnconfigure(0, weight=7)
        content.grid_columnconfigure(1, weight=4)
        content.grid_rowconfigure(0, weight=1)

        left_column = tk.Frame(content, bg=self.COLORS["bg"])
        left_column.grid(row=0, column=0, sticky="nsew")
        left_column.grid_columnconfigure(0, weight=1)
        left_column.grid_rowconfigure(0, weight=0)
        left_column.grid_rowconfigure(1, weight=1, minsize=300)

        action_panel = self._make_card(left_column, row=0, column=0, title="一键操作", columnspan=1)
        action_body = tk.Frame(action_panel, bg=self.COLORS["panel"])
        action_body.pack(fill="x", padx=14, pady=(8, 14))
        action_body.grid_columnconfigure(0, weight=1)
        action_body.grid_columnconfigure(1, weight=1)
        action_body.grid_columnconfigure(2, weight=1)
        action_body.grid_columnconfigure(3, weight=1)

        self.btn_morning = self._make_action_button(
            action_body,
            text="开始盘前分析",
            subtext="立即更新今天的建仓判断",
            bg=self.COLORS["gold"],
            fg="#1D1405",
            badge="点击运行",
            command=lambda: self._start_task("morning"),
        )
        self.btn_morning.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.btn_intraday = self._make_action_button(
            action_body,
            text="开始盘中监控",
            subtext="立即检查回调加仓窗口",
            bg=self.COLORS["neutral"],
            fg="#081018",
            badge="点击运行",
            command=lambda: self._start_task("intraday"),
        )
        self.btn_intraday.grid(row=0, column=1, sticky="ew", padx=8)
        self.btn_record_buy = self._make_action_button(
            action_body,
            text="记录今天已买入",
            subtext="写入状态并更新冷却期",
            bg=self.COLORS["bull"],
            fg="#07140E",
            badge="点击记录",
            command=self._record_buy,
        )
        self.btn_record_buy.grid(row=0, column=2, sticky="ew", padx=8)
        self.quick_hint_var = tk.StringVar(value="系统建议：先执行盘前分析")
        tk.Label(
            action_body,
            textvariable=self.quick_hint_var,
            font=("Avenir Next", 11),
            fg=self.COLORS["muted"],
            bg=self.COLORS["panel"],
            justify="left",
        ).grid(row=0, column=3, sticky="nsew", padx=(12, 0))
        tk.Label(
            action_body,
            text="演示数据" if self.offline_demo else "实时抓取",
            font=("Avenir Next", 10, "bold"),
            fg=self.COLORS["gold"] if self.offline_demo else self.COLORS["muted"],
            bg=self.COLORS["panel"],
            justify="left",
        ).grid(row=1, column=3, sticky="sw", padx=(12, 0), pady=(12, 0))

        report_panel = self._make_card(left_column, row=1, column=0, title="报告预览", pady=12)
        self.report_meta = tk.Label(
            report_panel,
            textvariable=self.report_path_var,
            font=("Avenir Next", 10),
            fg=self.COLORS["muted"],
            bg=self.COLORS["panel"],
            anchor="w",
        )
        self.report_meta.pack(fill="x", padx=14, pady=(0, 8))
        report_body = tk.Frame(report_panel, bg=self.COLORS["panel"])
        report_body.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        report_body.grid_rowconfigure(0, weight=1)
        report_body.grid_columnconfigure(0, weight=1)
        self.report_preview = tk.Text(
            report_body,
            font=("Menlo", 10),
            bg=self.COLORS["input"],
            fg=self.COLORS["text"],
            insertbackground=self.COLORS["text"],
            relief="flat",
            padx=12,
            pady=12,
            wrap="none",
        )
        self.report_preview.grid(row=0, column=0, sticky="nsew")
        self.report_vscroll = tk.Scrollbar(report_body, orient="vertical", command=self.report_preview.yview)
        self.report_vscroll.grid(row=0, column=1, sticky="ns")
        self.report_hscroll = tk.Scrollbar(report_body, orient="horizontal", command=self.report_preview.xview)
        self.report_hscroll.grid(row=1, column=0, sticky="ew")
        self.report_preview.configure(
            yscrollcommand=self.report_vscroll.set,
            xscrollcommand=self.report_hscroll.set,
        )
        self.report_preview.configure(state="disabled")

        sidebar = tk.Frame(content, bg=self.COLORS["bg"])
        sidebar.grid(row=0, column=1, sticky="nsew", padx=(18, 0))
        sidebar.grid_rowconfigure(2, weight=1)

        settings_panel = self._make_card(sidebar, row=0, column=0, title="参数设置")
        settings_body = tk.Frame(settings_panel, bg=self.COLORS["panel"])
        settings_body.pack(fill="x", padx=14, pady=(8, 14))
        settings_body.grid_columnconfigure(1, weight=1)
        self.config_vars = {
            "portfolio_gold_weight": tk.StringVar(),
            "gold_volatility": tk.StringVar(),
            "portfolio_volatility": tk.StringVar(),
            "min_add_cooldown_days": tk.StringVar(),
            "reports_dir": tk.StringVar(),
        }
        fields = [
            ("黄金仓位", "portfolio_gold_weight"),
            ("黄金波动率", "gold_volatility"),
            ("组合波动率", "portfolio_volatility"),
            ("冷却天数", "min_add_cooldown_days"),
            ("报告目录", "reports_dir"),
        ]
        for row, (label, key) in enumerate(fields):
            tk.Label(
                settings_body,
                text=label,
                font=("Avenir Next", 10, "bold"),
                fg=self.COLORS["muted"],
                bg=self.COLORS["panel"],
            ).grid(row=row, column=0, sticky="w", padx=14, pady=8)
            entry = tk.Entry(
                settings_body,
                textvariable=self.config_vars[key],
                font=("Avenir Next", 11),
                fg=self.COLORS["text"],
                bg=self.COLORS["input"],
                insertbackground=self.COLORS["text"],
                relief="flat",
                highlightthickness=1,
                highlightbackground=self.COLORS["line"],
                highlightcolor=self.COLORS["gold"],
            )
            entry.grid(row=row, column=1, sticky="ew", padx=(10, 14), pady=8, ipady=6)

        self.btn_save_settings = tk.Button(
            settings_body,
            text="保存设置",
            command=self._save_settings,
            font=("Avenir Next", 11, "bold"),
            bg=self.COLORS["panel_alt"],
            fg=self.COLORS["text"],
            activebackground=self.COLORS["panel_soft"],
            activeforeground=self.COLORS["text"],
            relief="flat",
            padx=14,
            pady=10,
            cursor="hand2",
        )
        self.btn_save_settings.grid(row=len(fields), column=0, columnspan=2, sticky="ew", padx=14, pady=(12, 14))

        history_panel = self._make_card(sidebar, row=1, column=0, title="最近报告", pady=12)
        history_panel.grid_columnconfigure(0, weight=1)
        filter_bar = tk.Frame(history_panel, bg=self.COLORS["panel"])
        filter_bar.pack(fill="x", padx=14, pady=(4, 8))
        for mode in ("全部", "盘前", "盘中"):
            btn = tk.Button(
                filter_bar,
                text=mode,
                command=lambda selected=mode: self._set_report_filter(selected),
                font=("Avenir Next", 10, "bold"),
                bg=self.COLORS["panel_alt"],
                fg=self.COLORS["muted"],
                relief="flat",
                activebackground=self.COLORS["panel_soft"],
                activeforeground=self.COLORS["text"],
                padx=12,
                pady=6,
                cursor="hand2",
            )
            btn.pack(side="left", padx=(0, 8))
            self.report_filter_buttons[mode] = btn
        self.history_container = tk.Frame(history_panel, bg=self.COLORS["panel"])
        self.history_container.pack(fill="both", expand=True, padx=14, pady=(4, 14))

        factor_panel = self._make_card(sidebar, row=2, column=0, title="原因拆解", pady=12)
        factor_body = tk.Frame(factor_panel, bg=self.COLORS["panel"])
        factor_body.pack(fill="both", expand=True, padx=14, pady=(4, 14))
        factor_body.grid_rowconfigure(0, weight=1)
        factor_body.grid_columnconfigure(0, weight=1)
        self.factor_canvas = tk.Canvas(
            factor_body,
            bg=self.COLORS["panel"],
            highlightthickness=0,
        )
        self.factor_scrollbar = tk.Scrollbar(factor_body, orient="vertical", command=self.factor_canvas.yview)
        self.factor_container = tk.Frame(self.factor_canvas, bg=self.COLORS["panel"])
        self.factor_container.bind(
            "<Configure>",
            lambda event: self.factor_canvas.configure(scrollregion=self.factor_canvas.bbox("all")),
        )
        self.factor_canvas.create_window((0, 0), window=self.factor_container, anchor="nw")
        self.factor_canvas.configure(yscrollcommand=self.factor_scrollbar.set)
        self.factor_canvas.grid(row=0, column=0, sticky="nsew")
        self.factor_scrollbar.grid(row=0, column=1, sticky="ns", padx=(8, 0))

        self.root.after(1000, self._tick_clock)

    def _make_card(self, parent, row: int, column: int, title: str, columnspan: int = 1, pady: int = 10):
        import tkinter as tk

        card = tk.Frame(parent, bg=self.COLORS["panel"], highlightthickness=1, highlightbackground=self.COLORS["line"])
        card.grid(row=row, column=column, sticky="nsew", padx=8, pady=pady, columnspan=columnspan)
        card.grid_columnconfigure(0, weight=1)
        tk.Label(
            card,
            text=title,
            font=("Avenir Next", 12, "bold"),
            fg=self.COLORS["gold"],
            bg=self.COLORS["panel"],
        ).pack(anchor="w", padx=14, pady=(14, 2))
        return card

    def _make_action_button(self, parent, text: str, subtext: str, bg: str, fg: str, badge: str, command):
        import tkinter as tk

        wrapper = tk.Frame(
            parent,
            bg=bg,
            cursor="hand2",
            highlightthickness=2,
            highlightbackground=self.COLORS["line"],
            bd=0,
        )
        wrapper.grid_rowconfigure(1, weight=1)
        wrapper.grid_columnconfigure(0, weight=1)
        wrapper.default_bg = bg  # type: ignore[attr-defined]
        wrapper.hover_bg = self._blend_color(bg, self.COLORS["text"], 0.16)  # type: ignore[attr-defined]
        wrapper.pressed_bg = self._blend_color(bg, self.COLORS["bg"], 0.15)  # type: ignore[attr-defined]
        wrapper.disabled_bg = self._blend_color(bg, self.COLORS["bg"], 0.42)  # type: ignore[attr-defined]
        button = tk.Button(
            wrapper,
            text=text,
            command=command,
            font=("Avenir Next", 16, "bold"),
            bg=bg,
            fg=fg,
            relief="flat",
            activebackground=bg,
            activeforeground=fg,
            cursor="hand2",
            padx=14,
            pady=16,
            bd=0,
            highlightthickness=0,
        )
        button.grid(row=1, column=0, sticky="ew", padx=14, pady=(4, 0))
        badge_label = tk.Label(
            wrapper,
            text=badge,
            font=("Avenir Next", 9, "bold"),
            fg=fg,
            bg=bg,
            padx=10,
            pady=5,
            anchor="e",
        )
        badge_label.grid(row=0, column=0, sticky="ne", padx=12, pady=(12, 0))
        label = tk.Label(
            wrapper,
            text=subtext,
            font=("Avenir Next", 10),
            fg=fg,
            bg=bg,
            padx=14,
            pady=0,
            justify="left",
        )
        label.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 14))

        def set_surface(surface_bg: str):
            wrapper.configure(bg=surface_bg)
            button.configure(bg=surface_bg, activebackground=surface_bg)
            label.configure(bg=surface_bg)
            badge_label.configure(bg=surface_bg)

        def is_enabled() -> bool:
            return str(button.cget("state")) != str(tk.DISABLED)

        def invoke(_event=None):
            if is_enabled():
                button.invoke()

        def on_enter(_event=None):
            if is_enabled():
                wrapper.configure(highlightbackground=self.COLORS["text"])
                set_surface(wrapper.hover_bg)  # type: ignore[attr-defined]

        def on_leave(_event=None):
            wrapper.configure(highlightbackground=self.COLORS["line"] if is_enabled() else self.COLORS["panel_soft"])
            set_surface(wrapper.default_bg if is_enabled() else wrapper.disabled_bg)  # type: ignore[attr-defined]

        def on_press(_event=None):
            if is_enabled():
                set_surface(wrapper.pressed_bg)  # type: ignore[attr-defined]

        def on_release(_event=None):
            if is_enabled():
                set_surface(wrapper.hover_bg)  # type: ignore[attr-defined]

        for widget in (wrapper, label, badge_label):
            widget.bind("<Button-1>", invoke)
            widget.bind("<Enter>", on_enter)
            widget.bind("<Leave>", on_leave)
            widget.bind("<ButtonPress-1>", on_press)
            widget.bind("<ButtonRelease-1>", on_release)

        set_surface(bg)
        wrapper._button = button  # type: ignore[attr-defined]
        wrapper._label = label  # type: ignore[attr-defined]
        wrapper._badge = badge_label  # type: ignore[attr-defined]
        return wrapper

    def _tick_clock(self):
        self.clock_var.set(datetime.now().strftime("%Y-%m-%d %H:%M"))
        self.root.after(1000, self._tick_clock)

    def _idle_result(self) -> AnalysisResult:
        return AnalysisResult(
            mode="待运行",
            as_of=datetime.now(),
            action_code="IDLE",
            action_label="等待分析",
            detail="点击“盘前分析”或“盘中监控”开始。",
            gfi=None,
            rc=calculate_risk_contribution(self.config),
        )

    def _load_config_form(self):
        self.config_vars["portfolio_gold_weight"].set(str(self.config.portfolio_gold_weight))
        self.config_vars["gold_volatility"].set(str(self.config.gold_volatility))
        self.config_vars["portfolio_volatility"].set(str(self.config.portfolio_volatility))
        self.config_vars["min_add_cooldown_days"].set(str(self.config.min_add_cooldown_days))
        self.config_vars["reports_dir"].set(self.config.reports_dir)

    def _render_dashboard(self):
        report_history = build_report_history(self.config.reports_dir)
        filtered_history = filter_report_history(report_history, self.report_filter)
        view = build_dashboard_view(self.snapshot, self.result, self.config, self.state, report_history=filtered_history)
        self._apply_view(view)
        if self.selected_report_path:
            self._set_report_preview(load_report_content(self.selected_report_path), source_path=self.selected_report_path)
        else:
            self._set_report_preview(self.latest_report, source_path=str(self.latest_report_path) if self.latest_report_path else None)

    def _apply_view(self, view: DashboardView):
        palette = self._tone_palette(view.gauge.tone)
        self.gauge_score_var.set(view.gauge.score_text)
        self.gauge_label_var.set(view.gauge.label)
        self._draw_gauge(view)

        self.decision_title_var.set(view.decision.title)
        self.decision_detail_var.set(view.decision.subtitle)
        self.badge_var.set(view.decision.badge)
        self.latest_analysis_var.set(f"最近分析: {view.analysis_time_text}")
        self.decision_badge.configure(bg=palette["soft"], fg=palette["strong"])
        if view.action_block_reason:
            self.action_lock_var.set(view.action_block_reason)
            self.action_lock_label.configure(bg=self.COLORS["blocked_soft"], fg=self.COLORS["blocked"])
            if not self.action_lock_box.winfo_ismapped():
                self.action_lock_box.pack(fill="x", padx=14, pady=(0, 10))
        else:
            self.action_lock_box.pack_forget()

        state_values = {
            "RC 风险": view.state.rc_text,
            "黄金仓位": view.state.weight_text,
            "上次买入": view.state.last_buy_text,
            "冷却状态": view.state.cooldown_text,
        }
        for label, value in state_values.items():
            self.state_metric_vars[label].set(value)

        if view.banner is None:
            self.banner_box.pack_forget()
        else:
            banner_palette = self._tone_palette(view.banner.tone)
            self.banner_title_var.set(view.banner.title)
            self.banner_var.set(view.banner.message)
            self.banner_title_label.configure(bg=banner_palette["soft"], fg=banner_palette["strong"])
            self.banner_message_label.configure(bg=banner_palette["soft"], fg=self.COLORS["text"])
            if not self.banner_box.winfo_ismapped():
                self.banner_box.pack(fill="x", padx=14, pady=(0, 10))

        self.quick_hint_var.set(self._quick_hint(view))
        self._render_report_filters()
        self._render_status_pills(view)
        self._render_report_history(view)
        self._render_factors(view)

    def _draw_gauge(self, view: DashboardView):
        canvas = self.gauge_canvas
        canvas.delete("all")
        palette = self._tone_palette(view.gauge.tone)

        x1, y1, x2, y2 = 35, 24, 245, 234
        canvas.create_arc(x1, y1, x2, y2, start=210, extent=120, style="arc", outline=self.COLORS["line"], width=18)
        canvas.create_arc(
            x1,
            y1,
            x2,
            y2,
            start=210,
            extent=120 * view.gauge.progress,
            style="arc",
            outline=palette["strong"],
            width=18,
        )
        canvas.create_text(140, 92, text="GFI", fill=self.COLORS["muted"], font=("Avenir Next", 12, "bold"))
        canvas.create_text(140, 128, text=view.gauge.score_text, fill=self.COLORS["text"], font=("Avenir Next", 32, "bold"))
        canvas.create_text(140, 164, text=view.gauge.label, fill=palette["strong"], font=("Avenir Next", 12, "bold"))
        canvas.create_text(42, 188, text="0", fill=self.COLORS["muted"], font=("Avenir Next", 10))
        canvas.create_text(140, 208, text="50", fill=self.COLORS["muted"], font=("Avenir Next", 10))
        canvas.create_text(237, 188, text="100", fill=self.COLORS["muted"], font=("Avenir Next", 10))

    def _render_factors(self, view: DashboardView):
        import tkinter as tk

        for frame in self.factor_frames:
            frame.destroy()
        self.factor_frames.clear()

        for index, factor in enumerate(view.factors):
            palette = self._tone_palette(factor.tone)
            card = tk.Frame(
                self.factor_container,
                bg=palette["soft"],
                highlightthickness=1,
                highlightbackground=self.COLORS["line"],
                padx=12,
                pady=12,
            )
            row = index // 2
            column = index % 2
            card.grid(row=row, column=column, sticky="nsew", padx=8, pady=8)
            self.factor_container.grid_columnconfigure(column, weight=1)
            tk.Label(
                card,
                text=factor.title,
                font=("Avenir Next", 11, "bold"),
                fg=palette["strong"],
                bg=palette["soft"],
            ).pack(anchor="w")
            tk.Label(
                card,
                text=f"分数 {factor.score_text}",
                font=("Avenir Next", 16, "bold"),
                fg=self.COLORS["text"],
                bg=palette["soft"],
            ).pack(anchor="w", pady=(6, 4))
            tk.Label(
                card,
                text=factor.detail,
                font=("Avenir Next", 10),
                fg=self.COLORS["text"],
                bg=palette["soft"],
                wraplength=180,
                justify="left",
            ).pack(anchor="w")
            self.factor_frames.append(card)

    def _render_status_pills(self, view: DashboardView):
        import tkinter as tk

        for frame in self.status_pill_frames:
            frame.destroy()
        self.status_pill_frames.clear()

        for pill in view.status_pills:
            palette = self._tone_palette(pill.tone)
            frame = tk.Frame(
                self.status_pill_container,
                bg=palette["soft"],
                highlightthickness=1,
                highlightbackground=self.COLORS["line"],
                padx=10,
                pady=8,
            )
            frame.pack(side="left", padx=(0, 8))
            tk.Label(
                frame,
                text=pill.label,
                font=("Avenir Next", 9, "bold"),
                fg=self.COLORS["muted"],
                bg=palette["soft"],
            ).pack(anchor="w")
            tk.Label(
                frame,
                text=pill.value,
                font=("Avenir Next", 12, "bold"),
                fg=palette["strong"],
                bg=palette["soft"],
            ).pack(anchor="w", pady=(2, 0))
            self.status_pill_frames.append(frame)

    def _render_report_filters(self):
        for mode, button in self.report_filter_buttons.items():
            selected = mode == self.report_filter
            button.configure(
                bg=self.COLORS["gold_soft"] if selected else self.COLORS["panel_alt"],
                fg=self.COLORS["gold"] if selected else self.COLORS["muted"],
            )

    def _render_report_history(self, view: DashboardView):
        import tkinter as tk

        for frame in self.history_frames:
            frame.destroy()
        self.history_frames.clear()

        if not view.report_history:
            empty = tk.Label(
                self.history_container,
                text="还没有历史报告。运行一次盘前分析或盘中监控后，这里会显示最近记录。",
                font=("Avenir Next", 10),
                fg=self.COLORS["muted"],
                bg=self.COLORS["panel"],
                wraplength=280,
                justify="left",
            )
            empty.pack(anchor="w")
            self.history_frames.append(empty)
            return

        for item in view.report_history:
            palette = self._tone_palette(item.tone)
            row = tk.Frame(
                self.history_container,
                bg=self.COLORS["panel_soft"] if self.selected_report_path == item.path else self.COLORS["panel_alt"],
                highlightthickness=1,
                highlightbackground=self.COLORS["gold"] if self.selected_report_path == item.path else self.COLORS["line"],
                padx=10,
                pady=10,
                cursor="hand2",
            )
            row.pack(fill="x", pady=(0, 8))
            title = tk.Label(
                row,
                text=item.title,
                font=("Avenir Next", 11, "bold"),
                fg=palette["strong"],
                bg=row.cget("bg"),
                cursor="hand2",
            )
            title.pack(anchor="w")
            subtitle = tk.Label(
                row,
                text=item.subtitle,
                font=("Avenir Next", 10),
                fg=self.COLORS["muted"],
                bg=row.cget("bg"),
                cursor="hand2",
            )
            subtitle.pack(anchor="w", pady=(4, 0))
            for widget in (row, title, subtitle):
                widget.bind("<Button-1>", lambda _event, path=item.path: self._select_report_history(path))
            self.history_frames.append(row)

    def _select_report_history(self, report_path: str):
        self.selected_report_path = report_path
        self._set_report_preview(load_report_content(report_path), source_path=report_path)
        self._render_dashboard()

    def _set_report_filter(self, mode: str):
        self.report_filter = mode
        if self.selected_report_path:
            if mode != "全部" and f"_{mode}_" not in Path(self.selected_report_path).name:
                self.selected_report_path = None
        self._render_dashboard()

    def _set_report_preview(self, text: str, source_path: str | None = None):
        self.report_preview.configure(state="normal")
        self.report_preview.delete("1.0", "end")
        self.report_preview.insert("1.0", text)
        self.report_preview.configure(state="disabled")
        self.report_path_var.set(source_path or "暂无报告")

    def _quick_hint(self, view: DashboardView) -> str:
        if view.banner is not None:
            return "关键数据缺失，今天不要依据系统做交易决策。"
        if not view.quick_action_enabled:
            return "当前处于限制状态，先处理冷却期或等待数据恢复。"
        return f"当前建议：{view.decision.title}。如已执行，请点击“记录今天买入”。"

    def _tone_palette(self, tone: str) -> dict[str, str]:
        if tone == "bull":
            return {"strong": self.COLORS["bull"], "soft": self.COLORS["bull_soft"]}
        if tone == "watch":
            return {"strong": self.COLORS["watch"], "soft": self.COLORS["watch_soft"]}
        if tone == "blocked":
            return {"strong": self.COLORS["blocked"], "soft": self.COLORS["blocked_soft"]}
        return {"strong": self.COLORS["neutral"], "soft": self.COLORS["neutral_soft"]}

    def _blend_color(self, left: str, right: str, alpha: float) -> str:
        left_rgb = left.lstrip("#")
        right_rgb = right.lstrip("#")
        mixed = []
        for index in range(0, 6, 2):
            left_value = int(left_rgb[index:index + 2], 16)
            right_value = int(right_rgb[index:index + 2], 16)
            value = round(left_value * (1 - alpha) + right_value * alpha)
            mixed.append(f"{value:02X}")
        return f"#{''.join(mixed)}"

    def _start_task(self, mode: str):
        self._set_running(True, f"{'盘前分析' if mode == 'morning' else '盘中监控'}进行中")
        threading.Thread(target=self._run_task, args=(mode,), daemon=True).start()

    def _run_task(self, mode: str):
        try:
            config, state, snapshot, result, report, path = perform_analysis(
                mode,
                self.config_path,
                self.state_path,
                offline_demo=self.offline_demo,
            )
            self.events.put(
                {
                    "kind": "analysis",
                    "config": config,
                    "state": state,
                    "snapshot": snapshot,
                    "result": result,
                    "report": report,
                    "path": path,
                    "status": "分析完成",
                }
            )
        except Exception as exc:
            self.events.put({"kind": "error", "message": str(exc)})

    def _record_buy(self):
        self.state = record_buy(self.state_path)
        self.status_var.set("已记录最近一次买入")
        self.latest_report = f"最近一次买入已记录：{self.state.last_buy_at.strftime('%Y-%m-%d %H:%M:%S')}"
        self.selected_report_path = None
        self._render_dashboard()

    def _save_settings(self):
        try:
            self.config = MonitorConfig(
                portfolio_gold_weight=float(self.config_vars["portfolio_gold_weight"].get()),
                gold_volatility=float(self.config_vars["gold_volatility"].get()),
                portfolio_volatility=float(self.config_vars["portfolio_volatility"].get()),
                min_add_cooldown_days=int(self.config_vars["min_add_cooldown_days"].get()),
                reports_dir=self.config_vars["reports_dir"].get().strip() or "reports",
            )
        except ValueError:
            self.status_var.set("设置保存失败：请检查数字格式")
            return

        save_config(self.config, self.config_path)
        self.result.rc = calculate_risk_contribution(self.config)
        self.status_var.set("设置已保存")
        self._render_dashboard()

    def _drain_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event["kind"] == "analysis":
                    self.config = event["config"]  # type: ignore[assignment]
                    self.state = event["state"]  # type: ignore[assignment]
                    self.snapshot = event["snapshot"]  # type: ignore[assignment]
                    self.result = event["result"]  # type: ignore[assignment]
                    self.latest_report = event["report"]  # type: ignore[assignment]
                    self.latest_report_path = event["path"]  # type: ignore[assignment]
                    self.selected_report_path = str(self.latest_report_path)
                    self.status_var.set(str(event["status"]))
                    self._render_dashboard()
                else:
                    self.status_var.set("分析失败")
                    self.latest_report = f"执行失败：{event['message']}"
                    self.selected_report_path = None
                    self._render_dashboard()
                self._set_running(False, self.status_var.get())
        except queue.Empty:
            pass
        self.root.after(120, self._drain_events)

    def _set_running(self, running: bool, status: str):
        import tkinter as tk

        button_state = tk.DISABLED if running else tk.NORMAL
        for wrapper in (self.btn_morning, self.btn_intraday, self.btn_record_buy):
            wrapper._button.configure(state=button_state)  # type: ignore[attr-defined]
            surface = wrapper.disabled_bg if running else wrapper.default_bg  # type: ignore[attr-defined]
            wrapper.configure(bg=surface, highlightbackground=self.COLORS["panel_soft"] if running else self.COLORS["line"])  # type: ignore[attr-defined]
            wrapper._button.configure(bg=surface, activebackground=surface, cursor="arrow" if running else "hand2")  # type: ignore[attr-defined]
            wrapper._label.configure(bg=surface, cursor="arrow" if running else "hand2")  # type: ignore[attr-defined]
            wrapper._badge.configure(bg=surface, cursor="arrow" if running else "hand2")  # type: ignore[attr-defined]
            wrapper.configure(cursor="arrow" if running else "hand2")
        self.btn_save_settings.configure(state=button_state)
        self.status_var.set(status)


def launch_gui(config_path: str, state_path: str, offline_demo: bool = False, autorun: str = "") -> int:
    try:
        import tkinter as tk
    except ModuleNotFoundError:
        print("tkinter is not available in this Python environment. Use CLI commands instead.", file=sys.stderr)
        return 1

    root = tk.Tk()
    MonitorGUI(root, config_path, state_path, offline_demo=offline_demo, autorun=autorun)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
