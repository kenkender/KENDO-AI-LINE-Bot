"""
db_supabase/notes.py
NOTE + REMINDER — รวมกันใน table reminders (เพราะ structure เดียวกัน)
"""
import re
import calendar as cal
from datetime import datetime, timedelta
from typing import Optional
import pytz

from db_supabase.client import get_supabase
from db_supabase.users import get_user_id, get_or_create_user


_BKK = pytz.timezone("Asia/Bangkok")


def append_note(line_user_id: str, raw_message: str, parsed: dict,
                 calendar_event_id: str = "", status: str = "OK") -> bool:
    """บันทึก NOTE หรือ REMINDER (โครงสร้างเดียวกัน)"""
    try:
        user_id = get_or_create_user(line_user_id)
        if not user_id:
            return False

        sb = get_supabase()
        sb.table("reminders").insert({
            "user_id": user_id,
            "note": parsed.get("note", ""),
            "raw_message": raw_message,
            "reminder_datetime": parsed.get("reminder_datetime") or None,
            "reminder_extras": parsed.get("reminder_extras") or "",
            "recurrence": parsed.get("recurrence") or "",
            "calendar_event_id": calendar_event_id or "",
            "status": status,
        }).execute()
        return True
    except Exception as e:
        print(f"[db_supabase.notes] append_note error: {e}")
        return False


def get_pending_reminders() -> list:
    """ดึง reminders ที่ถึงเวลา (status='OK', อยู่ในช่วง -60 ถึง +300 วินาที)"""
    try:
        now = datetime.now(_BKK)
        # ใช้ range query ที่ database — เร็วกว่ามาก
        lower = (now - timedelta(seconds=60)).isoformat()
        upper = (now + timedelta(seconds=300)).isoformat()

        sb = get_supabase()
        result = sb.table("reminders").select(
            "id,note,reminder_datetime,reminder_extras,recurrence,users(line_user_id)"
        ).eq("status", "OK").gte("reminder_datetime", lower).lte("reminder_datetime", upper).execute()

        out = []
        for r in (result.data or []):
            users_obj = r.get("users") or {}
            line_uid = users_obj.get("line_user_id") if isinstance(users_obj, dict) else None
            if not line_uid:
                continue
            out.append({
                "row_index": r["id"],  # legacy field name, value = pg row id
                "user_id": line_uid,
                "note": r.get("note", ""),
                "reminder_datetime": r.get("reminder_datetime", ""),
                "reminder_extras": r.get("reminder_extras", "") or "",
                "recurrence": r.get("recurrence", "") or "",
            })
        return out
    except Exception as e:
        print(f"[db_supabase.notes] get_pending_reminders error: {e}")
        return []


def mark_reminder_sent(row_index: int) -> bool:
    try:
        sb = get_supabase()
        sb.table("reminders").update({"status": "SENT"}).eq("id", row_index).execute()
        return True
    except Exception as e:
        print(f"[db_supabase.notes] mark_reminder_sent error: {e}")
        return False


def get_active_reminders(line_user_id: str) -> list:
    """ดึง reminders ที่ status='OK' ของ user"""
    try:
        user_id = get_user_id(line_user_id)
        if not user_id:
            return []
        sb = get_supabase()
        result = sb.table("reminders").select(
            "id,note,reminder_datetime,calendar_event_id"
        ).eq("user_id", user_id).eq("status", "OK").order("reminder_datetime").execute()
        return [
            {
                "row_index": r["id"],
                "note": r.get("note", ""),
                "reminder_datetime": r.get("reminder_datetime", ""),
                "calendar_event_id": r.get("calendar_event_id", "") or "",
            }
            for r in (result.data or [])
        ]
    except Exception as e:
        print(f"[db_supabase.notes] get_active_reminders error: {e}")
        return []


def cancel_reminder(row_index: int) -> bool:
    try:
        sb = get_supabase()
        sb.table("reminders").update({"status": "CANCELLED"}).eq("id", row_index).execute()
        return True
    except Exception as e:
        print(f"[db_supabase.notes] cancel_reminder error: {e}")
        return False


def get_today_reminders(line_user_id: str) -> list:
    """ดึง reminders ของวันนี้ — ใช้กับ briefing"""
    try:
        user_id = get_user_id(line_user_id)
        if not user_id:
            return []
        now = datetime.now(_BKK)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1) - timedelta(seconds=1)

        sb = get_supabase()
        result = sb.table("reminders").select("note,reminder_datetime") \
            .eq("user_id", user_id).eq("status", "OK") \
            .gte("reminder_datetime", start.isoformat()) \
            .lte("reminder_datetime", end.isoformat()) \
            .order("reminder_datetime").execute()

        out = []
        for r in (result.data or []):
            dt_str = str(r.get("reminder_datetime", ""))
            out.append({
                "note": r.get("note", ""),
                "time": dt_str[11:16] if len(dt_str) >= 16 else "",
            })
        return out
    except Exception as e:
        print(f"[db_supabase.notes] get_today_reminders error: {e}")
        return []


def create_recurring_reminder(line_user_id: str, display_note: str, current_dt: datetime,
                                recurrence: str, extras: str = "") -> bool:
    """สร้าง reminder ซ้ำสำหรับ cycle ถัดไป — daily/weekly:N/monthly:N"""
    try:
        user_id = get_or_create_user(line_user_id)
        if not user_id:
            return False

        next_dt = None
        if recurrence == "daily":
            next_dt = current_dt + timedelta(days=1)
        elif recurrence.startswith("weekly:"):
            target_wd = int(recurrence.split(":")[1]) - 1
            days_ahead = (target_wd - current_dt.weekday()) % 7 or 7
            next_dt = current_dt + timedelta(days=days_ahead)
        elif recurrence.startswith("monthly:"):
            target_day = int(recurrence.split(":")[1])
            if current_dt.month == 12:
                ny, nm = current_dt.year + 1, 1
            else:
                ny, nm = current_dt.year, current_dt.month + 1
            next_dt = current_dt.replace(
                year=ny, month=nm,
                day=min(target_day, cal.monthrange(ny, nm)[1]),
            )
        if not next_dt:
            return False

        sb = get_supabase()
        sb.table("reminders").insert({
            "user_id": user_id,
            "note": display_note,
            "raw_message": f"[recurring] {display_note}",
            "reminder_datetime": next_dt.isoformat(),
            "reminder_extras": extras or "",
            "recurrence": recurrence,
            "calendar_event_id": "",
            "status": "OK",
        }).execute()
        return True
    except Exception as e:
        print(f"[db_supabase.notes] create_recurring_reminder error: {e}")
        return False
