"""
scripts/migrate_sheets_to_supabase.py
ย้ายข้อมูลเก่าจาก Google Sheets → Supabase

Usage:
    python scripts/migrate_sheets_to_supabase.py [--dry-run] [--skip-test-users] [--only TABLE]

Strategy:
    - Read-only ต่อ Google Sheets (ไม่แตะ)
    - Idempotent: ตรวจ existing rows ก่อน insert เพื่อกัน duplicate
      (เพราะ Phase 3 dual-write ทำให้บางแถวเข้า Supabase ไปแล้ว)
    - User mapping ทำครั้งเดียวต่อ line_user_id แล้ว cache
    - Error 1 row → log แล้วไปต่อ ไม่ abort
"""

import argparse
import re
import sys
from typing import Optional

# เพิ่ม path ให้ import db / db_supabase ได้
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.client import get_sheet_client  # noqa: E402
from db_supabase.client import get_supabase, is_supabase_configured  # noqa: E402
from db_supabase.users import get_or_create_user  # noqa: E402


TEST_USER_IDS = {"test_smoke_123", "dual_write_test_456"}


# ─── User cache ─────────────────────────────────────────────────────────────
_user_cache: dict = {}


def resolve_user(line_user_id: str) -> Optional[str]:
    """แปลง line_user_id → UUID (cache)"""
    if not line_user_id:
        return None
    if line_user_id in _user_cache:
        return _user_cache[line_user_id]
    uid = get_or_create_user(line_user_id)
    if uid:
        _user_cache[line_user_id] = uid
    return uid


# ─── Helpers ────────────────────────────────────────────────────────────────
def _bool(v) -> bool:
    return str(v).strip().upper() == "TRUE"


def _float(v) -> float:
    try:
        return float(v) if v not in (None, "", "None") else 0.0
    except (ValueError, TypeError):
        return 0.0


def _int(v) -> Optional[int]:
    try:
        s = str(v).strip()
        return int(s) if s.lstrip("-").isdigit() else None
    except (ValueError, TypeError):
        return None


def _str(v) -> str:
    return str(v) if v not in (None,) else ""


def _strip_extras_recur(note: str) -> tuple:
    """parse [EXTRAS:...] และ [RECUR:...] ออกจาก note — คืน (clean_note, extras, recurrence)"""
    extras = ""
    recurrence = ""
    m = re.search(r'\r?\n\[EXTRAS:(.*?)\]', note, re.DOTALL)
    if m:
        extras = m.group(1).strip()
    m = re.search(r'\r?\n\[RECUR:(.*?)\]', note, re.DOTALL)
    if m:
        recurrence = m.group(1).strip()
    clean = re.sub(r'\r?\n\[EXTRAS:.*?\]', '', note, flags=re.DOTALL)
    clean = re.sub(r'\r?\n\[RECUR:.*?\]', '', clean, flags=re.DOTALL)
    return clean.strip(), extras, recurrence


# ─── Sheet readers ──────────────────────────────────────────────────────────
def _read_sheet(name: str) -> list:
    try:
        ss = get_sheet_client()
        sheet = ss.worksheet(name)
        return sheet.get_all_records()
    except Exception as e:
        print(f"  [warn] read sheet '{name}' failed: {e}")
        return []


# ─── Stats container ────────────────────────────────────────────────────────
class Stats:
    def __init__(self, name: str):
        self.name = name
        self.read = 0
        self.inserted = 0
        self.skipped = 0
        self.errors = 0

    def __str__(self):
        return f"{self.name:24} | read={self.read:5} | inserted={self.inserted:5} | skipped={self.skipped:5} | errors={self.errors:3}"


# ─── Per-table migrators ────────────────────────────────────────────────────
def migrate_settings(dry: bool, skip_test: bool) -> Stats:
    s = Stats("settings")
    rows = _read_sheet("settings")
    sb = get_supabase()
    for r in rows:
        s.read += 1
        line_id = _str(r.get("source_user_id"))
        if not line_id or (skip_test and line_id in TEST_USER_IDS):
            s.skipped += 1
            continue
        uid = resolve_user(line_id)
        if not uid:
            s.errors += 1
            continue
        payload = {
            "user_id": uid,
            "budget": _float(r.get("budget")),
            "savings_goal": _float(r.get("savings_goal")),
        }
        try:
            if not dry:
                sb.table("settings").upsert(payload, on_conflict="user_id").execute()
            s.inserted += 1
        except Exception as e:
            print(f"  [err] settings row uid={line_id}: {e}")
            s.errors += 1
    return s


def migrate_user_prefs(dry: bool, skip_test: bool) -> Stats:
    s = Stats("user_prefs")
    rows = _read_sheet("user_prefs")
    sb = get_supabase()
    for r in rows:
        s.read += 1
        line_id = _str(r.get("source_user_id"))
        if not line_id or (skip_test and line_id in TEST_USER_IDS):
            s.skipped += 1
            continue
        uid = resolve_user(line_id)
        if not uid:
            s.errors += 1
            continue
        hour = _int(r.get("briefing_hour"))
        minute = _int(r.get("briefing_minute")) or 0
        city = _str(r.get("briefing_city")) or "กรุงเทพ"
        remind_day = _int(r.get("recurring_remind_day"))
        payload = {
            "user_id": uid,
            "briefing_hour": hour,
            "briefing_minute": minute if 0 <= minute <= 59 else 0,
            "briefing_city": city,
            "recurring_remind_day": remind_day if (remind_day and 1 <= remind_day <= 31) else None,
        }
        try:
            if not dry:
                sb.table("user_prefs").upsert(payload, on_conflict="user_id").execute()
            s.inserted += 1
        except Exception as e:
            print(f"  [err] user_prefs row uid={line_id}: {e}")
            s.errors += 1
    return s


def migrate_budget_warnings(dry: bool, skip_test: bool) -> Stats:
    s = Stats("budget_warnings")
    rows = _read_sheet("budget_warnings")
    sb = get_supabase()
    for r in rows:
        s.read += 1
        line_id = _str(r.get("source_user_id"))
        month_key = _str(r.get("month_key"))
        if not line_id or not month_key or (skip_test and line_id in TEST_USER_IDS):
            s.skipped += 1
            continue
        uid = resolve_user(line_id)
        if not uid:
            s.errors += 1
            continue
        payload = {
            "user_id": uid,
            "month_key": month_key,
            "warned_levels": _str(r.get("warned_levels")),
        }
        try:
            if not dry:
                sb.table("budget_warnings").upsert(payload, on_conflict="user_id,month_key").execute()
            s.inserted += 1
        except Exception as e:
            print(f"  [err] budget_warnings row uid={line_id} mk={month_key}: {e}")
            s.errors += 1
    return s


def migrate_transactions(dry: bool, skip_test: bool) -> Stats:
    s = Stats("transactions")
    rows = _read_sheet("transactions")
    sb = get_supabase()

    # pre-fetch existing (user_id, ts, raw_message) เพื่อ dedup
    existing: set = set()
    if not dry:
        try:
            page_size = 1000
            offset = 0
            while True:
                res = sb.table("transactions").select("user_id,ts,raw_message").range(offset, offset + page_size - 1).execute()
                data = res.data or []
                for row in data:
                    existing.add((row.get("user_id"), row.get("ts"), row.get("raw_message") or ""))
                if len(data) < page_size:
                    break
                offset += page_size
        except Exception as e:
            print(f"  [warn] prefetch transactions: {e}")

    for r in rows:
        s.read += 1
        line_id = _str(r.get("source_user_id"))
        intent = _str(r.get("intent"))
        if intent not in ("EXPENSE", "INCOME"):
            s.skipped += 1
            continue
        if not line_id or (skip_test and line_id in TEST_USER_IDS):
            s.skipped += 1
            continue
        uid = resolve_user(line_id)
        if not uid:
            s.errors += 1
            continue
        ts = _str(r.get("timestamp"))
        raw_msg = _str(r.get("raw_message"))
        if (uid, ts, raw_msg) in existing:
            s.skipped += 1
            continue
        payload = {
            "user_id": uid,
            "intent": intent,
            "amount": _float(r.get("amount")),
            "currency": _str(r.get("currency")) or "THB",
            "category": _str(r.get("category")) or "อื่นๆ",
            "note": _str(r.get("note")),
            "raw_message": raw_msg,
            "status": _str(r.get("status")) or "OK",
            "ts": ts,
        }
        try:
            if not dry:
                sb.table("transactions").insert(payload).execute()
            s.inserted += 1
            existing.add((uid, ts, raw_msg))
        except Exception as e:
            print(f"  [err] transactions row uid={line_id} ts={ts}: {e}")
            s.errors += 1
    return s


def migrate_notes(dry: bool, skip_test: bool) -> Stats:
    """notes sheet → reminders table (NOTE + REMINDER รวมกัน)"""
    s = Stats("notes→reminders")
    rows = _read_sheet("notes")
    sb = get_supabase()

    existing: set = set()
    if not dry:
        try:
            page_size = 1000
            offset = 0
            while True:
                res = sb.table("reminders").select("user_id,ts,raw_message").range(offset, offset + page_size - 1).execute()
                data = res.data or []
                for row in data:
                    existing.add((row.get("user_id"), row.get("ts"), row.get("raw_message") or ""))
                if len(data) < page_size:
                    break
                offset += page_size
        except Exception as e:
            print(f"  [warn] prefetch reminders: {e}")

    for r in rows:
        s.read += 1
        line_id = _str(r.get("source_user_id"))
        if not line_id or (skip_test and line_id in TEST_USER_IDS):
            s.skipped += 1
            continue
        uid = resolve_user(line_id)
        if not uid:
            s.errors += 1
            continue
        ts = _str(r.get("timestamp"))
        raw_msg = _str(r.get("raw_message"))
        if (uid, ts, raw_msg) in existing:
            s.skipped += 1
            continue
        note_raw = _str(r.get("note"))
        clean_note, extras, recurrence = _strip_extras_recur(note_raw)
        reminder_dt = _str(r.get("reminder_datetime")) or None
        payload = {
            "user_id": uid,
            "note": clean_note,
            "raw_message": raw_msg,
            "reminder_datetime": reminder_dt,
            "reminder_extras": extras,
            "recurrence": recurrence,
            "calendar_event_id": _str(r.get("calendar_event_id")),
            "status": _str(r.get("status")) or "OK",
            "ts": ts,
        }
        try:
            if not dry:
                sb.table("reminders").insert(payload).execute()
            s.inserted += 1
            existing.add((uid, ts, raw_msg))
        except Exception as e:
            print(f"  [err] reminders row uid={line_id} ts={ts}: {e}")
            s.errors += 1
    return s


def migrate_tasks(dry: bool, skip_test: bool) -> Stats:
    s = Stats("tasks")
    rows = _read_sheet("tasks")
    sb = get_supabase()

    existing: set = set()
    if not dry:
        try:
            res = sb.table("tasks").select("user_id,ts,task").execute()
            for row in (res.data or []):
                existing.add((row.get("user_id"), row.get("ts"), row.get("task") or ""))
        except Exception as e:
            print(f"  [warn] prefetch tasks: {e}")

    for r in rows:
        s.read += 1
        line_id = _str(r.get("source_user_id"))
        if not line_id or (skip_test and line_id in TEST_USER_IDS):
            s.skipped += 1
            continue
        uid = resolve_user(line_id)
        if not uid:
            s.errors += 1
            continue
        ts = _str(r.get("timestamp"))
        task = _str(r.get("task"))
        if not task:
            s.skipped += 1
            continue
        if (uid, ts, task) in existing:
            s.skipped += 1
            continue
        payload = {
            "user_id": uid,
            "task": task,
            "status": _str(r.get("status")) or "PENDING",
            "ts": ts,
        }
        try:
            if not dry:
                sb.table("tasks").insert(payload).execute()
            s.inserted += 1
            existing.add((uid, ts, task))
        except Exception as e:
            print(f"  [err] tasks row uid={line_id} ts={ts}: {e}")
            s.errors += 1
    return s


def migrate_bills(dry: bool, skip_test: bool) -> Stats:
    s = Stats("bills")
    rows = _read_sheet("bills")
    sb = get_supabase()

    existing: set = set()
    if not dry:
        try:
            res = sb.table("bills").select("user_id,bill_name,due_day,amount").execute()
            for row in (res.data or []):
                key = (row.get("user_id"), row.get("bill_name") or "", row.get("due_day"), float(row.get("amount") or 0))
                existing.add(key)
        except Exception as e:
            print(f"  [warn] prefetch bills: {e}")

    for r in rows:
        s.read += 1
        line_id = _str(r.get("source_user_id"))
        if not line_id or (skip_test and line_id in TEST_USER_IDS):
            s.skipped += 1
            continue
        uid = resolve_user(line_id)
        if not uid:
            s.errors += 1
            continue
        name = _str(r.get("bill_name"))
        amount = _float(r.get("amount"))
        due_day = _int(r.get("due_day"))
        if not name or not due_day or not (1 <= due_day <= 31):
            s.skipped += 1
            continue
        key = (uid, name, due_day, amount)
        if key in existing:
            s.skipped += 1
            continue
        last_reminded = _str(r.get("last_reminded")) or None
        payload = {
            "user_id": uid,
            "bill_name": name,
            "amount": amount,
            "due_day": due_day,
            "status": _str(r.get("status")) or "ACTIVE",
            "last_reminded": last_reminded,
        }
        try:
            if not dry:
                sb.table("bills").insert(payload).execute()
            s.inserted += 1
            existing.add(key)
        except Exception as e:
            print(f"  [err] bills row uid={line_id} name={name}: {e}")
            s.errors += 1
    return s


def migrate_watchlist(dry: bool, skip_test: bool) -> Stats:
    s = Stats("watchlist")
    rows = _read_sheet("watchlist")
    sb = get_supabase()

    existing: set = set()
    if not dry:
        try:
            res = sb.table("watchlist").select("user_id,ts,title").execute()
            for row in (res.data or []):
                existing.add((row.get("user_id"), row.get("ts"), row.get("title") or ""))
        except Exception as e:
            print(f"  [warn] prefetch watchlist: {e}")

    for r in rows:
        s.read += 1
        line_id = _str(r.get("source_user_id"))
        if not line_id or (skip_test and line_id in TEST_USER_IDS):
            s.skipped += 1
            continue
        uid = resolve_user(line_id)
        if not uid:
            s.errors += 1
            continue
        ts = _str(r.get("timestamp"))
        title = _str(r.get("title"))
        if not title:
            s.skipped += 1
            continue
        if (uid, ts, title) in existing:
            s.skipped += 1
            continue
        payload = {
            "user_id": uid,
            "category": _str(r.get("category")) or "อื่นๆ",
            "title": title,
            "status": _str(r.get("status")) or "PENDING",
            "ts": ts,
        }
        try:
            if not dry:
                sb.table("watchlist").insert(payload).execute()
            s.inserted += 1
            existing.add((uid, ts, title))
        except Exception as e:
            print(f"  [err] watchlist row uid={line_id} title={title}: {e}")
            s.errors += 1
    return s


def migrate_recurring(dry: bool, skip_test: bool) -> Stats:
    """recurring_expenses sheet → recurring_expenses table
    NOTE: sheet column = item_name, supabase = name
    """
    s = Stats("recurring_expenses")
    rows = _read_sheet("recurring_expenses")
    sb = get_supabase()

    existing: set = set()
    if not dry:
        try:
            res = sb.table("recurring_expenses").select("user_id,name,amount,status").execute()
            for row in (res.data or []):
                key = (row.get("user_id"), row.get("name") or "", float(row.get("amount") or 0), row.get("status"))
                existing.add(key)
        except Exception as e:
            print(f"  [warn] prefetch recurring: {e}")

    for r in rows:
        s.read += 1
        line_id = _str(r.get("source_user_id"))
        if not line_id or (skip_test and line_id in TEST_USER_IDS):
            s.skipped += 1
            continue
        uid = resolve_user(line_id)
        if not uid:
            s.errors += 1
            continue
        name = _str(r.get("item_name"))
        amount = _float(r.get("amount"))
        status = _str(r.get("status")) or "ACTIVE"
        if not name or amount <= 0:
            s.skipped += 1
            continue
        key = (uid, name, amount, status)
        if key in existing:
            s.skipped += 1
            continue
        payload = {
            "user_id": uid,
            "name": name,
            "amount": amount,
            "category": _str(r.get("category")) or "อื่นๆ",
            "status": status,
        }
        try:
            if not dry:
                sb.table("recurring_expenses").insert(payload).execute()
            s.inserted += 1
            existing.add(key)
        except Exception as e:
            print(f"  [err] recurring row uid={line_id} name={name}: {e}")
            s.errors += 1
    return s


def migrate_interval_reminders(dry: bool, skip_test: bool) -> Stats:
    """sheet column = user_id (LINE id ตรงๆ ไม่ใช่ source_user_id)"""
    s = Stats("interval_reminders")
    rows = _read_sheet("interval_reminders")
    sb = get_supabase()

    existing: set = set()
    if not dry:
        try:
            res = sb.table("interval_reminders").select("user_id,label,interval_minutes,active").execute()
            for row in (res.data or []):
                key = (row.get("user_id"), row.get("label") or "", row.get("interval_minutes"), bool(row.get("active")))
                existing.add(key)
        except Exception as e:
            print(f"  [warn] prefetch interval_reminders: {e}")

    for r in rows:
        s.read += 1
        line_id = _str(r.get("user_id"))  # หมายเหตุ: column name แตกต่าง
        if not line_id or (skip_test and line_id in TEST_USER_IDS):
            s.skipped += 1
            continue
        uid = resolve_user(line_id)
        if not uid:
            s.errors += 1
            continue
        label = _str(r.get("label"))
        interval = _int(r.get("interval_minutes"))
        if not label or not interval or interval < 1:
            s.skipped += 1
            continue
        active = _bool(r.get("active"))
        key = (uid, label, interval, active)
        if key in existing:
            s.skipped += 1
            continue
        next_fire = _str(r.get("next_fire"))
        if not next_fire:
            s.skipped += 1
            continue
        payload = {
            "user_id": uid,
            "label": label,
            "interval_minutes": interval,
            "next_fire": next_fire,
            "active": active,
        }
        try:
            if not dry:
                sb.table("interval_reminders").insert(payload).execute()
            s.inserted += 1
            existing.add(key)
        except Exception as e:
            print(f"  [err] interval row uid={line_id} label={label}: {e}")
            s.errors += 1
    return s


# ─── Orchestrator ───────────────────────────────────────────────────────────
MIGRATORS = {
    "settings": migrate_settings,
    "user_prefs": migrate_user_prefs,
    "budget_warnings": migrate_budget_warnings,
    "transactions": migrate_transactions,
    "notes": migrate_notes,
    "tasks": migrate_tasks,
    "bills": migrate_bills,
    "watchlist": migrate_watchlist,
    "recurring": migrate_recurring,
    "interval_reminders": migrate_interval_reminders,
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="ไม่ insert จริง — แค่ scan + นับ")
    parser.add_argument("--skip-test-users", action="store_true", help="ข้าม test_smoke_123 / dual_write_test_456")
    parser.add_argument("--only", type=str, default=None, help="รันเฉพาะ table (comma-separated)")
    args = parser.parse_args()

    if not is_supabase_configured():
        print("ERROR: SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY ไม่ได้ตั้งค่า")
        sys.exit(1)

    print(f"=== Migration: Sheets → Supabase ===")
    print(f"  dry_run={args.dry_run}  skip_test_users={args.skip_test_users}")
    if args.only:
        print(f"  only={args.only}")
    print()

    selected = set(args.only.split(",")) if args.only else set(MIGRATORS.keys())
    results = []
    for name, fn in MIGRATORS.items():
        if name not in selected:
            continue
        print(f"→ Migrating {name} ...")
        try:
            stats = fn(args.dry_run, args.skip_test_users)
            results.append(stats)
            print(f"  {stats}")
        except Exception as e:
            print(f"  [FATAL] {name}: {e}")

    print()
    print("=== Summary ===")
    for s in results:
        print(s)
    print(f"\nUsers resolved: {len(_user_cache)}")


if __name__ == "__main__":
    main()
