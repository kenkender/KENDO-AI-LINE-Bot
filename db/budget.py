from datetime import datetime
import pytz
from db.client import get_sheet_client, get_or_create_sheet
from db.summary import get_summary
from db_supabase import safe_write
from db_supabase.budget import (
    set_budget as _sb_set_budget,
    set_savings_goal as _sb_set_savings,
    mark_budget_warned as _sb_mark_warned,
)


def _settings_sheet(spreadsheet):
    return get_or_create_sheet(
        spreadsheet, "settings",
        ["source_user_id", "budget", "savings_goal", "updated_at"]
    )


def _find_settings_row(sheet, user_id: str):
    records = sheet.get_all_records()
    for i, r in enumerate(records):
        if r.get("source_user_id") == user_id:
            return i + 2, r
    return None, {}


def set_budget(user_id: str, amount: float) -> bool:
    try:
        spreadsheet = get_sheet_client()
        sheet = _settings_sheet(spreadsheet)
        row_idx, existing = _find_settings_row(sheet, user_id)
        now = datetime.now(pytz.timezone("Asia/Bangkok")).isoformat()
        if row_idx:
            sheet.update_cell(row_idx, 2, amount)
            sheet.update_cell(row_idx, 4, now)
        else:
            sheet.append_row([user_id, amount, existing.get("savings_goal", ""), now])
        # Dual-write Supabase
        safe_write(_sb_set_budget, user_id, amount)
        return True
    except Exception as e:
        print(f"[db.budget] set_budget error: {e}")
        return False


def get_budget_status(user_id: str) -> dict:
    try:
        spreadsheet = get_sheet_client()
        _, settings = _find_settings_row(_settings_sheet(spreadsheet), user_id)
        budget = float(settings.get("budget", 0) or 0)
        summary = get_summary(user_id=user_id)
        expense = summary.get("total_expense", 0) if summary.get("success") else 0
        return {"budget": budget, "expense": expense, "remaining": budget - expense}
    except Exception as e:
        print(f"[db.budget] get_budget_status error: {e}")
        return {"budget": 0, "expense": 0, "remaining": 0}


def set_savings_goal(user_id: str, amount: float) -> bool:
    try:
        spreadsheet = get_sheet_client()
        sheet = _settings_sheet(spreadsheet)
        row_idx, existing = _find_settings_row(sheet, user_id)
        now = datetime.now(pytz.timezone("Asia/Bangkok")).isoformat()
        if row_idx:
            sheet.update_cell(row_idx, 3, amount)
            sheet.update_cell(row_idx, 4, now)
        else:
            sheet.append_row([user_id, existing.get("budget", ""), amount, now])
        # Dual-write Supabase
        safe_write(_sb_set_savings, user_id, amount)
        return True
    except Exception as e:
        print(f"[db.budget] set_savings_goal error: {e}")
        return False


def get_savings_status(user_id: str) -> dict:
    try:
        spreadsheet = get_sheet_client()
        _, settings = _find_settings_row(_settings_sheet(spreadsheet), user_id)
        goal = float(settings.get("savings_goal", 0) or 0)
        summary = get_summary(user_id=user_id)
        balance = summary.get("balance", 0) if summary.get("success") else 0
        return {"goal": goal, "saved": max(balance, 0), "remaining": max(goal - balance, 0)}
    except Exception as e:
        print(f"[db.budget] get_savings_status error: {e}")
        return {"goal": 0, "saved": 0, "remaining": 0}


def _budget_warnings_sheet(spreadsheet):
    return get_or_create_sheet(
        spreadsheet, "budget_warnings",
        ["source_user_id", "month_key", "warned_levels", "updated_at"]
    )


def get_budget_warn_state(user_id: str, month_key: str) -> set:
    try:
        spreadsheet = get_sheet_client()
        sheet = _budget_warnings_sheet(spreadsheet)
        records = sheet.get_all_records()
        for r in records:
            if r.get("source_user_id") == user_id and r.get("month_key") == month_key:
                levels_str = str(r.get("warned_levels", ""))
                if not levels_str:
                    return set()
                return {int(x) for x in levels_str.split(",") if x.strip().isdigit()}
        return set()
    except Exception as e:
        print(f"[db.budget] get_budget_warn_state error: {e}")
        return set()


def mark_budget_warned(user_id: str, month_key: str, level: int) -> bool:
    try:
        spreadsheet = get_sheet_client()
        sheet = _budget_warnings_sheet(spreadsheet)
        records = sheet.get_all_records()
        now = datetime.now(pytz.timezone("Asia/Bangkok")).isoformat()
        for i, r in enumerate(records):
            if r.get("source_user_id") == user_id and r.get("month_key") == month_key:
                existing = str(r.get("warned_levels", ""))
                levels = {int(x) for x in existing.split(",") if x.strip().isdigit()} if existing else set()
                levels.add(level)
                new_levels = ",".join(str(l) for l in sorted(levels))
                row_idx = i + 2
                sheet.update_cell(row_idx, 3, new_levels)
                sheet.update_cell(row_idx, 4, now)
                # Dual-write Supabase
                safe_write(_sb_mark_warned, user_id, month_key, level)
                return True
        sheet.append_row([user_id, month_key, str(level), now])
        # Dual-write Supabase
        safe_write(_sb_mark_warned, user_id, month_key, level)
        return True
    except Exception as e:
        print(f"[db.budget] mark_budget_warned error: {e}")
        return False
