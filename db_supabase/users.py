"""
db_supabase/users.py
จัดการ users table — get_or_create, tier management
"""
from typing import Optional
from db_supabase.client import get_supabase


def get_or_create_user(line_user_id: str, display_name: Optional[str] = None) -> Optional[str]:
    """คืน users.id (UUID string) ตาม line_user_id — สร้างใหม่ถ้ายังไม่มี
    ใช้ atomic SQL function `get_or_create_user` ที่ define ใน schema.sql
    """
    try:
        sb = get_supabase()
        result = sb.rpc("get_or_create_user", {
            "p_line_user_id": line_user_id,
            "p_display_name": display_name,
        }).execute()
        # result.data คือ UUID string โดยตรง
        return result.data if result.data else None
    except Exception as e:
        print(f"[db_supabase.users] get_or_create_user error: {e}")
        return None


def get_user_id(line_user_id: str) -> Optional[str]:
    """หา users.id โดยไม่สร้างใหม่ — return None ถ้ายังไม่มี"""
    try:
        sb = get_supabase()
        result = sb.table("users").select("id").eq("line_user_id", line_user_id).limit(1).execute()
        rows = result.data or []
        return rows[0]["id"] if rows else None
    except Exception as e:
        print(f"[db_supabase.users] get_user_id error: {e}")
        return None


def get_tier(line_user_id: str) -> str:
    """คืน tier ของ user: 'free' | 'premium' | 'enterprise' (default free)"""
    try:
        sb = get_supabase()
        result = sb.table("users").select("tier").eq("line_user_id", line_user_id).limit(1).execute()
        rows = result.data or []
        return rows[0]["tier"] if rows else "free"
    except Exception as e:
        print(f"[db_supabase.users] get_tier error: {e}")
        return "free"


def set_tier(line_user_id: str, tier: str, expires_at: Optional[str] = None) -> bool:
    """ตั้ง tier — expires_at เป็น ISO string หรือ None (ไม่หมดอายุ)"""
    if tier not in ("free", "premium", "enterprise"):
        return False
    try:
        sb = get_supabase()
        from datetime import datetime
        import pytz
        now = datetime.now(pytz.timezone("Asia/Bangkok")).isoformat()
        payload = {
            "tier": tier,
            "tier_started_at": now,
            "tier_expires_at": expires_at,
        }
        sb.table("users").update(payload).eq("line_user_id", line_user_id).execute()
        return True
    except Exception as e:
        print(f"[db_supabase.users] set_tier error: {e}")
        return False


def get_all_line_user_ids() -> list:
    """คืน list ของ line_user_id ทั้งหมด — ใช้สำหรับ broadcast (weekly summary, etc.)"""
    try:
        sb = get_supabase()
        result = sb.table("users").select("line_user_id").execute()
        return [r["line_user_id"] for r in (result.data or []) if r.get("line_user_id")]
    except Exception as e:
        print(f"[db_supabase.users] get_all_line_user_ids error: {e}")
        return []
