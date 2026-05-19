from __future__ import annotations

import json
from urllib.error import HTTPError, URLError

import pytest

from aiagent.tools.weather import (
    _extract_forecast,
    _normalize_date,
    _pick_hourly,
    fetch_weather,
    fetch_weather_by_date,
    get_weather,
)


class TestNormalizeDate:
    def test_mm_dd_format_prepends_current_year(self) -> None:
        result = _normalize_date("05-15")
        assert result.startswith("202")
        assert result.endswith("-05-15")

    def test_full_date_passes_through(self) -> None:
        assert _normalize_date("2026-12-01") == "2026-12-01"

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="Date is required"):
            _normalize_date("")


class TestPickHourly:
    def test_prefers_noon_entry(self) -> None:
        hourly = [
            {"time": "0600", "tempC": "10"},
            {"time": "1200", "tempC": "20"},
            {"time": "1800", "tempC": "15"},
        ]
        assert _pick_hourly(hourly) == {"time": "1200", "tempC": "20"}

    def test_fallback_to_first(self) -> None:
        hourly = [{"time": "0600", "tempC": "10"}]
        assert _pick_hourly(hourly) == {"time": "0600", "tempC": "10"}

    def test_empty_returns_empty_dict(self) -> None:
        assert _pick_hourly([]) == {}


class TestExtractForecast:
    def test_extracts_by_date(self) -> None:
        payload = {
            "weather": [
                {
                    "date": "2026-05-15",
                    "mintempC": "12",
                    "maxtempC": "25",
                    "avgtempC": "18",
                    "hourly": [{"time": "1200", "lang_zh": [{"value": "晴"}]}],
                }
            ]
        }
        result = _extract_forecast(payload, "2026-05-15")
        assert result["date"] == "2026-05-15"
        assert result["desc"] == "晴"
        assert result["tempC_min"] == 12
        assert result["tempC_max"] == 25

    def test_date_not_found(self) -> None:
        result = _extract_forecast({"weather": []}, "2026-05-15")
        assert "error" in result


class TestFetchWeather:
    def test_empty_city_raises(self) -> None:
        with pytest.raises(ValueError, match="City is required"):
            fetch_weather("")

    def test_valid_city_returns_expected_keys(self, monkeypatch) -> None:
        class FakeResp:
            def read(self) -> bytes: return b"Sunny"
            def __enter__(self): return self
            def __exit__(self, *a): return False

        monkeypatch.setattr("urllib.request.urlopen", lambda url, timeout=30: FakeResp())
        result = fetch_weather("Beijing")
        assert result["city"] == "Beijing"
        assert "url" in result
        assert result["text"] == "Sunny"


class TestFetchWeatherByDate:
    def test_empty_city_raises(self) -> None:
        with pytest.raises(ValueError, match="City is required"):
            fetch_weather_by_date("", "2026-05-15")

    def test_returns_forecast(self, monkeypatch) -> None:
        payload_data = {
            "weather": [
                {
                    "date": "2026-05-15",
                    "mintempC": "10",
                    "maxtempC": "20",
                    "avgtempC": "15",
                    "hourly": [{"time": "1200", "lang_zh": [{"value": "多云"}]}],
                }
            ]
        }

        class FakeResp:
            def read(self) -> bytes: return json.dumps(payload_data).encode()
            def __enter__(self): return self
            def __exit__(self, *a): return False

        monkeypatch.setattr("urllib.request.urlopen", lambda url, timeout=30: FakeResp())
        result = fetch_weather_by_date("Shanghai", "2026-05-15")
        assert result["city"] == "Shanghai"
        assert result["forecast"]["desc"] == "多云"


class TestGetWeather:
    def test_without_date_defaults_to_today_json(self, monkeypatch) -> None:
        payload_data = {
            "weather": [
                {
                    "date": "2026-05-12",
                    "mintempC": "15",
                    "maxtempC": "25",
                    "avgtempC": "20",
                    "hourly": [{"time": "1200", "lang_zh": [{"value": "晴"}]}],
                }
            ]
        }

        class FakeResp:
            def read(self) -> bytes: return json.dumps(payload_data).encode()
            def __enter__(self): return self
            def __exit__(self, *a): return False

        monkeypatch.setattr("urllib.request.urlopen", lambda url, timeout=30: FakeResp())
        result = get_weather("Tokyo")
        assert result["city"] == "Tokyo"
        assert "forecast" in result
        assert result["forecast"]["desc"] == "晴"

    def test_with_date_calls_fetch_weather_by_date(self, monkeypatch) -> None:
        payload_data = {
            "weather": [
                {
                    "date": "2026-06-01",
                    "mintempC": "18",
                    "maxtempC": "30",
                    "avgtempC": "24",
                    "hourly": [{"time": "1200", "lang_zh": [{"value": "雨"}]}],
                }
            ]
        }

        class FakeResp:
            def read(self) -> bytes: return json.dumps(payload_data).encode()
            def __enter__(self): return self
            def __exit__(self, *a): return False

        monkeypatch.setattr("urllib.request.urlopen", lambda url, timeout=30: FakeResp())
        result = get_weather("Taipei", date="2026-06-01")
        assert result["forecast"]["desc"] == "雨"
