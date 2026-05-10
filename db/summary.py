from datetime import datetime
import pytz
from db.client import get_sheet_client


def get_summary(month: int = None, year: int = None, user_id: str = None) -> dict:
    try:
        spreadsheet = get_sheet_client()
        sheet = spreadsheet.worksheet("transactions")
        now = datetime.now(pytz.timezone("Asia/Bangkok"))
        month = month or now.month
        year = year or now.year
        records = sheet.get_all_records()
        total_income = 0.0
        total_expense = 0.0
        expense_by_category = {}
        transactions = []
        bkk = pytz.timezone("Asia/Bangkok")
        for record in records:
            ts = record.get("timestamp", "")
            if not ts:
                continue
            try:
                record_date = datetime.fromisoformat(ts)
                if record_date.tzinfo is None:
                    record_date = bkk.localize(record_date)
                else:
                    record_date = record_date.astimezone(bkk)
                if record_date.month != month or record_date.year != year:
                    continue
            except (ValueError, Exception):
                continue
            if user_id and record.get("source_user_id", "") != user_id:
                continue
            if record.get("status") == "DELETED":
                continue
            intent = record.get("intent", "")
            try:
                amount = float(record.get("amount", 0) or 0)
            except (ValueError, TypeError):
                amount = 0.0
            if intent == "INCOME":
                total_income += amount
                transactions.append({
                    "type": "INCOME", "note": record.get("note", ""),
                    "amount": amount, "category": record.get("category", "รายได้")
                })
            elif intent == "EXPENSE":
                total_expense += amount
                category = record.get("category", "อื่นๆ")
                expense_by_category[category] = expense_by_category.get(category, 0.0) + amount
                transactions.append({
                    "type": "EXPENSE", "note": record.get("note", ""),
                    "amount": amount, "category": category
                })
        return {
            "success": True, "month": month, "year": year,
            "total_income": total_income, "total_expense": total_expense,
            "balance": total_income - total_expense,
            "expense_by_category": expense_by_category,
            "transactions": transactions
        }
    except Exception as e:
        print(f"[db.summary] get_summary error: {e}")
        return {"success": False, "error": str(e)}


def get_today_summary(user_id: str = None) -> dict:
    try:
        spreadsheet = get_sheet_client()
        sheet = spreadsheet.worksheet("transactions")
        now = datetime.now(pytz.timezone("Asia/Bangkok"))
        today_str = now.strftime("%Y-%m-%d")
        records = sheet.get_all_records()
        total_income, total_expense = 0.0, 0.0
        expense_by_category: dict = {}
        transactions = []
        for record in records:
            ts = str(record.get("timestamp", ""))
            if not ts.startswith(today_str):
                continue
            if user_id and record.get("source_user_id", "") != user_id:
                continue
            if record.get("status") == "DELETED":
                continue
            intent = record.get("intent", "")
            amount = float(record.get("amount", 0) or 0)
            if intent == "INCOME":
                total_income += amount
                transactions.append({"type": "INCOME", "note": record.get("note", ""), "amount": amount})
            elif intent == "EXPENSE":
                total_expense += amount
                cat = record.get("category", "อื่นๆ")
                expense_by_category[cat] = expense_by_category.get(cat, 0.0) + amount
                transactions.append({"type": "EXPENSE", "note": record.get("note", ""), "amount": amount, "category": cat})
        return {
            "success": True, "date": today_str, "total_income": total_income,
            "total_expense": total_expense, "balance": total_income - total_expense,
            "expense_by_category": expense_by_category, "transactions": transactions
        }
    except Exception as e:
        print(f"[db.summary] get_today_summary error: {e}")
        return {"success": False, "error": str(e)}


def get_date_summary(user_id: str = None, target_date=None) -> dict:
    """ดึงสรุปรายรับ-รายจ่ายของวันที่กำหนด (default = วันนี้)"""
    try:
        spreadsheet = get_sheet_client()
        sheet = spreadsheet.worksheet("transactions")
        bkk = pytz.timezone("Asia/Bangkok")
        if target_date is None:
            target_date = datetime.now(bkk)
        elif isinstance(target_date, str):
            try:
                target_date = datetime.fromisoformat(target_date)
            except ValueError:
                target_date = datetime.now(bkk)
        if target_date.tzinfo is None:
            target_date = bkk.localize(target_date)
        else:
            target_date = target_date.astimezone(bkk)
        date_str = target_date.strftime("%Y-%m-%d")
        records = sheet.get_all_records()
        total_income, total_expense = 0.0, 0.0
        expense_by_category: dict = {}
        transactions = []
        for record in records:
            ts = str(record.get("timestamp", ""))
            if not ts.startswith(date_str):
                continue
            if user_id and record.get("source_user_id", "") != user_id:
                continue
            if record.get("status") == "DELETED":
                continue
            intent = record.get("intent", "")
            try:
                amount = float(record.get("amount", 0) or 0)
            except (ValueError, TypeError):
                amount = 0.0
            if intent == "INCOME":
                total_income += amount
                transactions.append({"type": "INCOME", "note": record.get("note", ""), "amount": amount})
            elif intent == "EXPENSE":
                total_expense += amount
                cat = record.get("category", "อื่นๆ")
                expense_by_category[cat] = expense_by_category.get(cat, 0.0) + amount
                transactions.append({"type": "EXPENSE", "note": record.get("note", ""), "amount": amount, "category": cat})
        return {
            "success": True, "date": date_str, "total_income": total_income,
            "total_expense": total_expense, "balance": total_income - total_expense,
            "expense_by_category": expense_by_category, "transactions": transactions
        }
    except Exception as e:
        print(f"[db.summary] get_date_summary error: {e}")
        return {"success": False, "error": str(e)}


def get_compare_days_summary(user_id: str, date_a, date_b) -> dict:
    """เปรียบเทียบ 2 วัน คืน {a: ..., b: ..., date_a: str, date_b: str}"""
    a = get_date_summary(user_id, date_a)
    b = get_date_summary(user_id, date_b)
    return {
        "a": a, "b": b,
        "date_a": a.get("date", ""),
        "date_b": b.get("date", ""),
    }


_THAI_MONTHS_FULL = {
    1: "มกราคม", 2: "กุมภาพันธ์", 3: "มีนาคม", 4: "เมษายน",
    5: "พฤษภาคม", 6: "มิถุนายน", 7: "กรกฎาคม", 8: "สิงหาคม",
    9: "กันยายน", 10: "ตุลาคม", 11: "พฤศจิกายน", 12: "ธันวาคม"
}
_THAI_MONTHS_SHORT = {
    1: "ม.ค.", 2: "ก.พ.", 3: "มี.ค.", 4: "เม.ย.",
    5: "พ.ค.", 6: "มิ.ย.", 7: "ก.ค.", 8: "ส.ค.",
    9: "ก.ย.", 10: "ต.ค.", 11: "พ.ย.", 12: "ธ.ค."
}


def format_summary_message(summary: dict) -> str:
    month_name = _THAI_MONTHS_FULL.get(summary["month"], str(summary["month"]))
    balance = summary["balance"]
    balance_label = "คงเหลือ" if balance >= 0 else "ติดลบ"
    lines = [
        f"📊 สรุป{month_name} {summary['year']}",
        "",
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


def get_compare_summary(month_a: int, year_a: int, month_b: int, year_b: int, user_id: str = None) -> dict:
    """ดึงสรุปของ 2 เดือนมาเปรียบเทียบ"""
    a = get_summary(month_a, year_a, user_id)
    b = get_summary(month_b, year_b, user_id)
    return {"a": a, "b": b}


def format_quick_summary(summary: dict) -> str:
    month_name = _THAI_MONTHS_SHORT.get(summary["month"], str(summary["month"]))
    lines = [
        "",
        "─────────────────────",
        f"📊 สรุปยอด {month_name} {summary['year']}",
        "─────────────────────",
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
