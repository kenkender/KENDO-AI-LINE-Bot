import calendar as cal
from datetime import datetime
import pytz
from db.client import get_sheet_client, get_or_create_sheet


def _bills_sheet(spreadsheet):
    return get_or_create_sheet(
        spreadsheet, "bills",
        ["source_user_id", "bill_name", "amount", "due_day", "status", "last_reminded", "created_at"]
    )


def add_bill(user_id: str, name: str, amount: float, due_day: int) -> bool:
    try:
        spreadsheet = get_sheet_client()
        sheet = _bills_sheet(spreadsheet)
        now = datetime.now(pytz.timezone("Asia/Bangkok")).isoformat()
        sheet.append_row([user_id, name, amount, due_day, "ACTIVE", "", now])
        return True
    except Exception as e:
        print(f"[db.bills] add_bill error: {e}")
        return False


def list_bills(user_id: str) -> list:
    try:
        spreadsheet = get_sheet_client()
        sheet = _bills_sheet(spreadsheet)
        records = sheet.get_all_records()
        return [
            {"row_index": i + 2, "name": r.get("bill_name", ""),
             "amount": float(r.get("amount", 0) or 0), "due_day": int(r.get("due_day", 0) or 0)}
            for i, r in enumerate(records)
            if r.get("source_user_id") == user_id and r.get("status") == "ACTIVE"
        ]
    except Exception as e:
        print(f"[db.bills] list_bills error: {e}")
        return []


def delete_bill(user_id: str, keyword: str) -> dict:
    try:
        spreadsheet = get_sheet_client()
        sheet = _bills_sheet(spreadsheet)
        records = sheet.get_all_records()
        kw = keyword.lower()
        matched = [
            (i + 2, r) for i, r in enumerate(records)
            if r.get("source_user_id") == user_id and r.get("status") == "ACTIVE"
            and kw in r.get("bill_name", "").lower()
        ]
        if not matched:
            return {"success": False}
        row_idx, r = matched[0]
        sheet.update_cell(row_idx, 5, "DELETED")
        return {"success": True, "name": r.get("bill_name", "")}
    except Exception as e:
        print(f"[db.bills] delete_bill error: {e}")
        return {"success": False}


def get_due_bills() -> list:
    try:
        spreadsheet = get_sheet_client()
        sheet = _bills_sheet(spreadsheet)
        records = sheet.get_all_records()
        now = datetime.now(pytz.timezone("Asia/Bangkok"))
        today_day = now.day
        today_str = now.strftime("%Y-%m-%d")
        days_in_month = cal.monthrange(now.year, now.month)[1]
        result = []
        for i, r in enumerate(records):
            if r.get("status") != "ACTIVE":
                continue
            due_day = int(r.get("due_day", 0) or 0)
            if not due_day or r.get("last_reminded") == today_str:
                continue
            days_until = due_day - today_day
            if days_until < 0:
                days_until = (days_in_month - today_day) + due_day
            if days_until in (0, 3):
                result.append({
                    "row_index": i + 2,
                    "user_id": r.get("source_user_id", ""),
                    "name": r.get("bill_name", ""),
                    "amount": float(r.get("amount", 0) or 0),
                    "due_day": due_day,
                    "days_until": days_until,
                })
        return result
    except Exception as e:
        print(f"[db.bills] get_due_bills error: {e}")
        return []


def mark_bill_reminded(row_index: int, date_str: str) -> bool:
    try:
        spreadsheet = get_sheet_client()
        sheet = _bills_sheet(spreadsheet)
        sheet.update_cell(row_index, 6, date_str)
        return True
    except Exception as e:
        print(f"[db.bills] mark_bill_reminded error: {e}")
        return False
