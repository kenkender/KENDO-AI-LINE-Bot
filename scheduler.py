"""
scheduler.py
ตรวจสอบ reminder ทุก 60 วินาที
ถ้าถึงเวลาแล้ว → ส่ง LINE Push Message
"""

import asyncio
import calendar
import os
import httpx
from dotenv import load_dotenv
from sheets import (get_pending_reminders, mark_reminder_sent, get_summary,
                    get_all_user_ids, format_summary_message,
                    get_budget_status, get_budget_warn_state, mark_budget_warned,
                    list_tasks)
from datetime import datetime
import pytz

load_dotenv()

LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"
LINE_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")


async def send_push_message(user_id: str, message: str) -> bool:
    """ส่ง LINE Push Message หา user โดยตรง"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"
    }
    payload = {
        "to": user_id,
        "messages": [{"type": "text", "text": message}]
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(LINE_PUSH_URL, json=payload, headers=headers)
            if response.status_code == 200:
                print(f"[scheduler] Push sent to {user_id}")
                return True
            else:
                print(f"[scheduler] Push failed: {response.status_code} {response.text}")
                return False
    except Exception as e:
        print(f"[scheduler] send_push_message error: {e}")
        return False


async def send_weekly_summary():
    """ส่งสรุปรายสัปดาห์ทุกวันอาทิตย์ เวลา 20:00"""
    user_ids = get_all_user_ids()
    for user_id in user_ids:
        try:
            summary = get_summary()
            if not summary["success"] or (summary["total_income"] == 0 and summary["total_expense"] == 0):
                continue
            msg = "📅 สรุปประจำสัปดาห์ จาก KENDO AI 🤖\n\n" + format_summary_message(summary)
            await send_push_message(user_id, msg)
            print(f"[scheduler] Weekly summary sent to {user_id}")
        except Exception as e:
            print(f"[scheduler] weekly summary error for {user_id}: {e}")


async def check_budget_warnings():
    """ตรวจ burn rate ของทุก user แจ้งเตือนที่ 50%, 75%, 90% ของงบ (แต่ละระดับ 1 ครั้ง/เดือน)"""
    THRESHOLDS = [50, 75, 90]
    bangkok_tz = pytz.timezone("Asia/Bangkok")
    now = datetime.now(bangkok_tz)
    month_key = now.strftime("%Y-%m")
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    days_elapsed = max(now.day, 1)

    user_ids = get_all_user_ids()
    for user_id in user_ids:
        try:
            status = get_budget_status(user_id)
            budget = status["budget"]
            if budget <= 0:
                continue

            expense = status["expense"]
            pct = (expense / budget) * 100
            projected = (expense / days_elapsed) * days_in_month

            warned = get_budget_warn_state(user_id, month_key)

            for threshold in THRESHOLDS:
                if threshold in warned or pct < threshold:
                    continue

                if threshold == 50:
                    icon, level_text = "🟡", "ใช้ไปครึ่งนึงแล้ว"
                elif threshold == 75:
                    icon, level_text = "🟠", "ใช้ไปสามในสี่แล้ว"
                else:
                    icon, level_text = "🔴", "ใกล้เต็มงบแล้ว!"

                remaining = status["remaining"]
                msg = (
                    f"{icon} แจ้งเตือนงบประมาณ — {level_text}\n\n"
                    f"💸 ใช้ไป:     {expense:,.0f} บาท ({pct:.1f}%)\n"
                    f"💼 งบทั้งหมด: {budget:,.0f} บาท\n"
                    f"💰 เหลือ:     {remaining:,.0f} บาท\n\n"
                    f"📈 burn rate: {days_elapsed} วันแรก ใช้ไป {expense:,.0f}\n"
                    f"   คาดสิ้นเดือนจะใช้ ~{projected:,.0f} บาท"
                )
                if projected > budget:
                    over = projected - budget
                    msg += f"\n⚠️ เกินงบประมาณประมาณ {over:,.0f} บาท!"
                msg += "\n\n— KENDO AI 🤖"

                success = await send_push_message(user_id, msg)
                if success:
                    mark_budget_warned(user_id, month_key, threshold)
                    print(f"[scheduler] Budget warning {threshold}% sent to {user_id}")
                break

        except Exception as e:
            print(f"[scheduler] budget warning error for {user_id}: {e}")


def _infer_extras_from_note(note: str) -> str:
    """Fallback: ถ้า parser ไม่ได้ส่ง reminder_extras มา ให้ตรวจสอบจาก note text แทน"""
    n = note.lower()
    parts = []

    weather_kw = ["อากาศ", "weather", "พยากรณ์", "อุณหภูมิ", "ฝนตก", "ร้อน", "หนาว", "ลม"]
    aq_kw      = ["ฝุ่น", "pm2.5", "pm25", "pm 2.5", "air quality", "คุณภาพอากาศ"]
    task_kw    = ["task", "checklist", "เช็คลิสต์", "รายการ", "ต้องทำ", "สิ่งที่ต้องทำ"]

    if any(kw in n for kw in weather_kw):
        parts.append("weather:กรุงเทพ")
    if any(kw in n for kw in aq_kw):
        parts.append("air_quality:กรุงเทพ")
    if any(kw in n for kw in task_kw):
        parts.append("tasks")

    inferred = ",".join(parts)
    if inferred:
        print(f"[scheduler] inferred extras from note: {inferred}")
    return inferred


async def fetch_reminder_extras(user_id: str, extras_str: str, note: str = "") -> str:
    """ดึงข้อมูลพิเศษสำหรับ rich reminder (weather, air_quality, tasks)"""
    if not extras_str and note:
        extras_str = _infer_extras_from_note(note)
    if not extras_str:
        return ""

    from weather_service import get_weather
    from airquality_service import get_air_quality

    loop = asyncio.get_running_loop()
    parts_out = []

    for part in (p.strip() for p in extras_str.split(",")):
        if not part:
            continue
        print(f"[scheduler] fetching extra: {part!r}")
        try:
            if part.startswith("weather:"):
                location = part[8:].strip() or "กรุงเทพ"
                result = await loop.run_in_executor(None, get_weather, location)
                print(f"[scheduler] weather result success={result.get('success')}")
                parts_out.append(result["message"])
            elif part.startswith("air_quality:"):
                location = part[12:].strip() or "กรุงเทพ"
                result = await loop.run_in_executor(None, get_air_quality, location)
                print(f"[scheduler] air_quality result success={result.get('success')}")
                parts_out.append(result["message"])
            elif part == "tasks":
                tasks = await loop.run_in_executor(None, list_tasks, user_id)
                print(f"[scheduler] tasks count={len(tasks)}")
                if tasks:
                    lines = ["📋 Task ที่ต้องทำ:"]
                    for t in tasks:
                        lines.append(f"  ☐ {t['task']}")
                    parts_out.append("\n".join(lines))
                else:
                    parts_out.append("📋 ไม่มี task ค้างอยู่ครับ")
        except Exception as e:
            import traceback
            print(f"[scheduler] fetch_extras error ({part}): {e}")
            traceback.print_exc()

    return "\n\n".join(parts_out)


async def check_reminders():
    """Loop หลัก: check ทุก 60 วินาที, ส่ง weekly summary วันอาทิตย์ 20:00, budget warning ทุกชั่วโมง"""
    print("[scheduler] Reminder scheduler started ✅")
    weekly_sent_date = None
    budget_warned_hour = None

    while True:
        try:
            bangkok_tz = pytz.timezone("Asia/Bangkok")
            now = datetime.now(bangkok_tz)
            print(f"[scheduler] Checking at: {now.isoformat()}")

            # Weekly summary — วันอาทิตย์ (weekday=6) เวลา 20:00-20:01
            if now.weekday() == 6 and now.hour == 20 and now.minute == 0:
                if weekly_sent_date != now.date():
                    weekly_sent_date = now.date()
                    await send_weekly_summary()

            # Budget warning — ทุกชั่วโมง (ที่นาที 0)
            current_hour = now.replace(minute=0, second=0, microsecond=0)
            if budget_warned_hour != current_hour and now.minute == 0:
                budget_warned_hour = current_hour
                await check_budget_warnings()

            due = get_pending_reminders()
            print(f"[scheduler] Found {len(due)} pending reminders")

            for reminder in due:
                user_id = reminder["user_id"]
                note = reminder["note"]
                row_index = reminder["row_index"]
                extras_str = reminder.get("reminder_extras", "")

                extras_content = await fetch_reminder_extras(user_id, extras_str, note)

                parts = [f"⏰ ถึงเวลาแล้วนะครับ!\n📝 {note}"]
                if extras_content:
                    parts.append(extras_content)
                parts.append("— KENDO AI 🤖")
                message = "\n\n".join(parts)

                success = await send_push_message(user_id, message)
                if success:
                    mark_reminder_sent(row_index)
                    print(f"[scheduler] Reminder sent & marked SENT: row {row_index}")

        except Exception as e:
            print(f"[scheduler] check_reminders error: {e}")
            import traceback
            traceback.print_exc()

        await asyncio.sleep(60)