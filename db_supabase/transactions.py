"""
db_supabase/transactions.py
EXPENSE / INCOME — CRUD operations
"""
from datetime import datetime
from typing import Optional
import pytz

from db_supabase.client import get_supabase
from db_supabase.users import get_or_create_user


def _to_float(v) -> float:
    try:
        return float(v) if v not in (None, "", "None") else 0.0
    except (ValueError, TypeError):
        return 0.0


def append_transaction(line_user_id: str, raw_message: str, parsed: dict,
                        status: str = "OK", display_name: str = "") -> bool:
    """บันทึก EXPENSE/INCOME — auto-create user ถ้ายังไม่มี"""
    try:
        user_id = get_or_create_user(line_user_id, display_name)
        if not user_id:
            return False

        intent = parsed.get("intent", "")
        if intent not in ("EXPENSE", "INCOME"):
            return False

        sb = get_supabase()
        ts = datetime.now(pytz.timezone("Asia/Bangkok")).isoformat()
        sb.table("transactions").insert({
            "user_id": user_id,
            "intent": intent,
            "amount": _to_float(parsed.get("amount", 0)),
            "currency": parsed.get("currency") or "THB",
            "category": parsed.get("category") or "อื่นๆ",
            "note": parsed.get("note", ""),
            "raw_message": raw_message,
            "status": status,
            "ts": ts,
        }).execute()
        return True
    except Exception as e:
        print(f"[db_supabase.transactions] append error: {e}")
        return False


def delete_last_transaction(line_user_id: str) -> dict:
    """ลบรายการล่าสุด (mark status='DELETED')"""
    try:
        from db_supabase.users import get_user_id
        user_id = get_user_id(line_user_id)
        if not user_id:
            return {"success": False}

        sb = get_supabase()
        result = sb.table("transactions").select("*").eq("user_id", user_id) \
            .eq("status", "OK").order("ts", desc=True).limit(1).execute()
        rows = result.data or []
        if not rows:
            return {"success": False}

        last = rows[0]
        sb.table("transactions").update({"status": "DELETED"}).eq("id", last["id"]).execute()
        return {
            "success": True,
            "note": last.get("note", ""),
            "amount": _to_float(last.get("amount")),
            "intent": last.get("intent", ""),
        }
    except Exception as e:
        print(f"[db_supabase.transactions] delete error: {e}")
        return {"success": False}


def search_transactions(line_user_id: str, keyword: str) -> list:
    """ค้นหาในรายการ EXPENSE/INCOME ตาม keyword"""
    try:
        from db_supabase.users import get_user_id
        user_id = get_user_id(line_user_id)
        if not user_id:
            return []

        sb = get_supabase()
        kw = keyword.lower()
        # ใช้ ilike ครอบ note + category + raw_message ผ่าน or_
        # Supabase or_ syntax: or='(note.ilike.%kw%,category.ilike.%kw%,raw_message.ilike.%kw%)'
        result = sb.table("transactions").select(
            "intent,note,amount,category,ts"
        ).eq("user_id", user_id).neq("status", "DELETED").or_(
            f"note.ilike.%{kw}%,category.ilike.%{kw}%,raw_message.ilike.%{kw}%"
        ).in_("intent", ["EXPENSE", "INCOME"]).order("ts", desc=True).limit(20).execute()

        results = []
        for r in (result.data or []):
            results.append({
                "intent": r.get("intent"),
                "note": r.get("note", ""),
                "amount": _to_float(r.get("amount")),
                "category": r.get("category", ""),
                "timestamp": (r.get("ts", "") or "")[:10],
            })
        # คืนรายการเก่าสุดก่อน (เพื่อให้ caller slice [-10:] ใช้ได้เหมือนเดิม)
        return list(reversed(results))
    except Exception as e:
        print(f"[db_supabase.transactions] search error: {e}")
        return []
