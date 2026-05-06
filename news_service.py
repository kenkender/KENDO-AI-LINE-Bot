"""
news_service.py
ระบบดึงข่าว 3 ชั้น: RSS Feed ไทย → Brave Search → NewsData.io
"""

import httpx
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")
NEWSDATA_API_KEY = os.getenv("NEWSDATA_API_KEY", "")

# ── Cache in-memory (key → {data, expires_at}) ──────────────────────────────
_cache: dict = {}
CACHE_TTL = 15 * 60  # 15 นาที

def _cache_get(key: str):
    entry = _cache.get(key)
    if entry and time.time() < entry["expires_at"]:
        return entry["data"]
    return None

def _cache_set(key: str, data):
    _cache[key] = {"data": data, "expires_at": time.time() + CACHE_TTL}


# ── RSS Feed Sources ──────────────────────────────────────────────────────────
RSS_SOURCES = {
    "general": [
        ("ไทยรัฐ",  "https://www.thairath.co.th/rss/news.xml"),
        ("มติชน",   "https://www.matichon.co.th/feed"),
        ("ข่าวสด",  "https://www.khaosod.co.th/feed"),
    ],
    "tech": [
        ("Blognone",     "https://www.blognone.com/node/feed"),
        ("TechTalkThai", "https://www.techtalkthai.com/feed/"),
    ],
    "crime": [
        ("มติชน อาชญากรรม", "https://www.matichon.co.th/crime/feed"),
        ("ข่าวสด อาชญากรรม", "https://www.khaosod.co.th/crime/feed"),
    ],
    "travel": [
        ("TAT News", "https://www.tatnews.org/feed/"),
    ],
}

# map category alias → RSS key
CATEGORY_MAP = {
    "ทั่วไป": "general",
    "อาชญากรรม": "crime",
    "เทคโนโลยี": "tech",
    "ไอที": "tech",
    "ท่องเที่ยว": "travel",
}


def _parse_rss(xml_text: str, source_name: str) -> list[dict]:
    """Parse RSS XML → list of article dicts"""
    articles = []
    try:
        root = ET.fromstring(xml_text)
        ns = ""
        # รองรับ Atom feed ด้วย
        if root.tag.startswith("{"):
            ns_uri = root.tag.split("}")[0].strip("{")
            if "atom" in ns_uri:
                for entry in root.findall(f"{{{ns_uri}}}entry")[:5]:
                    title_el = entry.find(f"{{{ns_uri}}}title")
                    summary_el = entry.find(f"{{{ns_uri}}}summary") or entry.find(f"{{{ns_uri}}}content")
                    link_el = entry.find(f"{{{ns_uri}}}link")
                    title = title_el.text.strip() if title_el is not None and title_el.text else ""
                    summary = summary_el.text.strip() if summary_el is not None and summary_el.text else ""
                    link = link_el.get("href", "") if link_el is not None else ""
                    if title:
                        articles.append({"title": title, "summary": _clean(summary, 100), "link": link, "source": source_name})
                return articles

        # RSS 2.0 standard
        channel = root.find("channel")
        if channel is None:
            channel = root
        for item in channel.findall("item")[:5]:
            title_el = item.find("title")
            desc_el  = item.find("description")
            link_el  = item.find("link")
            title   = title_el.text.strip() if title_el is not None and title_el.text else ""
            summary = desc_el.text.strip()  if desc_el  is not None and desc_el.text  else ""
            link    = link_el.text.strip()  if link_el  is not None and link_el.text  else ""
            if title:
                articles.append({"title": title, "summary": _clean(summary, 100), "link": link, "source": source_name})
    except Exception as e:
        print(f"[news_service] _parse_rss error ({source_name}): {e}")
    return articles


def _clean(text: str, max_len: int) -> str:
    """ลบ HTML tags และตัดความยาว"""
    import re
    text = re.sub(r"<[^>]+>", "", text or "")
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&#8230;", "...").strip()
    return text[:max_len] + "…" if len(text) > max_len else text


# ── Layer 1: RSS Feed ────────────────────────────────────────────────────────
def _fetch_rss(rss_key: str) -> list[dict]:
    cache_key = f"rss_{rss_key}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    sources = RSS_SOURCES.get(rss_key, [])
    articles = []
    with httpx.Client(timeout=10, follow_redirects=True) as client:
        for name, url in sources:
            try:
                resp = client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                if resp.status_code == 200:
                    articles.extend(_parse_rss(resp.text, name))
            except Exception as e:
                print(f"[news_service] RSS fetch error ({name}): {e}")

    _cache_set(cache_key, articles)
    return articles


# ── Layer 2: Brave Search ────────────────────────────────────────────────────
def _brave_news(query: str) -> list[dict]:
    if not BRAVE_API_KEY:
        return []

    cache_key = f"brave_{query}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    articles = []
    try:
        headers = {
            "X-Subscription-Token": BRAVE_API_KEY,
            "Accept": "application/json",
        }
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                "https://api.search.brave.com/res/v1/news/search",
                headers=headers,
                params={"q": query, "count": 5, "search_lang": "th"},
            )
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("results", [])[:5]:
                articles.append({
                    "title":   item.get("title", ""),
                    "summary": _clean(item.get("description", ""), 100),
                    "link":    item.get("url", ""),
                    "source":  item.get("source", {}).get("name", "Brave"),
                })
        else:
            print(f"[news_service] Brave API error: {resp.status_code}")
    except Exception as e:
        print(f"[news_service] Brave error: {e}")

    _cache_set(cache_key, articles)
    return articles


# ── Layer 3: NewsData.io ─────────────────────────────────────────────────────
def _newsdata(query: str = "", category: str = "") -> list[dict]:
    if not NEWSDATA_API_KEY:
        return []

    cache_key = f"newsdata_{query}_{category}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    articles = []
    try:
        params = {
            "apikey":   NEWSDATA_API_KEY,
            "country":  "th",
            "language": "th",
        }
        if query:
            params["q"] = query
        if category:
            params["category"] = category

        with httpx.Client(timeout=10) as client:
            resp = client.get("https://newsdata.io/api/1/news", params=params)

        if resp.status_code == 200:
            for item in resp.json().get("results", [])[:5]:
                articles.append({
                    "title":   item.get("title", ""),
                    "summary": _clean(item.get("description", "") or "", 100),
                    "link":    item.get("link", ""),
                    "source":  item.get("source_id", "NewsData"),
                })
        else:
            print(f"[news_service] NewsData error: {resp.status_code}")
    except Exception as e:
        print(f"[news_service] NewsData error: {e}")

    _cache_set(cache_key, articles)
    return articles


# ── Public API ───────────────────────────────────────────────────────────────
def get_thai_news(category: str = "ทั่วไป") -> dict:
    """ชั้น 1: RSS → ชั้น 3: NewsData fallback"""
    rss_key = CATEGORY_MAP.get(category, "general")
    articles = _fetch_rss(rss_key)

    # fallback NewsData ถ้า RSS ได้น้อยกว่า 3
    if len(articles) < 3:
        nd_cat_map = {"อาชญากรรม": "crime", "ท่องเที่ยว": "tourism", "เทคโนโลยี": "technology"}
        nd_cat = nd_cat_map.get(category, "top")
        fallback = _newsdata(category=nd_cat)
        articles = (articles + fallback)[:5]

    return _format_response(articles, f"ข่าวไทย{category}")


def get_world_news() -> dict:
    """ชั้น 2: Brave Search ข่าวต่างประเทศ"""
    articles = _brave_news("world news today")
    if len(articles) < 3:
        articles += _newsdata(category="world")
    return _format_response(articles[:5], "ข่าวต่างประเทศ")


def get_tech_news() -> dict:
    """ชั้น 1: RSS Blognone+TechTalkThai → ชั้น 2: Brave ช่วย"""
    articles = _fetch_rss("tech")
    if len(articles) < 3:
        articles += _brave_news("เทคโนโลยี IT news")
    return _format_response(articles[:5], "ข่าวเทคโนโลยี")


def search_news(query: str) -> dict:
    """ชั้น 2: Brave Search → ชั้น 1: RSS กรอง keyword"""
    articles = _brave_news(query)

    # เสริม RSS ที่ตรงกับ query
    if len(articles) < 3:
        for rss_key in ["general", "tech", "crime"]:
            rss_arts = _fetch_rss(rss_key)
            for a in rss_arts:
                if query.lower() in a["title"].lower() or query.lower() in a["summary"].lower():
                    if a not in articles:
                        articles.append(a)

    return _format_response(articles[:5], f"ข่าว \"{query}\"")


def _format_response(articles: list[dict], label: str) -> dict:
    """แปลง list of articles เป็น dict {success, message}"""
    if not articles:
        return {
            "success": False,
            "message": f"❌ ไม่พบ{label}ในขณะนี้ครับ ลองถามใหม่ภายหลังนะครับ",
        }

    lines = [f"📰 {label}ล่าสุด\n"]
    for i, a in enumerate(articles, 1):
        title  = a.get("title", "").strip()
        source = a.get("source", "").strip()
        line = f"{i}. {title}"
        if source:
            line += f" — {source}"
        lines.append(line)

    return {"success": True, "message": "\n".join(lines).strip()}


# ── Quick test ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== ข่าวไทยทั่วไป ===")
    r = get_thai_news()
    print(r["message"])

    print("\n=== ข่าวเทคโนโลยี ===")
    r = get_tech_news()
    print(r["message"])
