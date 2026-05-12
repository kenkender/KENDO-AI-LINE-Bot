from datetime import datetime
import pytz
from db.client import get_sheet_client, get_or_create_sheet
from db_supabase import safe_write
from db_supabase.watchlist import (
    add_watchlist_item as _sb_add_watch,
    done_watchlist_item as _sb_done_watch,
)


def _watchlist_sheet(spreadsheet):
    return get_or_create_sheet(
        spreadsheet, "watchlist",
        ["timestamp", "source_user_id", "category", "title", "status"]
    )


def add_watchlist_item(user_id: str, category: str, title: str) -> bool:
    try:
        spreadsheet = get_sheet_client()
        sheet = _watchlist_sheet(spreadsheet)
        now = datetime.now(pytz.timezone("Asia/Bangkok")).isoformat()
        sheet.append_row([now, user_id, category or "อื่นๆ", title, "PENDING"])
        safe_write(_sb_add_watch, user_id, category, title)
        return True
    except Exception as e:
        print(f"[db.watchlist] add_watchlist_item error: {e}")
        return False


def list_watchlist_items(user_id: str) -> list:
    try:
        spreadsheet = get_sheet_client()
        sheet = _watchlist_sheet(spreadsheet)
        records = sheet.get_all_records()
        return [
            {"row_index": i + 2, "category": r.get("category", "อื่นๆ"), "title": r.get("title", "")}
            for i, r in enumerate(records)
            if r.get("source_user_id") == user_id and r.get("status") == "PENDING"
        ]
    except Exception as e:
        print(f"[db.watchlist] list_watchlist_items error: {e}")
        return []


def done_watchlist_item(user_id: str, keyword: str) -> dict:
    try:
        spreadsheet = get_sheet_client()
        sheet = _watchlist_sheet(spreadsheet)
        records = sheet.get_all_records()
        kw = keyword.lower()
        matched = [
            (i + 2, r) for i, r in enumerate(records)
            if r.get("source_user_id") == user_id and r.get("status") == "PENDING"
            and kw in r.get("title", "").lower()
        ]
        if not matched:
            return {"success": False}
        if len(matched) == 1:
            row_idx, r = matched[0]
            sheet.update_cell(row_idx, 5, "DONE")
            safe_write(_sb_done_watch, user_id, keyword)
            return {"success": True, "title": r.get("title", ""), "category": r.get("category", "")}
        return {"success": False, "ambiguous": [{"title": r.get("title"), "category": r.get("category")} for _, r in matched]}
    except Exception as e:
        print(f"[db.watchlist] done_watchlist_item error: {e}")
        return {"success": False}
