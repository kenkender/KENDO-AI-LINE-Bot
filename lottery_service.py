"""
lottery_service.py
ดึงผลสลากกินแบ่งรัฐบาลไทยจาก glo.or.th
งวดออก: วันที่ 1 และ 16 ของทุกเดือน
Cache: 1 ชั่วโมง
"""
import httpx
import re
import time
from datetime import datetime, date
import pytz

_cache: dict = {}
CACHE_TTL = 3600  # 1 hour

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "th-TH,th;q=0.9",
}

_THAI_MONTHS = {
    1: "มกราคม", 2: "กุมภาพันธ์", 3: "มีนาคม", 4: "เมษายน",
    5: "พฤษภาคม", 6: "มิถุนายน", 7: "กรกฎาคม", 8: "สิงหาคม",
    9: "กันยายน", 10: "ตุลาคม", 11: "พฤศจิกายน", 12: "ธันวาคม"
}


def _cache_get(key: str):
    e = _cache.get(key)
    if e and time.time() < e["expires_at"]:
        return e["data"]
    return None


def _cache_set(key: str, data, ttl: int = CACHE_TTL):
    _cache[key] = {"data": data, "expires_at": time.time() + ttl}


def _latest_draw_date(today: date) -> date:
    """คืนวันออกผลล่าสุด (วันที่ 1 หรือ 16)"""
    if today.day >= 16:
        return today.replace(day=16)
    elif today.day >= 1:
        if today.month == 1:
            return date(today.year - 1, 12, 16)
        return date(today.year, today.month - 1, 16) if today.day < 16 else today.replace(day=1)
    return today.replace(day=1)


def _get_draw_date() -> date:
    bkk = pytz.timezone("Asia/Bangkok")
    today = datetime.now(bkk).date()
    if today.day >= 16:
        return today.replace(day=16)
    if today.day >= 1:
        # งวดก่อนหน้า
        if today.month == 1:
            return date(today.year - 1, 12, 16)
        return date(today.year, today.month - 1, 16)
    return today.replace(day=1)


def get_lottery_result() -> dict:
    draw_date = _get_draw_date()
    cache_key = f"lottery_{draw_date}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    date_str = draw_date.strftime("%Y-%m-%d")
    url = f"https://www.glo.or.th/result/lotterys/{date_str}"

    try:
        with httpx.Client(timeout=15, headers=_HEADERS, follow_redirects=True) as client:
            resp = client.get(url)

        if resp.status_code != 200:
            return _fallback_no_result(draw_date)

        html = resp.text

        # รางวัลที่ 1 — 6 หลัก
        first_prize = _find_numbers(html, r'รางวัลที่\s*1.*?(\d{6})', count=1)
        if not first_prize:
            first_prize = _find_numbers(html, r'first[_-]?prize.*?(\d{6})', count=1, flags=re.I)

        # รางวัลเลขท้าย 3 ตัว
        last3 = _find_numbers(html, r'(?:เลขท้าย|3\s*ตัวท้าย).*?(\d{3}).*?(\d{3})', count=2, multi=True)

        # รางวัลเลขท้าย 2 ตัว
        last2 = _find_numbers(html, r'(?:เลขท้าย|2\s*ตัวท้าย)[^0-9]*(\d{2})\b', count=1)

        # เลขหน้า 3 ตัว
        front3 = _find_numbers(html, r'(?:เลขหน้า|3\s*ตัวหน้า).*?(\d{3}).*?(\d{3})', count=2, multi=True)

        result = {
            "success": bool(first_prize),
            "draw_date": draw_date.strftime("%d/%m/%Y"),
            "draw_date_thai": f"{draw_date.day} {_THAI_MONTHS.get(draw_date.month, '')} {draw_date.year + 543}",
            "first_prize": first_prize[0] if first_prize else None,
            "last3": last3 or [],
            "last2": last2[0] if last2 else None,
            "front3": front3 or [],
        }

        if result["success"]:
            _cache_set(cache_key, result)
        return result

    except httpx.TimeoutException:
        return {"success": False, "message": "⏱ ดึงข้อมูลช้าเกินไปครับ ลองใหม่ทีหลังนะ",
                "draw_date_thai": ""}
    except Exception as e:
        print(f"[lottery] error: {e}")
        return _fallback_no_result(draw_date)


def _find_numbers(html: str, pattern: str, count: int = 1,
                  multi: bool = False, flags: int = re.DOTALL) -> list:
    """ค้นหาตัวเลขตาม regex pattern"""
    matches = list(re.finditer(pattern, html, flags))
    results = []
    for m in matches[:count]:
        if multi:
            results.extend(g for g in m.groups() if g)
        else:
            results.append(m.group(1))
    return results


def _fallback_no_result(draw_date: date) -> dict:
    date_thai = f"{draw_date.day} {_THAI_MONTHS.get(draw_date.month, '')} {draw_date.year + 543}"
    return {
        "success": False,
        "draw_date_thai": date_thai,
        "message": f"❌ ยังไม่พบผลสลากงวด {date_thai} ครับ\nอาจยังไม่ออกผล หรือลองใหม่ทีหลังนะครับ"
    }


def format_lottery_message(result: dict) -> str:
    if not result.get("success"):
        msg = result.get("message", "")
        date_thai = result.get("draw_date_thai", "")
        if not msg:
            return f"🎫 ยังไม่พบผลสลากงวด {date_thai} ครับ"
        return f"🎫 {msg}"

    lines = [
        f"🎫 ผลสลากกินแบ่งรัฐบาล",
        f"📅 งวดวันที่ {result['draw_date_thai']}",
        "",
        f"🥇 รางวัลที่ 1:       {result.get('first_prize', 'N/A')}",
    ]

    if result.get("last2"):
        lines.append(f"🔢 เลขท้าย 2 ตัว:    {result['last2']}")

    if result.get("last3"):
        lines.append(f"3️⃣  เลขท้าย 3 ตัว:    {' | '.join(result['last3'])}")

    if result.get("front3"):
        lines.append(f"3️⃣  เลขหน้า 3 ตัว:    {' | '.join(result['front3'])}")

    lines.append("\n📡 ข้อมูล: สำนักงานสลากกินแบ่งรัฐบาล (glo.or.th)")
    return "\n".join(lines)
