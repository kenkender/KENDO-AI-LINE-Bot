"""
db/interval_reminder.py
Interval Reminder — แจ้งเตือนซ้ำทุก X นาที/ชั่วโมง (สูงสุด 5 รายการ/user)
Sheet: interval_reminders
Columns: user_id, label, interval_minutes, next_fire, active, created_at
"""

from datetime import datetime, timedelta
import pytz
from db.client import get_sheet_client, get_or_create_sheet

_COLS = ["user_id", "label", "interval_minutes", "next_fire", "active", "created_at"]
_BKK = pytz.timezone("Asia/Bangkok")
MAX_PER_USER = 5


def _sheet():
    return get_or_create_sheet(get_sheet_client(), "interval_reminders", _COLS)


def add_interval_reminder(user_id: str, label: str, interval_minutes: int) -> dict:
    """เพิ่ม interval reminder ใหม่ — คืน {success, message}"""
    try:
        sheet = _sheet()
        records = sheet.get_all_records()
        active_count = sum(
            1 for r in records
            if r.get("user_id") == user_id and str(r.get("active", "")).upper() == "TRUE"
        )
        if active_count >= MAX_PER_USER:
            return {"success": False, "message": f"มีการแจ้งเตือนที่ใช้งานอยู่ {active_count} รายการแล้วครับ (สูงสุด {MAX_PER_USER} รายการ)\nกรุณายกเลิกรายการเก่าก่อนนะครับ"}

        now = datetime.now(_BKK)
        next_fire = (now + timedelta(minutes=interval_minutes)).isoformat()
        sheet.append_row([user_id, label, interval_minutes, next_fire, "TRUE", now.isoformat()])
        return {"success": True}
    except Exception as e:
        print(f"[db.interval_reminder] add error: {e}")
        return {"success": False, "message": "เกิดข้อผิดพลาดครับ ลองใหม่นะครับ"}


def get_active_interval_reminders(user_id: str) -> list:
    """คืนรายการ interval reminders ที่ active ของ user"""
    try:
        sheet = _sheet()
        records = sheet.get_all_records()
        result = []
        for i, r in enumerate(records):
            if r.get("user_id") == user_id and str(r.get("active", "")).upper() == "TRUE":
                result.append({
                    "row_index": i + 2,
                    "label": r.get("label", ""),
                    "interval_minutes": int(r.get("interval_minutes", 0)),
                    "next_fire": r.get("next_fire", ""),
                })
        return result
    except Exception as e:
        print(f"[db.interval_reminder] get_active error: {e}")
        return []


def get_all_due_interval_reminders() -> list:
    """คืนทุก interval reminder ที่ถึงเวลาแล้ว (next_fire <= now)"""
    try:
        sheet = _sheet()
        records = sheet.get_all_records()
        now = datetime.now(_BKK)
        result = []
        for i, r in enumerate(records):
            if str(r.get("active", "")).upper() != "TRUE":
                continue
            next_fire_str = r.get("next_fire", "")
            if not next_fire_str:
                continue
            try:
                nf = datetime.fromisoformat(next_fire_str)
                if nf.tzinfo is None:
                    nf = _BKK.localize(nf)
                if now >= nf:
                    result.append({
                        "row_index": i + 2,
                        "user_id": r.get("user_id", ""),
                        "label": r.get("label", ""),
                        "interval_minutes": int(r.get("interval_minutes", 0)),
                    })
            except Exception:
                continue
        return result
    except Exception as e:
        print(f"[db.interval_reminder] get_due error: {e}")
        return []


def update_next_fire(row_index: int, interval_minutes: int):
    """อัปเดต next_fire หลังจากส่งแจ้งเตือนแล้ว"""
    try:
        sheet = _sheet()
        next_fire = (datetime.now(_BKK) + timedelta(minutes=interval_minutes)).isoformat()
        headers = sheet.row_values(1)
        col = headers.index("next_fire") + 1
        sheet.update_cell(row_index, col, next_fire)
    except Exception as e:
        print(f"[db.interval_reminder] update_next_fire error: {e}")


def cancel_interval_reminder_by_label(user_id: str, label: str) -> dict:
    """ยกเลิก interval reminder ตาม label — คืน {success, cancelled_count}"""
    try:
        sheet = _sheet()
        records = sheet.get_all_records()
        headers = sheet.row_values(1)
        active_col = headers.index("active") + 1
        cancelled = 0
        for i, r in enumerate(records):
            if (r.get("user_id") == user_id
                    and str(r.get("active", "")).upper() == "TRUE"
                    and label.lower() in r.get("label", "").lower()):
                sheet.update_cell(i + 2, active_col, "FALSE")
                cancelled += 1
        return {"success": True, "cancelled_count": cancelled}
    except Exception as e:
        print(f"[db.interval_reminder] cancel error: {e}")
        return {"success": False, "cancelled_count": 0}


def cancel_all_interval_reminders(user_id: str) -> int:
    """ยกเลิกทุก interval reminder ของ user — คืนจำนวนที่ยกเลิก"""
    try:
        sheet = _sheet()
        records = sheet.get_all_records()
        headers = sheet.row_values(1)
        active_col = headers.index("active") + 1
        count = 0
        for i, r in enumerate(records):
            if r.get("user_id") == user_id and str(r.get("active", "")).upper() == "TRUE":
                sheet.update_cell(i + 2, active_col, "FALSE")
                count += 1
        return count
    except Exception as e:
        print(f"[db.interval_reminder] cancel_all error: {e}")
        return 0
