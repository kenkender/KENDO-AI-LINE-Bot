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
