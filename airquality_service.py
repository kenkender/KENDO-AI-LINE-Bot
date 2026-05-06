"""
airquality_service.py
ค่าฝุ่น PM2.5 รายสถานที่ในไทย ใช้ Open-Meteo Air Quality API (ฟรี ไม่ต้อง key)
reuse geocoding จาก weather_service
"""

import httpx
import time
from datetime import datetime
import pytz

from weather_service import _lookup_province, _geocode, _cache_get, _cache_set

CACHE_TTL_AQ = 60 * 60  # 1 ชั่วโมง


# ── มาตรฐาน PM2.5 ของกรมควบคุมมลพิษไทย (μg/m³) ─────────────────────────────
AQI_LEVELS = [
    (25,  "🟢", "ดีมาก",                   "อากาศบริสุทธิ์ เหมาะกับกิจกรรมกลางแจ้งทุกประเภท"),
    (37,  "🟢", "ดี",                       "อากาศดี ไม่มีผลต่อสุขภาพ"),
    (50,  "🟡", "ปานกลาง",                  "กลุ่มเสี่ยง (หอบหืด/โรคปอด) ควรระวัง"),
    (90,  "🟠", "เริ่มมีผลต่อสุขภาพ",        "ลดกิจกรรมกลางแจ้งนานๆ สวมหน้ากากถ้าออกนอกบ้าน"),
    (120, "🔴", "มีผลต่อสุขภาพ",             "หลีกเลี่ยงกิจกรรมกลางแจ้ง สวมหน้ากาก N95"),
    (float("inf"), "🟣", "อันตราย",         "อยู่ในอาคาร ปิดหน้าต่าง สวมหน้ากาก N95 ตลอดเวลา"),
]


def _classify_pm25(value: float) -> tuple[str, str, str]:
    for threshold, dot, label, advice in AQI_LEVELS:
        if value <= threshold:
            return dot, label, advice
    return "🟣", "อันตราย", "อยู่ในอาคาร ปิดหน้าต่าง สวมหน้ากาก N95"


def get_air_quality(place: str) -> dict:
    """ดึงค่า PM2.5 ของสถานที่ที่ระบุ"""
    place = place.strip()

    display_name, coords = _lookup_province(place)
    if not coords:
        display_name, coords = _geocode(place)

    if not coords:
        return {
            "success": False,
            "message": (
                f"❌ ไม่พบสถานที่ \"{place}\" ครับ\n"
                "ลองพิมพ์ให้ชัดขึ้น เช่น:\n"
                "  • ค่าฝุ่นที่เชียงใหม่\n"
                "  • pm2.5 อำเภอแม่ริม เชียงใหม่\n"
                "  • ฝุ่นกรุงเทพวันนี้"
            ),
        }

    lat, lon = coords
    cache_key = f"aq_{round(lat, 3)}_{round(lon, 3)}"
    cached = _cache_get(cache_key)
    if cached:
        return _format_aq(cached, display_name or place)

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                "https://air-quality-api.open-meteo.com/v1/air-quality",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "pm2_5,pm10,us_aqi,european_aqi",
                    "timezone": "Asia/Bangkok",
                },
            )
        if resp.status_code != 200:
            return {"success": False, "message": "❌ ไม่สามารถดึงข้อมูลคุณภาพอากาศได้ครับ"}

        data = resp.json()
        _cache_set(cache_key, data, ttl=CACHE_TTL_AQ)
        return _format_aq(data, display_name or place)

    except Exception as e:
        print(f"[airquality_service] error: {e}")
        return {"success": False, "message": "❌ ดึงข้อมูลคุณภาพอากาศไม่ได้ครับ ลองใหม่อีกทีนะครับ"}


def _format_aq(data: dict, place: str) -> dict:
    cur = data.get("current", {})
    pm25    = cur.get("pm2_5")
    pm10    = cur.get("pm10")
    us_aqi  = cur.get("us_aqi")

    if pm25 is None:
        return {"success": False, "message": "❌ ไม่มีข้อมูล PM2.5 สำหรับพื้นที่นี้ครับ"}

    dot, label, advice = _classify_pm25(pm25)

    bkk_tz = pytz.timezone("Asia/Bangkok")
    now_str = datetime.now(bkk_tz).strftime("%H:%M น.")

    lines = [
        f"💨 คุณภาพอากาศ {place}",
        f"🕐 ข้อมูล ณ {now_str}\n",
        f"{dot} สถานะ: {label}",
        f"🌫 PM2.5: {pm25:.1f} μg/m³",
    ]

    if pm10 is not None:
        lines.append(f"💨 PM10:  {pm10:.1f} μg/m³")
    if us_aqi is not None:
        lines.append(f"📊 US AQI: {us_aqi}")

    lines += [
        "",
        f"💡 {advice}",
    ]

    # คำแนะนำหน้ากาก
    if pm25 > 50:
        lines.append("😷 แนะนำสวมหน้ากาก N95 ครับ")
    elif pm25 > 37:
        lines.append("😷 กลุ่มเสี่ยงควรสวมหน้ากากด้วยนะครับ")

    return {"success": True, "message": "\n".join(lines)}


if __name__ == "__main__":
    for place in ["เชียงใหม่", "กรุงเทพ", "สมุทรปราการ"]:
        r = get_air_quality(place)
        print(f"\n=== {place} ===")
        print("success:", r["success"])
