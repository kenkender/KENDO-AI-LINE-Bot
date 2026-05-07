"""
holiday_service.py
วันหยุดนักขัตฤกษ์ไทยจาก Calendarific API (ฟรี 1,000 req/month)
"""
import httpx
import os
import time
from datetime import datetime
import pytz

CALENDARIFIC_API_KEY = os.getenv("CALENDARIFIC_API_KEY", "")

_cache: dict = {}
CACHE_TTL = 24 * 3600

MONTH_TH = {
    1: "มกราคม", 2: "กุมภาพันธ์", 3: "มีนาคม", 4: "เมษายน",
    5: "พฤษภาคม", 6: "มิถุนายน", 7: "กรกฎาคม", 8: "สิงหาคม",
    9: "กันยายน", 10: "ตุลาคม", 11: "พฤศจิกายน", 12: "ธันวาคม"
}
DAY_TH = {0: "จันทร์", 1: "อังคาร", 2: "พุธ", 3: "พฤหัสบดี", 4: "ศุกร์", 5: "เสาร์", 6: "อาทิตย์"}


def _cache_get(key: str):
    e = _cache.get(key)
    if e and time.time() < e["expires_at"]:
        return e["data"]
    return None


def _cache_set(key: str, data, ttl: int = CACHE_TTL):
    _cache[key] = {"data": data, "expires_at": time.time() + ttl}


def get_holidays(year: int = None, month: int = None) -> dict:
    bkk = pytz.timezone("Asia/Bangkok")
    now = datetime.now(bkk)
    year = year or now.year

    cache_key = f"holiday_{year}_{month}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    if not CALENDARIFIC_API_KEY:
        return {"success": False, "message": "⚠️ ยังไม่ได้ตั้งค่า CALENDARIFIC_API_KEY ครับ\nไปสมัครฟรีได้ที่ calendarific.com แล้วใส่ใน .env"}

    params = {
        "api_key": CALENDARIFIC_API_KEY,
        "country": "TH",
        "year": year,
        "type": "national",
    }
    if month:
        params["month"] = month

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get("https://calendarific.com/api/v2/holidays", params=params)

        if resp.status_code == 401:
            return {"success": False, "message": "❌ CALENDARIFIC_API_KEY ไม่ถูกต้องครับ"}

        if resp.status_code != 200:
            return {"success": False, "message": f"❌ Calendarific API error {resp.status_code}"}

        data = resp.json()
        if data.get("meta", {}).get("code") != 200:
            return {"success": False, "message": "❌ Calendarific API ตอบกลับผิดพลาดครับ"}

        holidays = data.get("response", {}).get("holidays", [])
        result = {"success": True, "holidays": holidays, "year": year, "month": month}
        _cache_set(cache_key, result)
        return result

    except httpx.TimeoutException:
        return {"success": False, "message": "⏱ Calendarific ตอบช้าเกินไปครับ ลองใหม่ทีหลังนะ"}
    except Exception as e:
        print(f"[holiday] error: {e}")
        return {"success": False, "message": "❌ เชื่อมต่อ Calendarific ไม่ได้ครับ"}


def format_holidays_message(result: dict, near_only: bool = False) -> str:
    if not result["success"]:
        return result.get("message", "❌ ไม่สามารถดึงข้อมูลได้ครับ")

    holidays = result["holidays"]
    year = result["year"]
    month = result["month"]
    year_th = year + 543

    bkk = pytz.timezone("Asia/Bangkok")
    today = datetime.now(bkk).date()

    if near_only:
        upcoming = [
            h for h in holidays
            if datetime.strptime(h["date"]["iso"][:10], "%Y-%m-%d").date() >= today
        ]
        holidays = upcoming[:5]

    if not holidays:
        if near_only:
            return "📅 ไม่มีวันหยุดที่ใกล้จะมาถึงในปีนี้แล้วครับ"
        period = f"เดือน{MONTH_TH.get(month, month)}" if month else f"ปี {year_th}"
        return f"📅 ไม่มีวันหยุดนักขัตฤกษ์ใน{period}ครับ"

    if near_only:
        header = "📅 วันหยุดนักขัตฤกษ์ที่ใกล้จะมาถึง\n"
    elif month:
        header = f"📅 วันหยุดนักขัตฤกษ์ เดือน{MONTH_TH.get(month, month)} {year_th}\n"
    else:
        header = f"📅 วันหยุดนักขัตฤกษ์ไทย ปี {year_th} ({len(holidays)} วัน)\n"

    lines = [header]
    for h in holidays:
        date_obj = datetime.strptime(h["date"]["iso"][:10], "%Y-%m-%d")
        hdate = date_obj.date()
        day_name = DAY_TH[date_obj.weekday()]
        name_th = h.get("name", "")
        day = date_obj.day
        mon = MONTH_TH[date_obj.month]

        if hdate < today:
            marker = "⚫"
        elif hdate == today:
            marker = "🟡"
        else:
            marker = "🔴"

        lines.append(f"  {marker} {day} {mon} (วัน{day_name}) — {name_th}")

    if not near_only:
        lines.append("\n🔴 = ยังไม่ถึง  🟡 = วันนี้  ⚫ = ผ่านมาแล้ว")

    return "\n".join(lines)
