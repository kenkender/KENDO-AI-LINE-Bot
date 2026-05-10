"""
air4thai_service.py
ดึงค่าฝุ่น PM2.5/PM10 จาก Air4Thai PCD (กรมควบคุมมลพิษ)
URL: http://air4thai.pcd.go.th/services/getNewAQI_JSON.php
มี 186 stations ทั่วประเทศ — ใช้ haversine หาสถานีใกล้สุด (รัศมี 30 km)
Cache: 30 นาที
"""

import httpx
import math
import time
from datetime import datetime
import pytz

_AIR4THAI_URL = "http://air4thai.pcd.go.th/services/getNewAQI_JSON.php"
_CACHE_TTL = 30 * 60  # 30 นาที
_MAX_DISTANCE_KM = 30.0

_cache: dict = {}


def _cache_get(key: str):
    e = _cache.get(key)
    if e and time.time() < e["expires_at"]:
        return e["data"]
    return None


def _cache_set(key: str, data, ttl: int = _CACHE_TTL):
    _cache[key] = {"data": data, "expires_at": time.time() + ttl}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """ระยะระหว่าง 2 จุด GPS เป็นกิโลเมตร"""
    R = 6371.0  # earth radius km
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _fetch_stations() -> list:
    """ดึง stations ทั้งหมด — cache 30 นาที"""
    cached = _cache_get("stations")
    if cached is not None:
        return cached
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(_AIR4THAI_URL)
        if resp.status_code != 200:
            print(f"[air4thai] HTTP {resp.status_code}")
            return []
        data = resp.json()
        stations = data.get("stations", [])
        _cache_set("stations", stations)
        return stations
    except Exception as e:
        print(f"[air4thai] fetch error: {e}")
        return []


def _safe_float(val) -> float | None:
    """แปลง string → float, return None ถ้าเป็น "-1" (no data) หรือผิดรูป"""
    if val is None:
        return None
    try:
        f = float(val)
        return None if f < 0 else f
    except (TypeError, ValueError):
        return None


def find_nearest_station(lat: float, lon: float, max_km: float = _MAX_DISTANCE_KM) -> dict | None:
    """
    หาสถานีใกล้สุดในรัศมี max_km ที่มีข้อมูล PM2.5 valid
    คืน {station_data, distance_km} หรือ None
    """
    stations = _fetch_stations()
    if not stations:
        return None

    best = None
    best_dist = max_km
    for st in stations:
        try:
            slat = float(st.get("lat", 0))
            slon = float(st.get("long", 0))
        except (TypeError, ValueError):
            continue
        if slat == 0 and slon == 0:
            continue
        d = _haversine_km(lat, lon, slat, slon)
        if d >= best_dist:
            continue
        # ตรวจว่ามีข้อมูล PM2.5 ที่ valid
        aqi_last = st.get("AQILast") or {}
        pm25 = aqi_last.get("PM25") or {}
        if _safe_float(pm25.get("value")) is None:
            continue
        best = st
        best_dist = d

    if best is None:
        return None
    return {"station": best, "distance_km": best_dist}


def get_air_quality_by_coords(lat: float, lon: float) -> dict | None:
    """
    คืนข้อมูลคุณภาพอากาศจากสถานี Air4Thai ใกล้สุด (≤ 30 km)
    คืน None ถ้าไม่มีสถานีใกล้พอ → caller ควร fallback ไป Open-Meteo
    """
    found = find_nearest_station(lat, lon)
    if not found:
        return None

    st = found["station"]
    dist = found["distance_km"]
    aqi_last = st.get("AQILast") or {}
    pm25_obj = aqi_last.get("PM25") or {}
    pm10_obj = aqi_last.get("PM10") or {}
    aqi_obj = aqi_last.get("AQI") or {}

    pm25 = _safe_float(pm25_obj.get("value"))
    pm10 = _safe_float(pm10_obj.get("value"))
    aqi_val = _safe_float(aqi_obj.get("aqi"))
    aqi_param = aqi_obj.get("param", "")

    return {
        "success": True,
        "source": "air4thai",
        "station_name_th": st.get("nameTH", ""),
        "station_area_th": st.get("areaTH", ""),
        "distance_km": dist,
        "date": aqi_last.get("date", ""),
        "time": aqi_last.get("time", ""),
        "pm25": pm25,
        "pm10": pm10,
        "aqi": aqi_val,
        "aqi_param": aqi_param,
    }


def format_air4thai_message(data: dict, place: str) -> str:
    """แปลงข้อมูล Air4Thai → ข้อความ LINE (PM2.5 + PM10 + AQI)"""
    from airquality_service import _classify_pm25  # reuse Thai PM2.5 scale

    pm25 = data.get("pm25")
    pm10 = data.get("pm10")
    aqi_val = data.get("aqi")
    aqi_param = data.get("aqi_param", "")
    station = data.get("station_name_th", "")
    dist = data.get("distance_km", 0)
    date = data.get("date", "")
    time_str = data.get("time", "")

    # Severity จาก PM2.5
    sev, dot, label, advice = (5, "🟣", "อันตราย", "อยู่ในอาคาร")
    if pm25 is not None:
        sev, dot, label, advice = _classify_pm25(pm25)

    bkk_tz = pytz.timezone("Asia/Bangkok")
    now_str = datetime.now(bkk_tz).strftime("%H:%M น.")
    data_time = f"{date} {time_str} น." if date and time_str else now_str

    lines = [
        f"💨 คุณภาพอากาศ {place}",
        f"🕐 ข้อมูล ณ {data_time}",
        f"📡 จากสถานี: {station} (ห่าง {dist:.1f} km)",
        "",
        f"{dot} สถานะ: {label}",
    ]
    if pm25 is not None:
        lines.append(f"🌫 PM2.5: {pm25:.1f} μg/m³")
    if pm10 is not None:
        lines.append(f"💨 PM10:  {pm10:.1f} μg/m³")
    if aqi_val is not None:
        param_str = f" (ตัวกำหนด: {aqi_param})" if aqi_param else ""
        lines.append(f"📊 AQI:   {aqi_val:.0f}{param_str}")

    lines += ["", f"💡 {advice}"]

    if sev >= 3:
        lines.append("😷 แนะนำสวมหน้ากาก N95 ครับ")
    elif sev == 2:
        lines.append("😷 กลุ่มเสี่ยงควรสวมหน้ากากด้วยนะครับ")

    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    # ทดสอบที่กรุงเทพ
    r = get_air_quality_by_coords(13.7563, 100.5018)
    if r:
        print(format_air4thai_message(r, "กรุงเทพ"))
    else:
        print("ไม่พบสถานีใกล้พอ")
