"""
serpapi_trends_service.py
ดึง Trending Searches ในไทยจาก SerpAPI Google Trends Trending Now
"""

import httpx
import os
import time
from datetime import datetime
import pytz
from dotenv import load_dotenv

load_dotenv()

SERPAPI_KEY = os.getenv("SERPAPI_KEY")
SERPAPI_URL = "https://serpapi.com/search"

_cache: dict = {}
CACHE_TTL = 60 * 60  # 1 ชั่วโมง (ประหยัด credit)

_THAI_MONTHS = {
    1: "มกราคม", 2: "กุมภาพันธ์", 3: "มีนาคม", 4: "เมษายน",
    5: "พฤษภาคม", 6: "มิถุนายน", 7: "กรกฎาคม", 8: "สิงหาคม",
    9: "กันยายน", 10: "ตุลาคม", 11: "พฤศจิกายน", 12: "ธันวาคม"
}


def get_trending_now() -> dict:
    """ดึง Top Trending Searches ในไทยวันนี้ผ่าน SerpAPI Google Trends Trending Now"""
    if not SERPAPI_KEY:
        return {"success": False, "message": "❌ ยังไม่ได้ตั้งค่า SERPAPI_KEY ครับ"}

    cache_key = "trends_th_daily"
    entry = _cache.get(cache_key)
    if entry and time.time() < entry["expires_at"]:
        return entry["data"]

    try:
        params = {
            "engine": "google_trends_trending_now",
            "frequency": "DAILY",
            "geo": "TH",
            "hl": "th",
            "api_key": SERPAPI_KEY,
        }
        with httpx.Client(timeout=15) as client:
            resp = client.get(SERPAPI_URL, params=params)

        if resp.status_code != 200:
            print(f"[serpapi_trends] error {resp.status_code}: {resp.text[:200]}")
            return {"success": False, "message": f"❌ ดึง Trending ไม่ได้ครับ (error {resp.status_code})"}

        data = resp.json()
        trending_searches = data.get("trending_searches", [])

        if not trending_searches:
            return {"success": False, "message": "❌ ไม่พบข้อมูล Trending ในขณะนี้ครับ ลองอีกครั้งทีหลังนะครับ"}

        bkk = pytz.timezone("Asia/Bangkok")
        now = datetime.now(bkk)
        date_thai = f"{now.day} {_THAI_MONTHS[now.month]} {now.year + 543}"

        lines = [
            f"🔥 Trending ในไทยวันนี้",
            f"📅 {date_thai}\n",
        ]

        for i, item in enumerate(trending_searches[:10], 1):
            query = item.get("query", "")
            volume = item.get("search_volume", "")
            if not query:
                continue
            line = f"{i}. {query}"
            if volume:
                line += f"  ({volume})"
            lines.append(line)

        result = {"success": True, "message": "\n".join(lines)}
        _cache[cache_key] = {"data": result, "expires_at": time.time() + CACHE_TTL}
        return result

    except Exception as e:
        print(f"[serpapi_trends] error: {e}")
        return {"success": False, "message": "❌ ดึง Trending ไม่ได้ครับ ลองอีกครั้งทีหลังนะครับ"}
