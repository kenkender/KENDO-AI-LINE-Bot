"""
db_supabase/tasks.py — Task / Checklist
"""
from datetime import datetime
import pytz

from db_supabase.client import get_supabase
from db_supabase.users import get_user_id, get_or_create_user


def add_task(line_user_id: str, task: str) -> bool:
    try:
        user_id = get_or_create_user(line_user_id)
        if not user_id:
            return False
        sb = get_supabase()
        sb.table("tasks").insert({
            "user_id": user_id,
            "task": task,
            "status": "PENDING",
        }).execute()
        return True
    except Exception as e:
        print(f"[db_supabase.tasks] add_task error: {e}")
        return False


def list_tasks(line_user_id: str) -> list:
    try:
        user_id = get_user_id(line_user_id)
        if not user_id:
            return []
        sb = get_supabase()
        result = sb.table("tasks").select("id,task,ts") \
            .eq("user_id", user_id).eq("status", "PENDING") \
            .order("ts").execute()
        return [
            {
                "row_index": r["id"],
                "task": r.get("task", ""),
                "timestamp": (r.get("ts", "") or "")[:10],
            }
            for r in (result.data or [])
        ]
    except Exception as e:
        print(f"[db_supabase.tasks] list_tasks error: {e}")
        return []


def complete_task(line_user_id: str, keyword: str) -> dict:
    """mark task ที่ keyword match เป็น DONE"""
    try:
        user_id = get_user_id(line_user_id)
        if not user_id:
            return {"success": False, "pending": []}

        sb = get_supabase()
        kw = (keyword or "").lower()
        result = sb.table("tasks").select("id,task") \
            .eq("user_id", user_id).eq("status", "PENDING") \
            .ilike("task", f"%{kw}%").execute()
        matched = result.data or []

        if not matched:
            all_pending = sb.table("tasks").select("task") \
                .eq("user_id", user_id).eq("status", "PENDING").execute()
            return {
                "success": False,
                "pending": [r.get("task", "") for r in (all_pending.data or [])],
            }
        if len(matched) == 1:
            now = datetime.now(pytz.timezone("Asia/Bangkok")).isoformat()
            sb.table("tasks").update({
                "status": "DONE",
                "completed_at": now,
            }).eq("id", matched[0]["id"]).execute()
            return {"success": True, "task": matched[0].get("task", "")}
        return {"success": False, "ambiguous": [r.get("task", "") for r in matched]}
    except Exception as e:
        print(f"[db_supabase.tasks] complete_task error: {e}")
        return {"success": False, "pending": []}
