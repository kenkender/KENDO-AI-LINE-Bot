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
# Severity 0-5: ยิ่งสูงยิ่งแย่ — ใช้เปรียบเทียบกับ US AQI เพื่อเลือก display ที่แย่กว่า
AQI_LEVELS = [
    (25,  0, "🟢", "ดีมาก",                   "อากาศบริสุทธิ์ เหมาะกับกิจกรรมกลางแจ้งทุกประเภท"),
    (37,  1, "🟢", "ดี",                       "อากาศดี ไม่มีผลต่อสุขภาพ"),
    (50,  2, "🟡", "ปานกลาง",                  "กลุ่มเสี่ยง (หอบหืด/โรคปอด) ควรระวัง"),
    (90,  3, "🟠", "เริ่มมีผลต่อสุขภาพ",        "ลดกิจกรรมกลางแจ้งนานๆ สวมหน้ากากถ้าออกนอกบ้าน"),
    (120, 4, "🔴", "มีผลต่อสุขภาพ",             "หลีกเลี่ยงกิจกรรมกลางแจ้ง สวมหน้ากาก N95"),
    (float("inf"), 5, "🟣", "อันตราย",         "อยู่ในอาคาร ปิดหน้าต่าง สวมหน้ากาก N95 ตลอดเวลา"),
]

# ── US AQI scale (EPA) ──────────────────────────────────────────────────────
# ใช้เป็น secondary indicator ครอบคลุม pollutants อื่นนอก PM2.5 (O3, NO2, CO, SO2)
US_AQI_LEVELS = [
    (50,  0, "🟢", "ดีมาก",                   "อากาศบริสุทธิ์ เหมาะกับกิจกรรมกลางแจ้งทุกประเภท"),
    (100, 2, "🟡", "ปานกลาง",                  "กลุ่มเสี่ยงควรระวัง"),
    (150, 3, "🟠", "เริ่มมีผลต่อสุขภาพ",        "กลุ่มเสี่ยงลดกิจกรรมกลางแจ้ง"),
    (200, 4, "🔴", "มีผลต่อสุขภาพ",             "ทุกคนควรลดกิจกรรมกลางแจ้ง สวมหน้ากาก N95"),
    (300, 5, "🟣", "มีผลต่อสุขภาพรุนแรง",       "อยู่ในอาคาร สวมหน้ากาก N95"),
    (float("inf"), 5, "🟣", "อันตราย",         "อยู่ในอาคาร ปิดหน้าต่าง สวมหน้ากาก N95 ตลอดเวลา"),
]


def _classify_pm25(value: float) -> tuple[int, str, str, str]:
    for threshold, sev, dot, label, advice in AQI_LEVELS:
        if value <= threshold:
            return sev, dot, label, advice
    return 5, "🟣", "อันตราย", "อยู่ในอาคาร ปิดหน้าต่าง สวมหน้ากาก N95"


def _classify_us_aqi(value: float) -> tuple[int, str, str, str]:
    for threshold, sev, dot, label, advice in US_AQI_LEVELS:
        if value <= threshold:
            return sev, dot, label, advice
    return 5, "🟣", "อันตราย", "อยู่ในอาคาร ปิดหน้าต่าง สวมหน้ากาก N95"


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

    # เลือกระดับที่แย่กว่าระหว่าง PM2.5 (Thai standard) และ US AQI (รวม pollutants อื่น)
    pm_sev, pm_dot, pm_label, pm_advice = _classify_pm25(pm25)
    if us_aqi is not None:
        aqi_sev, aqi_dot, aqi_label, aqi_advice = _classify_us_aqi(us_aqi)
        if aqi_sev > pm_sev:
            sev, dot, label, advice = aqi_sev, aqi_dot, aqi_label, aqi_advice
        else:
            sev, dot, label, advice = pm_sev, pm_dot, pm_label, pm_advice
    else:
        sev, dot, label, advice = pm_sev, pm_dot, pm_label, pm_advice

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

    # คำแนะนำหน้ากาก — ใช้ severity สูงสุดที่เลือก
    if sev >= 3:
        lines.append("😷 แนะนำสวมหน้ากาก N95 ครับ")
    elif sev == 2:
        lines.append("😷 กลุ่มเสี่ยงควรสวมหน้ากากด้วยนะครับ")

    return {"success": True, "message": "\n".join(lines)}


if __name__ == "__main__":
    for place in ["เชียงใหม่", "กรุงเทพ", "สมุทรปราการ"]:
        r = get_air_quality(place)
        print(f"\n=== {place} ===")
        print("success:", r["success"])
