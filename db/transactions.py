from datetime import datetime
import pytz
from db.client import get_sheet_client
from db_supabase import safe_write
from db_supabase.transactions import (
    append_transaction as _sb_append,
    delete_last_transaction as _sb_delete_last,
)


def _safe_float(val) -> float:
    try:
        return float(val) if val not in (None, "", "None") else 0.0
    except (ValueError, TypeError):
        return 0.0


def append_transaction(user_id: str, raw_message: str, parsed: dict, status: str = "OK") -> bool:
    try:
        spreadsheet = get_sheet_client()
        sheet = spreadsheet.worksheet("transactions")
        timestamp = datetime.now(pytz.timezone("Asia/Bangkok")).isoformat()
        # Sheet header: timestamp | source_user_id | raw_message | intent | category | amount | currency | note | _ | status
        row = [
            timestamp, user_id, raw_message,
            parsed.get("intent", ""), parsed.get("category", ""),
            parsed.get("amount", ""), parsed.get("currency", "THB"),
            parsed.get("note", ""), "", status
        ]
        sheet.append_row(row, value_input_option="USER_ENTERED")
        # Dual-write: Supabase (best-effort)
        safe_write(_sb_append, user_id, raw_message, parsed, status)
        return True
    except Exception as e:
        print(f"[db.transactions] append_transaction error: {e}")
        return False


def delete_last_transaction(user_id: str) -> dict:
    try:
        spreadsheet = get_sheet_client()
        sheet = spreadsheet.worksheet("transactions")
        records = sheet.get_all_records()
        for i in range(len(records) - 1, -1, -1):
            r = records[i]
            if r.get("source_user_id") == user_id and r.get("status") == "OK":
                row_index = i + 2
                sheet.update_cell(row_index, 10, "DELETED")
                # Dual-write: Supabase หา latest ของ user แล้ว mark DELETED อิสระจาก Sheets
                safe_write(_sb_delete_last, user_id)
                return {
                    "success": True,
                    "note": r.get("note", ""),
                    "amount": _safe_float(r.get("amount")),
                    "intent": r.get("intent", "")
                }
        return {"success": False}
    except Exception as e:
        print(f"[db.transactions] delete_last_transaction error: {e}")
        return {"success": False}


def search_transactions(user_id: str, keyword: str) -> list:
    try:
        spreadsheet = get_sheet_client()
        sheet = spreadsheet.worksheet("transactions")
        records = sheet.get_all_records()
        kw = keyword.lower()
        results = []
        for r in records:
            if r.get("source_user_id") != user_id:
                continue
            if r.get("status") == "DELETED":
                continue
            if r.get("intent") not in ("EXPENSE", "INCOME"):
                continue
            if (kw in str(r.get("note", "")).lower() or
                    kw in str(r.get("category", "")).lower() or
                    kw in str(r.get("raw_message", "")).lower()):
                results.append({
                    "intent": r.get("intent"),
                    "note": r.get("note", ""),
                    "amount": _safe_float(r.get("amount")),
                    "category": r.get("category", ""),
                    "timestamp": r.get("timestamp", "")[:10]
                })
        return results[-20:]
    except Exception as e:
        print(f"[db.transactions] search_transactions error: {e}")
        return []


def get_all_user_ids() -> list:
    try:
        spreadsheet = get_sheet_client()
        sheet = spreadsheet.worksheet("transactions")
        records = sheet.get_all_records()
        seen = set()
        result = []
        for r in records:
            uid = r.get("source_user_id", "")
            if uid and uid not in seen:
                seen.add(uid)
                result.append(uid)
        return result
    except Exception as e:
        print(f"[db.transactions] get_all_user_ids error: {e}")
        return []
