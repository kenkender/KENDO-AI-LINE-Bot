"""
news_service.py
ระบบดึงข่าว 4 ชั้น: SerpAPI Google News → RSS Feed ไทย → Brave Search → NewsData.io
"""

import httpx
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime
import pytz
from dotenv import load_dotenv

load_dotenv()

SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")
SERPAPI_URL = "https://serpapi.com/search"
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
        ("มติชน",        "https://www.matichon.co.th/feed"),
        ("ข่าวสด",       "https://www.khaosod.co.th/feed"),
        ("The Standard", "https://thestandard.co/feed/"),
    ],
    "tech": [
        ("Blognone",     "https://www.blognone.com/node/feed"),
        ("TechTalkThai", "https://www.techtalkthai.com/feed/"),
        ("The Standard Tech", "https://thestandard.co/category/tech/feed/"),
    ],
    "crime": [
        ("มติชน อาชญากรรม", "https://www.matichon.co.th/crime/feed"),
        ("ข่าวสด อาชญากรรม", "https://www.khaosod.co.th/crime/feed"),
    ],
    "travel": [
        ("TAT News", "https://www.tatnews.org/feed/"),
        ("มติชน ท่องเที่ยว", "https://www.matichon.co.th/tag/%e0%b8%97%e0%b9%88%e0%b8%ad%e0%b8%87%e0%b9%80%e0%b8%97%e0%b8%b5%e0%b9%88%e0%b8%a2%e0%b8%a7/feed"),
    ],
    "weather": [
        ("ข่าวสด สิ่งแวดล้อม", "https://www.khaosod.co.th/around-the-world/feed"),
        ("มติชน", "https://www.matichon.co.th/feed"),
    ],
}

# map category alias → RSS key
CATEGORY_MAP = {
    "ทั่วไป": "general",
    "อาชญากรรม": "crime",
    "เทคโนโลยี": "tech",
    "ไอที": "tech",
    "ท่องเที่ยว": "travel",
    "อากาศ": "weather",
    "อุตุ": "weather",
    "สภาพอากาศ": "weather",
    "พยากรณ์": "weather",
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


# ── Layer 0: SerpAPI Google News ────────────────────────────────────────────
_SERPAPI_QUERY_MAP = {
    "general":  "ข่าวไทยวันนี้",
    "tech":     "ข่าวเทคโนโลยี IT ไทย",
    "crime":    "ข่าวอาชญากรรมไทย",
    "travel":   "ข่าวท่องเที่ยวไทย",
    "weather":  "ข่าวสภาพอากาศไทย",
    "world":    "world news today",
}


def _serpapi_news(query: str) -> list[dict]:
    """ดึงข่าวจาก SerpAPI Google News API — Layer 0"""
    if not SERPAPI_KEY:
        return []

    cache_key = f"serpapi_{query}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        params = {
            "engine": "google_news",
            "q": query,
            "gl": "TH",
            "hl": "th",
            "api_key": SERPAPI_KEY,
        }
        with httpx.Client(timeout=15) as client:
            resp = client.get(SERPAPI_URL, params=params)

        if resp.status_code != 200:
            print(f"[news_service] SerpAPI error {resp.status_code}")
            return []

        articles = []
        for item in resp.json().get("news_results", [])[:5]:
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            link = item.get("link", "")
            source_raw = item.get("source", {})
            source = source_raw.get("name", "Google News") if isinstance(source_raw, dict) else str(source_raw or "Google News")
            if title:
                articles.append({
                    "title": title,
                    "summary": snippet[:100] + "…" if len(snippet) > 100 else snippet,
                    "link": link,
                    "source": source,
                })

        _cache_set(cache_key, articles)
        return articles

    except Exception as e:
        print(f"[news_service] _serpapi_news error: {e}")
        return []


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
    """ชั้น 0: SerpAPI → ชั้น 1: RSS → ชั้น 3: NewsData fallback"""
    rss_key = CATEGORY_MAP.get(category, "general")

    # Layer 0: SerpAPI
    serpapi_query = _SERPAPI_QUERY_MAP.get(rss_key, f"ข่าวไทย {category}")
    articles = _serpapi_news(serpapi_query)

    # Layer 1: RSS fallback
    if len(articles) < 3:
        articles = (_serpapi_news(serpapi_query) + _fetch_rss(rss_key))[:5]

    # Layer 3: NewsData fallback
    if len(articles) < 3:
        nd_cat_map = {"อาชญากรรม": "crime", "ท่องเที่ยว": "tourism", "เทคโนโลยี": "technology"}
        nd_cat = nd_cat_map.get(category, "top")
        articles = (articles + _newsdata(category=nd_cat))[:5]

    return _format_response(articles, f"ข่าวไทย{category}")


def get_world_news() -> dict:
    """ชั้น 0: SerpAPI → ชั้น 2: Brave → ชั้น 3: NewsData fallback"""
    articles = _serpapi_news(_SERPAPI_QUERY_MAP["world"])
    if len(articles) < 3:
        articles = (articles + _brave_news("world news today"))[:5]
    if len(articles) < 3:
        articles = (articles + _newsdata(category="world"))[:5]
    return _format_response(articles[:5], "ข่าวต่างประเทศ")


def get_tech_news() -> dict:
    """ชั้น 0: SerpAPI → ชั้น 1: RSS Blognone+TechTalkThai → ชั้น 2: Brave"""
    articles = _serpapi_news(_SERPAPI_QUERY_MAP["tech"])
    if len(articles) < 3:
        articles = (articles + _fetch_rss("tech"))[:5]
    if len(articles) < 3:
        articles = (articles + _brave_news("เทคโนโลยี IT news"))[:5]
    return _format_response(articles[:5], "ข่าวเทคโนโลยี")


def search_news(query: str) -> dict:
    """ชั้น 0: SerpAPI → ชั้น 2: Brave → ชั้น 1: RSS กรอง keyword"""
    articles = _serpapi_news(query)

    if len(articles) < 3:
        articles = (articles + _brave_news(query))[:5]

    if len(articles) < 3:
        for rss_key in ["general", "tech", "crime"]:
            rss_arts = _fetch_rss(rss_key)
            for a in rss_arts:
                if query.lower() in a["title"].lower() or query.lower() in a["summary"].lower():
                    if a not in articles:
                        articles.append(a)

    return _format_response(articles[:5], f"ข่าว \"{query}\"")


_THAI_MONTHS_NEWS = {
    1: "มกราคม", 2: "กุมภาพันธ์", 3: "มีนาคม", 4: "เมษายน",
    5: "พฤษภาคม", 6: "มิถุนายน", 7: "กรกฎาคม", 8: "สิงหาคม",
    9: "กันยายน", 10: "ตุลาคม", 11: "พฤศจิกายน", 12: "ธันวาคม"
}


def _format_response(articles: list[dict], label: str) -> dict:
    """แปลง list of articles เป็น dict {success, message}"""
    if not articles:
        return {
            "success": False,
            "message": f"❌ ไม่พบ{label}ในขณะนี้ครับ ลองถามใหม่ภายหลังนะครับ",
        }

    bkk = pytz.timezone("Asia/Bangkok")
    now = datetime.now(bkk)
    date_thai = f"{now.day} {_THAI_MONTHS_NEWS[now.month]} {now.year + 543}"

    lines = [f"📰 {label}ล่าสุด", f"📅 ประจำวันที่ {date_thai}\n"]
    for i, a in enumerate(articles, 1):
        title   = a.get("title", "").strip()
        summary = a.get("summary", "").strip()
        source  = a.get("source", "").strip()
        link    = a.get("link", "").strip()
        line = f"{i}. {title}"
        if summary:
            line += f"\n   {summary}"
        if source:
            line += f"\n   📌 {source}"
        if link:
            line += f"\n   🔗 {link}"
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
