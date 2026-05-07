"""
gold_service.py
ดึงราคาทองคำไทยจาก goldtraders.or.th JSON API (สมาคมค้าทองคำ)
Cache: 15 นาที
"""
import httpx
import time
from datetime import datetime
import pytz

_cache: dict = {}
CACHE_TTL = 15 * 60  # 15 minutes

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "th-TH,th;q=0.9",
    "Referer": "https://www.goldtraders.or.th/",
    "Origin": "https://www.goldtraders.or.th",
}

_API_URL = "https://www.goldtraders.or.th/api/GoldPrices/details?readjson=false"


def _cache_get(key: str):
    e = _cache.get(key)
    if e and time.time() < e["expires_at"]:
        return e["data"]
    return None


def _cache_set(key: str, data, ttl: int = CACHE_TTL):
    _cache[key] = {"data": data, "expires_at": time.time() + ttl}


def get_gold_prices() -> dict:
    cached = _cache_get("gold")
    if cached:
        return cached

    try:
        with httpx.Client(timeout=15, headers=_HEADERS, follow_redirects=True) as client:
            resp = client.get(_API_URL)

        if resp.status_code != 200:
            return {"success": False, "message": f"❌ ดึงข้อมูลไม่ได้ ({resp.status_code})"}

        records = resp.json()
        if not records:
            return {"success": False, "message": "❌ ไม่พบข้อมูลราคาทองครับ"}

        latest = records[0]

        prices = {}
        if latest.get("bL_BuyPrice"):
            prices["bar_buy"] = float(latest["bL_BuyPrice"])
        if latest.get("bL_SellPrice"):
            prices["bar_sell"] = float(latest["bL_SellPrice"])
        if latest.get("oM965_BuyPrice"):
            prices["orn_buy"] = float(latest["oM965_BuyPrice"])
        if latest.get("oM965_SellPrice"):
            prices["orn_sell"] = float(latest["oM965_SellPrice"])

        if not prices:
            return {"success": False, "message": "❌ ไม่พบข้อมูลราคาทองครับ"}

        # แปลง asTime เป็น string วันที่
        as_time = latest.get("asTime", "")
        try:
            dt = datetime.fromisoformat(as_time)
            bkk = pytz.timezone("Asia/Bangkok")
            dt_bkk = dt.replace(tzinfo=pytz.utc).astimezone(bkk) if dt.tzinfo is None else dt.astimezone(bkk)
            date_str = dt_bkk.strftime("%d/%m/%Y %H:%M")
        except Exception:
            date_str = datetime.now(pytz.timezone("Asia/Bangkok")).strftime("%d/%m/%Y %H:%M")

        change = latest.get("priceChangeFromPrevDayLast")

        result = {
            "success": True,
            "prices": prices,
            "date": date_str,
            "change": float(change) if change is not None else None,
            "source": "สมาคมค้าทองคำ (goldtraders.or.th)",
        }
        _cache_set("gold", result)
        return result

    except httpx.TimeoutException:
        return {"success": False, "message": "⏱ ดึงข้อมูลช้าเกินไปครับ ลองใหม่ทีหลังนะ"}
    except Exception as e:
        print(f"[gold] error: {e}")
        return {"success": False, "message": "❌ เชื่อมต่อไม่ได้ครับ ลองใหม่ทีหลังนะ"}


def format_gold_message(result: dict) -> str:
    if not result["success"]:
        return result.get("message", "❌ ไม่สามารถดึงราคาทองได้ครับ")

    p = result["prices"]
    change = result.get("change")

    if change is not None and change != 0:
        arrow = "🔺" if change > 0 else "🔻"
        change_str = f" ({arrow}{abs(change):,.0f})"
    else:
        change_str = ""

    lines = [
        f"🏅 ราคาทองคำวันนี้{change_str}",
        f"📅 {result.get('date', '')}",
        "",
        "📊 ทองคำแท่ง 96.5%:",
    ]
    if "bar_buy" in p:
        lines.append(f"  ซื้อ:  {p['bar_buy']:,.2f} บาท")
    if "bar_sell" in p:
        lines.append(f"  ขาย:  {p['bar_sell']:,.2f} บาท")

    lines.append("")
    lines.append("💍 ทองรูปพรรณ 96.5%:")
    if "orn_buy" in p:
        lines.append(f"  ซื้อ:  {p['orn_buy']:,.2f} บาท")
    if "orn_sell" in p:
        lines.append(f"  ขาย:  {p['orn_sell']:,.2f} บาท")

    if "bar_buy" in p and "bar_sell" in p:
        spread = p["bar_sell"] - p["bar_buy"]
        lines.append(f"\n💡 ส่วนต่าง: {spread:,.0f} บาท/บาท")

    lines.append(f"\n📡 ข้อมูล: {result.get('source', '')}")
    return "\n".join(lines)
