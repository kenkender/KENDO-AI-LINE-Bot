import re
import calendar as cal
from datetime import datetime, timedelta
import pytz
from db.client import get_sheet_client
from db_supabase import safe_write
from db_supabase.notes import (
    append_note as _sb_append_note,
    create_recurring_reminder as _sb_create_recurring,
)


def append_note(user_id: str, raw_message: str, parsed: dict, calendar_event_id: str = "", status: str = "OK") -> bool:
    try:
        spreadsheet = get_sheet_client()
        sheet = spreadsheet.worksheet("notes")
        timestamp = datetime.now(pytz.timezone("Asia/Bangkok")).isoformat()
        note = parsed.get("note", "")
        extras = parsed.get("reminder_extras", "") or ""
        recurrence = parsed.get("recurrence", "") or ""
        if extras:
            note = f"{note}\n[EXTRAS:{extras}]"
        if recurrence:
            note = f"{note}\n[RECUR:{recurrence}]"
        row = [
            timestamp, user_id, raw_message,
            parsed.get("intent", ""), note,
            parsed.get("reminder_datetime", ""), calendar_event_id, status
        ]
        sheet.append_row(row, value_input_option="USER_ENTERED")
        # Dual-write Supabase — note สะอาด (ไม่มี [EXTRAS:]/[RECUR:])
        # เพราะ Supabase มี column แยกสำหรับ extras + recurrence
        safe_write(_sb_append_note, user_id, raw_message, parsed, calendar_event_id, status)
        return True
    except Exception as e:
        print(f"[db.notes] append_note error: {e}")
        return False


def get_pending_reminders() -> list:
    try:
        spreadsheet = get_sheet_client()
        sheet = spreadsheet.worksheet("notes")
        records = sheet.get_all_records()
        bkk = pytz.timezone("Asia/Bangkok")
        now = datetime.now(bkk)
        due_reminders = []
        for i, record in enumerate(records):
            if record.get("intent") != "REMINDER" or record.get("status") != "OK":
                continue
            reminder_dt_str = record.get("reminder_datetime", "")
            if not reminder_dt_str:
                continue
            try:
                reminder_dt = datetime.fromisoformat(str(reminder_dt_str))
                if reminder_dt.tzinfo is None:
                    reminder_dt = bkk.localize(reminder_dt)
                else:
                    reminder_dt = reminder_dt.astimezone(bkk)
                diff = (reminder_dt - now).total_seconds()
                if -60 <= diff <= 300:
                    raw_note = record.get("note", "")
                    extras_str, recurrence_str = "", ""
                    # รองรับกรณีมีหลาย block — เก็บ block แรก แล้วลบทุก block ออกจาก note
                    m_extras = re.search(r'\r?\n\[EXTRAS:(.*?)\]', raw_note, re.DOTALL)
                    if m_extras:
                        extras_str = m_extras.group(1).strip()
                    m_recur = re.search(r'\r?\n\[RECUR:(.*?)\]', raw_note, re.DOTALL)
                    if m_recur:
                        recurrence_str = m_recur.group(1).strip()
                    raw_note = re.sub(r'\r?\n\[EXTRAS:.*?\]', '', raw_note, flags=re.DOTALL)
                    raw_note = re.sub(r'\r?\n\[RECUR:.*?\]', '', raw_note, flags=re.DOTALL)
                    due_reminders.append({
                        "row_index": i + 2,
                        "user_id": record.get("source_user_id", ""),
                        "note": raw_note.strip(),
                        "reminder_datetime": reminder_dt_str,
                        "reminder_extras": extras_str,
                        "recurrence": recurrence_str,
                    })
            except Exception as e:
                print(f"[db.notes] Row {i+2} parse error: {e}")
        return due_reminders
    except Exception as e:
        print(f"[db.notes] get_pending_reminders error: {e}")
        return []


def mark_reminder_sent(row_index: int) -> bool:
    try:
        spreadsheet = get_sheet_client()
        sheet = spreadsheet.worksheet("notes")
        sheet.update_cell(row_index, 8, "SENT")
        return True
    except Exception as e:
        print(f"[db.notes] mark_reminder_sent error: {e}")
        return False


def get_active_reminders(user_id: str) -> list:
    try:
        spreadsheet = get_sheet_client()
        sheet = spreadsheet.worksheet("notes")
        records = sheet.get_all_records()
        return [
            {
                "row_index": i + 2,
                "note": record.get("note", ""),
                "reminder_datetime": record.get("reminder_datetime", ""),
                "calendar_event_id": record.get("calendar_event_id", "")
            }
            for i, record in enumerate(records)
            if record.get("source_user_id") == user_id
            and record.get("intent") == "REMINDER"
            and record.get("status") == "OK"
        ]
    except Exception as e:
        print(f"[db.notes] get_active_reminders error: {e}")
        return []


def cancel_reminder(row_index: int) -> bool:
    try:
        spreadsheet = get_sheet_client()
        sheet = spreadsheet.worksheet("notes")
        sheet.update_cell(row_index, 8, "CANCELLED")
        return True
    except Exception as e:
        print(f"[db.notes] cancel_reminder error: {e}")
        return False


def get_today_reminders(user_id: str) -> list:
    try:
        spreadsheet = get_sheet_client()
        sheet = spreadsheet.worksheet("notes")
        records = sheet.get_all_records()
        today_str = datetime.now(pytz.timezone("Asia/Bangkok")).strftime("%Y-%m-%d")
        result = []
        for record in records:
            if record.get("source_user_id") != user_id:
                continue
            if record.get("intent") != "REMINDER" or record.get("status") != "OK":
                continue
            dt_str = str(record.get("reminder_datetime", ""))
            if not dt_str.startswith(today_str):
                continue
            raw = re.sub(r'\r?\n\[EXTRAS:.*?\]', '', record.get("note", ""), flags=re.DOTALL)
            raw = re.sub(r'\r?\n\[RECUR:.*?\]', '', raw, flags=re.DOTALL)
            result.append({"note": raw.strip(), "time": dt_str[11:16]})
        return result
    except Exception as e:
        print(f"[db.notes] get_today_reminders error: {e}")
        return []


def create_recurring_reminder(user_id: str, display_note: str, current_dt: datetime,
                               recurrence: str, extras: str = "") -> bool:
    try:
        next_dt = None
        if recurrence == "daily":
            next_dt = current_dt + timedelta(days=1)
        elif recurrence.startswith("weekly:"):
            target_wd = int(recurrence.split(":")[1]) - 1
            days_ahead = (target_wd - current_dt.weekday()) % 7 or 7
            next_dt = current_dt + timedelta(days=days_ahead)
        elif recurrence.startswith("monthly:"):
            target_day = int(recurrence.split(":")[1])
            if current_dt.month == 12:
                ny, nm = current_dt.year + 1, 1
            else:
                ny, nm = current_dt.year, current_dt.month + 1
            next_dt = current_dt.replace(year=ny, month=nm,
                                         day=min(target_day, cal.monthrange(ny, nm)[1]))
        if not next_dt:
            return False
        stored_note = display_note
        if extras:
            stored_note += f"\n[EXTRAS:{extras}]"
        stored_note += f"\n[RECUR:{recurrence}]"
        spreadsheet = get_sheet_client()
        sheet = spreadsheet.worksheet("notes")
        timestamp = datetime.now(pytz.timezone("Asia/Bangkok")).isoformat()
        sheet.append_row(
            [timestamp, user_id, f"[recurring] {display_note}",
             "REMINDER", stored_note, next_dt.isoformat(), "", "OK"],
            value_input_option="USER_ENTERED"
        )
        # Dual-write Supabase — สร้าง recurring reminder รอบถัดไป
        safe_write(_sb_create_recurring, user_id, display_note, current_dt, recurrence, extras)
        return True
    except Exception as e:
        print(f"[db.notes] create_recurring_reminder error: {e}")
        return False
