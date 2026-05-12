from datetime import datetime
import pytz
from db.client import get_sheet_client, get_or_create_sheet
from db_supabase import safe_write
from db_supabase.tasks import (
    add_task as _sb_add_task,
    complete_task as _sb_complete_task,
)


def _tasks_sheet(spreadsheet):
    return get_or_create_sheet(
        spreadsheet, "tasks",
        ["timestamp", "source_user_id", "task", "status"]
    )


def add_task(user_id: str, task: str) -> bool:
    try:
        spreadsheet = get_sheet_client()
        sheet = _tasks_sheet(spreadsheet)
        now = datetime.now(pytz.timezone("Asia/Bangkok")).isoformat()
        sheet.append_row([now, user_id, task, "PENDING"])
        safe_write(_sb_add_task, user_id, task)
        return True
    except Exception as e:
        print(f"[db.tasks] add_task error: {e}")
        return False


def list_tasks(user_id: str) -> list:
    try:
        spreadsheet = get_sheet_client()
        sheet = _tasks_sheet(spreadsheet)
        records = sheet.get_all_records()
        return [
            {"row_index": i + 2, "task": r.get("task", ""), "timestamp": r.get("timestamp", "")[:10]}
            for i, r in enumerate(records)
            if r.get("source_user_id") == user_id and r.get("status") == "PENDING"
        ]
    except Exception as e:
        print(f"[db.tasks] list_tasks error: {e}")
        return []


def complete_task(user_id: str, keyword: str) -> dict:
    try:
        spreadsheet = get_sheet_client()
        sheet = _tasks_sheet(spreadsheet)
        records = sheet.get_all_records()
        kw = keyword.lower()
        matched = [
            (i + 2, r) for i, r in enumerate(records)
            if r.get("source_user_id") == user_id
            and r.get("status") == "PENDING"
            and kw in r.get("task", "").lower()
        ]
        if not matched:
            pending = [r.get("task", "") for i, r in enumerate(records)
                       if r.get("source_user_id") == user_id and r.get("status") == "PENDING"]
            return {"success": False, "pending": pending}
        if len(matched) == 1:
            row_idx, r = matched[0]
            sheet.update_cell(row_idx, 4, "DONE")
            # Dual-write Supabase — ค้นด้วย keyword เดียวกัน
            safe_write(_sb_complete_task, user_id, keyword)
            return {"success": True, "task": r.get("task", "")}
        return {"success": False, "ambiguous": [r.get("task", "") for _, r in matched]}
    except Exception as e:
        print(f"[db.tasks] complete_task error: {e}")
        return {"success": False, "pending": []}
