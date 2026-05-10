"""
gold_service.py
ดึงราคาทองคำไทย:
  Layer 1 — goldtraders.or.th JSON API (สมาคมค้าทองคำ)
  Layer 2 — SerpAPI Google Search (ถ้า Layer 1 ถูกบล็อก)
Cache: 15 นาที
"""
import httpx
import os
import time
import re
from datetime import datetime
import pytz

SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")
SERPAPI_URL = "https://serpapi.com/search"

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


def _get_from_goldtraders() -> dict | None:
    """Layer 1: goldtraders.or.th — คืน None ถ้าถูกบล็อก"""
    try:
        with httpx.Client(timeout=10, headers=_HEADERS, follow_redirects=True) as client:
            resp = client.get(_API_URL)
        if resp.status_code != 200:
            print(f"[gold] goldtraders status {resp.status_code} — falling back")
            return None
        records = resp.json()
        if not records:
            return None
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
            return None
        as_time = latest.get("asTime", "")
        try:
            dt = datetime.fromisoformat(as_time)
            bkk = pytz.timezone("Asia/Bangkok")
            # asTime จาก goldtraders.or.th เป็นเวลาไทย — ถ้า naive ให้ localize เป็น Asia/Bangkok
            if dt.tzinfo is None:
                dt_bkk = bkk.localize(dt)
            else:
                dt_bkk = dt.astimezone(bkk)
            date_str = dt_bkk.strftime("%d/%m/%Y %H:%M")
        except Exception:
            date_str = datetime.now(pytz.timezone("Asia/Bangkok")).strftime("%d/%m/%Y %H:%M")
        change = latest.get("priceChangeFromPrevDayLast")
        return {
            "success": True,
            "prices": prices,
            "date": date_str,
            "change": float(change) if change is not None else None,
            "source": "สมาคมค้าทองคำ (goldtraders.or.th)",
        }
    except Exception as e:
        print(f"[gold] goldtraders error: {e}")
        return None


def _parse_price(text: str) -> float | None:
    """แปลงข้อความราคา เช่น '47,650' หรือ '47650.00' เป็น float"""
    if not text:
        return None
    cleaned = re.sub(r"[^\d.]", "", str(text).replace(",", ""))
    try:
        return float(cleaned)
    except Exception:
        return None


def _get_from_serpapi() -> dict | None:
    """Layer 2: SerpAPI Google Search — ดึงราคาทองจาก Google Answer Box"""
    if not SERPAPI_KEY:
        print("[gold] No SERPAPI_KEY — cannot fallback")
        return None
    try:
        params = {
            "engine": "google",
            "q": "ราคาทองคำวันนี้ สมาคมค้าทองคำ",
            "hl": "th",
            "gl": "th",
            "api_key": SERPAPI_KEY,
        }
        with httpx.Client(timeout=15) as client:
            resp = client.get(SERPAPI_URL, params=params)
        if resp.status_code != 200:
            print(f"[gold] SerpAPI status {resp.status_code}")
            return None

        data = resp.json()
        now_str = datetime.now(pytz.timezone("Asia/Bangkok")).strftime("%d/%m/%Y %H:%M")

        # ลอง parse จาก answer_box
        answer = data.get("answer_box", {})
        organic = data.get("organic_results", [])

        prices = {}

        # กรณี answer_box มีข้อมูลราคาทอง
        if answer:
            raw_text = answer.get("answer") or answer.get("result") or ""
            # ลอง regex หาตัวเลขราคาทองแท่ง เช่น "47,650"
            nums = re.findall(r"[\d,]+(?:\.\d+)?", raw_text.replace(",", ""))
            floats = [float(n) for n in nums if 30000 < float(n) < 200000]
            if len(floats) >= 2:
                prices["bar_buy"] = floats[0]
                prices["bar_sell"] = floats[1]

        # กรณี organic results — หา snippet ที่มีราคา
        if not prices:
            for r in organic[:3]:
                snippet = r.get("snippet", "")
                # หาตัวเลขในช่วงราคาทอง (30,000–200,000)
                nums = re.findall(r"([\d]{2,3},[\d]{3})", snippet)
                floats = [float(n.replace(",", "")) for n in nums if 30000 < float(n.replace(",", "")) < 200000]
                if len(floats) >= 2:
                    prices["bar_buy"] = floats[0]
                    prices["bar_sell"] = floats[1]
                    break
                elif len(floats) == 1:
                    prices["bar_buy"] = floats[0]
                    break

        if not prices:
            print("[gold] SerpAPI: ไม่สามารถ parse ราคาทองจาก snippet ได้")
            return None

        return {
            "success": True,
            "prices": prices,
            "date": now_str,
            "change": None,
            "source": "Google Search (SerpAPI)",
        }
    except Exception as e:
        print(f"[gold] SerpAPI error: {e}")
        return None


def get_gold_prices() -> dict:
    cached = _cache_get("gold")
    if cached:
        return cached

    result = _get_from_goldtraders()
    if result is None:
        print("[gold] Trying SerpAPI fallback...")
        result = _get_from_serpapi()

    if result is None:
        return {"success": False, "message": "❌ ดึงราคาทองไม่ได้ตอนนี้ครับ ลองใหม่ทีหลังนะ"}

    _cache_set("gold", result)
    return result


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
