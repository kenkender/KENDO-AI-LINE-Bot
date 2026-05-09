"""
serpapi_search_service.py
Smart Search Combo:
  Layer 1 — Google AI Overview (ถ้ามี)
  Layer 2 — Google Search organic_results + Groq สรุป
"""

import httpx
import os
import time
from datetime import datetime
import pytz
from dotenv import load_dotenv

load_dotenv()

SERPAPI_KEY = os.getenv("SERPAPI_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
SERPAPI_URL = "https://serpapi.com/search"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

_cache: dict = {}
CACHE_TTL = 30 * 60  # 30 นาที

_THAI_MONTHS = {
    1: "มกราคม", 2: "กุมภาพันธ์", 3: "มีนาคม", 4: "เมษายน",
    5: "พฤษภาคม", 6: "มิถุนายน", 7: "กรกฎาคม", 8: "สิงหาคม",
    9: "กันยายน", 10: "ตุลาคม", 11: "พฤศจิกายน", 12: "ธันวาคม"
}


def _google_search(query: str) -> dict:
    """เรียก SerpAPI Google Search — ดึงทั้ง ai_overview + organic_results"""
    cache_key = f"gsearch_{query}"
    entry = _cache.get(cache_key)
    if entry and time.time() < entry["expires_at"]:
        return entry["data"]

    try:
        params = {
            "engine": "google",
            "q": query,
            "gl": "th",
            "hl": "th",
            "num": 5,
            "api_key": SERPAPI_KEY,
        }
        with httpx.Client(timeout=15) as client:
            resp = client.get(SERPAPI_URL, params=params)

        if resp.status_code != 200:
            print(f"[serpapi_search] error {resp.status_code}")
            return {}

        data = resp.json()
        _cache[cache_key] = {"data": data, "expires_at": time.time() + CACHE_TTL}
        return data

    except Exception as e:
        print(f"[serpapi_search] _google_search error: {e}")
        return {}


def _extract_ai_overview_text(ai_overview: dict) -> str:
    """ดึงข้อความจาก ai_overview — รองรับหลาย structure"""
    if not ai_overview:
        return ""

    # รูปแบบ text_blocks หรือ blocks
    for key in ("text_blocks", "blocks"):
        blocks = ai_overview.get(key, [])
        if blocks:
            parts = []
            for block in blocks:
                if isinstance(block, dict):
                    text = block.get("snippet") or block.get("text") or block.get("content", "")
                    if text:
                        parts.append(text.strip())
            if parts:
                return " ".join(parts)

    # fallback: text หรือ snippet ตรงๆ
    return ai_overview.get("text", "") or ai_overview.get("snippet", "")


def _ai_summarize(query: str, organic: list, answer_box: dict) -> str:
    """ให้ AI สรุป search results — ลอง DeepSeek → Groq → fallback snippet"""
    # สร้าง context จาก results
    parts = []
    if answer_box:
        ab_text = answer_box.get("answer") or answer_box.get("snippet", "")
        if ab_text:
            parts.append(f"[คำตอบตรง] {ab_text}")

    for item in organic[:4]:
        snippet = item.get("snippet", "")
        title = item.get("title", "")
        if snippet:
            parts.append(f"- {title}: {snippet}")

    if not parts:
        return ""

    context = "\n".join(parts)
    prompt = (
        f"คุณคือ KENDO AI ผู้ช่วยของ Kendo (ตำรวจท่องเที่ยว ชอบ IT)\n\n"
        f"คำถาม: {query}\n\n"
        f"ข้อมูลจาก Google Search:\n{context}\n\n"
        f"สรุปคำตอบเป็นภาษาไทยพูดธรรมดา เป็นกันเอง ไม่เกิน 200 คำ "
        f"ถ้ามีข้อมูลหลายแหล่ง เลือกที่น่าเชื่อถือที่สุดและระบุแหล่งที่มาด้วย"
    )

    # ลอง DeepSeek ก่อน
    if DEEPSEEK_API_KEY:
        try:
            with httpx.Client(timeout=20) as client:
                resp = client.post(
                    DEEPSEEK_API_URL,
                    headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
                    json={"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "temperature": 0.3, "max_tokens": 350}
                )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"[serpapi_search] DeepSeek summarize error: {e}")

    # Fallback: Groq
    if GROQ_API_KEY:
        try:
            with httpx.Client(timeout=20) as client:
                resp = client.post(
                    GROQ_API_URL,
                    headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                    json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}], "temperature": 0.3, "max_tokens": 350}
                )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"[serpapi_search] Groq summarize error: {e}")

    # Fallback สุดท้าย: คืน snippet อันแรก
    return parts[0] if parts else ""


def smart_search(query: str) -> dict:
    """
    Smart Search Combo:
      Layer 1 — AI Overview ถ้า Google มีให้
      Layer 2 — Answer Box (คำตอบสำเร็จรูปจาก Google)
      Layer 3 — Organic Results + AI สรุป
    """
    if not SERPAPI_KEY:
        return {"success": False, "message": "❌ ยังไม่ได้ตั้งค่า SERPAPI_KEY ครับ"}

    data = _google_search(query)
    if not data:
        return {"success": False, "message": f"❌ ค้นหา \"{query}\" ไม่ได้ครับ ลองอีกครั้งทีหลังนะครับ"}

    bkk = pytz.timezone("Asia/Bangkok")
    now = datetime.now(bkk)
    date_thai = f"{now.day} {_THAI_MONTHS[now.month]} {now.year + 543}"

    # ── Layer 1: AI Overview ──────────────────────────────────────────────────
    ai_overview = data.get("ai_overview")
    if ai_overview:
        overview_text = _extract_ai_overview_text(ai_overview)
        if overview_text:
            sources = ai_overview.get("sources", [])
            lines = [
                f"🤖 AI Overview",
                f"🔍 \"{query}\"",
                f"📅 {date_thai}\n",
                overview_text,
            ]
            if sources:
                lines.append("\n📌 แหล่งข้อมูล:")
                for s in sources[:3]:
                    name = s.get("title") or s.get("name", "")
                    link = s.get("link", "")
                    if name:
                        lines.append(f"  • {name}{' — ' + link if link else ''}")
            return {"success": True, "mode": "ai_overview", "message": "\n".join(lines)}

    # ── Layer 2: Answer Box ───────────────────────────────────────────────────
    answer_box = data.get("answer_box", {})
    if answer_box:
        answer = answer_box.get("answer") or answer_box.get("snippet", "")
        title = answer_box.get("title", "")
        if answer:
            lines = [
                f"🔍 ผลค้นหา: \"{query}\"",
                f"📅 {date_thai}\n",
                f"💡 {title + ': ' if title else ''}{answer}",
            ]
            source = answer_box.get("source", {})
            if isinstance(source, dict) and source.get("link"):
                lines.append(f"\n🔗 {source['link']}")
            return {"success": True, "mode": "answer_box", "message": "\n".join(lines)}

    # ── Layer 3: Organic Results + AI Summary ─────────────────────────────────
    organic = data.get("organic_results", [])
    if not organic:
        return {"success": False, "message": f"❌ ไม่พบผลการค้นหาสำหรับ \"{query}\" ครับ"}

    summary = _ai_summarize(query, organic, answer_box)

    lines = [
        f"🔍 ผลค้นหา: \"{query}\"",
        f"📅 {date_thai}\n",
    ]

    if summary:
        lines.append(summary)
        lines.append("\n📌 แหล่งข้อมูล:")
        for item in organic[:3]:
            title = item.get("title", "")
            link = item.get("link", "")
            if title and link:
                lines.append(f"  • {title}")
                lines.append(f"    🔗 {link}")
    else:
        for i, item in enumerate(organic[:3], 1):
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            link = item.get("link", "")
            lines.append(f"{i}. {title}")
            if snippet:
                lines.append(f"   {snippet[:100]}…")
            if link:
                lines.append(f"   🔗 {link}")

    return {"success": True, "mode": "search", "message": "\n".join(lines)}
