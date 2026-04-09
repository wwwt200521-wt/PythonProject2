import json
from datetime import date
from urllib import error, parse, request


def _normalize_date(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        raise ValueError("Date is required")
    if len(raw) == 5 and raw[2] == "-":
        year = date.today().year
        return f"{year}-{raw}"
    return raw


def _pick_hourly(hourly: list[dict]) -> dict:
    if not hourly:
        return {}
    for entry in hourly:
        if str(entry.get("time", "")).zfill(4) == "1200":
            return entry
    return hourly[0]


def _extract_forecast(payload: dict, target_date: str, lang: str = "zh") -> dict:
    """Extract a forecast for target_date from wttr.in JSON payload.

    Prefer language-specific description fields (e.g. 'lang_zh') when available,
    otherwise fall back to the generic 'weatherDesc'.
    """
    lang_key = f"lang_{lang}"
    for day in payload.get("weather", []):
        if day.get("date") == target_date:
            hourly = day.get("hourly", [])
            picked = _pick_hourly(hourly)

            # Prefer language-specific description if present (e.g. 'lang_zh')
            desc = ""
            if picked.get(lang_key):
                desc = picked.get(lang_key, [{}])[0].get("value", "")
            if not desc and picked.get("weatherDesc"):
                desc = picked.get("weatherDesc", [{}])[0].get("value", "")

            # If still empty, try day-level language fields
            if not desc and day.get(lang_key):
                desc = day.get(lang_key, [{}])[0].get("value", "")

            temps = []
            for entry in hourly:
                temp = entry.get("tempC")
                if temp is None:
                    continue
                try:
                    temps.append(int(temp))
                except (TypeError, ValueError):
                    continue
            if temps:
                temp_min = min(temps)
                temp_max = max(temps)
                temp_source = "hourly"
            else:
                temp_min = day.get("mintempC")
                temp_max = day.get("maxtempC")
                temp_source = "daily"
            return {
                "date": target_date,
                "desc": desc,
                "tempC_min": temp_min,
                "tempC_max": temp_max,
                "tempC_avg": day.get("avgtempC"),
                "temp_source": temp_source,
            }
    return {"date": target_date, "error": "Date not found in forecast"}


def fetch_weather(city: str, fmt: str = "3", lang: str = "zh") -> dict:
    if not city.strip():
        raise ValueError("City is required")

    safe_city = parse.quote(city.strip())
    params = {"format": fmt, "lang": lang}
    url = f"https://wttr.in/{safe_city}?{parse.urlencode(params)}"

    try:
        with request.urlopen(url, timeout=30) as resp:
            text = resp.read().decode("utf-8", errors="ignore").strip()
            return {"city": city, "url": url, "text": text}
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def fetch_weather_by_date(city: str, target_date: str, lang: str = "zh", raw_json: bool = False) -> dict:
    if not city.strip():
        raise ValueError("City is required")

    normalized = _normalize_date(target_date)
    safe_city = parse.quote(city.strip())
    params = {"format": "j1", "lang": lang}
    url = f"https://wttr.in/{safe_city}?{parse.urlencode(params)}"

    try:
        with request.urlopen(url, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="ignore"))
            forecast = _extract_forecast(payload, normalized, lang)
            result = {"city": city, "url": url, "forecast": forecast}
            if raw_json:
                result["raw"] = payload
            return result
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def tool_specs() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get weather from wttr.in for a given city.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "description": "City name, e.g. 青城山"},
                        "fmt": {
                            "type": "string",
                            "description": "wttr.in format, default '3' for brief",
                        },
                        "date": {
                            "type": "string",
                            "description": "Forecast date (YYYY-MM-DD or MM-DD)",
                        },
                        "lang": {
                            "type": "string",
                            "description": "Language code, default 'zh'",
                        },
                        "raw_json": {
                            "type": "boolean",
                            "description": "Include raw wttr.in JSON when using date",
                        },
                    },
                    "required": ["city"],
                },
            },
        }
    ]


def tool_dispatch() -> dict:
    return {"get_weather": get_weather}


def get_weather(
    city: str,
    fmt: str = "3",
    date: str | None = None,
    lang: str = "zh",
    raw_json: bool = False,
) -> dict:
    if date:
        return fetch_weather_by_date(city, date, lang=lang, raw_json=raw_json)
    return fetch_weather(city, fmt=fmt, lang=lang)


def format_tool_result(result: dict) -> str:
    return json.dumps(result, ensure_ascii=False)
