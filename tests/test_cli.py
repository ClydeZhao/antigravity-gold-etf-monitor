from __future__ import annotations

import json
import subprocess
import sys


def test_cli_help_runs_without_tkinter():
    result = subprocess.run(
        [sys.executable, "gold_monitor.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "morning" in result.stdout
    assert "gui" in result.stdout


def test_system_python_can_parse_cli_entrypoint():
    result = subprocess.run(
        ["/usr/bin/python3", "gold_monitor.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "intraday" in result.stdout


def test_gui_help_exposes_demo_options():
    result = subprocess.run(
        [sys.executable, "gold_monitor.py", "gui", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--offline-demo" in result.stdout
    assert "--autorun" in result.stdout


def test_uv_tk_python_can_construct_gui_in_demo_mode():
    result = subprocess.run(
        [
            ".venv311/bin/python",
            "-c",
            (
                "import tkinter as tk; "
                "from gold_monitor import MonitorGUI; "
                "root = tk.Tk(); "
                "app = MonitorGUI(root, 'config.example.json', 'state.json', offline_demo=True, autorun=''); "
                "root.update_idletasks(); "
                "root.after(300, root.quit); "
                "root.mainloop(); "
                "print(app.report_preview.cget('wrap')); "
                "print(app.report_preview.winfo_height()); "
                "print(app.demo_var.get()); "
                "print(app.btn_morning._button.cget('text')); "
                "print(app.btn_intraday._button.cget('text')); "
                "print(app.btn_record_buy._button.cget('text')); "
                "print(app.btn_morning._button.cget('relief')); "
                "root.destroy()"
            ),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    lines = result.stdout.strip().splitlines()
    assert lines[0] == "none"
    assert int(lines[1]) >= 180
    assert "当前不是实时行情" in lines[2]
    assert lines[3] == "开始盘前分析"
    assert lines[4] == "开始盘中监控"
    assert lines[5] == "记录今天已买入"
    assert lines[6] == "flat"


def test_offline_demo_morning_generates_report(tmp_path):
    config_path = tmp_path / "config.json"
    state_path = tmp_path / "state.json"
    reports_dir = tmp_path / "reports"
    config_path.write_text(
        json.dumps(
            {
                "portfolio_gold_weight": 0.12,
                "gold_volatility": 0.15,
                "portfolio_volatility": 0.12,
                "min_add_cooldown_days": 3,
                "reports_dir": str(reports_dir),
            }
        ),
        encoding="utf-8",
    )
    state_path.write_text("{}", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "gold_monitor.py",
            "morning",
            "--offline-demo",
            "--config",
            str(config_path),
            "--state",
            str(state_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    created = list(reports_dir.glob("*_盘前_*.txt"))
    assert len(created) == 1
    assert "当前评级" in created[0].read_text(encoding="utf-8")
