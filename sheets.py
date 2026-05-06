"""
sheets.py
จัดการการอ่านและเขียนข้อมูลลง Google Sheets
"""

import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import pytz
import os
import json
from dotenv import load_dotenv

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
CREDENTIALS_FILE = "credentials.json"


def get_sheet_client():
    credentials_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if credentials_json:
        # Render: อ่านจาก environment variable
        info = json.loads(credentials_json)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        # Local dev: อ่านจากไฟล์ credentials.json
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID)


def append_transaction(user_id: str, raw_message: str, parsed: dict, status: str = "OK") -> bool:
    try:
        spreadsheet = get_sheet_client()
        sheet = spreadsheet.worksheet("transactions")
        bangkok_tz = pytz.timezone("Asia/Bangkok")
        timestamp = datetime.now(bangkok_tz).isoformat()
        row = [
            timestamp, user_id, raw_message,
            parsed.get("intent", ""), parsed.get("category", ""),
            parsed.get("amount", ""), parsed.get("currency", "THB"),
            parsed.get("note", ""), "", status
        ]
        sheet.append_row(row, value_input_option="USER_ENTERED")
        return True
    except Exception as e:
        print(f"[sheets.py] append_transaction error: {e}")
        return False


def append_note(user_id: str, raw_message: str, parsed: dict, calendar_event_id: str = "", status: str = "OK") -> bool:
    try:
        spreadsheet = get_sheet_client()
        sheet = spreadsheet.worksheet("notes")
        bangkok_tz = pytz.timezone("Asia/Bangkok")
        timestamp = datetime.now(bangkok_tz).isoformat()
        row = [
            timestamp, user_id, raw_message,
            parsed.get("intent", ""), parsed.get("note", ""),
            parsed.get("reminder_datetime", ""), calendar_event_id, status
        ]
        sheet.append_row(row, value_input_option="USER_ENTERED")
        return True
    except Exception as e:
        print(f"[sheets.py] append_note error: {e}")
        return False


def get_summary(month: int = None, year: int = None) -> dict:
    try:
        spreadsheet = get_sheet_client()
        sheet = spreadsheet.worksheet("transactions")
        bangkok_tz = pytz.timezone("Asia/Bangkok")
        now = datetime.now(bangkok_tz)
        if month is None:
            month = now.month
        if year is None:
            year = now.year
        records = sheet.get_all_records()
        total_income = 0.0
        total_expense = 0.0
        expense_by_category = {}
        transactions = []
        for record in records:
            timestamp_str = record.get("timestamp", "")
            if not timestamp_str:
                continue
            try:
                record_date = datetime.fromisoformat(timestamp_str)
                if record_date.month != month or record_date.year != year:
                    continue
            except ValueError:
                continue
            intent = record.get("intent", "")
            amount = record.get("amount", 0)
            try:
                amount = float(amount) if amount else 0.0
            except (ValueError, TypeError):
                amount = 0.0
            if intent == "INCOME":
                total_income += amount
                transactions.append({
                    "type": "INCOME",
                    "note": record.get("note", ""),
                    "amount": amount,
                    "category": record.get("category", "รายได้")
                })
            elif intent == "EXPENSE":
                total_expense += amount
                category = record.get("category", "อื่นๆ")
                expense_by_category[category] = expense_by_category.get(category, 0.0) + amount
                transactions.append({
                    "type": "EXPENSE",
                    "note": record.get("note", ""),
                    "amount": amount,
                    "category": category
                })
        return {
            "success": True, "month": month, "year": year,
            "total_income": total_income, "total_expense": total_expense,
            "balance": total_income - total_expense,
            "expense_by_category": expense_by_category,
            "transactions": transactions
        }
    except Exception as e:
        print(f"[sheets.py] get_summary error: {e}")
        return {"success": False, "error": str(e)}


def format_summary_message(summary: dict) -> str:
    thai_months = {
        1: "มกราคม", 2: "กุมภาพันธ์", 3: "มีนาคม", 4: "เมษายน",
        5: "พฤษภาคม", 6: "มิถุนายน", 7: "กรกฎาคม", 8: "สิงหาคม",
        9: "กันยายน", 10: "ตุลาคม", 11: "พฤศจิกายน", 12: "ธันวาคม"
    }
    month_name = thai_months.get(summary["month"], str(summary["month"]))
    balance = summary["balance"]
    balance_label = "คงเหลือ" if balance >= 0 else "ติดลบ"
    lines = [
        f"📊 สรุป{month_name} {summary['year']}",
        f"",
        f"💰 รายรับ:  {summary['total_income']:,.2f} บาท",
        f"💸 รายจ่าย: {summary['total_expense']:,.2f} บาท",
        f"{'✅' if balance >= 0 else '⚠️'} {balance_label}: {abs(balance):,.2f} บาท",
    ]
    if summary["expense_by_category"]:
        lines.append("")
        lines.append("📂 รายจ่ายแยกตามหมวด:")
        for category, amount in sorted(summary["expense_by_category"].items(), key=lambda x: x[1], reverse=True):
            lines.append(f"  • {category}: {amount:,.2f} บาท")
    return "\n".join(lines)


def format_quick_summary(summary: dict) -> str:
    """สรุปยอดสั้นๆ แสดงต่อท้ายการจดรายการ EXPENSE/INCOME"""
    thai_months = {
        1: "ม.ค.", 2: "ก.พ.", 3: "มี.ค.", 4: "เม.ย.",
        5: "พ.ค.", 6: "มิ.ย.", 7: "ก.ค.", 8: "ส.ค.",
        9: "ก.ย.", 10: "ต.ค.", 11: "พ.ย.", 12: "ธ.ค."
    }
    month_name = thai_months.get(summary["month"], str(summary["month"]))
    lines = [
        "",
        f"─────────────────────",
        f"📊 สรุปยอด {month_name} {summary['year']}",
        f"─────────────────────",
    ]

    transactions = summary.get("transactions", [])
    if transactions:
        lines.append("📋 รายการ:")
        visible = transactions[-10:]
        hidden = len(transactions) - len(visible)
        if hidden > 0:
            lines.append(f"  ⋯ (ย้อนหลัง {hidden} รายการ)")
        for t in visible:
            if t["type"] == "INCOME":
                lines.append(f"  ✅ +{t['amount']:,.0f}  {t['note']}")
            else:
                lines.append(f"  💸 -{t['amount']:,.0f}  {t['note']}")

    balance = summary["balance"]
    lines += [
        "",
        f"💰 รายรับ:   {summary['total_income']:,.2f} บาท",
        f"💸 รายจ่าย:  {summary['total_expense']:,.2f} บาท",
        f"{'✅' if balance >= 0 else '⚠️'} {'คงเหลือ' if balance >= 0 else 'ติดลบ'}:   {abs(balance):,.2f} บาท",
    ]
    return "\n".join(lines)


def _get_or_create_sheet(spreadsheet, name: str, headers: list):
    """ดึง worksheet ถ้ามีอยู่แล้ว หรือสร้างใหม่พร้อม header"""
    try:
        return spreadsheet.worksheet(name)
    except Exception:
        sheet = spreadsheet.add_worksheet(title=name, rows=1000, cols=len(headers))
        sheet.append_row(headers)
        return sheet


# ── DELETE ────────────────────────────────────────────────────────────────────

def delete_last_transaction(user_id: str) -> dict:
    """ลบรายการ EXPENSE/INCOME ล่าสุดของ user"""
    try:
        spreadsheet = get_sheet_client()
        sheet = spreadsheet.worksheet("transactions")
        records = sheet.get_all_records()
        for i in range(len(records) - 1, -1, -1):
            r = records[i]
            if r.get("source_user_id") == user_id and r.get("status") == "OK":
                row_index = i + 2
                sheet.update_cell(row_index, 10, "DELETED")
                return {
                    "success": True,
                    "note": r.get("note", ""),
                    "amount": float(r.get("amount", 0) or 0),
                    "intent": r.get("intent", "")
                }
        return {"success": False}
    except Exception as e:
        print(f"[sheets] delete_last_transaction error: {e}")
        return {"success": False}


# ── SEARCH ────────────────────────────────────────────────────────────────────

def search_transactions(user_id: str, keyword: str) -> list:
    """ค้นหารายการที่ note หรือ category ตรงกับ keyword"""
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
            note = str(r.get("note", "")).lower()
            category = str(r.get("category", "")).lower()
            raw = str(r.get("raw_message", "")).lower()
            if kw in note or kw in category or kw in raw:
                results.append({
                    "intent": r.get("intent"),
                    "note": r.get("note", ""),
                    "amount": float(r.get("amount", 0) or 0),
                    "category": r.get("category", ""),
                    "timestamp": r.get("timestamp", "")[:10]
                })
        return results[-20:]
    except Exception as e:
        print(f"[sheets] search_transactions error: {e}")
        return []


# ── BUDGET ────────────────────────────────────────────────────────────────────

def _settings_sheet(spreadsheet):
    return _get_or_create_sheet(
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
        bangkok_tz = pytz.timezone("Asia/Bangkok")
        now = datetime.now(bangkok_tz).isoformat()
        if row_idx:
            sheet.update_cell(row_idx, 2, amount)
            sheet.update_cell(row_idx, 4, now)
        else:
            sheet.append_row([user_id, amount, existing.get("savings_goal", ""), now])
        return True
    except Exception as e:
        print(f"[sheets] set_budget error: {e}")
        return False


def get_budget_status(user_id: str) -> dict:
    """คืน budget และ total_expense เดือนนี้"""
    try:
        spreadsheet = get_sheet_client()
        _, settings = _find_settings_row(_settings_sheet(spreadsheet), user_id)
        budget = float(settings.get("budget", 0) or 0)
        summary = get_summary()
        expense = summary.get("total_expense", 0) if summary.get("success") else 0
        return {"budget": budget, "expense": expense, "remaining": budget - expense}
    except Exception as e:
        print(f"[sheets] get_budget_status error: {e}")
        return {"budget": 0, "expense": 0, "remaining": 0}


# ── SAVINGS ───────────────────────────────────────────────────────────────────

def set_savings_goal(user_id: str, amount: float) -> bool:
    try:
        spreadsheet = get_sheet_client()
        sheet = _settings_sheet(spreadsheet)
        row_idx, existing = _find_settings_row(sheet, user_id)
        bangkok_tz = pytz.timezone("Asia/Bangkok")
        now = datetime.now(bangkok_tz).isoformat()
        if row_idx:
            sheet.update_cell(row_idx, 3, amount)
            sheet.update_cell(row_idx, 4, now)
        else:
            sheet.append_row([user_id, existing.get("budget", ""), amount, now])
        return True
    except Exception as e:
        print(f"[sheets] set_savings_goal error: {e}")
        return False


def get_savings_status(user_id: str) -> dict:
    """คืน savings_goal และ balance เดือนนี้"""
    try:
        spreadsheet = get_sheet_client()
        _, settings = _find_settings_row(_settings_sheet(spreadsheet), user_id)
        goal = float(settings.get("savings_goal", 0) or 0)
        summary = get_summary()
        balance = summary.get("balance", 0) if summary.get("success") else 0
        return {"goal": goal, "saved": max(balance, 0), "remaining": max(goal - balance, 0)}
    except Exception as e:
        print(f"[sheets] get_savings_status error: {e}")
        return {"goal": 0, "saved": 0, "remaining": 0}


# ── TASKS ─────────────────────────────────────────────────────────────────────

def _tasks_sheet(spreadsheet):
    return _get_or_create_sheet(
        spreadsheet, "tasks",
        ["timestamp", "source_user_id", "task", "status"]
    )


def add_task(user_id: str, task: str) -> bool:
    try:
        spreadsheet = get_sheet_client()
        sheet = _tasks_sheet(spreadsheet)
        bangkok_tz = pytz.timezone("Asia/Bangkok")
        now = datetime.now(bangkok_tz).isoformat()
        sheet.append_row([now, user_id, task, "PENDING"])
        return True
    except Exception as e:
        print(f"[sheets] add_task error: {e}")
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
        print(f"[sheets] list_tasks error: {e}")
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
            pending = [r.get("task", "") for _, r in [
                (i + 2, r) for i, r in enumerate(records)
                if r.get("source_user_id") == user_id and r.get("status") == "PENDING"
            ]]
            return {"success": False, "pending": pending}
        if len(matched) == 1:
            row_idx, r = matched[0]
            sheet.update_cell(row_idx, 4, "DONE")
            return {"success": True, "task": r.get("task", "")}
        return {"success": False, "ambiguous": [r.get("task", "") for _, r in matched]}
    except Exception as e:
        print(f"[sheets] complete_task error: {e}")
        return {"success": False, "pending": []}


def get_all_user_ids() -> list:
    """ดึง user_id ทั้งหมดที่มีรายการใน transactions"""
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
        print(f"[sheets] get_all_user_ids error: {e}")
        return []


def get_pending_reminders() -> list:
    try:
        spreadsheet = get_sheet_client()
        sheet = spreadsheet.worksheet("notes")
        records = sheet.get_all_records()
        bangkok_tz = pytz.timezone("Asia/Bangkok")
        now = datetime.now(bangkok_tz)
        print(f"[sheets] Total records in notes: {len(records)}")
        if records:
            print(f"[sheets] Keys: {list(records[0].keys())}")
        due_reminders = []
        for i, record in enumerate(records):
            intent = record.get("intent", "")
            status = record.get("status", "")
            reminder_dt_str = record.get("reminder_datetime", "")
            print(f"[sheets] Row {i+2}: intent={intent}, status={status}, dt={reminder_dt_str}")
            if intent != "REMINDER" or status != "OK":
                continue
            if not reminder_dt_str:
                continue
            try:
                reminder_dt = datetime.fromisoformat(str(reminder_dt_str))
                diff = (reminder_dt - now).total_seconds()
                print(f"[sheets] Row {i+2}: diff={diff:.0f}s")
                if -60 <= diff <= 300:
                    due_reminders.append({
                        "row_index": i + 2,
                        "user_id": record.get("source_user_id", ""),
                        "note": record.get("note", ""),
                        "reminder_datetime": reminder_dt_str
                    })
            except Exception as e:
                print(f"[sheets] Row {i+2} parse error: {e}")
                continue
        return due_reminders
    except Exception as e:
        print(f"[sheets.py] get_pending_reminders error: {e}")
        return []


def mark_reminder_sent(row_index: int) -> bool:
    try:
        spreadsheet = get_sheet_client()
        sheet = spreadsheet.worksheet("notes")
        # A=timestamp, B=source_user_id, C=raw_message,
        # D=intent, E=note, F=reminder_datetime, G=calendar_event_id, H=status
        sheet.update_cell(row_index, 8, "SENT")
        return True
    except Exception as e:
        print(f"[sheets.py] mark_reminder_sent error: {e}")
        return False
    
def get_active_reminders(user_id: str) -> list:
    """
    ดึง REMINDER ที่ยังไม่ได้ส่ง (status=OK) ของ user นั้น
    """
    try:
        spreadsheet = get_sheet_client()
        sheet = spreadsheet.worksheet("notes")
        records = sheet.get_all_records()

        active = []
        for i, record in enumerate(records):
            if (record.get("source_user_id", "") == user_id and
                record.get("intent", "") == "REMINDER" and
                record.get("status", "") == "OK"):
                active.append({
                    "row_index": i + 2,
                    "note": record.get("note", ""),
                    "reminder_datetime": record.get("reminder_datetime", ""),
                    "calendar_event_id": record.get("calendar_event_id", "")
                })
        return active

    except Exception as e:
        print(f"[sheets.py] get_active_reminders error: {e}")
        return []


def cancel_reminder(row_index: int) -> bool:
    """
    อัปเดต status ของ reminder เป็น CANCELLED
    """
    try:
        spreadsheet = get_sheet_client()
        sheet = spreadsheet.worksheet("notes")
        # H = status column
        sheet.update_cell(row_index, 8, "CANCELLED")
        return True
    except Exception as e:
        print(f"[sheets.py] cancel_reminder error: {e}")
        return False