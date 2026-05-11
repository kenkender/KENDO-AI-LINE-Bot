# db_supabase — Supabase Migration

โมดูลใหม่สำหรับเก็บข้อมูลใน Supabase (PostgreSQL) แทน Google Sheets

## Phase 1: Schema Setup (ตอนนี้)

### วิธี deploy schema

1. เปิด **Supabase Dashboard** → project ของคุณ
2. ทางซ้าย เลือก **SQL Editor** (ไอคอน `<>`)
3. กด **+ New query**
4. Copy ทั้งหมดจาก `schema.sql` paste ลงไป
5. กด **Run** (มุมขวาล่าง) — รอ ~5 วินาที
6. ควรเห็น "Success. No rows returned"

### ตรวจสอบว่าสร้างครบ

ใน SQL Editor รันคำสั่งนี้:
```sql
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public' ORDER BY table_name;
```

ควรเห็น **12 tables**:
- bills
- budget_warnings
- feature_requests
- interval_reminders
- recurring_expenses
- reminders
- settings
- tasks
- transactions
- user_prefs
- users
- watchlist

## Architecture

```
users (line_user_id + auth_user_id)
  ↓ FK (UUID)
  ├─ user_prefs (1:1)
  ├─ settings (1:1)
  ├─ transactions (1:N)
  ├─ reminders (1:N)
  ├─ tasks (1:N)
  ├─ bills (1:N)
  ├─ watchlist (1:N)
  ├─ recurring_expenses (1:N)
  ├─ interval_reminders (1:N)
  ├─ budget_warnings (1:N, composite PK)
  └─ feature_requests (1:N)
```

## Auth flow

- **ตอนนี้:** Backend ใช้ `service_role` key → bypass RLS → ทำงานได้เลย
- **Identity:** ใช้ `line_user_id` (จาก LINE webhook) → lookup `users.id` (UUID)
- **Helper:** Call `get_or_create_user(line_user_id, display_name)` → คืน UUID

## Tier system

- `free` (default), `premium`, `enterprise`
- Feature gating ทำใน Python — ไม่ใช่ที่ database

## Next phases

- **Phase 2:** Python module ที่ใช้ supabase-py — เขียนขนานกับ `db/` เดิม
- **Phase 3:** Dual-write — เขียนทั้ง Sheets + Supabase
- **Phase 4:** Migrate ข้อมูลเก่า → ตัด Sheets
