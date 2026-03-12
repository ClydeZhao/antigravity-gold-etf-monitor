from __future__ import annotations

import contextlib
import io
import re
from datetime import datetime

from monitor_core import MarketSnapshot


def build_snapshot(mode: str, offline_demo: bool = False) -> MarketSnapshot:
    if offline_demo:
        return demo_snapshot(mode)

    now = datetime.now()
    data_notes: list[str] = []
    gold_price, gold_change_pct, gold_note = fetch_comex_gold()
    shanghai_gold = fetch_shanghai_gold()
    etf_price, etf_sma20, etf_sma60, etf_note = fetch_etf_trend()
    tips_10y, tips_note = _resolve_tips()
    core_cpi_yoy, cpi_note = _resolve_core_cpi()
    dxy, dxy_mom, dxy_note = fetch_dxy()
    vix, vix_note = fetch_vix()
    _, gold_sma50, gold_sma200, gold_trend_note = fetch_gold_sma()
    gold_24h_change_pct, intraday_note = fetch_gold_24h_change() if mode == "intraday" else (None, None)
    for note in (gold_note, etf_note, tips_note, cpi_note, dxy_note, vix_note, gold_trend_note, intraday_note):
        if note:
            data_notes.append(note)

    return MarketSnapshot(
        as_of=now,
        gold_price=gold_price,
        gold_change_pct=gold_change_pct,
        shanghai_gold=shanghai_gold,
        etf_price=etf_price,
        etf_sma20=etf_sma20,
        etf_sma60=etf_sma60,
        tips_10y=tips_10y,
        core_cpi_yoy=core_cpi_yoy,
        dxy=dxy,
        dxy_mom=dxy_mom,
        vix=vix,
        gold_sma50=gold_sma50,
        gold_sma200=gold_sma200,
        share_trend=None,
        gold_24h_change_pct=gold_24h_change_pct,
        data_notes=data_notes,
    )


def demo_snapshot(mode: str) -> MarketSnapshot:
    return MarketSnapshot(
        as_of=datetime(2026, 3, 12, 8, 50),
        gold_price=2950.0,
        gold_change_pct=0.8,
        shanghai_gold=690.0,
        etf_price=6.12,
        etf_sma20=6.00,
        etf_sma60=5.88,
        tips_10y=-0.25,
        core_cpi_yoy=3.1,
        dxy=101.5,
        dxy_mom=-2.8,
        vix=21.0,
        gold_sma50=2875.0,
        gold_sma200=2610.0,
        share_trend=None,
        gold_24h_change_pct=-3.4 if mode == "intraday" else None,
    )


def fetch_comex_gold():
    for symbol in ("GC=F", "XAUUSD=X"):
        history, note = _fetch_yf_history(symbol, period="5d", interval="1d")
        if history is not None and len(history) >= 2:
            current = float(history["Close"].iloc[-1])
            previous = float(history["Close"].iloc[-2])
            return current, (current - previous) / previous * 100, None
    return None, None, "COMEX 黄金行情抓取失败，可能是网络中断或 Yahoo 行情接口异常。"


def fetch_vix():
    history, _note = _fetch_yf_history("^VIX", period="5d", interval="1d")
    if history is not None and not history.empty:
        return float(history["Close"].iloc[-1]), None
    return None, "VIX 抓取失败，可能是网络中断或 Yahoo 行情接口异常。"


def fetch_dxy():
    for symbol in ("DX-Y.NYB", "DX=F"):
        history, note = _fetch_yf_history(symbol, period="50d", interval="1d")
        if history is not None and len(history) >= 22:
            current = float(history["Close"].iloc[-1])
            previous = float(history["Close"].iloc[-22])
            return current, (current - previous) / previous * 100, None
    return None, None, "美元指数抓取失败，可能是网络中断或 Yahoo 行情接口异常。"


def fetch_tips():
    value, _ = _resolve_tips()
    return value


def fetch_core_cpi():
    value, _ = _resolve_core_cpi()
    return value


def fetch_gold_sma():
    for symbol in ("GC=F", "XAUUSD=X"):
        history, note = _fetch_yf_history(symbol, period="300d", interval="1d")
        if history is not None and len(history) >= 200:
            closes = history["Close"]
            return float(closes.iloc[-1]), float(closes.iloc[-50:].mean()), float(closes.iloc[-200:].mean()), None
    return None, None, None, "黄金趋势抓取失败，可能是网络中断或 Yahoo 行情接口异常。"


def fetch_etf_trend():
    history, _note = _fetch_yf_history("518880.SS", period="120d", interval="1d")
    if history is not None and len(history) >= 60:
        closes = history["Close"]
        return float(closes.iloc[-1]), float(closes.iloc[-20:].mean()), float(closes.iloc[-60:].mean()), None
    return None, None, None, "518880 行情抓取失败，可能是网络中断或 Yahoo 行情接口异常。"


def fetch_shanghai_gold():
    requests = _require_requests()
    try:
        response = requests.get(
            "https://hq.sinajs.cn/list=Au9999",
            headers={"Referer": "https://finance.sina.com.cn/"},
            timeout=8,
        )
        response.encoding = "gbk"
        data = response.text.split('"')[1].split(",")
        if len(data) > 2:
            return float(data[1])
    except Exception:
        return None
    return None


def fetch_gold_24h_change():
    history, _note = _fetch_yf_history("GC=F", period="5d", interval="1h")
    if history is not None and len(history) >= 25:
        current = float(history["Close"].iloc[-1])
        previous = float(history["Close"].iloc[-25])
        return (current - previous) / previous * 100, None
    return None, "盘中黄金 24h 变动抓取失败，可能是网络中断或 Yahoo 行情接口异常。"


def _require_yfinance():
    import yfinance as yf

    return yf


def _require_requests():
    import requests

    return requests


def _fetch_yf_history(symbol: str, period: str, interval: str):
    yf = _require_yfinance()
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            history = yf.Ticker(symbol).history(period=period, interval=interval)
        return history, None
    except Exception as exc:
        return None, f"{symbol} 抓取失败: {exc}"


def _resolve_tips() -> tuple[float | None, str | None]:
    requests = _require_requests()
    try:
        response = requests.get(
            "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFII10",
            timeout=12,
        )
        value = _parse_fred_scalar(response.text)
        if value is not None:
            return value, None
    except Exception:
        pass

    try:
        response = requests.get(
            "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_real_yield_curve",
            timeout=15,
        )
        value = _parse_treasury_real_yield(response.text)
        if value is not None:
            return value, "FRED 超时，10Y 实际利率已切换到美国财政部官方收益率曲线备用数据。"
    except Exception:
        pass
    return None, None


def _resolve_core_cpi() -> tuple[float | None, str | None]:
    requests = _require_requests()
    try:
        response = requests.get(
            "https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPILFESL",
            timeout=12,
        )
        value = _parse_fred_cpi_yoy(response.text)
        if value is not None:
            return value, None
    except Exception:
        pass

    try:
        current_year = datetime.now().year
        response = requests.post(
            "https://api.bls.gov/publicAPI/v2/timeseries/data/",
            json={
                "seriesid": ["CUUR0000SA0L1E"],
                "startyear": str(current_year - 2),
                "endyear": str(current_year),
            },
            timeout=15,
        )
        value = _parse_bls_core_cpi_yoy(response.json())
        if value is not None:
            return value, "FRED 超时，核心 CPI 已切换到 BLS 官方 API 备用数据。"
    except Exception:
        pass
    return None, None


def _parse_fred_scalar(csv_text: str) -> float | None:
    lines = [line for line in csv_text.strip().splitlines()[1:] if line.strip()]
    for line in reversed(lines):
        _date, value = line.split(",", 1)
        if value.strip() != ".":
            return float(value.strip())
    return None


def _parse_fred_cpi_yoy(csv_text: str) -> float | None:
    values = []
    for line in csv_text.strip().splitlines()[1:]:
        if not line.strip():
            continue
        _date, value = line.split(",", 1)
        if value.strip() != ".":
            values.append(float(value.strip()))
    if len(values) < 13:
        return None
    return round((values[-1] - values[-13]) / values[-13] * 100, 2)


def _parse_treasury_real_yield(html_text: str) -> float | None:
    body_match = re.search(r"<tbody>(.*?)</tbody>", html_text, re.S)
    if not body_match:
        return None
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", body_match.group(1), re.S)
    for row in reversed(rows):
        cells = re.findall(r'<td[^>]*headers="([^"]+)"[^>]*>(.*?)</td>', row, re.S)
        for headers, raw_value in cells:
            if headers != "view-field-tc-10year-table-column":
                continue
            text = re.sub(r"<[^>]+>", "", raw_value).strip()
            if text and text != "N/A":
                return float(text)
    return None


def _parse_bls_core_cpi_yoy(payload: dict) -> float | None:
    try:
        series = payload["Results"]["series"][0]["data"]
    except (KeyError, IndexError, TypeError):
        return None

    month_values: dict[tuple[int, int], float] = {}
    for item in series:
        period = item.get("period", "")
        if not period.startswith("M"):
            continue
        year = int(item["year"])
        month = int(period[1:])
        raw_value = item.get("value", "").strip()
        if raw_value in {"", "-"}:
            continue
        month_values[(year, month)] = float(raw_value)

    if not month_values:
        return None

    latest_year, latest_month = max(month_values)
    previous_key = (latest_year - 1, latest_month)
    if previous_key not in month_values:
        return None

    latest_value = month_values[(latest_year, latest_month)]
    previous_value = month_values[previous_key]
    return round((latest_value - previous_value) / previous_value * 100, 2)
