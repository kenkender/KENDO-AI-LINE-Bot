"""
db_supabase/bills.py — บิลรายเดือน
"""
import calendar as cal
from datetime import datetime
import pytz

from db_supabase.client import get_supabase
from db_supabase.users import get_user_id, get_or_create_user


def _to_float(v) -> float:
    try:
        return float(v) if v not in (None, "", "None") else 0.0
    except (ValueError, TypeError):
        return 0.0


def add_bill(line_user_id: str, name: str, amount: float, due_day: int) -> bool:
    try:
        user_id = get_or_create_user(line_user_id)
        if not user_id:
            return False
        sb = get_supabase()
        sb.table("bills").insert({
            "user_id": user_id,
            "bill_name": name,
            "amount": amount,
            "due_day": int(due_day),
            "status": "ACTIVE",
        }).execute()
        return True
    except Exception as e:
        print(f"[db_supabase.bills] add_bill error: {e}")
        return False


def list_bills(line_user_id: str) -> list:
    try:
        user_id = get_user_id(line_user_id)
        if not user_id:
            return []
        sb = get_supabase()
        result = sb.table("bills").select("id,bill_name,amount,due_day") \
            .eq("user_id", user_id).eq("status", "ACTIVE") \
            .order("due_day").execute()
        return [
            {
                "row_index": r["id"],
                "name": r.get("bill_name", ""),
                "amount": _to_float(r.get("amount")),
                "due_day": int(r.get("due_day") or 0),
            }
            for r in (result.data or [])
        ]
    except Exception as e:
        print(f"[db_supabase.bills] list_bills error: {e}")
        return []


def delete_bill(line_user_id: str, keyword: str) -> dict:
    try:
        user_id = get_user_id(line_user_id)
        if not user_id:
            return {"success": False}

        sb = get_supabase()
        kw = (keyword or "").lower()
        result = sb.table("bills").select("id,bill_name") \
            .eq("user_id", user_id).eq("status", "ACTIVE") \
            .ilike("bill_name", f"%{kw}%").limit(1).execute()
        matched = result.data or []
        if not matched:
            return {"success": False}
        sb.table("bills").update({"status": "DELETED"}).eq("id", matched[0]["id"]).execute()
        return {"success": True, "name": matched[0].get("bill_name", "")}
    except Exception as e:
        print(f"[db_supabase.bills] delete_bill error: {e}")
        return {"success": False}


def get_due_bills() -> list:
    """คืน bills ที่ครบกำหนดวันนี้หรืออีก 3 วัน — ทุก user"""
    try:
        bkk = pytz.timezone("Asia/Bangkok")
        now = datetime.now(bkk)
        today_day = now.day
        today_str = now.strftime("%Y-%m-%d")
        days_in_month = cal.monthrange(now.year, now.month)[1]

        sb = get_supabase()
        result = sb.table("bills").select(
            "id,bill_name,amount,due_day,last_reminded,users(line_user_id)"
        ).eq("status", "ACTIVE").execute()

        out = []
        for r in (result.data or []):
            users_obj = r.get("users") or {}
            line_uid = users_obj.get("line_user_id") if isinstance(users_obj, dict) else None
            if not line_uid:
                continue
            if (r.get("last_reminded") or "") == today_str:
                continue
            due_day = int(r.get("due_day") or 0)
            if not due_day:
                continue
            days_until = due_day - today_day
            if days_until < 0:
                days_until = (days_in_month - today_day) + due_day
            if days_until in (0, 3):
                out.append({
                    "row_index": r["id"],
                    "user_id": line_uid,
                    "name": r.get("bill_name", ""),
                    "amount": _to_float(r.get("amount")),
                    "due_day": due_day,
                    "days_until": days_until,
                })
        return out
    except Exception as e:
        print(f"[db_supabase.bills] get_due_bills error: {e}")
        return []


def mark_bill_reminded(row_index: int, date_str: str) -> bool:
    try:
        sb = get_supabase()
        sb.table("bills").update({"last_reminded": date_str}).eq("id", row_index).execute()
        return True
    except Exception as e:
        print(f"[db_supabase.bills] mark_bill_reminded error: {e}")
        return False
