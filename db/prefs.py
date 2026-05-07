from datetime import datetime
import pytz
from db.client import get_sheet_client, get_or_create_sheet


def _user_prefs_sheet(spreadsheet):
    return get_or_create_sheet(
        spreadsheet, "user_prefs",
        ["source_user_id", "briefing_hour", "briefing_city", "updated_at"]
    )


def _find_prefs_row(sheet, user_id: str):
    records = sheet.get_all_records()
    for i, r in enumerate(records):
        if r.get("source_user_id") == user_id:
            return i + 2, r
    return None, {}


def set_briefing(user_id: str, hour, city: str = "") -> bool:
    try:
        spreadsheet = get_sheet_client()
        sheet = _user_prefs_sheet(spreadsheet)
        row_idx, existing = _find_prefs_row(sheet, user_id)
        now = datetime.now(pytz.timezone("Asia/Bangkok")).isoformat()
        hour_val = int(hour) if hour is not None else ""
        city_val = city.strip() or str(existing.get("briefing_city", "") or "กรุงเทพ")
        if row_idx:
            sheet.update_cell(row_idx, 2, hour_val)
            sheet.update_cell(row_idx, 3, city_val)
            sheet.update_cell(row_idx, 4, now)
        else:
            sheet.append_row([user_id, hour_val, city_val, now])
        return True
    except Exception as e:
        print(f"[db.prefs] set_briefing error: {e}")
        return False


def get_briefing(user_id: str) -> dict:
    try:
        spreadsheet = get_sheet_client()
        sheet = _user_prefs_sheet(spreadsheet)
        _, prefs = _find_prefs_row(sheet, user_id)
        hour_raw = prefs.get("briefing_hour", "")
        hour = int(hour_raw) if str(hour_raw).strip().isdigit() else None
        city = str(prefs.get("briefing_city", "") or "กรุงเทพ")
        return {"hour": hour, "city": city}
    except Exception as e:
        print(f"[db.prefs] get_briefing error: {e}")
        return {"hour": None, "city": "กรุงเทพ"}


def _ensure_column(sheet, col_name: str) -> int:
    """ตรวจสอบว่า column มีอยู่ใน sheet หรือไม่ ถ้าไม่มีให้เพิ่ม — คืน 1-based index"""
    headers = sheet.row_values(1)
    if col_name in headers:
        return headers.index(col_name) + 1
    col_idx = len(headers) + 1
    sheet.update_cell(1, col_idx, col_name)
    return col_idx


def set_recurring_remind_day(user_id: str, day: int) -> bool:
    """ตั้งวันที่ต้องการรับแจ้งเตือนรายจ่ายซ้ำ (1-31) — 0 หรือ None = ปิดแจ้งเตือน"""
    try:
        spreadsheet = get_sheet_client()
        sheet = _user_prefs_sheet(spreadsheet)
        col_idx = _ensure_column(sheet, "recurring_remind_day")
        row_idx, _ = _find_prefs_row(sheet, user_id)
        now = datetime.now(pytz.timezone("Asia/Bangkok")).isoformat()
        day_val = int(day) if day and 1 <= int(day) <= 31 else ""
        if row_idx:
            sheet.update_cell(row_idx, col_idx, day_val)
            # อัปเดต updated_at (column 4)
            sheet.update_cell(row_idx, 4, now)
        else:
            row_data = [user_id, "", "กรุงเทพ", now]
            # เติม column ว่างให้ถึง col_idx-1 แล้วใส่ day_val
            while len(row_data) < col_idx - 1:
                row_data.append("")
            row_data.append(day_val)
            sheet.append_row(row_data)
        return True
    except Exception as e:
        print(f"[db.prefs] set_recurring_remind_day error: {e}")
        return False


def get_recurring_remind_day(user_id: str) -> int | None:
    """คืน remind_day ของ user (1-31) หรือ None ถ้าไม่ได้ตั้ง"""
    try:
        spreadsheet = get_sheet_client()
        sheet = _user_prefs_sheet(spreadsheet)
        _, prefs = _find_prefs_row(sheet, user_id)
        raw = prefs.get("recurring_remind_day", "")
        return int(raw) if str(raw).strip().isdigit() else None
    except Exception as e:
        print(f"[db.prefs] get_recurring_remind_day error: {e}")
        return None


def get_all_recurring_remind_users() -> list:
    """คืน [{user_id, remind_day}] ของ user ที่ตั้ง recurring_remind_day ไว้"""
    try:
        spreadsheet = get_sheet_client()
        sheet = _user_prefs_sheet(spreadsheet)
        records = sheet.get_all_records()
        result = []
        for r in records:
            raw = r.get("recurring_remind_day", "")
            if str(raw).strip().isdigit() and r.get("source_user_id"):
                result.append({
                    "user_id": r["source_user_id"],
                    "remind_day": int(raw)
                })
        return result
    except Exception as e:
        print(f"[db.prefs] get_all_recurring_remind_users error: {e}")
        return []


def get_all_briefing_users() -> list:
    try:
        spreadsheet = get_sheet_client()
        sheet = _user_prefs_sheet(spreadsheet)
        records = sheet.get_all_records()
        result = []
        for r in records:
            hour_raw = r.get("briefing_hour", "")
            hour = int(hour_raw) if str(hour_raw).strip().isdigit() else None
            if hour is not None and r.get("source_user_id"):
                result.append({
                    "user_id": r.get("source_user_id"),
                    "hour": hour,
                    "city": str(r.get("briefing_city", "") or "กรุงเทพ")
                })
        return result
    except Exception as e:
        print(f"[db.prefs] get_all_briefing_users error: {e}")
        return []
