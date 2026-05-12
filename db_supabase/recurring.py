"""
db_supabase/recurring.py — รายจ่ายซ้ำ (subscriptions)
"""
from db_supabase.client import get_supabase
from db_supabase.users import get_user_id, get_or_create_user


def _to_float(v) -> float:
    try:
        return float(v) if v not in (None, "", "None") else 0.0
    except (ValueError, TypeError):
        return 0.0


def add_recurring_items(line_user_id: str, items: list) -> int:
    """เพิ่มหลายรายการพร้อมกัน — items = [{name, amount, category?}, ...]
    คืนจำนวนที่เพิ่มสำเร็จ"""
    try:
        user_id = get_or_create_user(line_user_id)
        if not user_id:
            return 0
        rows = []
        for it in items or []:
            name = (it.get("name") or "").strip()
            amount = _to_float(it.get("amount"))
            if not name or amount <= 0:
                continue
            rows.append({
                "user_id": user_id,
                "name": name,
                "amount": amount,
                "category": it.get("category") or "อื่นๆ",
                "status": "ACTIVE",
            })
        if not rows:
            return 0
        sb = get_supabase()
        sb.table("recurring_expenses").insert(rows).execute()
        return len(rows)
    except Exception as e:
        print(f"[db_supabase.recurring] add error: {e}")
        return 0


def list_recurring_items(line_user_id: str) -> list:
    try:
        user_id = get_user_id(line_user_id)
        if not user_id:
            return []
        sb = get_supabase()
        result = sb.table("recurring_expenses").select("id,name,amount,category") \
            .eq("user_id", user_id).eq("status", "ACTIVE").execute()
        return [
            {
                "row_index": r["id"],
                "name": r.get("name", ""),
                "amount": _to_float(r.get("amount")),
                "category": r.get("category", "อื่นๆ"),
            }
            for r in (result.data or [])
        ]
    except Exception as e:
        print(f"[db_supabase.recurring] list error: {e}")
        return []


def delete_recurring_item(line_user_id: str, keyword: str) -> dict:
    try:
        user_id = get_user_id(line_user_id)
        if not user_id:
            return {"success": False}
        sb = get_supabase()
        kw = (keyword or "").lower()
        result = sb.table("recurring_expenses").select("id,name") \
            .eq("user_id", user_id).eq("status", "ACTIVE") \
            .ilike("name", f"%{kw}%").limit(1).execute()
        matched = result.data or []
        if not matched:
            return {"success": False}
        sb.table("recurring_expenses").update({"status": "DELETED"}) \
            .eq("id", matched[0]["id"]).execute()
        return {"success": True, "name": matched[0].get("name", "")}
    except Exception as e:
        print(f"[db_supabase.recurring] delete error: {e}")
        return {"success": False}


def get_all_recurring_users() -> list:
    """คืน list line_user_id ของ user ที่มี recurring items"""
    try:
        sb = get_supabase()
        result = sb.table("recurring_expenses").select(
            "users(line_user_id)"
        ).eq("status", "ACTIVE").execute()
        seen = set()
        out = []
        for r in (result.data or []):
            users_obj = r.get("users") or {}
            line_uid = users_obj.get("line_user_id") if isinstance(users_obj, dict) else None
            if line_uid and line_uid not in seen:
                seen.add(line_uid)
                out.append(line_uid)
        return out
    except Exception as e:
        print(f"[db_supabase.recurring] get_all_users error: {e}")
        return []
