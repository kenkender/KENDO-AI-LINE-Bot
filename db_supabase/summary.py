"""
db_supabase/summary.py
สรุปรายเดือน / รายวัน / เปรียบเทียบ
"""
from datetime import datetime, timedelta
from typing import Optional
import calendar as cal
import pytz

from db_supabase.client import get_supabase
from db_supabase.users import get_user_id


def _to_float(v) -> float:
    try:
        return float(v) if v not in (None, "", "None") else 0.0
    except (ValueError, TypeError):
        return 0.0


def _aggregate(rows: list) -> dict:
    """Helper: aggregate list of transaction rows → totals + category"""
    total_income, total_expense = 0.0, 0.0
    expense_by_category: dict = {}
    transactions = []
    for r in rows:
        if r.get("status") == "DELETED":
            continue
        intent = r.get("intent")
        amount = _to_float(r.get("amount"))
        if intent == "INCOME":
            total_income += amount
            transactions.append({
                "type": "INCOME", "note": r.get("note", ""),
                "amount": amount, "category": r.get("category", "รายได้"),
            })
        elif intent == "EXPENSE":
            total_expense += amount
            cat = r.get("category", "อื่นๆ")
            expense_by_category[cat] = expense_by_category.get(cat, 0.0) + amount
            transactions.append({
                "type": "EXPENSE", "note": r.get("note", ""),
                "amount": amount, "category": cat,
            })
    return {
        "total_income": total_income,
        "total_expense": total_expense,
        "balance": total_income - total_expense,
        "expense_by_category": expense_by_category,
        "transactions": transactions,
    }


def get_summary(month: Optional[int] = None, year: Optional[int] = None,
                 line_user_id: Optional[str] = None) -> dict:
    """สรุปรายเดือน — ของ user คนเดียว (ถ้าระบุ) หรือทุกคน (legacy compat)"""
    try:
        bkk = pytz.timezone("Asia/Bangkok")
        now = datetime.now(bkk)
        month = month or now.month
        year = year or now.year

        # ช่วงเวลาของเดือนนั้น
        start_dt = bkk.localize(datetime(year, month, 1))
        last_day = cal.monthrange(year, month)[1]
        end_dt = bkk.localize(datetime(year, month, last_day, 23, 59, 59))

        sb = get_supabase()
        q = sb.table("transactions").select(
            "intent,amount,category,note,status,ts"
        ).gte("ts", start_dt.isoformat()).lte("ts", end_dt.isoformat()).neq("status", "DELETED")

        if line_user_id:
            user_id = get_user_id(line_user_id)
            if not user_id:
                # ยังไม่มี user → ไม่มีข้อมูล
                return {
                    "success": True, "month": month, "year": year,
                    "total_income": 0, "total_expense": 0, "balance": 0,
                    "expense_by_category": {}, "transactions": [],
                }
            q = q.eq("user_id", user_id)

        result = q.execute()
        agg = _aggregate(result.data or [])
        return {"success": True, "month": month, "year": year, **agg}
    except Exception as e:
        print(f"[db_supabase.summary] get_summary error: {e}")
        return {"success": False, "error": str(e)}


def get_date_summary(line_user_id: Optional[str] = None, target_date=None) -> dict:
    """สรุปรายวัน — target_date เป็น datetime หรือ ISO string"""
    try:
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

        # เริ่ม-สิ้นสุดของวันนั้น
        start_dt = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = start_dt + timedelta(days=1) - timedelta(seconds=1)
        date_str = start_dt.strftime("%Y-%m-%d")

        sb = get_supabase()
        q = sb.table("transactions").select(
            "intent,amount,category,note,status,ts"
        ).gte("ts", start_dt.isoformat()).lte("ts", end_dt.isoformat()).neq("status", "DELETED")

        if line_user_id:
            user_id = get_user_id(line_user_id)
            if not user_id:
                return {
                    "success": True, "date": date_str,
                    "total_income": 0, "total_expense": 0, "balance": 0,
                    "expense_by_category": {}, "transactions": [],
                }
            q = q.eq("user_id", user_id)

        result = q.execute()
        agg = _aggregate(result.data or [])
        return {"success": True, "date": date_str, **agg}
    except Exception as e:
        print(f"[db_supabase.summary] get_date_summary error: {e}")
        return {"success": False, "error": str(e)}


def get_today_summary(line_user_id: Optional[str] = None) -> dict:
    return get_date_summary(line_user_id, datetime.now(pytz.timezone("Asia/Bangkok")))


def get_compare_summary(month_a: int, year_a: int, month_b: int, year_b: int,
                         line_user_id: Optional[str] = None) -> dict:
    """เปรียบเทียบ 2 เดือน"""
    a = get_summary(month_a, year_a, line_user_id)
    b = get_summary(month_b, year_b, line_user_id)
    return {"a": a, "b": b}


def get_compare_days_summary(line_user_id: str, date_a, date_b) -> dict:
    a = get_date_summary(line_user_id, date_a)
    b = get_date_summary(line_user_id, date_b)
    return {
        "a": a, "b": b,
        "date_a": a.get("date", ""),
        "date_b": b.get("date", ""),
    }
