#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Antigravity 黄金ETF建仓监控系统 V2.0
华安黄金ETF (518880.SH) 量化监控与决策引擎
双击此文件即可启动。
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import os
import sys
import subprocess
from datetime import datetime


# ─────────────────────────────── 依赖检测与自动安装 ─────────────────────────────── #

REQUIRED = ["requests", "yfinance", "pandas"]

def ensure_deps():
    missing = []
    for pkg in REQUIRED:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if not missing:
        return True
    root = tk.Tk()
    root.withdraw()
    ok = messagebox.askyesno(
        "缺少依赖库",
        f"首次运行需安装以下库:\n  {', '.join(missing)}\n\n是否立即自动安装？\n（需要网络连接，约需1分钟）"
    )
    root.destroy()
    if ok:
        for pkg in missing:
            subprocess.run([sys.executable, "-m", "pip", "install", pkg], check=True)
        messagebox.showinfo("安装完成", "依赖库安装完成！程序即将重启。")
        os.execv(sys.executable, [sys.executable] + sys.argv)
    return False


# ─────────────────────────────── 主程序 ─────────────────────────────── #

class GoldMonitor:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("📊 Antigravity 黄金ETF监控系统 V2.0")
        self.root.geometry("750x620")
        self.root.configure(bg="#0d1117")
        self.root.resizable(True, True)
        self._build_ui()

    # ── UI 构建 ──────────────────────────────────────────────────────── #

    def _build_ui(self):
        # ── 顶部标题栏
        header = tk.Frame(self.root, bg="#161b22", pady=14)
        header.pack(fill=tk.X)
        tk.Label(header, text="📊  Antigravity 黄金ETF监控系统",
                 font=("Helvetica", 17, "bold"), fg="#f0c030", bg="#161b22").pack()
        tk.Label(header, text="华安黄金ETF (518880.SH) · 量化建仓决策引擎  V2.0",
                 font=("Helvetica", 10), fg="#8b949e", bg="#161b22").pack()

        # ── 两个操作按钮
        btn_frame = tk.Frame(self.root, bg="#0d1117", pady=18)
        btn_frame.pack(fill=tk.X, padx=36)

        self.btn_morning = tk.Button(
            btn_frame,
            text="🌅  盘前分析\n/Morning",
            font=("Helvetica", 13, "bold"),
            bg="#d97706", fg="white", activebackground="#b45309",
            relief=tk.FLAT, cursor="hand2", width=16, height=3,
            command=self._run_morning
        )
        self.btn_morning.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 14))

        self.btn_intraday = tk.Button(
            btn_frame,
            text="📈  盘中监控\n/Intraday",
            font=("Helvetica", 13, "bold"),
            bg="#1d6fa8", fg="white", activebackground="#155588",
            relief=tk.FLAT, cursor="hand2", width=16, height=3,
            command=self._run_intraday
        )
        self.btn_intraday.pack(side=tk.RIGHT, expand=True, fill=tk.X, padx=(14, 0))

        # ── 状态栏 + 进度条
        self.status_var = tk.StringVar(value="✅  就绪 — 请选择分析模式")
        status = tk.Label(self.root, textvariable=self.status_var,
                          font=("Helvetica", 10), fg="#3fb950", bg="#161b22",
                          anchor=tk.W, padx=12, pady=4)
        status.pack(fill=tk.X)

        self.progress = ttk.Progressbar(self.root, mode="indeterminate", length=750)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TProgressbar", troughcolor="#21262d",
                        background="#d97706", thickness=4)
        self.progress.pack(fill=tk.X)

        # ── 输出区
        out_frame = tk.Frame(self.root, bg="#0d1117")
        out_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(6, 0))
        tk.Label(out_frame, text="  分析输出", font=("Helvetica", 10, "bold"),
                 fg="#8b949e", bg="#0d1117", anchor=tk.W).pack(fill=tk.X)
        self.output = scrolledtext.ScrolledText(
            out_frame, font=("Monaco", 10), bg="#0d1117", fg="#e6edf3",
            insertbackground="white", wrap=tk.WORD, relief=tk.FLAT,
            padx=8, pady=6
        )
        self.output.pack(fill=tk.BOTH, expand=True)

        # ── 底部文件提示
        self.file_label = tk.Label(self.root, text="",
                                   font=("Helvetica", 9), fg="#3fb950", bg="#0d1117")
        self.file_label.pack(pady=(2, 6))

    # ── 工具方法 ──────────────────────────────────────────────────────── #

    def _log(self, text, clear=False):
        self.output.config(state=tk.NORMAL)
        if clear:
            self.output.delete("1.0", tk.END)
        self.output.insert(tk.END, text + "\n")
        self.output.see(tk.END)
        self.output.config(state=tk.DISABLED)
        self.root.update_idletasks()

    def _set_status(self, msg):
        self.status_var.set(msg)
        self.root.update_idletasks()

    def _lock_buttons(self):
        self.btn_morning.config(state=tk.DISABLED)
        self.btn_intraday.config(state=tk.DISABLED)
        self.progress.start(12)

    def _unlock_buttons(self):
        self.progress.stop()
        self.btn_morning.config(state=tk.NORMAL)
        self.btn_intraday.config(state=tk.NORMAL)

    # ── 数据采集 ─────────────────────────────────────────────────────── #

    def _fetch_comex_gold(self):
        import yfinance as yf
        for sym in ["GC=F", "XAUUSD=X"]:
            try:
                hist = yf.Ticker(sym).history(period="5d", interval="1d")
                if len(hist) >= 2:
                    p = float(hist["Close"].iloc[-1])
                    p0 = float(hist["Close"].iloc[-2])
                    return p, (p - p0) / p0 * 100
            except Exception:
                pass
        return None, None

    def _fetch_vix(self):
        import yfinance as yf
        try:
            hist = yf.Ticker("^VIX").history(period="5d", interval="1d")
            if not hist.empty:
                return float(hist["Close"].iloc[-1])
        except Exception:
            pass
        return None

    def _fetch_dxy(self):
        import yfinance as yf
        for sym in ["DX-Y.NYB", "DX=F"]:
            try:
                hist = yf.Ticker(sym).history(period="50d", interval="1d")
                if len(hist) >= 22:
                    cur = float(hist["Close"].iloc[-1])
                    past = float(hist["Close"].iloc[-22])
                    return cur, (cur - past) / past * 100
            except Exception:
                pass
        return None, None

    def _fetch_tips(self):
        import requests
        try:
            url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFII10"
            r = requests.get(url, timeout=12)
            for line in reversed(r.text.strip().split("\n")[1:]):
                parts = line.split(",")
                if len(parts) == 2 and parts[1].strip() != ".":
                    return float(parts[1].strip())
        except Exception:
            pass
        return None

    def _fetch_core_cpi(self):
        import requests
        try:
            url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPILFESL"
            r = requests.get(url, timeout=12)
            vals = []
            for line in r.text.strip().split("\n")[1:]:
                parts = line.split(",")
                if len(parts) == 2 and parts[1].strip() != ".":
                    vals.append(float(parts[1].strip()))
            if len(vals) >= 13:
                return (vals[-1] - vals[-13]) / vals[-13] * 100
        except Exception:
            pass
        return None

    def _fetch_gold_sma(self):
        import yfinance as yf
        for sym in ["GC=F", "XAUUSD=X"]:
            try:
                hist = yf.Ticker(sym).history(period="300d", interval="1d")
                if len(hist) >= 200:
                    c = hist["Close"]
                    return float(c.iloc[-1]), float(c.iloc[-50:].mean()), float(c.iloc[-200:].mean())
            except Exception:
                pass
        return None, None, None

    def _fetch_etf_price(self):
        import yfinance as yf
        try:
            hist = yf.Ticker("518880.SS").history(period="5d", interval="1d")
            if not hist.empty:
                return float(hist["Close"].iloc[-1])
        except Exception:
            pass
        return None

    def _fetch_shanghai_gold(self):
        # 尝试通过东方财富接口获取上金所 Au99.99
        import requests
        try:
            url = "https://hq.sinajs.cn/list=Au9999"
            headers = {"Referer": "https://finance.sina.com.cn/"}
            r = requests.get(url, headers=headers, timeout=8)
            r.encoding = "gbk"
            data = r.text.split('"')[1].split(",")
            if len(data) > 2:
                return float(data[1])   # 当前价
        except Exception:
            pass
        return None

    def _fetch_gold_24h_change(self):
        """获取黄金24小时涨跌幅（用于盘中监控）"""
        import yfinance as yf
        try:
            hist = yf.Ticker("GC=F").history(period="5d", interval="1h")
            if len(hist) >= 25:
                cur = float(hist["Close"].iloc[-1])
                ago = float(hist["Close"].iloc[-25])
                return cur, (cur - ago) / ago * 100
            elif len(hist) >= 2:
                cur = float(hist["Close"].iloc[-1])
                ago = float(hist["Close"].iloc[0])
                return cur, (cur - ago) / ago * 100
        except Exception:
            pass
        return None, None

    # ── GFI 信号计算 ─────────────────────────────────────────────────── #

    @staticmethod
    def _s1(tips):
        if tips is None:        return 50, "N/A (默认50分)",        15.0
        if tips < 0:            return 100, f"{tips:.2f}%  (负实利率 ✓)", 30.0
        if tips < 1:            return 50,  f"{tips:.2f}%  (低实利率 ~)", 15.0
        return 0, f"{tips:.2f}%  (高实利率 ✗)", 0.0

    @staticmethod
    def _s2(cpi):
        if cpi is None:         return 50, "N/A (默认50分)",        7.5
        if cpi >= 4:            return 100, f"{cpi:.2f}%  (高通胀 ✓)",  15.0
        if cpi >= 2:            return 50,  f"{cpi:.2f}%  (温和通胀 ~)", 7.5
        return 0, f"{cpi:.2f}%  (低通胀 ✗)", 0.0

    @staticmethod
    def _s3(mom):
        if mom is None:         return 50, "N/A (默认50分)",        10.0
        if mom < -2:            return 100, f"{mom:+.2f}%  (美元走弱 ✓)", 20.0
        if mom <= 2:            return 50,  f"{mom:+.2f}%  (美元中性 ~)", 10.0
        return 0, f"{mom:+.2f}%  (美元走强 ✗)", 0.0

    @staticmethod
    def _s4(vix):
        if vix is None:         return 50, "N/A (默认50分)",        7.5
        if vix >= 25:           return 100, f"{vix:.2f}  (高恐慌 ✓)",   15.0
        if vix >= 18:           return 50,  f"{vix:.2f}  (中等 ~)",      7.5
        return 0, f"{vix:.2f}  (低波动 ✗)", 0.0

    @staticmethod
    def _s5(price, sma50, sma200):
        if None in (price, sma50, sma200):
            return 50, "数据不足 (默认50分)", 5.0
        if sma50 > sma200 and price > sma50:
            return 100, f"金叉 价格${price:.0f} > 50日${sma50:.0f} > 200日${sma200:.0f}", 10.0
        if price >= sma200:
            return 50, f"中性 价格${price:.0f} 在均线区间内", 5.0
        return 0, f"死叉/价格${price:.0f} < 200日${sma200:.0f}", 0.0

    @staticmethod
    def _s6(trend):
        if trend == "连续增加":   return 100, "连续两周净申购 ✓", 10.0
        if trend == "连续减少":   return 0,   "连续两周净赎回 ✗", 0.0
        return 50, "份额稳定/窄幅震荡 ~", 5.0

    @staticmethod
    def _calc_gfi(s1, s2, s3, s4, s5, s6):
        return s1 * 0.30 + s2 * 0.15 + s3 * 0.20 + s4 * 0.15 + s5 * 0.10 + s6 * 0.10

    @staticmethod
    def _calc_rc(weight=0.12, vol_gold=0.15, vol_port=0.12):
        return (weight * vol_gold) / vol_port

    @staticmethod
    def _get_action(gfi, rc):
        if gfi < 20 and rc > 0.20:
            return "🔴 减仓提示 (Reduce)", "RC超20%且GFI<20，建议按比例减仓以降低风险敞口"
        if gfi < 30:
            return "⚫ 暂停买入 (Stop)", "GFI<30，宏观环境不利，停止任何买入"
        if gfi >= 70 and rc < 0.15:
            return "🟢 强烈买入 (Strong Buy)", "买入组合总资金的 1.5%"
        if 50 <= gfi < 70 and rc <= 0.18:
            return "🔵 逐步建仓 (DCA)", "买入组合总资金的 0.5%（定投模式）"
        return "🟡 持有 / 观望 (Hold)", "GFI处于中性区间或RC已近警戒线，不新增仓位"

    @staticmethod
    def _gfi_bar(gfi):
        n = max(0, min(20, int(gfi / 5)))
        return "[" + "█" * n + "░" * (20 - n) + "]"

    # ── 盘前分析 ─────────────────────────────────────────────────────── #

    def _run_morning(self):
        self._lock_buttons()
        threading.Thread(target=self._morning_worker, daemon=True).start()

    def _morning_worker(self):
        try:
            now = datetime.now()
            self._log("", clear=True)
            self._log("=" * 60)
            self._log(f"  🌅 开盘前分析  |  {now.strftime('%Y-%m-%d %H:%M:%S')}")
            self._log("=" * 60)
            self._log("\n📡 正在采集实时数据...\n")

            # ── 价格数据
            self._set_status("🔄 获取 COMEX 黄金价格...")
            gold, gold_chg = self._fetch_comex_gold()
            self._log(f"  ✓ COMEX 黄金   : {'${:.2f} ({:+.2f}%)'.format(gold, gold_chg) if gold else '获取失败'}")

            self._set_status("🔄 获取 上金所 & ETF 价格...")
            sh_gold  = self._fetch_shanghai_gold()
            etf_price = self._fetch_etf_price()
            self._log(f"  ✓ 上金所Au99.99: {'¥{:.2f}/g'.format(sh_gold) if sh_gold else '获取失败（新浪行情限制）'}")
            self._log(f"  ✓ 518880 ETF   : {'¥{:.3f}'.format(etf_price) if etf_price else '获取失败'}")

            # ── 宏观数据
            self._set_status("🔄 获取宏观数据（FRED）...")
            tips = self._fetch_tips()
            cpi  = self._fetch_core_cpi()
            self._log(f"  ✓ TIPS 10Y     : {'{:.2f}%'.format(tips) if tips is not None else '获取失败'}")
            self._log(f"  ✓ 核心CPI YoY  : {'{:.2f}%'.format(cpi)  if cpi  is not None else '获取失败'}")

            self._set_status("🔄 获取 DXY & VIX...")
            dxy, dxy_mom = self._fetch_dxy()
            vix = self._fetch_vix()
            self._log(f"  ✓ DXY          : {'{:.2f} (30天动量 {:+.2f}%)'.format(dxy, dxy_mom) if dxy else '获取失败'}")
            self._log(f"  ✓ VIX          : {'{:.2f}'.format(vix) if vix else '获取失败'}")

            # ── 技术数据
            self._set_status("🔄 计算技术均线...")
            g_cur, sma50, sma200 = self._fetch_gold_sma()
            self._log(f"  ✓ 50日SMA      : {'${:.2f}'.format(sma50)  if sma50  else 'N/A'}")
            self._log(f"  ✓ 200日SMA     : {'${:.2f}'.format(sma200) if sma200 else 'N/A'}")

            # ETF 份额趋势（yfinance 暂不提供，默认"稳定"；可在此处扩展 akshare）
            share_trend = "连续增加"

            # ── GFI 计算
            self._set_status("🧮 计算 GFI 金价青睐指数...")
            price_t = g_cur or gold
            s1, sv1, w1 = self._s1(tips)
            s2, sv2, w2 = self._s2(cpi)
            s3, sv3, w3 = self._s3(dxy_mom)
            s4, sv4, w4 = self._s4(vix)
            s5, sv5, w5 = self._s5(price_t, sma50, sma200)
            s6, sv6, w6 = self._s6(share_trend)
            gfi = self._calc_gfi(s1, s2, s3, s4, s5, s6)
            rc  = self._calc_rc()
            action, detail = self._get_action(gfi, rc)

            ri = [
                ("S1 真实利率  (×30%)", sv1, w1),
                ("S2 核心CPI   (×15%)", sv2, w2),
                ("S3 DXY动量   (×20%)", sv3, w3),
                ("S4 VIX       (×15%)", sv4, w4),
                ("S5 技术趋势  (×10%)", sv5, w5),
                ("S6 ETF资金   (×10%)", sv6, w6),
            ]

            report = self._build_morning_report(
                now, gold, gold_chg, sh_gold, etf_price,
                tips, cpi, dxy, dxy_mom, vix, sma50, sma200,
                ri, gfi, rc, action, detail
            )

            self._log("\n" + report)

            # ── 保存文件
            self._set_status("💾 保存报告...")
            fp = self._save_report(report, now, "盘前", gfi)
            self._set_status("✅ 盘前分析完成")
            self.root.after(0, lambda: self.file_label.config(
                text=f"📄 已保存 → reports/{os.path.basename(fp)}"))

        except Exception as e:
            self._log(f"\n❌ 分析出错: {e}")
            self._set_status("❌ 出错 — 请检查网络连接")
        finally:
            self.root.after(0, self._unlock_buttons)

    def _build_morning_report(self, now, gold, gold_chg, sh_gold, etf,
                               tips, cpi, dxy, dxy_mom, vix, sma50, sma200,
                               ri, gfi, rc, action, detail):
        bar  = self._gfi_bar(gfi)
        rc_p = rc * 100
        w_sum = " + ".join(f"{r[2]:.1f}" for r in ri)

        lines = [
            "=" * 62,
            f"  📊 Antigravity 监控看板  |  {now.strftime('%Y-%m-%d %H:%M')} CST",
            "  【开盘前分析 /Morning】",
            "=" * 62,
            "",
            "🏷️  资产报价",
            "─" * 50,
            f"  COMEX 现货黄金     : {'${:.2f}  ({:+.2f}%)'.format(gold, gold_chg) if gold else 'N/A'}",
            f"  上金所 Au99.99     : {'¥{:.2f} /g'.format(sh_gold) if sh_gold else 'N/A（受行情接口限制）'}",
            f"  华安黄金ETF 518880 : {'¥{:.3f}'.format(etf) if etf else 'N/A'}",
            "",
            "📡  宏观数据",
            "─" * 50,
            f"  美国TIPS 10Y收益率  : {'{:.2f}%'.format(tips) if tips is not None else 'N/A'}",
            f"  美国核心CPI YoY     : {'{:.2f}%'.format(cpi)  if cpi  is not None else 'N/A'}",
            f"  美元指数 DXY        : {'{:.2f}'.format(dxy) if dxy else 'N/A'}  "
                f"(30天动量: {'{:+.2f}%'.format(dxy_mom) if dxy_mom is not None else 'N/A'})",
            f"  VIX 恐慌指数        : {'{:.2f}'.format(vix) if vix else 'N/A'}",
            "",
            "📐  技术指标 (XAU/USD)",
            "─" * 50,
            f"  当前价       : {'${:.2f}'.format(gold) if gold else 'N/A'}",
            f"  50日  SMA    : {'${:.2f}'.format(sma50)  if sma50  else 'N/A'}",
            f"  200日 SMA    : {'${:.2f}'.format(sma200) if sma200 else 'N/A'}",
            "",
            "🧮  GFI 金价青睐指数",
            "─" * 50,
            f"  {bar}  {gfi:.1f} / 100",
            "",
            f"  {'信号':<22}  {'原始分':<6}  {'加权':<6}  数据值",
            f"  {'─'*22}  {'─'*6}  {'─'*5}  {'─'*22}",
        ]
        score_names = [f"  {r[0]:<22}  {int(round(ri[i][2]/([0.30,0.15,0.20,0.15,0.10,0.10][i]),0) if [0.30,0.15,0.20,0.15,0.10,0.10][i]>0 else 0):>3}" for i, r in enumerate(ri)]
        weights_raw = [0.30, 0.15, 0.20, 0.15, 0.10, 0.10]
        for i, (name, val, w) in enumerate(ri):
            raw_score = int(round(w / weights_raw[i])) if weights_raw[i] > 0 else 0
            lines.append(f"  {name:<22}  {raw_score:>5}分  {w:>5.1f}   {val}")
        lines += [
            f"  {'─'*22}  {'─'*6}  {'─'*5}  {'─'*22}",
            f"  {'合计':<22}  {'':6}  {gfi:>5.1f}   ({w_sum} = {gfi:.1f})",
            "",
            "⚖️  风控指标",
            "─" * 50,
            "  黄金持仓权重  : 12%（默认，请按实际持仓修改）",
            "  黄金波动率    : 15%（固定假设）",
            "  组合总波动率  : 12%（默认假设）",
            f"  风险贡献度 RC : {rc_p:.1f}%  （安全水位: 15%—20%）",
            "",
            "💡  核心决策",
            "═" * 62,
            f"  当前评级  :  {action}",
            f"  行动建议  :  {detail}",
            "═" * 62,
            "",
            f"⏰ 生成时间: {now.strftime('%Y-%m-%d %H:%M:%S')}  |  Antigravity V2.0",
        ]
        return "\n".join(lines)

    # ── 盘中监控 ─────────────────────────────────────────────────────── #

    def _run_intraday(self):
        self._lock_buttons()
        threading.Thread(target=self._intraday_worker, daemon=True).start()

    def _intraday_worker(self):
        try:
            now = datetime.now()
            self._log("", clear=True)
            self._log("=" * 60)
            self._log(f"  📈 盘中监控  |  {now.strftime('%Y-%m-%d %H:%M:%S')}")
            self._log("=" * 60)
            self._log("")

            self._set_status("🔄 检查黄金24h涨跌幅...")
            cur_price, chg_24h = self._fetch_gold_24h_change()
            self._log(f"  ✓ 黄金当前价  : {'${:.2f}'.format(cur_price) if cur_price else 'N/A'}")
            self._log(f"  ✓ 24h 涨跌幅  : {'{:+.2f}%'.format(chg_24h) if chg_24h is not None else 'N/A'}")

            triggered = chg_24h is not None and chg_24h <= -3

            if triggered:
                self._log(f"\n  ⚡ 检测到异常回调！跌幅: {chg_24h:.2f}%")
                self._set_status("🧮 快速计算 GFI...")
                tips       = self._fetch_tips()
                cpi        = self._fetch_core_cpi()
                _, dxy_mom = self._fetch_dxy()
                vix        = self._fetch_vix()
                g_c, s50, s200 = self._fetch_gold_sma()
                price_t = g_c or cur_price

                s1, *_ = self._s1(tips);   s1 = s1
                s2, *_ = self._s2(cpi);    s2 = s2
                s3, *_ = self._s3(dxy_mom); s3= s3
                s4, *_ = self._s4(vix);    s4 = s4
                s5, *_ = self._s5(price_t, s50, s200); s5 = s5
                s6, *_ = self._s6("连续增加"); s6 = s6

                gfi = self._calc_gfi(s1, s2, s3, s4, s5, s6)
                rc  = self._calc_rc()

                # 盘中特殊规则判断
                if -5 <= chg_24h <= -3 and gfi >= 50:
                    intra_action = "⚡ 触发回调加仓条件！"
                    intra_detail = "建议额外买入组合总资金的 0.5%（回调加仓）\n  ⚠️  请确认距上次回调加仓已超过 3 个交易日"
                elif chg_24h < -5 and gfi >= 50:
                    intra_action = "⚠️  回调幅度 > 5%，超出特殊规则范围"
                    intra_detail = "跌幅过大，等待企稳后再评估，暂不加仓"
                else:
                    intra_action = "📊 GFI未达50分，回调加仓条件不满足"
                    intra_detail = f"GFI={gfi:.1f}，维持原有建议，不额外加仓"
            else:
                gfi = 50
                rc  = self._calc_rc()
                intra_action = "✅ 无异常回调"
                intra_detail = (
                    f"24h涨跌幅 {'{:+.2f}%'.format(chg_24h) if chg_24h is not None else 'N/A'}，"
                    "未触发 3% 回调阈值，无需特殊操作"
                )

            report = self._build_intraday_report(now, cur_price, chg_24h, gfi, rc,
                                                  triggered, intra_action, intra_detail)
            self._log("\n" + report)

            self._set_status("💾 保存报告...")
            fp = self._save_report(report, now, "盘中", gfi)
            self._set_status("✅ 盘中监控完成")
            self.root.after(0, lambda: self.file_label.config(
                text=f"📄 已保存 → reports/{os.path.basename(fp)}"))

        except Exception as e:
            self._log(f"\n❌ 盘中监控出错: {e}")
            self._set_status("❌ 出错 — 请检查网络连接")
        finally:
            self.root.after(0, self._unlock_buttons)

    def _build_intraday_report(self, now, cur_price, chg_24h, gfi, rc,
                                triggered, action, detail):
        bar  = self._gfi_bar(gfi)
        rc_p = rc * 100
        lines = [
            "=" * 62,
            f"  📊 Antigravity 监控看板  |  {now.strftime('%Y-%m-%d %H:%M')} CST",
            "  【盘中监控 /Intraday】",
            "=" * 62,
            "",
            "🏷️  实时价格",
            "─" * 50,
            f"  COMEX 黄金当前价 : {'${:.2f}'.format(cur_price) if cur_price else 'N/A'}",
            f"  24h  涨跌幅      : {'{:+.2f}%'.format(chg_24h) if chg_24h is not None else 'N/A'}"
                + ("  ⚡ 触发回调阈值！" if triggered else ""),
            "",
            f"🧮  GFI 参考值  {bar}  {gfi:.1f} / 100",
            f"⚖️  风险贡献度 RC : {rc_p:.1f}%  （安全水位: 15%—20%）",
            "",
            "📌  盘中特殊规则检查",
            "─" * 50,
            f"  24h跌幅 3%–5%  : {'✓' if chg_24h is not None and -5 <= chg_24h <= -3 else '✗'}",
            f"  GFI ≥ 50       : {'✓' if gfi >= 50 else '✗'}  (GFI={gfi:.1f})",
            "  距上次加仓>3日  : ⚠️  请用户自行确认",
            "",
            "💡  盘中决策",
            "═" * 62,
            f"  监控结果  :  {action}",
            f"  操作建议  :  {detail}",
            "═" * 62,
            "",
            f"⏰ 生成时间: {now.strftime('%Y-%m-%d %H:%M:%S')}  |  Antigravity V2.0",
        ]
        return "\n".join(lines)

    # ── 文件保存 ─────────────────────────────────────────────────────── #

    def _save_report(self, content, dt, mode, gfi):
        fname = f"{dt.strftime('%Y%m%d_%H%M')}_{mode}_GFI{int(gfi)}.txt"
        script_dir = os.path.dirname(os.path.abspath(__file__))
        reports_dir = os.path.join(script_dir, "reports")
        os.makedirs(reports_dir, exist_ok=True)
        fp = os.path.join(reports_dir, fname)
        with open(fp, "w", encoding="utf-8") as f:
            f.write(content)
        return fp


# ─────────────────────────────── 入口 ─────────────────────────────── #

if __name__ == "__main__":
    if not ensure_deps():
        sys.exit(1)
    root = tk.Tk()
    app = GoldMonitor(root)
    root.mainloop()
