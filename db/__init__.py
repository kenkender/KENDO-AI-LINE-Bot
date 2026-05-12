"""
db/__init__.py

Feature flag READ_FROM_SUPABASE ควบคุมว่า read path มาจากไหน:
  - READ_FROM_SUPABASE=false (default)  → อ่านจาก Google Sheets (db/*)
  - READ_FROM_SUPABASE=true             → อ่านจาก Supabase (db_supabase/*)

write path:
  - db/*  ตัว module เดิมยัง dual-write ทั้ง Sheets + Supabase อยู่
  - db_supabase/*  เขียนเฉพาะ Supabase

Rollback: toggle env var บน Render → restart → ใช้ Sheets อีกครั้ง
"""
import os

from db.client import get_sheet_client, get_or_create_sheet

_USE_SUPABASE = os.getenv("READ_FROM_SUPABASE", "false").strip().lower() == "true"

if _USE_SUPABASE:
    print("[db] READ_FROM_SUPABASE=true -> using Supabase as read path")
    from db_supabase.transactions import (
        append_transaction, delete_last_transaction, search_transactions,
    )
    from db_supabase.users import get_all_line_user_ids as get_all_user_ids
    from db_supabase.notes import (
        append_note, get_pending_reminders, mark_reminder_sent,
        get_active_reminders, cancel_reminder, get_today_reminders,
        create_recurring_reminder,
    )
    from db_supabase.budget import (
        set_budget, get_budget_status, set_savings_goal, get_savings_status,
        get_budget_warn_state, mark_budget_warned,
    )
    from db_supabase.tasks import add_task, list_tasks, complete_task
    from db_supabase.bills import (
        add_bill, list_bills, delete_bill, get_due_bills, mark_bill_reminded,
    )
    from db_supabase.watchlist import (
        add_watchlist_item, list_watchlist_items, done_watchlist_item,
    )
    from db_supabase.prefs import (
        set_briefing, get_briefing, get_all_briefing_users,
        set_recurring_remind_day, get_recurring_remind_day,
        get_all_recurring_remind_users,
    )
    from db_supabase.summary import (
        get_summary, get_today_summary, get_date_summary,
        get_compare_summary, get_compare_days_summary,
    )
    # format_summary_message / format_quick_summary ยังอยู่ที่ db.summary
    # เพราะเป็น pure formatter ไม่แตะ data store
    from db.summary import format_summary_message, format_quick_summary
    from db_supabase.recurring import (
        add_recurring_items, list_recurring_items, delete_recurring_item,
        get_all_recurring_users,
    )
    from db_supabase.interval_reminder import (
        add_interval_reminder, get_active_interval_reminders,
        get_all_due_interval_reminders, update_next_fire,
        cancel_interval_reminder_by_label, cancel_all_interval_reminders,
    )
else:
    from db.transactions import append_transaction, delete_last_transaction, search_transactions, get_all_user_ids
    from db.notes import append_note, get_pending_reminders, mark_reminder_sent, get_active_reminders, cancel_reminder, get_today_reminders, create_recurring_reminder
    from db.budget import set_budget, get_budget_status, set_savings_goal, get_savings_status, get_budget_warn_state, mark_budget_warned
    from db.tasks import add_task, list_tasks, complete_task
    from db.bills import add_bill, list_bills, delete_bill, get_due_bills, mark_bill_reminded
    from db.watchlist import add_watchlist_item, list_watchlist_items, done_watchlist_item
    from db.prefs import (set_briefing, get_briefing, get_all_briefing_users,
                          set_recurring_remind_day, get_recurring_remind_day,
                          get_all_recurring_remind_users)
    from db.summary import get_summary, format_summary_message, format_quick_summary, get_today_summary, get_date_summary, get_compare_summary, get_compare_days_summary
    from db.recurring import add_recurring_items, list_recurring_items, delete_recurring_item, get_all_recurring_users
    from db.interval_reminder import (add_interval_reminder, get_active_interval_reminders,
                                       get_all_due_interval_reminders, update_next_fire,
                                       cancel_interval_reminder_by_label, cancel_all_interval_reminders)
