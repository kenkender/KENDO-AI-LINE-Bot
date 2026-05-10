"""
lottery_service.py
ดึงผลสลากกินแบ่งรัฐบาลไทยจาก lotto.api.rayriffy.com (JSON API)
Cache: 1 ชั่วโมง
"""
import httpx
import time

_cache: dict = {}
CACHE_TTL = 3600  # 1 hour

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}


def _cache_get(key: str):
    e = _cache.get(key)
    if e and time.time() < e["expires_at"]:
        return e["data"]
    return None


def _cache_set(key: str, data, ttl: int = CACHE_TTL):
    _cache[key] = {"data": data, "expires_at": time.time() + ttl}


def get_lottery_result() -> dict:
    cache_key = "lottery_latest"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    url = "https://lotto.api.rayriffy.com/latest"

    try:
        with httpx.Client(timeout=15, headers=_HEADERS, follow_redirects=True) as client:
            resp = client.get(url)

        if resp.status_code != 200:
            return _fallback_no_result()

        body = resp.json()
        if body.get("status") != "success":
            return _fallback_no_result()

        data = body["response"]
        prizes = {p["id"]: p for p in data.get("prizes", [])}
        running = {r["id"]: r for r in data.get("runningNumbers", [])}

        first_list = prizes.get("prizeFirst", {}).get("number", [])
        front3 = running.get("runningNumberFrontThree", {}).get("number", [])
        back3  = running.get("runningNumberBackThree", {}).get("number", [])
        back2  = running.get("runningNumberBackTwo", {}).get("number", [])

        result = {
            "success": bool(first_list),
            "draw_date_thai": data.get("date", ""),
            "first_prize": first_list[0] if first_list else None,
            "last3": back3,
            "last2": back2[0] if back2 else None,
            "front3": front3,
        }

        if result["success"]:
            _cache_set(cache_key, result)
        return result

    except httpx.TimeoutException:
        return {"success": False, "message": "⏱ ดึงข้อมูลช้าเกินไปครับ ลองใหม่ทีหลังนะ", "draw_date_thai": ""}
    except Exception as e:
        print(f"[lottery] error: {e}")
        return _fallback_no_result()


def _fallback_no_result() -> dict:
    return {
        "success": False,
        "draw_date_thai": "",
        "message": "❌ ยังไม่พบผลสลากงวดล่าสุดครับ\nอาจยังไม่ออกผล หรือลองใหม่ทีหลังนะครับ"
    }


def format_lottery_message(result: dict) -> str:
    if not result.get("success"):
        msg = result.get("message", "")
        date_thai = result.get("draw_date_thai", "")
        if not msg:
            return f"🎫 ยังไม่พบผลสลากงวด {date_thai} ครับ" if date_thai else "🎫 ยังไม่พบผลสลากงวดล่าสุดครับ"
        return f"🎫 {msg}"

    lines = [
        "🎫 ผลสลากกินแบ่งรัฐบาล",
        f"📅 งวดวันที่ {result['draw_date_thai']}",
        "",
        f"🥇 รางวัลที่ 1:       {result.get('first_prize', 'N/A')}",
    ]

    if result.get("last2"):
        lines.append(f"🔢 เลขท้าย 2 ตัว:    {result['last2']}")

    last3 = [str(x) for x in (result.get("last3") or []) if x]
    if last3:
        lines.append(f"3️⃣  เลขท้าย 3 ตัว:    {' | '.join(last3)}")

    front3 = [str(x) for x in (result.get("front3") or []) if x]
    if front3:
        lines.append(f"3️⃣  เลขหน้า 3 ตัว:    {' | '.join(front3)}")

    lines.append("\n📡 ข้อมูล: สำนักงานสลากกินแบ่งรัฐบาล")
    return "\n".join(lines)
