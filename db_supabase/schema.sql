-- ============================================================================
-- KENDO AI LINE Bot — Supabase Schema (Phase 1)
-- ============================================================================
-- Run นี้ทั้งไฟล์ใน Supabase SQL Editor แค่ครั้งเดียว
-- จะสร้าง 12 tables + indexes + RLS policies + helper functions
--
-- Architecture:
-- - line_user_id (จาก LINE webhook) เป็น identity หลัก
-- - auth_user_id (Supabase Auth) เป็น optional link สำหรับ web dashboard อนาคต
-- - ทุก table มี user_id (UUID) FK → users.id
-- - service_role bypass RLS (backend ทำงานได้เลย)
-- - RLS policies เตรียมไว้สำหรับ web client (anon/authenticated)
-- ============================================================================

-- ─── Helper Function: updated_at auto-update ────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ============================================================================
-- 1. USERS (master)
-- ============================================================================
CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    line_user_id    TEXT UNIQUE NOT NULL,
    auth_user_id    UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    display_name    TEXT,
    tier            TEXT NOT NULL DEFAULT 'free'
                    CHECK (tier IN ('free', 'premium', 'enterprise')),
    tier_started_at TIMESTAMPTZ DEFAULT NOW(),
    tier_expires_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_line_id ON users(line_user_id);
CREATE INDEX IF NOT EXISTS idx_users_auth_id ON users(auth_user_id) WHERE auth_user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_users_tier ON users(tier);

DROP TRIGGER IF EXISTS trg_users_updated ON users;
CREATE TRIGGER trg_users_updated BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- ============================================================================
-- 2. USER_PREFS (briefing, recurring reminder day)
-- ============================================================================
CREATE TABLE IF NOT EXISTS user_prefs (
    user_id              UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    briefing_hour        SMALLINT CHECK (briefing_hour BETWEEN 0 AND 23),
    briefing_minute      SMALLINT DEFAULT 0 CHECK (briefing_minute BETWEEN 0 AND 59),
    briefing_city        TEXT DEFAULT 'กรุงเทพ',
    recurring_remind_day SMALLINT CHECK (recurring_remind_day BETWEEN 1 AND 31),
    updated_at           TIMESTAMPTZ DEFAULT NOW()
);

DROP TRIGGER IF EXISTS trg_user_prefs_updated ON user_prefs;
CREATE TRIGGER trg_user_prefs_updated BEFORE UPDATE ON user_prefs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- ============================================================================
-- 3. SETTINGS (budget, savings)
-- ============================================================================
CREATE TABLE IF NOT EXISTS settings (
    user_id       UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    budget        NUMERIC(12, 2) DEFAULT 0,
    savings_goal  NUMERIC(12, 2) DEFAULT 0,
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

DROP TRIGGER IF EXISTS trg_settings_updated ON settings;
CREATE TRIGGER trg_settings_updated BEFORE UPDATE ON settings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();


-- ============================================================================
-- 4. TRANSACTIONS (EXPENSE / INCOME)
-- ============================================================================
CREATE TABLE IF NOT EXISTS transactions (
    id           BIGSERIAL PRIMARY KEY,
    user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    intent       TEXT NOT NULL CHECK (intent IN ('EXPENSE', 'INCOME')),
    amount       NUMERIC(12, 2) NOT NULL,
    currency     TEXT DEFAULT 'THB',
    category     TEXT DEFAULT 'อื่นๆ',
    note         TEXT,
    raw_message  TEXT,
    status       TEXT DEFAULT 'OK' CHECK (status IN ('OK', 'DELETED')),
    ts           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tx_user_ts ON transactions(user_id, ts DESC);
CREATE INDEX IF NOT EXISTS idx_tx_user_intent ON transactions(user_id, intent, status);
-- หมายเหตุ: query สรุปเดือน ใช้ idx_tx_user_ts ก็เร็วพอ
-- (WHERE user_id = ? AND ts >= '...' AND ts < '...')


-- ============================================================================
-- 5. REMINDERS (NOTE + REMINDER รวมกัน — เพราะ structure เหมือนกัน)
-- ============================================================================
CREATE TABLE IF NOT EXISTS reminders (
    id                BIGSERIAL PRIMARY KEY,
    user_id           UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    note              TEXT NOT NULL,
    raw_message       TEXT,
    reminder_datetime TIMESTAMPTZ,
    reminder_extras   TEXT,                 -- "weather:กรุงเทพ,tasks"
    recurrence        TEXT,                 -- "daily" | "weekly:1" | "monthly:25"
    calendar_event_id TEXT,
    status            TEXT DEFAULT 'OK'
                      CHECK (status IN ('OK', 'SENT', 'CANCELLED')),
    ts                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rem_user_status ON reminders(user_id, status);
CREATE INDEX IF NOT EXISTS idx_rem_due
    ON reminders(reminder_datetime)
    WHERE status = 'OK' AND reminder_datetime IS NOT NULL;


-- ============================================================================
-- 6. TASKS
-- ============================================================================
CREATE TABLE IF NOT EXISTS tasks (
    id           BIGSERIAL PRIMARY KEY,
    user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    task         TEXT NOT NULL,
    status       TEXT DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'DONE')),
    ts           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_tasks_user_status ON tasks(user_id, status);


-- ============================================================================
-- 7. BILLS (รายเดือน)
-- ============================================================================
CREATE TABLE IF NOT EXISTS bills (
    id            BIGSERIAL PRIMARY KEY,
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bill_name     TEXT NOT NULL,
    amount        NUMERIC(12, 2) NOT NULL,
    due_day       SMALLINT NOT NULL CHECK (due_day BETWEEN 1 AND 31),
    status        TEXT DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'DELETED')),
    last_reminded DATE,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bills_active ON bills(user_id, status) WHERE status = 'ACTIVE';


-- ============================================================================
-- 8. WATCHLIST (หนัง / เกม / เพลง / หนังสือ)
-- ============================================================================
CREATE TABLE IF NOT EXISTS watchlist (
    id        BIGSERIAL PRIMARY KEY,
    user_id   UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category  TEXT DEFAULT 'อื่นๆ',
    title     TEXT NOT NULL,
    status    TEXT DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'DONE')),
    ts        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_watch_user_status ON watchlist(user_id, status);


-- ============================================================================
-- 9. RECURRING_EXPENSES (subscriptions)
-- ============================================================================
CREATE TABLE IF NOT EXISTS recurring_expenses (
    id          BIGSERIAL PRIMARY KEY,
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    amount      NUMERIC(12, 2) NOT NULL,
    category    TEXT DEFAULT 'อื่นๆ',
    status      TEXT DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'DELETED')),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_recur_active ON recurring_expenses(user_id, status) WHERE status = 'ACTIVE';


-- ============================================================================
-- 10. INTERVAL_REMINDERS (เตือนทุก X นาที/ชม.)
-- ============================================================================
CREATE TABLE IF NOT EXISTS interval_reminders (
    id               BIGSERIAL PRIMARY KEY,
    user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    label            TEXT NOT NULL,
    interval_minutes INTEGER NOT NULL CHECK (interval_minutes >= 1),
    next_fire        TIMESTAMPTZ NOT NULL,
    active           BOOLEAN DEFAULT TRUE,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_interval_due ON interval_reminders(next_fire) WHERE active = TRUE;
CREATE INDEX IF NOT EXISTS idx_interval_user ON interval_reminders(user_id, active);


-- ============================================================================
-- 11. BUDGET_WARNINGS (anti-spam state สำหรับ 50%/75%/90%)
-- ============================================================================
CREATE TABLE IF NOT EXISTS budget_warnings (
    user_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    month_key      TEXT NOT NULL,  -- "2026-05"
    warned_levels  TEXT,           -- "50,75,90"
    updated_at     TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (user_id, month_key)
);


-- ============================================================================
-- 12. FEATURE_REQUESTS (log สิ่งที่บอทไม่เข้าใจ)
-- ============================================================================
CREATE TABLE IF NOT EXISTS feature_requests (
    id              BIGSERIAL PRIMARY KEY,
    user_id         UUID REFERENCES users(id) ON DELETE SET NULL,
    message         TEXT,
    detected_intent TEXT,
    ts              TIMESTAMPTZ DEFAULT NOW()
);


-- ============================================================================
-- HELPER FUNCTION: get_or_create_user (atomic)
-- ============================================================================
-- ใช้ใน Python: result = supabase.rpc('get_or_create_user', {'p_line_user_id': '...', 'p_display_name': '...'}).execute()
-- คืน users.id (UUID) — ใช้เป็น user_id ใน table อื่น
CREATE OR REPLACE FUNCTION get_or_create_user(
    p_line_user_id TEXT,
    p_display_name TEXT DEFAULT NULL
)
RETURNS UUID AS $$
DECLARE
    v_user_id UUID;
BEGIN
    -- หา user ที่มีอยู่
    SELECT id INTO v_user_id FROM users WHERE line_user_id = p_line_user_id;

    -- ถ้าไม่มี → สร้างใหม่
    IF v_user_id IS NULL THEN
        INSERT INTO users (line_user_id, display_name)
        VALUES (p_line_user_id, p_display_name)
        RETURNING id INTO v_user_id;
    ELSE
        -- อัปเดต display_name ถ้าส่งมาและต่างจากเดิม
        IF p_display_name IS NOT NULL AND p_display_name <> '' THEN
            UPDATE users SET display_name = p_display_name
            WHERE id = v_user_id AND COALESCE(display_name, '') <> p_display_name;
        END IF;
    END IF;

    RETURN v_user_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;


-- ============================================================================
-- ROW LEVEL SECURITY (RLS)
-- ============================================================================
-- เปิด RLS ทุก table — service_role bypass อัตโนมัติ (backend ทำงานได้)
-- ตอนนี้ยังไม่มี policy สำหรับ anon/authenticated → เห็นไม่ได้
-- อนาคต web dashboard เพิ่ม policy: USING (user_id IN (SELECT id FROM users WHERE auth_user_id = auth.uid()))

ALTER TABLE users               ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_prefs          ENABLE ROW LEVEL SECURITY;
ALTER TABLE settings            ENABLE ROW LEVEL SECURITY;
ALTER TABLE transactions        ENABLE ROW LEVEL SECURITY;
ALTER TABLE reminders           ENABLE ROW LEVEL SECURITY;
ALTER TABLE tasks               ENABLE ROW LEVEL SECURITY;
ALTER TABLE bills               ENABLE ROW LEVEL SECURITY;
ALTER TABLE watchlist           ENABLE ROW LEVEL SECURITY;
ALTER TABLE recurring_expenses  ENABLE ROW LEVEL SECURITY;
ALTER TABLE interval_reminders  ENABLE ROW LEVEL SECURITY;
ALTER TABLE budget_warnings     ENABLE ROW LEVEL SECURITY;
ALTER TABLE feature_requests    ENABLE ROW LEVEL SECURITY;


-- ============================================================================
-- DONE — ตรวจสอบโดยรัน:
--   SELECT table_name FROM information_schema.tables
--   WHERE table_schema = 'public' ORDER BY table_name;
-- ควรเห็น 12 tables
-- ============================================================================
