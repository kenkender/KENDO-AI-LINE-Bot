"""
scripts/verify_migration.py
เทียบจำนวน rows + sum(amount) ระหว่าง Google Sheets และ Supabase

Usage:
    python scripts/verify_migration.py [--skip-test-users]
"""

import argparse
import os
import sys
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.client import get_sheet_client  # noqa: E402
from db_supabase.client import get_supabase, is_supabase_configured  # noqa: E402


TEST_USER_IDS = {"test_smoke_123", "dual_write_test_456"}


def _float(v) -> float:
    try:
        return float(v) if v not in (None, "", "None") else 0.0
    except (ValueError, TypeError):
        return 0.0


def _read_sheet(name: str) -> list:
    try:
        ss = get_sheet_client()
        return ss.worksheet(name).get_all_records()
    except Exception as e:
        print(f"  [warn] read sheet '{name}' failed: {e}")
        return []


# ─── Supabase counters (count rows per table, joining users for line_user_id) ─

def _sb_count_all(table: str) -> int:
    sb = get_supabase()
    res = sb.table(table).select("id", count="exact").execute()
    return res.count or 0


def _sb_count_with_line(table: str, skip_test: bool) -> int:
    """Count rows ใน Supabase table — exclude test users ถ้า skip_test=True"""
    sb = get_supabase()
    if not skip_test:
        return _sb_count_all(table)
    # หา UUID ของ test users
    res = sb.table("users").select("id,line_user_id").in_("line_user_id", list(TEST_USER_IDS)).execute()
    test_uids = [r["id"] for r in (res.data or [])]
    q = sb.table(table).select("id", count="exact")
    if test_uids:
        q = q.not_.in_("user_id", test_uids)
    res = q.execute()
    return res.count or 0


def _sb_sum_amount(table: str, skip_test: bool, amount_col: str = "amount", status_filter: Optional[tuple] = None) -> float:
    """SUM(amount) ใน Supabase — ดึงทุกแถวมาบวกเอง (Supabase REST ไม่ support aggregate)"""
    sb = get_supabase()
    test_uids: list = []
    if skip_test:
        res = sb.table("users").select("id").in_("line_user_id", list(TEST_USER_IDS)).execute()
        test_uids = [r["id"] for r in (res.data or [])]

    total = 0.0
    offset = 0
    page = 1000
    cols = f"{amount_col},user_id"
    if status_filter:
        cols += ",status"
    while True:
        q = sb.table(table).select(cols).range(offset, offset + page - 1)
        if status_filter:
            col, val = status_filter
            q = q.eq(col, val)
        if test_uids:
            q = q.not_.in_("user_id", test_uids)
        res = q.execute()
        data = res.data or []
        for r in data:
            total += _float(r.get(amount_col))
        if len(data) < page:
            break
        offset += page
    return total


# ─── Sheet counters ─────────────────────────────────────────────────────────

def _sheet_count(name: str, user_col: str, skip_test: bool, status_eq: Optional[tuple] = None) -> int:
    rows = _read_sheet(name)
    cnt = 0
    for r in rows:
        uid = str(r.get(user_col, ""))
        if not uid:
            continue
        if skip_test and uid in TEST_USER_IDS:
            continue
        if status_eq:
            col, vals = status_eq
            if str(r.get(col, "")) not in vals:
                continue
        cnt += 1
    return cnt


def _sheet_sum(name: str, user_col: str, amount_col: str, skip_test: bool,
                status_eq: Optional[tuple] = None) -> float:
    rows = _read_sheet(name)
    total = 0.0
    for r in rows:
        uid = str(r.get(user_col, ""))
        if not uid:
            continue
        if skip_test and uid in TEST_USER_IDS:
            continue
        if status_eq:
            col, vals = status_eq
            if str(r.get(col, "")) not in vals:
                continue
        total += _float(r.get(amount_col))
    return total


# ─── Main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-test-users", action="store_true")
    args = parser.parse_args()

    if not is_supabase_configured():
        print("ERROR: SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY ไม่ได้ตั้งค่า")
        sys.exit(1)

    print(f"=== Verify migration ===  skip_test_users={args.skip_test_users}\n")

    print(f"{'Table':24} | {'Sheets':>10} | {'Supabase':>10} | {'Diff':>10}")
    print("-" * 70)

    checks = [
        # (label, sheet_name, sheet_user_col, supabase_table)
        ("transactions",        "transactions",       "source_user_id", "transactions"),
        ("notes→reminders",     "notes",              "source_user_id", "reminders"),
        ("tasks",               "tasks",              "source_user_id", "tasks"),
        ("bills",               "bills",              "source_user_id", "bills"),
        ("watchlist",           "watchlist",          "source_user_id", "watchlist"),
        ("recurring_expenses",  "recurring_expenses", "source_user_id", "recurring_expenses"),
        ("interval_reminders",  "interval_reminders", "user_id",        "interval_reminders"),
        ("settings",            "settings",           "source_user_id", "settings"),
        ("user_prefs",          "user_prefs",         "source_user_id", "user_prefs"),
        ("budget_warnings",     "budget_warnings",    "source_user_id", "budget_warnings"),
    ]

    for label, sheet_name, user_col, sb_table in checks:
        sheet_n = _sheet_count(sheet_name, user_col, args.skip_test_users)
        try:
            sb_n = _sb_count_with_line(sb_table, args.skip_test_users)
        except Exception as e:
            print(f"{label:24} | {sheet_n:>10} | ERR        | -          ({e})")
            continue
        diff = sb_n - sheet_n
        mark = "✓" if diff == 0 else ("+" if diff > 0 else "!")
        print(f"{label:24} | {sheet_n:>10} | {sb_n:>10} | {diff:>+9} {mark}")

    # SUM(amount) — transactions (EXPENSE+INCOME, status=OK)
    print()
    print("=== SUM(amount) checks ===")
    print(f"{'Metric':40} | {'Sheets':>14} | {'Supabase':>14} | {'Diff':>12}")
    print("-" * 90)

    # transactions: status OK เท่านั้น
    tx_sheet_sum = _sheet_sum("transactions", "source_user_id", "amount",
                                args.skip_test_users, status_eq=("status", {"OK", ""}))
    try:
        tx_sb_sum = _sb_sum_amount("transactions", args.skip_test_users,
                                     status_filter=("status", "OK"))
    except Exception as e:
        tx_sb_sum = -1
        print(f"  [err] supabase sum transactions: {e}")
    diff = tx_sb_sum - tx_sheet_sum
    print(f"{'transactions amount (status=OK)':40} | {tx_sheet_sum:>14.2f} | {tx_sb_sum:>14.2f} | {diff:>+12.2f}")

    # bills: ACTIVE
    bills_sheet_sum = _sheet_sum("bills", "source_user_id", "amount",
                                   args.skip_test_users, status_eq=("status", {"ACTIVE"}))
    try:
        bills_sb_sum = _sb_sum_amount("bills", args.skip_test_users,
                                        status_filter=("status", "ACTIVE"))
    except Exception as e:
        bills_sb_sum = -1
        print(f"  [err] supabase sum bills: {e}")
    diff = bills_sb_sum - bills_sheet_sum
    print(f"{'bills amount (ACTIVE)':40} | {bills_sheet_sum:>14.2f} | {bills_sb_sum:>14.2f} | {diff:>+12.2f}")

    # recurring: ACTIVE
    rec_sheet_sum = _sheet_sum("recurring_expenses", "source_user_id", "amount",
                                 args.skip_test_users, status_eq=("status", {"ACTIVE"}))
    try:
        rec_sb_sum = _sb_sum_amount("recurring_expenses", args.skip_test_users,
                                      status_filter=("status", "ACTIVE"))
    except Exception as e:
        rec_sb_sum = -1
        print(f"  [err] supabase sum recurring: {e}")
    diff = rec_sb_sum - rec_sheet_sum
    print(f"{'recurring_expenses amount (ACTIVE)':40} | {rec_sheet_sum:>14.2f} | {rec_sb_sum:>14.2f} | {diff:>+12.2f}")


if __name__ == "__main__":
    main()
