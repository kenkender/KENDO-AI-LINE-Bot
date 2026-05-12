"""
db_supabase/client.py
Singleton Supabase client (service_role) สำหรับ backend
"""
import os
from functools import lru_cache
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    """คืน Supabase client (cached) — ใช้ service_role bypass RLS"""
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError(
            "Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in .env / env vars"
        )
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


def is_supabase_configured() -> bool:
    """เช็คว่าตั้งค่า env แล้วหรือยัง — ใช้สำหรับ dual-write fallback"""
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)
