"""Short-range point forecasts for Munda Watch, based on MET Norway data."""

import json
from datetime import datetime, time, timedelta, timezone
from email.utils import parsedate_to_datetime
from threading import Lock
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SOURCE_URL = "https://api.met.no/weatherapi/locationforecast/2.0/documentation"
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
DCCMS_DAILY_URL = "https://www.metmalawi.gov.mw/products/daily-forecast/"
DCCMS_WARNINGS_URL = "https://www.metmalawi.gov.mw/"
API_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
CAT = timezone(timedelta(hours=2), "CAT")
UTC = timezone.utc
HOUR = timedelta(hours=1)
MAX_MODEL_AGE = timedelta(hours=18)

# GeoNames Malawi gazetteer (https://www.geonames.org/), CC BY 4.0.
# Town reference points, truncated to four decimals for MET Norway.
LOCATIONS = {
    "Balaka": (-14.9792, 34.9557),
    "Blantyre": (-15.7849, 35.0085),
    "Chikwawa": (-16.0335, 34.8009),
    "Chiradzulu": (-15.6746, 35.1407),
    "Chitipa": (-9.7023, 33.2696),
    "Dedza": (-14.3779, 34.3332),
    "Dowa": (-13.6539, 33.9375),
    "Karonga": (-9.9333, 33.9333),
    "Kasungu": (-13.0333, 33.4833),
    "Likoma": (-12.0666, 34.7333),
    "Lilongwe": (-13.9669, 33.7872),
    "Machinga": (-15.1684, 35.3000),
    "Mangochi": (-14.4781, 35.2644),
    "Mchinji": (-13.7984, 32.8801),
    "Mulanje": (-16.0316, 35.5000),
    "Mwanza": (-15.6026, 34.5247),
    "Mzimba": (-11.9000, 33.6000),
    "Neno": (-15.3980, 34.6534),
    "Nkhata Bay": (-11.6065, 34.2907),
    "Nkhotakota": (-12.9274, 34.2961),
    "Nsanje": (-16.9199, 35.2619),
    "Ntcheu": (-14.8202, 34.6358),
    "Ntchisi": (-13.5277, 33.9149),
    "Phalombe": (-15.8063, 35.6506),
    "Rumphi": (-11.0186, 33.8574),
    "Salima": (-13.7804, 34.4587),
    "Thyolo": (-16.0677, 35.1404),
    "Zomba": (-15.3859, 35.3188),
}
DISTRICT_NAMES = {district.casefold(): district for district in LOCATIONS}
CHICHEWA_WEEKDAYS = ("Lolemba", "Lachiwiri", "Lachitatu", "Lachinayi", "Lachisanu", "Loweruka", "Lamlungu")
# Local weather vocabulary for the bilingual forecast previews. Keep timing
# and attribution in English until the longer wording has fluent review.
FORECAST_PREVIEWS = {
    "chitumbuka": ("Chitumbuka", "tum", "vula", "mphepo"),
    "chisena": ("Chisena", "seh", "bvula", "mphepo"),
    "chiyao": ("Chiyao", "yao", "ula", "mbungo"),
    "chilomwe": ("Chilomwe", "ngl", "epula", "echeku"),
}
_locks = {district: Lock() for district in LOCATIONS}
_cache = {}


def _parse_forecast(payload):
    properties = payload["properties"]
    updated = datetime.fromisoformat(properties["meta"]["updated_at"])
    points = {
        datetime.fromisoformat(point["time"]): point["data"]
        for point in properties["timeseries"]
    }
    if updated.tzinfo is None or not points or any(stamp.tzinfo is None for stamp in points):
        raise ValueError("Invalid MET Norway forecast timestamps")
    return updated, points


def _refresh(district, now, previous):
    lat, lon = LOCATIONS[district]
    request = Request(
        f"{API_URL}?{urlencode({'lat': lat, 'lon': lon})}",
        headers={"User-Agent": "IBROWS-Munda-Watch/1.0 https://www.ibrowsenterprise.com"},
    )
    if previous.get("modified"):
        request.add_header("If-Modified-Since", previous["modified"])
    try:
        with urlopen(request, timeout=8) as response:
            forecast = _parse_forecast(json.load(response))
            expires = response.headers.get("Expires")
            modified = response.headers.get("Last-Modified")
    except HTTPError as error:
        with error:
            if error.code != 304 or not previous.get("forecast"):
                raise
            forecast = previous["forecast"]
            expires = error.headers.get("Expires")
            modified = previous["modified"]
    retry_at = now + 3 * HOUR
    if expires:
        retry_at = max(retry_at, parsedate_to_datetime(expires))
    return {"forecast": forecast, "modified": modified, "retry_at": retry_at}


def _daily_rows(points, now):
    # The global feed eventually switches to 6-hour UTC intervals.
    # Anchoring at 00:00 UTC (02:00 CAT) avoids splitting those rain totals.
    first_day = datetime.combine(now.date(), time.min, tzinfo=UTC)
    next_hour = now.replace(minute=0, second=0, microsecond=0) + HOUR
    first_point = min(points)
    for offset in range(6):
        start = first_day + timedelta(days=offset)
        end = start + timedelta(days=1)
        cursor = max(start, next_hour, first_point)
        if cursor >= end:
            continue
        from_time = cursor
        rain = 0.0
        while cursor < end:
            data = points.get(cursor, {})
            for hours in (6, 1):
                interval = hours * HOUR
                amount = data.get(f"next_{hours}_hours", {}).get("details", {}).get("precipitation_amount")
                if amount is not None and cursor + interval <= end:
                    rain += amount
                    cursor += interval
                    break
            else:
                break
        if cursor != end:
            continue
        conditions = [
            data["instant"]["details"]
            for stamp, data in points.items()
            if from_time <= stamp < end
        ]
        temperatures = [point["air_temperature"] for point in conditions]
        max_wind = max(point["wind_speed"] for point in conditions)
        yield {
            "date": start.astimezone(CAT).date(),
            "from_time": from_time.astimezone(CAT).strftime("%H:%M"),
            "rain_mm": round(rain, 1),
            "temp_low": round(min(temperatures)),
            "temp_high": round(max(temperatures)),
            "wind_kmh": round(max_wind * 3.6),
        }


def daily_forecast(district):
    now = datetime.now(UTC)
    district_lock = _locks[district]
    cached = _cache.get(district, {})
    if now >= cached.get("retry_at", now) and district_lock.acquire(blocking=False):
        try:
            cached = _cache.get(district, {})
            if now >= cached.get("retry_at", now):
                try:
                    cached = _refresh(district, now, cached)
                except (OSError, ValueError, KeyError, TypeError):
                    cached = {**cached, "retry_at": now + 3 * HOUR}
                _cache[district] = cached
        finally:
            district_lock.release()
    if not cached.get("forecast"):
        return None
    updated, points = cached["forecast"]
    if not -timedelta(minutes=5) <= now - updated <= MAX_MODEL_AGE:
        return None
    try:
        rows = list(_daily_rows(points, now.astimezone(CAT)))
    except (ValueError, KeyError, TypeError, OverflowError):
        return None
    if rows:
        return {
            "district": district,
            "updated": updated.astimezone(CAT).strftime("%d %b %Y at %H:%M CAT"),
            "rows": rows,
            "source": SOURCE_URL,
            "licence": LICENSE_URL,
        }


def _chichewa_weather_reply(district, forecast, base_url):
    if not forecast:
        return (
            f"Ulosi wanyengo wa ku {district} sukupezeka pakadali pano.\n"
            f"Ulosi wovomerezeka wa DCCMS: {DCCMS_DAILY_URL}"
        )
    days = []
    for row in forecast["rows"]:
        day = row["date"]
        label = f"*{CHICHEWA_WEEKDAYS[day.weekday()]} {day:%d/%m}*"
        if row["from_time"] != "02:00":
            label += f" kuyambira {row['from_time']}"
        days.append(
            f"{label}: mvula {row['rain_mm']:g} mm · "
            f"{row['temp_low']}–{row['temp_high']}°C · mphepo mpaka {row['wind_kmh']} km/h"
        )
    daily_lines = "\n".join(days)
    return (
        f"*Munda Watch · Nyengo ya ku {district}*\n\n{daily_lines}\n\n"
        "Ulosiwu ndi wa malo amodzi m'bomali. Nthawi ndi ya ku Malawi (CAT). "
        "Tsiku lonse limayambira 02:00 mpaka 02:00 m'mawa mwake.\n"
        f"Zasinthidwa {forecast['updated']}. Deta yochokera ku MET Norway, "
        f"yaphatikizidwa ndi IBROWS ({LICENSE_URL}).\n"
        f"Ulosi wovomerezeka wa DCCMS: {DCCMS_DAILY_URL}\n"
        f"{base_url}/agriculture/munda-watch"
    )


def whatsapp_weather_reply(message, base_url):
    text = " ".join(str(message or "").casefold().strip(" ?.").split())
    if text in {"munda languages", "weather languages"}:
        previews = "\n".join(
            f"• {name}: *{command.upper()} LILONGWE*"
            for command, (name, _, _, _) in FORECAST_PREVIEWS.items()
        )
        return (
            "*Munda Watch forecast languages*\n\n"
            "• English: *WEATHER LILONGWE*\n"
            "• Chichewa: *NYENGO LILONGWE*\n"
            f"{previews}\n\n"
            "Replace LILONGWE with your district.\n\n"
            "Chitumbuka, Chisena, Chiyao and Chilomwe are bilingual previews. "
            "To suggest a wording correction, send *0* to reach IBROWS. "
            "Tell us the language, the word you saw and how you would say it."
        )
    text = text.removeprefix("munda ")
    command, _, district_input = text.partition(" ")
    district = DISTRICT_NAMES.get(district_input)
    preview = FORECAST_PREVIEWS.get(command)
    if not district or (not preview and command not in {"weather", "nyengo"}):
        return None
    forecast = daily_forecast(district)
    if command == "nyengo":
        return _chichewa_weather_reply(district, forecast, base_url)
    if not forecast:
        return (
            f"The short-range forecast for the {district} reference location is temporarily unavailable.\n"
            f"Official Malawi daily forecast: {DCCMS_DAILY_URL}"
        )
    if preview:
        name, _, rain, wind = preview
        days = []
        for row in forecast["rows"]:
            day = f"*{row['date']:%d/%m}*"
            if row["from_time"] != "02:00":
                day += f" ({row['from_time']} CAT)"
            days.append(
                f"{day}: {rain} {row['rain_mm']:g} mm · "
                f"{row['temp_low']}–{row['temp_high']}°C · "
                f"{wind} (max) {row['wind_kmh']} km/h"
            )
        daily_lines = "\n".join(days)
        return (
            f"*Munda Watch · {district} · {name}*\n"
            f"Bilingual preview · {rain} = rain · {wind} = wind\n\n{daily_lines}\n\n"
            "District reference location. Full periods run 02:00 to 02:00 the next morning, Malawi time.\n"
            f"Updated {forecast['updated']}. MET Norway data, aggregated by IBROWS ({LICENSE_URL}).\n"
            f"Official DCCMS forecast: {DCCMS_DAILY_URL}\n"
            f"{base_url}/agriculture/munda-watch"
        )
    days = []
    for row in forecast["rows"]:
        day = f"*{row['date']:%a %d %b}*"
        if row["from_time"] != "02:00":
            day += f" from {row['from_time']}"
        days.append(
            f"{day}: {row['rain_mm']:g} mm rain · "
            f"{row['temp_low']}–{row['temp_high']}°C · wind up to {row['wind_kmh']} km/h"
        )
    daily_lines = "\n".join(days)
    return (
        f"*Munda Watch weather · {district}*\n\n{daily_lines}\n\n"
        "District reference location. All times CAT. Full days run from 02:00 to 02:00 the next morning.\n"
        f"Updated {forecast['updated']}. Based on MET Norway data, aggregated by IBROWS "
        f"({LICENSE_URL}).\nOfficial DCCMS forecast: {DCCMS_DAILY_URL}\n"
        f"{base_url}/agriculture/munda-watch\n"
        f"Pa Chichewa: *NYENGO {district.upper()}*"
    )
