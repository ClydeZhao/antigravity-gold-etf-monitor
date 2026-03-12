from __future__ import annotations

from monitor_data import (
    _fetch_yf_history,
    _parse_bls_core_cpi_yoy,
    _parse_treasury_real_yield,
    _resolve_core_cpi,
    _resolve_tips,
)


TREASURY_HTML = """
<table>
  <tbody>
    <tr>
      <td headers="view-field-tdr-date-table-column">03/11/2026</td>
      <td headers="view-field-tc-10year-table-column">1.83</td>
    </tr>
    <tr>
      <td headers="view-field-tdr-date-table-column">03/12/2026</td>
      <td headers="view-field-tc-10year-table-column">1.79</td>
    </tr>
  </tbody>
</table>
"""


def test_parse_treasury_real_yield_returns_latest_10y_value():
    assert _parse_treasury_real_yield(TREASURY_HTML) == 1.79


def test_parse_bls_core_cpi_yoy_uses_latest_month_against_prior_year():
    payload = {
        "Results": {
            "series": [
                {
                    "seriesID": "CUUR0000SA0L1E",
                    "data": [
                        {"year": "2026", "period": "M02", "value": "333.242"},
                        {"year": "2026", "period": "M01", "value": "331.950"},
                        {"year": "2025", "period": "M12", "value": "330.123"},
                        {"year": "2025", "period": "M02", "value": "320.040"},
                    ],
                }
            ]
        }
    }

    assert _parse_bls_core_cpi_yoy(payload) == round((333.242 - 320.040) / 320.040 * 100, 2)


def test_parse_bls_core_cpi_yoy_skips_unavailable_months():
    payload = {
        "Results": {
            "series": [
                {
                    "seriesID": "CUUR0000SA0L1E",
                    "data": [
                        {"year": "2026", "period": "M02", "value": "333.242"},
                        {"year": "2025", "period": "M10", "value": "-"},
                        {"year": "2025", "period": "M02", "value": "320.040"},
                    ],
                }
            ]
        }
    }

    assert _parse_bls_core_cpi_yoy(payload) == round((333.242 - 320.040) / 320.040 * 100, 2)


def test_resolve_tips_falls_back_to_treasury_when_fred_fails(monkeypatch):
    class FakeRequests:
        class exceptions:
            Timeout = TimeoutError

        def __init__(self):
            self.calls = []

        def get(self, url, timeout=0, headers=None):
            self.calls.append(url)
            if "fredgraph" in url:
                raise TimeoutError("fred timeout")

            class Response:
                text = TREASURY_HTML

            return Response()

    fake_requests = FakeRequests()
    monkeypatch.setattr("monitor_data._require_requests", lambda: fake_requests)

    value, note = _resolve_tips()

    assert value == 1.79
    assert "财政部" in note


def test_resolve_core_cpi_falls_back_to_bls_when_fred_fails(monkeypatch):
    payload = {
        "Results": {
            "series": [
                {
                    "seriesID": "CUUR0000SA0L1E",
                    "data": [
                        {"year": "2026", "period": "M02", "value": "333.242"},
                        {"year": "2025", "period": "M02", "value": "320.040"},
                    ],
                }
            ]
        }
    }

    class FakeResponse:
        def __init__(self, text="", json_payload=None):
            self.text = text
            self._json_payload = json_payload

        def json(self):
            return self._json_payload

    class FakeRequests:
        def post(self, url, json=None, timeout=0):
            return FakeResponse(json_payload=payload)

        def get(self, url, timeout=0):
            raise TimeoutError("fred timeout")

    monkeypatch.setattr("monitor_data._require_requests", lambda: FakeRequests())

    value, note = _resolve_core_cpi()

    assert value == round((333.242 - 320.040) / 320.040 * 100, 2)
    assert "BLS" in note


def test_fetch_yf_history_suppresses_stderr_noise_and_returns_friendly_note(capsys, monkeypatch):
    class FakeTicker:
        def __init__(self, symbol):
            self.symbol = symbol

        def history(self, period="", interval=""):
            import sys

            print("curl tls noise", file=sys.stderr)
            raise RuntimeError("network down")

    class FakeYF:
        @staticmethod
        def Ticker(symbol):
            return FakeTicker(symbol)

    monkeypatch.setattr("monitor_data._require_yfinance", lambda: FakeYF())

    history, note = _fetch_yf_history("GC=F", period="5d", interval="1d")
    captured = capsys.readouterr()

    assert history is None
    assert captured.err == ""
    assert "GC=F" in note
