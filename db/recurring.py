"""
db/recurring.py — รายจ่ายซ้ำ (Recurring Expense) เช่น Netflix, Spotify, ค่าเน็ต
เก็บใน Sheet recurring_expenses
"""

from datetime import datetime
import pytz
from db.client import get_sheet_client, get_or_create_sheet
from db_supabase import safe_write
from db_supabase.recurring import (
    add_recurring_items as _sb_add_recurring,
    delete_recurring_item as _sb_delete_recurring,
)


def _recurring_sheet(spreadsheet):
    return get_or_create_sheet(
        spreadsheet, "recurring_expenses",
        ["source_user_id", "item_name", "amount", "category", "status", "created_at"]
    )


def add_recurring_items(user_id: str, items: list) -> int:
    """เพิ่มรายการซ้ำหลายรายการพร้อมกัน — คืน count ที่เพิ่มสำเร็จ"""
    try:
        spreadsheet = get_sheet_client()
        sheet = _recurring_sheet(spreadsheet)
        now = datetime.now(pytz.timezone("Asia/Bangkok")).isoformat()
        added = 0
        for item in items:
            name = str(item.get("name", "")).strip()
            amount = float(item.get("amount") or 0)
            category = str(item.get("category", "อื่นๆ")).strip() or "อื่นๆ"
            if not name or amount <= 0:
                continue
            sheet.append_row([user_id, name, amount, category, "ACTIVE", now])
            added += 1
        # Dual-write: bulk insert ไป Supabase ในครั้งเดียว
        if added > 0:
            safe_write(_sb_add_recurring, user_id, items)
        return added
    except Exception as e:
        print(f"[db.recurring] add_recurring_items error: {e}")
        return 0


def list_recurring_items(user_id: str) -> list:
    """ดึงรายการซ้ำ ACTIVE ทั้งหมดของ user"""
    try:
        spreadsheet = get_sheet_client()
        sheet = _recurring_sheet(spreadsheet)
        records = sheet.get_all_records()
        return [
            {
                "row_index": i + 2,
                "name": r.get("item_name", ""),
                "amount": float(r.get("amount", 0) or 0),
                "category": r.get("category", "อื่นๆ"),
            }
            for i, r in enumerate(records)
            if r.get("source_user_id") == user_id and r.get("status") == "ACTIVE"
        ]
    except Exception as e:
        print(f"[db.recurring] list_recurring_items error: {e}")
        return []


def delete_recurring_item(user_id: str, keyword: str) -> dict:
    """ลบรายการซ้ำที่ชื่อตรงกับ keyword"""
    try:
        spreadsheet = get_sheet_client()
        sheet = _recurring_sheet(spreadsheet)
        records = sheet.get_all_records()
        kw = keyword.lower()
        matched = [
            (i + 2, r) for i, r in enumerate(records)
            if r.get("source_user_id") == user_id
            and r.get("status") == "ACTIVE"
            and kw in r.get("item_name", "").lower()
        ]
        if not matched:
            return {"success": False}
        row_idx, r = matched[0]
        sheet.update_cell(row_idx, 5, "DELETED")
        safe_write(_sb_delete_recurring, user_id, keyword)
        return {"success": True, "name": r.get("item_name", "")}
    except Exception as e:
        print(f"[db.recurring] delete_recurring_item error: {e}")
        return {"success": False}


def get_all_recurring_users() -> list:
    """ดึง list of {user_id, items} ที่มีรายการซ้ำ ACTIVE — ใช้ใน scheduler"""
    try:
        spreadsheet = get_sheet_client()
        sheet = _recurring_sheet(spreadsheet)
        records = sheet.get_all_records()
        user_map: dict = {}
        for r in records:
            if r.get("status") != "ACTIVE":
                continue
            uid = r.get("source_user_id", "")
            if not uid:
                continue
            if uid not in user_map:
                user_map[uid] = []
            user_map[uid].append({
                "name": r.get("item_name", ""),
                "amount": float(r.get("amount", 0) or 0),
                "category": r.get("category", "อื่นๆ"),
            })
        return [{"user_id": uid, "items": items} for uid, items in user_map.items()]
    except Exception as e:
        print(f"[db.recurring] get_all_recurring_users error: {e}")
        return []
