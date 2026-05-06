"""
trend_service.py
ประเด็นร้อนและ trending ไทยวันนี้ ใช้ Brave Search News API
(ไม่มี official X/TikTok free API — ใช้ข่าวที่กำลังถูกพูดถึงมากที่สุดแทน)
"""

import httpx
import os
import time
import re
from dotenv import load_dotenv

load_dotenv()

BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")

_cache: dict = {}
CACHE_TTL = 20 * 60  # 20 นาที (trending เปลี่ยนเร็ว)


def _cache_get(key: str):
    e = _cache.get(key)
    if e and time.time() < e["expires_at"]:
        return e["data"]
    return None


def _cache_set(key: str, data):
    _cache[key] = {"data": data, "expires_at": time.time() + CACHE_TTL}


# ── queries สำหรับดึง trending จาก Brave News ────────────────────────────────
TREND_QUERIES = {
    "general": [
        "ประเด็นร้อน ไทย วันนี้",
        "trending thailand today",
    ],
    "x": [
        "twitter X trending ไทย วันนี้",
        "hashtag ไทย ติดเทรนด์",
    ],
    "tiktok": [
        "tiktok ติดเทรนด์ ไทย วันนี้",
        "viral tiktok thailand",
    ],
}


def _brave_search(query: str, count: int = 8) -> list[dict]:
    """เรียก Brave News Search แล้วคืน list of {title, source, url}"""
    if not BRAVE_API_KEY:
        return []

    cache_key = f"trend_{query}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    results = []
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                "https://api.search.brave.com/res/v1/news/search",
                headers={
                    "X-Subscription-Token": BRAVE_API_KEY,
                    "Accept": "application/json",
                },
                params={"q": query, "count": count, "search_lang": "th"},
            )
        if resp.status_code == 200:
            for item in resp.json().get("results", []):
                title = item.get("title", "").strip()
                source = item.get("source", {}).get("name", "")
                url = item.get("url", "")
                if title:
                    results.append({"title": title, "source": source, "url": url})
        else:
            print(f"[trend_service] Brave error: {resp.status_code}")
    except Exception as e:
        print(f"[trend_service] error: {e}")

    _cache_set(cache_key, results)
    return results


def _dedupe(items: list[dict], limit: int) -> list[dict]:
    """กรองหัวข้อซ้ำด้วย fuzzy title comparison"""
    seen: list[str] = []
    unique: list[dict] = []
    for item in items:
        # ย่อ title ให้สั้นสำหรับเปรียบเทียบ
        short = re.sub(r"[^฀-๿a-zA-Z0-9]", "", item["title"])[:30]
        if not any(short in s or s in short for s in seen):
            seen.append(short)
            unique.append(item)
        if len(unique) >= limit:
            break
    return unique


def get_trending(platform: str = "general") -> dict:
    """
    ดึงประเด็นร้อน/trending
    platform: "general" | "x" | "tiktok"
    """
    if not BRAVE_API_KEY:
        return {
            "success": False,
            "message": "❌ ยังไม่ได้ตั้งค่า BRAVE_API_KEY ครับ",
        }

    queries = TREND_QUERIES.get(platform, TREND_QUERIES["general"])

    all_results: list[dict] = []
    for q in queries:
        all_results.extend(_brave_search(q, count=8))

    items = _dedupe(all_results, limit=8)

    if not items:
        return {
            "success": False,
            "message": "❌ ไม่พบข้อมูล trending ในขณะนี้ครับ ลองใหม่อีกทีนะครับ",
        }

    labels = {
        "general": "🔥 ประเด็นร้อนไทยวันนี้",
        "x":       "🐦 X (Twitter) Trending ไทยวันนี้",
        "tiktok":  "🎵 TikTok Trending ไทยวันนี้",
    }
    header = labels.get(platform, "🔥 ประเด็นร้อนวันนี้")

    lines = [f"{header}\n"]
    for i, item in enumerate(items, 1):
        source = f" — {item['source']}" if item["source"] else ""
        lines.append(f"{i}. {item['title']}{source}")

    lines.append("\n⚠️ ข้อมูลจากข่าวที่กำลังถูกพูดถึงมากที่สุด ณ ขณะนี้")

    return {"success": True, "message": "\n".join(lines).strip()}


if __name__ == "__main__":
    for p in ["general", "x", "tiktok"]:
        r = get_trending(p)
        print(f"\n=== {p} ===")
        print("success:", r["success"])
