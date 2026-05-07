"""
oilprice_service.py
ดึงราคาน้ำมันไทยจาก thai-oil-api (JSON, ฟรี ไม่ต้อง key)
Source: https://github.com/max180643/thai-oil-api
Endpoint: https://api.chnwt.dev/thai-oil-api/latest
Cache: 3 ชั่วโมง
"""
import httpx
import time
from datetime import datetime
import pytz

_cache: dict = {}
CACHE_TTL = 3 * 3600

FUEL_LABELS = {
    "gasohol_91":          "แก๊สโซฮอล์ 91",
    "gasohol_95":          "แก๊สโซฮอล์ 95",
    "gasohol_e20":         "แก๊สโซฮอล์ E20",
    "gasohol_e85":         "แก๊สโซฮอล์ E85",
    "gasoline_95":         "เบนซิน 95",
    "diesel":              "ดีเซล",
    "diesel_b20":          "ดีเซล B20",
    "premium_diesel":      "พรีเมียม ดีเซล",
    "superpower_gasohol_95": "ซุปเปอร์เพาเวอร์ 95",
    "ngv":                 "NGV",
}

DISPLAY_ORDER = [
    "gasohol_91", "gasohol_95", "gasohol_e20", "gasohol_e85",
    "gasoline_95", "superpower_gasohol_95",
    "diesel", "diesel_b20", "premium_diesel",
    "ngv",
]


def _cache_get(key: str):
    e = _cache.get(key)
    if e and time.time() < e["expires_at"]:
        return e["data"]
    return None


def _cache_set(key: str, data, ttl: int = CACHE_TTL):
    _cache[key] = {"data": data, "expires_at": time.time() + ttl}


def get_oil_prices() -> dict:
    cached = _cache_get("oil_prices")
    if cached:
        return cached

    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get("https://api.chnwt.dev/thai-oil-api/latest")

        if resp.status_code != 200:
            return {"success": False, "message": f"❌ API error {resp.status_code}"}

        data = resp.json()

        if data.get("status") != "success":
            return {"success": False, "message": "❌ ดึงข้อมูลไม่สำเร็จครับ"}

        ptt_prices = data["response"]["stations"].get("ptt", {})
        date_str = data["response"].get("date", "")

        prices = {}
        for key, info in ptt_prices.items():
            try:
                price = float(info["price"])
                if 10.0 <= price <= 150.0:
                    prices[key] = price
            except (ValueError, KeyError, TypeError):
                pass

        result = {
            "success": True,
            "prices": prices,
            "date": date_str,
            "source": "OR / PTT (thai-oil-api)",
        }
        _cache_set("oil_prices", result)
        return result

    except httpx.TimeoutException:
        return {"success": False, "message": "⏱ API ตอบช้าเกินไปครับ ลองใหม่ทีหลังนะ"}
    except Exception as e:
        print(f"[oilprice] error: {e}")
        return {"success": False, "message": "❌ เชื่อมต่อ API ไม่ได้ครับ"}


def format_oil_price_message(result: dict) -> str:
    if not result["success"]:
        return result.get(
            "message",
            "⛽ ไม่สามารถดึงราคาน้ำมันได้ในขณะนี้ครับ ลองใหม่ทีหลังนะ"
        )

    prices = result["prices"]
    date_str = result.get("date", "")
    source = result.get("source", "")

    gasohol_keys = {"gasohol_91", "gasohol_95", "gasohol_e20", "gasohol_e85",
                    "gasoline_95", "superpower_gasohol_95"}
    diesel_keys = {"diesel", "diesel_b20", "premium_diesel"}
    other_keys = {"ngv"}

    lines = [f"⛽ ราคาน้ำมัน PTT/OR (บาท/ลิตร)"]
    if date_str:
        lines.append(f"📅 {date_str}\n")

    gasohol_lines = []
    for key in DISPLAY_ORDER:
        if key in gasohol_keys and key in prices:
            gasohol_lines.append(f"  • {FUEL_LABELS.get(key, key)}: {prices[key]:.2f} บาท")

    diesel_lines = []
    for key in DISPLAY_ORDER:
        if key in diesel_keys and key in prices:
            diesel_lines.append(f"  • {FUEL_LABELS.get(key, key)}: {prices[key]:.2f} บาท")

    other_lines = []
    for key in DISPLAY_ORDER:
        if key in other_keys and key in prices:
            other_lines.append(f"  • {FUEL_LABELS.get(key, key)}: {prices[key]:.2f} บาท")

    if gasohol_lines:
        lines.append("🏍 แก๊สโซฮอล์ / เบนซิน:")
        lines.extend(gasohol_lines)

    if diesel_lines:
        lines.append("🚗 ดีเซล:")
        lines.extend(diesel_lines)

    if other_lines:
        lines.append("🔵 อื่นๆ:")
        lines.extend(other_lines)

    lines.append(f"\n📡 ข้อมูล: {source}")

    return "\n".join(lines)
