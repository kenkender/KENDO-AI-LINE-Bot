"""
db_supabase/prefs.py
User preferences — briefing time/city, recurring remind day
"""
from typing import Optional
from db_supabase.client import get_supabase
from db_supabase.users import get_user_id, get_or_create_user


def _validate_hour(h) -> Optional[int]:
    try:
        h = int(h)
        return h if 0 <= h <= 23 else None
    except (TypeError, ValueError):
        return None


def _validate_minute(m) -> int:
    try:
        m = int(m)
        return m if 0 <= m <= 59 else 0
    except (TypeError, ValueError):
        return 0


def set_briefing(line_user_id: str, hour, city: str = "", minute=0) -> bool:
    """ตั้ง briefing time + city — None = ปิด briefing"""
    try:
        user_id = get_or_create_user(line_user_id)
        if not user_id:
            return False

        sb = get_supabase()
        h_val = _validate_hour(hour)  # None = ปิด
        m_val = _validate_minute(minute) if h_val is not None else 0
        city_clean = (city or "").strip() or "กรุงเทพ"

        sb.table("user_prefs").upsert({
            "user_id": user_id,
            "briefing_hour": h_val,
            "briefing_minute": m_val,
            "briefing_city": city_clean,
        }).execute()
        return True
    except Exception as e:
        print(f"[db_supabase.prefs] set_briefing error: {e}")
        return False


def get_briefing(line_user_id: str) -> dict:
    """คืน {hour, city} ของ briefing — hour=None = ไม่ได้ตั้ง"""
    try:
        user_id = get_user_id(line_user_id)
        if not user_id:
            return {"hour": None, "city": "กรุงเทพ"}

        sb = get_supabase()
        result = sb.table("user_prefs").select("briefing_hour,briefing_minute,briefing_city") \
            .eq("user_id", user_id).limit(1).execute()
        rows = result.data or []
        if not rows:
            return {"hour": None, "city": "กรุงเทพ"}
        return {
            "hour": rows[0].get("briefing_hour"),
            "minute": rows[0].get("briefing_minute", 0) or 0,
            "city": rows[0].get("briefing_city") or "กรุงเทพ",
        }
    except Exception as e:
        print(f"[db_supabase.prefs] get_briefing error: {e}")
        return {"hour": None, "city": "กรุงเทพ"}


def get_all_briefing_users() -> list:
    """คืนทุก user ที่ตั้ง briefing — สำหรับ scheduler"""
    try:
        sb = get_supabase()
        # join user_prefs กับ users เพื่อเอา line_user_id
        result = sb.table("user_prefs").select(
            "briefing_hour,briefing_minute,briefing_city,user_id,users(line_user_id)"
        ).not_.is_("briefing_hour", "null").execute()

        out = []
        for r in (result.data or []):
            users_obj = r.get("users") or {}
            line_uid = users_obj.get("line_user_id") if isinstance(users_obj, dict) else None
            if not line_uid:
                continue
            h = r.get("briefing_hour")
            if h is None:
                continue
            out.append({
                "user_id": line_uid,  # ใช้ line_user_id เพื่อ compat กับ LINE Push API
                "hour": int(h),
                "minute": int(r.get("briefing_minute") or 0),
                "city": r.get("briefing_city") or "กรุงเทพ",
            })
        return out
    except Exception as e:
        print(f"[db_supabase.prefs] get_all_briefing_users error: {e}")
        return []


def set_recurring_remind_day(line_user_id: str, day: int) -> bool:
    """ตั้งวันแจ้งเตือนรายจ่ายซ้ำ (1-31), 0 หรือ None = ปิด"""
    try:
        user_id = get_or_create_user(line_user_id)
        if not user_id:
            return False

        try:
            d = int(day) if day else 0
        except (TypeError, ValueError):
            d = 0
        d_val = d if 1 <= d <= 31 else None

        sb = get_supabase()
        sb.table("user_prefs").upsert({
            "user_id": user_id,
            "recurring_remind_day": d_val,
        }).execute()
        return True
    except Exception as e:
        print(f"[db_supabase.prefs] set_recurring_remind_day error: {e}")
        return False


def get_recurring_remind_day(line_user_id: str) -> Optional[int]:
    try:
        user_id = get_user_id(line_user_id)
        if not user_id:
            return None
        sb = get_supabase()
        result = sb.table("user_prefs").select("recurring_remind_day") \
            .eq("user_id", user_id).limit(1).execute()
        rows = result.data or []
        return rows[0].get("recurring_remind_day") if rows else None
    except Exception as e:
        print(f"[db_supabase.prefs] get_recurring_remind_day error: {e}")
        return None


def get_all_recurring_remind_users() -> list:
    try:
        sb = get_supabase()
        result = sb.table("user_prefs").select(
            "recurring_remind_day,users(line_user_id)"
        ).not_.is_("recurring_remind_day", "null").execute()

        out = []
        for r in (result.data or []):
            users_obj = r.get("users") or {}
            line_uid = users_obj.get("line_user_id") if isinstance(users_obj, dict) else None
            day = r.get("recurring_remind_day")
            if line_uid and day:
                out.append({"user_id": line_uid, "remind_day": int(day)})
        return out
    except Exception as e:
        print(f"[db_supabase.prefs] get_all_recurring_remind_users error: {e}")
        return []
