"""
gold_service.py
ดึงราคาทองคำไทยจาก goldtraders.or.th (สมาคมค้าทองคำ)
Cache: 15 นาที (ราคาทองเปลี่ยนบ่อย)
"""
import httpx
import re
import time
from datetime import datetime
import pytz

_cache: dict = {}
CACHE_TTL = 15 * 60  # 15 minutes

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "th-TH,th;q=0.9",
}


def _cache_get(key: str):
    e = _cache.get(key)
    if e and time.time() < e["expires_at"]:
        return e["data"]
    return None


def _cache_set(key: str, data, ttl: int = CACHE_TTL):
    _cache[key] = {"data": data, "expires_at": time.time() + ttl}


def _parse_price(text: str) -> float | None:
    """แปลงข้อความราคา เช่น '32,350.00' หรือ '32350' → float"""
    cleaned = re.sub(r"[^\d.]", "", text.replace(",", ""))
    try:
        v = float(cleaned)
        return v if 20_000 <= v <= 60_000 else None
    except (ValueError, TypeError):
        return None


def get_gold_prices() -> dict:
    cached = _cache_get("gold")
    if cached:
        return cached

    try:
        with httpx.Client(timeout=15, headers=_HEADERS, follow_redirects=True) as client:
            resp = client.get("https://www.goldtraders.or.th/")

        if resp.status_code != 200:
            return {"success": False, "message": f"❌ ดึงข้อมูลไม่ได้ ({resp.status_code})"}

        html = resp.text

        # goldtraders.or.th ใช้ span IDs สำหรับราคา
        id_map = {
            "bar_buy":  ["SpanGBBuy",  "lblGBBuy"],
            "bar_sell": ["SpanGBSell", "lblGBSell"],
            "orn_buy":  ["SpanGOBuy",  "lblGOBuy"],
            "orn_sell": ["SpanGOSell", "lblGOSell"],
        }

        prices = {}
        for field, ids in id_map.items():
            for span_id in ids:
                m = re.search(
                    rf'id=["\']?{span_id}["\']?[^>]*>([0-9,]+\.?[0-9]*)',
                    html, re.IGNORECASE
                )
                if m:
                    val = _parse_price(m.group(1))
                    if val:
                        prices[field] = val
                        break

        if len(prices) < 2:
            # Fallback: หาตัวเลขในช่วงราคาทองทั้งหมด แล้วเอาค่าสูงสุด 4 ค่า
            candidates = []
            for m in re.finditer(r'\b([2-4][0-9],[0-9]{3}(?:\.[0-9]{1,2})?)\b', html):
                val = _parse_price(m.group(1))
                if val:
                    candidates.append(val)
            candidates = sorted(set(candidates), reverse=True)
            if len(candidates) >= 2:
                prices.setdefault("bar_sell", candidates[0])
                prices.setdefault("bar_buy",  candidates[1] if len(candidates) > 1 else candidates[0])

        if not prices:
            return {"success": False, "message": "❌ ไม่พบข้อมูลราคาทองครับ"}

        # หาวันที่จาก HTML
        date_m = re.search(r'(\d{1,2})[/\-\s]+(\d{1,2})[/\-\s]+(\d{4})', html)
        bkk_now = datetime.now(pytz.timezone("Asia/Bangkok"))
        date_str = date_m.group(0) if date_m else bkk_now.strftime("%d/%m/%Y")

        result = {"success": True, "prices": prices, "date": date_str,
                  "source": "สมาคมค้าทองคำ (goldtraders.or.th)"}
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
    lines = [
        f"🏅 ราคาทองคำวันนี้",
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
    elif "bar_sell" in p:
        # ทองรูปพรรณขายสูงกว่าแท่งประมาณ 300-600 บาท
        est = p["bar_sell"] + 500
        lines.append(f"  ขาย:  ~{est:,.0f} บาท (ประมาณ)")

    # Spread ของทองแท่ง
    if "bar_buy" in p and "bar_sell" in p:
        spread = p["bar_sell"] - p["bar_buy"]
        lines.append(f"\n💡 ส่วนต่าง: {spread:,.2f} บาท/บาท")

    lines.append(f"\n📡 ข้อมูล: {result.get('source', '')}")
    return "\n".join(lines)
