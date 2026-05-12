"""
db_supabase/interval_reminder.py
แจ้งเตือนซ้ำทุก X นาที/ชั่วโมง
"""
from datetime import datetime, timedelta
import pytz

from db_supabase.client import get_supabase
from db_supabase.users import get_user_id, get_or_create_user


_BKK = pytz.timezone("Asia/Bangkok")
MAX_PER_USER = 5


def add_interval_reminder(line_user_id: str, label: str, interval_minutes: int) -> dict:
    """เพิ่ม interval reminder — สูงสุด 5 รายการ/user"""
    try:
        try:
            interval_minutes = int(interval_minutes)
        except (TypeError, ValueError):
            return {"success": False, "message": "ระยะเวลาไม่ถูกต้องครับ ลองใหม่นะครับ"}
        if interval_minutes < 1:
            return {"success": False, "message": "ระยะเวลาต้องอย่างน้อย 1 นาทีครับ"}

        user_id = get_or_create_user(line_user_id)
        if not user_id:
            return {"success": False, "message": "เกิดข้อผิดพลาดครับ"}

        sb = get_supabase()
        # นับ active reminders
        count_res = sb.table("interval_reminders").select("id", count="exact") \
            .eq("user_id", user_id).eq("active", True).execute()
        active_count = count_res.count or 0
        if active_count >= MAX_PER_USER:
            return {
                "success": False,
                "message": f"มีการแจ้งเตือนที่ใช้งานอยู่ {active_count} รายการแล้วครับ "
                           f"(สูงสุด {MAX_PER_USER} รายการ)\nกรุณายกเลิกรายการเก่าก่อนนะครับ",
            }

        now = datetime.now(_BKK)
        next_fire = (now + timedelta(minutes=interval_minutes)).isoformat()
        sb.table("interval_reminders").insert({
            "user_id": user_id,
            "label": label,
            "interval_minutes": interval_minutes,
            "next_fire": next_fire,
            "active": True,
        }).execute()
        return {"success": True}
    except Exception as e:
        print(f"[db_supabase.interval] add error: {e}")
        return {"success": False, "message": "เกิดข้อผิดพลาดครับ ลองใหม่นะครับ"}


def get_active_interval_reminders(line_user_id: str) -> list:
    try:
        user_id = get_user_id(line_user_id)
        if not user_id:
            return []
        sb = get_supabase()
        result = sb.table("interval_reminders").select("id,label,interval_minutes,next_fire") \
            .eq("user_id", user_id).eq("active", True).execute()
        return [
            {
                "row_index": r["id"],
                "label": r.get("label", ""),
                "interval_minutes": int(r.get("interval_minutes") or 0),
                "next_fire": r.get("next_fire", ""),
            }
            for r in (result.data or [])
        ]
    except Exception as e:
        print(f"[db_supabase.interval] get_active error: {e}")
        return []


def get_all_due_interval_reminders() -> list:
    """คืน interval reminders ที่ถึงเวลาแล้ว (next_fire <= now) — ทุก user"""
    try:
        now = datetime.now(_BKK)
        sb = get_supabase()
        result = sb.table("interval_reminders").select(
            "id,label,interval_minutes,next_fire,users(line_user_id)"
        ).eq("active", True).lte("next_fire", now.isoformat()).execute()

        out = []
        for r in (result.data or []):
            users_obj = r.get("users") or {}
            line_uid = users_obj.get("line_user_id") if isinstance(users_obj, dict) else None
            if not line_uid:
                continue
            out.append({
                "row_index": r["id"],
                "user_id": line_uid,
                "label": r.get("label", ""),
                "interval_minutes": int(r.get("interval_minutes") or 0),
            })
        return out
    except Exception as e:
        print(f"[db_supabase.interval] get_due error: {e}")
        return []


def update_next_fire(row_index: int, interval_minutes: int):
    try:
        sb = get_supabase()
        next_fire = (datetime.now(_BKK) + timedelta(minutes=interval_minutes)).isoformat()
        sb.table("interval_reminders").update({"next_fire": next_fire}).eq("id", row_index).execute()
    except Exception as e:
        print(f"[db_supabase.interval] update_next_fire error: {e}")


def cancel_interval_reminder_by_label(line_user_id: str, label: str) -> dict:
    try:
        user_id = get_user_id(line_user_id)
        if not user_id:
            return {"success": False, "cancelled_count": 0}
        sb = get_supabase()
        kw = (label or "").lower()
        result = sb.table("interval_reminders").select("id") \
            .eq("user_id", user_id).eq("active", True) \
            .ilike("label", f"%{kw}%").execute()
        matched = result.data or []
        cancelled = 0
        for r in matched:
            sb.table("interval_reminders").update({"active": False}).eq("id", r["id"]).execute()
            cancelled += 1
        return {"success": True, "cancelled_count": cancelled}
    except Exception as e:
        print(f"[db_supabase.interval] cancel error: {e}")
        return {"success": False, "cancelled_count": 0}


def cancel_all_interval_reminders(line_user_id: str) -> int:
    try:
        user_id = get_user_id(line_user_id)
        if not user_id:
            return 0
        sb = get_supabase()
        result = sb.table("interval_reminders").select("id") \
            .eq("user_id", user_id).eq("active", True).execute()
        matched = result.data or []
        for r in matched:
            sb.table("interval_reminders").update({"active": False}).eq("id", r["id"]).execute()
        return len(matched)
    except Exception as e:
        print(f"[db_supabase.interval] cancel_all error: {e}")
        return 0
