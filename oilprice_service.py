"""
oilprice_service.py
ดึงราคาน้ำมันจาก OR (PTT Oil and Retail) — scrape HTML, cache 3 ชั่วโมง
Primary source: www.pttor.com/th/fuel-price
Fallback source: www.eppo.go.th (กรมธุรกิจพลังงาน)
"""
import httpx
import re
import time
from datetime import datetime
import pytz

_cache: dict = {}
CACHE_TTL = 3 * 3600

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "th-TH,th;q=0.9,en-US;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

FUEL_LABELS = {
    "diesel_b7":    "ดีเซล B7",
    "diesel_b10":   "ดีเซล B10",
    "diesel_b20":   "ดีเซล B20",
    "gasohol_91":   "แก๊สโซฮอล์ 91",
    "gasohol_95":   "แก๊สโซฮอล์ 95",
    "e10":          "แก๊สโซฮอล์ E10",
    "e20":          "แก๊สโซฮอล์ E20",
    "e85":          "แก๊สโซฮอล์ E85",
    "premium_diesel": "พรีเมียม ดีเซล",
}


def _cache_get(key: str):
    e = _cache.get(key)
    if e and time.time() < e["expires_at"]:
        return e["data"]
    return None


def _cache_set(key: str, data, ttl: int = CACHE_TTL):
    _cache[key] = {"data": data, "expires_at": time.time() + ttl}


def _extract_prices_from_html(html: str) -> dict:
    """
    ดึงราคาจาก HTML โดยจับคู่ชื่อน้ำมัน → ราคา (บาท/ลิตร)
    รองรับทั้งชื่อภาษาไทยและอังกฤษที่ OR ใช้
    """
    prices = {}

    patterns = [
        # (key, regex pattern) — จับราคา float ที่ตามหลังชื่อน้ำมัน
        ("diesel_b7",     r"(?:ดีเซล\s*B7|Diesel\s*B7|HSD\s*B7)[^0-9]{0,80}?(\d{2}\.\d{2})"),
        ("diesel_b10",    r"(?:ดีเซล\s*B10|Diesel\s*B10|HSD\s*B10)[^0-9]{0,80}?(\d{2}\.\d{2})"),
        ("diesel_b20",    r"(?:ดีเซล\s*B20|Diesel\s*B20|HSD\s*B20)[^0-9]{0,80}?(\d{2}\.\d{2})"),
        ("gasohol_91",    r"(?:แก๊สโซฮอล์\s*91|Gasohol\s*91|ULG\s*91|E10\s*91)[^0-9]{0,80}?(\d{2}\.\d{2})"),
        ("gasohol_95",    r"(?:แก๊สโซฮอล์\s*95|Gasohol\s*95|ULG\s*95|E10\s*95)[^0-9]{0,80}?(\d{2}\.\d{2})"),
        ("e20",           r"(?:แก๊สโซฮอล์\s*E20|E20|Gasohol\s*E20)[^0-9]{0,80}?(\d{2}\.\d{2})"),
        ("e85",           r"(?:แก๊สโซฮอล์\s*E85|E85|Gasohol\s*E85)[^0-9]{0,80}?(\d{2}\.\d{2})"),
        ("premium_diesel", r"(?:พรีเมียม\s*ดีเซล|Premium\s*Diesel|Hi\s*Diesel)[^0-9]{0,80}?(\d{2}\.\d{2})"),
    ]

    for key, pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
        if match:
            try:
                price = float(match.group(1))
                # ตรวจสอบ range ราคาน้ำมันที่สมเหตุสมผล (20–100 บาท/ลิตร)
                if 20.0 <= price <= 100.0:
                    prices[key] = price
            except ValueError:
                pass

    return prices


def _scrape_or() -> dict:
    """Scrape ราคาน้ำมันจาก OR website"""
    try:
        with httpx.Client(timeout=15, headers=HEADERS, follow_redirects=True) as client:
            resp = client.get("https://www.pttor.com/th/fuel-price")

        if resp.status_code != 200:
            print(f"[oilprice] OR returned {resp.status_code}")
            return {"success": False}

        prices = _extract_prices_from_html(resp.text)
        if prices:
            return {"success": True, "prices": prices, "source": "OR (PTT Oil and Retail)"}

        print("[oilprice] OR: ไม่พบราคาในหน้าเว็บ")
        return {"success": False}

    except Exception as e:
        print(f"[oilprice] OR scrape error: {e}")
        return {"success": False}


def _scrape_eppo() -> dict:
    """Fallback: Scrape ราคาน้ำมันจาก EPPO (กรมธุรกิจพลังงาน)"""
    try:
        with httpx.Client(timeout=15, headers=HEADERS, follow_redirects=True) as client:
            resp = client.get(
                "https://www.eppo.go.th/index.php/th/petroleum/oil-price/bangkok-price"
            )

        if resp.status_code != 200:
            print(f"[oilprice] EPPO returned {resp.status_code}")
            return {"success": False}

        prices = _extract_prices_from_html(resp.text)
        if prices:
            return {"success": True, "prices": prices, "source": "EPPO (กรมธุรกิจพลังงาน)"}

        print("[oilprice] EPPO: ไม่พบราคาในหน้าเว็บ")
        return {"success": False}

    except Exception as e:
        print(f"[oilprice] EPPO scrape error: {e}")
        return {"success": False}


def get_oil_prices() -> dict:
    cached = _cache_get("oil_prices")
    if cached:
        return cached

    result = _scrape_or()
    if not result["success"]:
        result = _scrape_eppo()

    if result["success"]:
        bkk = pytz.timezone("Asia/Bangkok")
        result["fetched_at"] = datetime.now(bkk).strftime("%d/%m/%Y %H:%M น.")
        _cache_set("oil_prices", result)

    return result


def format_oil_price_message(result: dict) -> str:
    if not result["success"]:
        return (
            "⛽ ไม่สามารถดึงราคาน้ำมันได้ในขณะนี้ครับ\n"
            "ลองใหม่ทีหลัง หรือดูได้ที่ pttor.com นะครับ"
        )

    prices = result["prices"]
    source = result.get("source", "")
    fetched_at = result.get("fetched_at", "")

    diesel = {k: v for k, v in prices.items() if "diesel" in k}
    gasohol = {k: v for k, v in prices.items() if k not in diesel}

    lines = ["⛽ ราคาน้ำมันวันนี้ (บาท/ลิตร)\n"]

    if diesel:
        lines.append("🚗 ดีเซล:")
        for key in ["diesel_b7", "diesel_b10", "diesel_b20", "premium_diesel"]:
            if key in diesel:
                lines.append(f"  • {FUEL_LABELS[key]}: {diesel[key]:.2f} บาท")

    if gasohol:
        lines.append("🏍 แก๊สโซฮอล์:")
        for key in ["gasohol_91", "gasohol_95", "e10", "e20", "e85"]:
            if key in gasohol:
                lines.append(f"  • {FUEL_LABELS[key]}: {gasohol[key]:.2f} บาท")

    lines.append(f"\n📡 แหล่งข้อมูล: {source}")
    if fetched_at:
        lines.append(f"🕐 อัปเดต: {fetched_at}")

    return "\n".join(lines)
