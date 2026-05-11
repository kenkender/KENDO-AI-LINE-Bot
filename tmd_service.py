"""
tmd_service.py
กรมอุตุนิยมวิทยา (TMD) nwpapi v1 integration
- Hourly: https://data.tmd.go.th/nwpapi/v1/forecast/location/hourly/at
- Daily:  https://data.tmd.go.th/nwpapi/v1/forecast/location/daily/at
Auth: Authorization: Bearer TMD_API_TOKEN

ใช้สำหรับพิกัดในไทยเท่านั้น (TMD ครอบคลุมเฉพาะประเทศไทย)
"""

import httpx
import os
import time
from datetime import datetime
import pytz
from dotenv import load_dotenv

load_dotenv()

TMD_API_TOKEN = os.getenv("TMD_API_TOKEN", "")
TMD_HOURLY_URL = "https://data.tmd.go.th/nwpapi/v1/forecast/location/hourly/at"
TMD_DAILY_URL = "https://data.tmd.go.th/nwpapi/v1/forecast/location/daily/at"

CACHE_TTL = 30 * 60  # 30 นาที
_cache: dict = {}

# Thailand bounding box (รวม EEZ — กว้างพอที่ user ในไทยจะ match แต่ไม่ครอบประเทศข้างเคียง)
_TH_LAT_MIN, _TH_LAT_MAX = 5.5, 20.5
_TH_LON_MIN, _TH_LON_MAX = 97.0, 105.7

# Condition code 1-12 → (emoji, Thai description)
COND_MAP = {
    1:  ("☀️", "ท้องฟ้าแจ่มใส"),
    2:  ("🌤", "มีเมฆบางส่วน"),
    3:  ("⛅️", "มีเมฆเป็นส่วนมาก"),
    4:  ("☁️", "มีเมฆมาก"),
    5:  ("🌦", "ฝนเล็กน้อย"),
    6:  ("🌧", "ฝนปานกลาง"),
    7:  ("🌧", "ฝนหนัก"),
    8:  ("⛈", "ฝนฟ้าคะนอง"),
    9:  ("🥶", "อากาศหนาวจัด"),
    10: ("🧥", "อากาศหนาว"),
    11: ("🍃", "อากาศเย็น"),
    12: ("🥵", "อากาศร้อนจัด"),
}

_THAI_MONTHS_SHORT = {
    1: "ม.ค.", 2: "ก.พ.", 3: "มี.ค.", 4: "เม.ย.",
    5: "พ.ค.", 6: "มิ.ย.", 7: "ก.ค.", 8: "ส.ค.",
    9: "ก.ย.", 10: "ต.ค.", 11: "พ.ย.", 12: "ธ.ค."
}


def _is_in_thailand(lat: float, lon: float) -> bool:
    return _TH_LAT_MIN <= lat <= _TH_LAT_MAX and _TH_LON_MIN <= lon <= _TH_LON_MAX


def _cache_get(key: str):
    e = _cache.get(key)
    if e and time.time() < e["expires_at"]:
        return e["data"]
    return None


def _cache_set(key: str, data, ttl: int = CACHE_TTL):
    _cache[key] = {"data": data, "expires_at": time.time() + ttl}


def _extract_first_forecasts(data: dict) -> list:
    """API hourly ใช้ key 'WeatherForcasts' (มี typo ในต้นทาง), daily ใช้ 'weather_forecast.locations'
    คืน list ของ forecast items
    """
    if not isinstance(data, dict):
        return []
    # hourly format
    for key in ("WeatherForcasts", "WeatherForecasts"):
        arr = data.get(key)
        if isinstance(arr, list) and arr:
            return arr[0].get("forecasts", []) or []
    # daily format
    wf = data.get("weather_forecast") or {}
    locs = wf.get("locations") or wf.get("Locations") or []
    if isinstance(locs, list) and locs:
        return locs[0].get("forecasts", []) or []
    return []


def get_tmd_weather(lat: float, lon: float) -> dict | None:
    """ดึง current + today high/low + 7-day outlook จาก TMD
    คืน None ถ้า:
      - ไม่มี TMD_API_TOKEN
      - พิกัดนอกประเทศไทย
      - API ล่ม / token หมดอายุ
    """
    if not TMD_API_TOKEN:
        return None
    if not _is_in_thailand(lat, lon):
        return None

    cache_key = f"tmd_{round(lat, 3)}_{round(lon, 3)}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    headers = {
        "Authorization": f"Bearer {TMD_API_TOKEN}",
        "Accept": "application/json",
    }

    # Hourly: ปัจจุบัน (1 ชั่วโมง)
    hourly = None
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(
                TMD_HOURLY_URL,
                headers=headers,
                params={
                    "lat": lat, "lon": lon,
                    "fields": "tc,rh,rain,ws10m,cond",
                    "duration": 1,
                },
            )
        if resp.status_code == 200:
            hourly = resp.json()
        elif resp.status_code in (401, 403):
            print(f"[tmd] auth error {resp.status_code} — check TMD_API_TOKEN")
            return None
        else:
            print(f"[tmd] hourly status {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[tmd] hourly error: {e}")

    if hourly is None:
        return None

    # Daily: 7 วัน (today + 6 ahead)
    daily = None
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(
                TMD_DAILY_URL,
                headers=headers,
                params={
                    "lat": lat, "lon": lon,
                    "fields": "tc_max,tc_min,rain,cond",
                    "duration": 7,
                },
            )
        if resp.status_code == 200:
            daily = resp.json()
        else:
            print(f"[tmd] daily status {resp.status_code}")
    except Exception as e:
        print(f"[tmd] daily error: {e}")

    result = {"hourly": hourly, "daily": daily}
    _cache_set(cache_key, result)
    return result


def format_tmd_weather(data: dict, place: str) -> dict:
    """แปลง TMD response → ข้อความ LINE (current + today high/low + 6-day outlook)"""
    bkk_tz = pytz.timezone("Asia/Bangkok")
    now_str = datetime.now(bkk_tz).strftime("%H:%M น.")

    hourly_forecasts = _extract_first_forecasts(data.get("hourly") or {})
    daily_forecasts = _extract_first_forecasts(data.get("daily") or {})

    # Current (จาก hourly แรก)
    current = (hourly_forecasts[0].get("data") if hourly_forecasts else {}) or {}
    tc = current.get("tc")
    rh = current.get("rh")
    rain = current.get("rain", 0)
    ws = current.get("ws10m")
    cond = current.get("cond")

    # ถ้า hourly cond ไม่มี ลอง fallback จาก daily (today)
    if cond is None and daily_forecasts:
        cond = (daily_forecasts[0].get("data") or {}).get("cond")

    emoji, desc = COND_MAP.get(int(cond) if cond is not None else 0, ("🌡", "ไม่ทราบสภาพอากาศ"))

    lines = [
        f"🌏 พยากรณ์อากาศ {place}",
        f"🕐 ข้อมูล ณ {now_str}",
        f"📡 จากกรมอุตุนิยมวิทยา (TMD)",
        "",
        f"{emoji} สภาพอากาศ: {desc}",
    ]

    if tc is not None:
        lines.append(f"🌡 อุณหภูมิ: {float(tc):.1f}°C")
    if rh is not None:
        lines.append(f"💧 ความชื้นสัมพัทธ์: {float(rh):.0f}%")

    # High/low ของวันนี้
    if daily_forecasts:
        today_data = (daily_forecasts[0].get("data") or {})
        tmax = today_data.get("tc_max")
        tmin = today_data.get("tc_min")
        if tmax is not None and tmin is not None:
            lines.append(f"🔺 สูงสุด {float(tmax):.1f}°C  🔻 ต่ำสุด {float(tmin):.1f}°C")

    if rain is not None and float(rain) > 0:
        lines.append(f"🌧 ฝน: {float(rain):.1f} mm/ชม.")
    if ws is not None:
        # m/s → km/h
        lines.append(f"💨 ความเร็วลม: {float(ws) * 3.6:.1f} km/h")

    # คำแนะนำ
    tips = []
    if rain is not None and float(rain) >= 5:
        tips.append("☂️ ฝนตกหนัก พกร่มด้วยนะครับ!")
    elif rain is not None and float(rain) > 0:
        tips.append("🌂 มีฝน เตรียมร่มไว้หน่อยนะครับ")
    if tc is not None and float(tc) >= 35:
        tips.append("🥵 อากาศร้อนมาก ดื่มน้ำบ่อยๆ นะครับ")
    if tips:
        lines.append("")
        lines.extend(tips)

    # 6-day outlook (skip today)
    if len(daily_forecasts) > 1:
        lines.append("")
        lines.append("📅 พยากรณ์ล่วงหน้า:")
        for d in daily_forecasts[1:7]:  # max 6 ข้อ
            t_str = d.get("time", "")
            try:
                dt = datetime.fromisoformat(t_str)
                date_str = f"{dt.day} {_THAI_MONTHS_SHORT.get(dt.month, '')}"
            except Exception:
                date_str = t_str[:10]
            dd = d.get("data") or {}
            d_max = dd.get("tc_max")
            d_min = dd.get("tc_min")
            d_rain = dd.get("rain")
            d_cond = dd.get("cond")
            d_emoji, d_desc = COND_MAP.get(int(d_cond) if d_cond is not None else 0, ("•", ""))
            parts = [f"  {d_emoji} {date_str}"]
            if d_min is not None and d_max is not None:
                parts.append(f"{float(d_min):.0f}–{float(d_max):.0f}°C")
            if d_rain is not None and float(d_rain) > 0:
                parts.append(f"☔ {float(d_rain):.0f} mm")
            if d_desc:
                parts.append(d_desc)
            lines.append("  ".join(parts))

    return {"success": True, "message": "\n".join(lines)}


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print("=== TMD test: กรุงเทพ ===")
    r = get_tmd_weather(13.7563, 100.5018)
    if r:
        print(format_tmd_weather(r, "กรุงเทพ")["message"])
    else:
        print("TMD failed (no token / outside TH / API error)")
