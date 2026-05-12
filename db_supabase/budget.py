"""
db_supabase/budget.py
Budget, savings goal, budget warning state
"""
from datetime import datetime
from typing import Optional
import pytz

from db_supabase.client import get_supabase
from db_supabase.users import get_user_id, get_or_create_user
from db_supabase.summary import get_summary


def _to_float(v) -> float:
    try:
        return float(v) if v not in (None, "", "None") else 0.0
    except (ValueError, TypeError):
        return 0.0


def set_budget(line_user_id: str, amount: float) -> bool:
    try:
        user_id = get_or_create_user(line_user_id)
        if not user_id:
            return False
        sb = get_supabase()
        sb.table("settings").upsert({
            "user_id": user_id,
            "budget": amount,
        }).execute()
        return True
    except Exception as e:
        print(f"[db_supabase.budget] set_budget error: {e}")
        return False


def get_budget_status(line_user_id: str) -> dict:
    try:
        user_id = get_user_id(line_user_id)
        if not user_id:
            return {"budget": 0, "expense": 0, "remaining": 0}

        sb = get_supabase()
        result = sb.table("settings").select("budget") \
            .eq("user_id", user_id).limit(1).execute()
        rows = result.data or []
        budget = _to_float(rows[0].get("budget")) if rows else 0.0

        summary = get_summary(line_user_id=line_user_id)
        expense = summary.get("total_expense", 0) if summary.get("success") else 0
        return {"budget": budget, "expense": expense, "remaining": budget - expense}
    except Exception as e:
        print(f"[db_supabase.budget] get_budget_status error: {e}")
        return {"budget": 0, "expense": 0, "remaining": 0}


def set_savings_goal(line_user_id: str, amount: float) -> bool:
    try:
        user_id = get_or_create_user(line_user_id)
        if not user_id:
            return False
        sb = get_supabase()
        sb.table("settings").upsert({
            "user_id": user_id,
            "savings_goal": amount,
        }).execute()
        return True
    except Exception as e:
        print(f"[db_supabase.budget] set_savings_goal error: {e}")
        return False


def get_savings_status(line_user_id: str) -> dict:
    try:
        user_id = get_user_id(line_user_id)
        if not user_id:
            return {"goal": 0, "saved": 0, "remaining": 0}
        sb = get_supabase()
        result = sb.table("settings").select("savings_goal") \
            .eq("user_id", user_id).limit(1).execute()
        rows = result.data or []
        goal = _to_float(rows[0].get("savings_goal")) if rows else 0.0

        summary = get_summary(line_user_id=line_user_id)
        balance = summary.get("balance", 0) if summary.get("success") else 0
        return {
            "goal": goal,
            "saved": max(balance, 0),
            "remaining": max(goal - balance, 0),
        }
    except Exception as e:
        print(f"[db_supabase.budget] get_savings_status error: {e}")
        return {"goal": 0, "saved": 0, "remaining": 0}


def get_budget_warn_state(line_user_id: str, month_key: str) -> set:
    """คืน set ของ threshold % ที่แจ้งเตือนไปแล้ว เช่น {50, 75}"""
    try:
        user_id = get_user_id(line_user_id)
        if not user_id:
            return set()
        sb = get_supabase()
        result = sb.table("budget_warnings").select("warned_levels") \
            .eq("user_id", user_id).eq("month_key", month_key).limit(1).execute()
        rows = result.data or []
        if not rows:
            return set()
        levels_str = str(rows[0].get("warned_levels", "") or "")
        return {int(x) for x in levels_str.split(",") if x.strip().isdigit()}
    except Exception as e:
        print(f"[db_supabase.budget] get_budget_warn_state error: {e}")
        return set()


def mark_budget_warned(line_user_id: str, month_key: str, level: int) -> bool:
    try:
        user_id = get_or_create_user(line_user_id)
        if not user_id:
            return False
        existing = get_budget_warn_state(line_user_id, month_key)
        existing.add(int(level))
        new_levels = ",".join(str(l) for l in sorted(existing))

        sb = get_supabase()
        sb.table("budget_warnings").upsert({
            "user_id": user_id,
            "month_key": month_key,
            "warned_levels": new_levels,
        }).execute()
        return True
    except Exception as e:
        print(f"[db_supabase.budget] mark_budget_warned error: {e}")
        return False
