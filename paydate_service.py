"""
paydate_service.py — คำนวณวันเงินเดือนข้าราชการไทย
= วันทำการสุดท้ายของเดือน (ถอยจากวันสุดท้าย ข้ามเสาร์-อาทิตย์ และวันหยุดราชการ)
"""

import calendar
from datetime import date, timedelta, datetime
import pytz
from holiday_service import get_holidays


def get_civil_servant_payday(year: int, month: int) -> date:
    """
    คืน date ของวันเงินเดือนข้าราชการ (วันทำการสุดท้ายของเดือน)
    ถ้า Calendarific ไม่พร้อม จะข้ามแค่เสาร์-อาทิตย์
    """
    last_day = calendar.monthrange(year, month)[1]
    payday = date(year, month, last_day)

    # ดึงวันหยุดราชการของเดือนนั้น
    holiday_result = get_holidays(year, month)
    holiday_dates: set = set()
    if holiday_result.get("success"):
        for h in holiday_result["holidays"]:
            try:
                d = datetime.strptime(h["date"]["iso"][:10], "%Y-%m-%d").date()
                holiday_dates.add(d)
            except Exception:
                continue

    # ถอยหลังจนได้วันทำการ
    while payday.weekday() >= 5 or payday in holiday_dates:
        payday -= timedelta(days=1)

    return payday


def is_payday_today() -> bool:
    """ตรวจว่าวันนี้คือวันเงินเดือนข้าราชการหรือไม่"""
    bkk = pytz.timezone("Asia/Bangkok")
    today = datetime.now(bkk).date()
    payday = get_civil_servant_payday(today.year, today.month)
    return today == payday


def get_payday_str(year: int = None, month: int = None) -> str:
    """คืน string ชื่อวันเงินเดือน เช่น 'วันศุกร์ที่ 30 พฤษภาคม'"""
    _THAI_MONTHS = {
        1: "มกราคม", 2: "กุมภาพันธ์", 3: "มีนาคม", 4: "เมษายน",
        5: "พฤษภาคม", 6: "มิถุนายน", 7: "กรกฎาคม", 8: "สิงหาคม",
        9: "กันยายน", 10: "ตุลาคม", 11: "พฤศจิกายน", 12: "ธันวาคม"
    }
    _THAI_DAYS = {
        0: "วันจันทร์", 1: "วันอังคาร", 2: "วันพุธ",
        3: "วันพฤหัสบดี", 4: "วันศุกร์", 5: "วันเสาร์", 6: "วันอาทิตย์"
    }
    bkk = pytz.timezone("Asia/Bangkok")
    now = datetime.now(bkk)
    year = year or now.year
    month = month or now.month
    payday = get_civil_servant_payday(year, month)
    day_name = _THAI_DAYS[payday.weekday()]
    month_name = _THAI_MONTHS[payday.month]
    return f"{day_name}ที่ {payday.day} {month_name}"
