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
from db import (get_pending_reminders, mark_reminder_sent, get_summary,
                get_all_user_ids, format_summary_message,
                get_budget_status, get_budget_warn_state, mark_budget_warned,
                list_tasks, get_all_briefing_users, get_today_reminders,
                get_due_bills, mark_bill_reminded, create_recurring_reminder)
from calendar_service import get_thai_holiday_today
from datetime import datetime
import pytz

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

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


async def send_morning_briefing(user_id: str, city: str):
    """ส่ง morning briefing: อากาศ + ค่าฝุ่น + เตือนวันนี้"""
    from weather_service import get_weather
    from airquality_service import get_air_quality

    loop = asyncio.get_running_loop()
    parts = ["🌅 Morning Briefing จาก KENDO AI 🤖\n"]

    try:
        weather = await loop.run_in_executor(None, get_weather, city)
        parts.append(weather["message"])
    except Exception as e:
        print(f"[scheduler] briefing weather error: {e}")

    try:
        aq = await loop.run_in_executor(None, get_air_quality, city)
        parts.append(aq["message"])
    except Exception as e:
        print(f"[scheduler] briefing aq error: {e}")

    try:
        reminders = await loop.run_in_executor(None, get_today_reminders, user_id)
        if reminders:
            lines = ["⏰ นัดหมายวันนี้:"]
            for r in reminders:
                lines.append(f"  • {r['time']} — {r['note']}")
            parts.append("\n".join(lines))
        else:
            parts.append("⏰ ไม่มีนัดหมายวันนี้ครับ")
    except Exception as e:
        print(f"[scheduler] briefing reminders error: {e}")

    parts.append("— มีวันที่ดีนะครับ 😊")
    await send_push_message(user_id, "\n\n".join(parts))


async def check_bill_reminders():
    """แจ้งเตือนบิลที่ครบกำหนดวันนี้ หรืออีก 3 วัน"""
    bangkok_tz = pytz.timezone("Asia/Bangkok")
    today_str = datetime.now(bangkok_tz).strftime("%Y-%m-%d")
    due = get_due_bills()
    for bill in due:
        user_id = bill["user_id"]
        if not user_id:
            continue
        days = bill["days_until"]
        if days == 0:
            msg = (
                f"🔔 บิลครบกำหนดวันนี้!\n\n"
                f"📋 {bill['name']}\n"
                f"💸 {bill['amount']:,.0f} บาท\n\n"
                f"— KENDO AI 🤖"
            )
        else:
            msg = (
                f"⚠️ บิลจะครบกำหนดใน {days} วัน\n\n"
                f"📋 {bill['name']}\n"
                f"💸 {bill['amount']:,.0f} บาท\n"
                f"📅 ครบกำหนดวันที่ {bill['due_day']}\n\n"
                f"— KENDO AI 🤖"
            )
        success = await send_push_message(user_id, msg)
        if success:
            mark_bill_reminded(bill["row_index"], today_str)
            print(f"[scheduler] Bill reminder sent: {bill['name']} → {user_id}")


async def generate_holiday_greeting(day_type: str, holiday_name: str = "") -> str:
    """สร้างข้อความวันหยุดแบบสนทนาธรรมชาติโดย Groq"""
    bangkok_tz = pytz.timezone("Asia/Bangkok")
    now = datetime.now(bangkok_tz)
    thai_days = {0: "วันจันทร์", 1: "วันอังคาร", 2: "วันพุธ",
                 3: "วันพฤหัสบดี", 4: "วันศุกร์", 5: "วันเสาร์", 6: "วันอาทิตย์"}
    day_name = thai_days[now.weekday()]

    if day_type == "public_holiday":
        day_context = f"วันนี้เป็น{holiday_name} ({day_name}) ซึ่งเป็นวันหยุดราชการ"
    elif day_type == "saturday":
        day_context = "วันนี้เป็นวันเสาร์ หยุดพักผ่อนได้เต็มที่"
    else:
        day_context = "วันนี้เป็นวันอาทิตย์ วันสุดท้ายก่อนเริ่มสัปดาห์ใหม่"

    prompt = f"""คุณคือ KENDO AI ผู้ช่วยส่วนตัวของ Kendo

ข้อมูล Kendo: ตำรวจท่องเที่ยว มีมอเตอร์ไซค์และรถยนต์ มีแมว 2 ตัวชื่อมั่งมี กับมารวย ชอบ IT เกม หนัง และเทคโนโลยี อยากออกกำลังกายแต่ขาด passion

สถานการณ์: {day_context}

เขียนข้อความทักทายและแนะนำกิจกรรมวันหยุดให้ Kendo โดย:
- ใช้ภาษาพูดทั่วไป เป็นกันเอง อบอุ่น เหมือนเพื่อนสนิทคุย ไม่ใช่ robot
- ความยาวประมาณ 5-8 ประโยค ไม่สั้นเกิน ไม่ยาวเกิน
- ให้เหตุผลว่าทำไมถึงแนะนำกิจกรรมนั้น ไม่ใช่แค่บอกให้ทำ
- แนะนำ 2-3 กิจกรรมที่เหมาะกับวันหยุด (เช่น ทำความสะอาดห้อง ซักผ้า เล่นเกม อยู่กับแมว ออกกำลังกายเบาๆ ดูหนัง)
- ถ้าเป็นวันหยุดพิเศษ (เช่น สงกรานต์ วันแม่ วันพ่อ) ให้พูดถึงความหมายของวันนั้นด้วย
- ลงท้ายด้วยคำให้กำลังใจสั้นๆ แบบเป็นกันเอง
- ห้ามขึ้นต้นด้วย "วันนี้เป็นวันหยุดครับ" หรือ "สวัสดีครับ" แบบแข็งๆ ให้เปิดด้วยประโยคที่น่าสนใจกว่านี้
- ห้ามใส่ bullet point หรือ list ให้เขียนเป็นย่อหน้าธรรมชาติ"""

    try:
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.8,
            "max_tokens": 500
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(GROQ_API_URL, headers=headers, json=payload)
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"[scheduler] generate_holiday_greeting error: {e}")

    # Fallback ถ้า Groq ล้มเหลว
    if day_type == "public_holiday":
        return (f"🎉 {holiday_name}นะครับ Kendo!\n\n"
                f"วันหยุดแบบนี้ถ้าไม่ได้ไปไหน ลองจัดการห้องให้เรียบร้อยก่อนนะครับ "
                f"ทำความสะอาดเสร็จแล้วจะรู้สึกสบายใจขึ้นเยอะเลย แล้วค่อยนอนพักหรือเล่นเกมกับมั่งมีมารวยก็ได้ครับ 😊")
    elif day_type == "saturday":
        return ("🌤 เสาร์แล้วครับ Kendo!\n\n"
                "ถ้ายังไม่ได้ซักผ้าหรือเก็บกวาดห้อง วันนี้เหมาะมากเลยครับ ทำเสร็จแล้วบ่ายๆ "
                "จะได้นอนพักหรือดูหนังอย่างสบายใจ ไม่มีเรื่องค้างคาในหัว 😊")
    else:
        return ("☀️ อาทิตย์แล้วครับ Kendo!\n\n"
                "วันสุดท้ายของสัปดาห์แล้ว ถ้ายังพักผ่อนไม่พอก็ชาร์จแบตให้เต็มก่อนนะครับ "
                "พรุ่งนี้จะได้ไปทำงานอย่างมีแรง 😊")


async def send_holiday_greetings(now: datetime):
    """ตรวจสอบและส่งข้อความวันหยุดให้ user ทั้งหมด เวลา 08:00"""
    loop = asyncio.get_running_loop()
    is_weekend = now.weekday() >= 5  # 5=เสาร์, 6=อาทิตย์

    holiday_name = await loop.run_in_executor(None, get_thai_holiday_today)
    is_holiday = bool(holiday_name)

    if not (is_weekend or is_holiday):
        return

    if is_holiday:
        day_type = "public_holiday"
    elif now.weekday() == 5:
        day_type = "saturday"
    else:
        day_type = "sunday"

    greeting = await generate_holiday_greeting(day_type, holiday_name or "")

    if day_type == "public_holiday":
        header = f"🎉 {holiday_name}\n\n"
    elif day_type == "saturday":
        header = "🌤 วันเสาร์\n\n"
    else:
        header = "☀️ วันอาทิตย์\n\n"

    message = header + greeting

    user_ids = await loop.run_in_executor(None, get_all_user_ids)
    for user_id in user_ids:
        try:
            await send_push_message(user_id, message)
            print(f"[scheduler] Holiday greeting sent ({day_type}) → {user_id}")
        except Exception as e:
            print(f"[scheduler] send_holiday_greetings error for {user_id}: {e}")


async def check_reminders():
    """Loop หลัก: check ทุก 60 วินาที, ส่ง weekly summary วันอาทิตย์ 20:00, budget warning ทุกชั่วโมง"""
    print("[scheduler] Reminder scheduler started ✅")
    weekly_sent_date = None
    budget_warned_hour = None
    bill_checked_date = None
    briefing_sent: dict = {}  # {user_id: date}
    holiday_greeted_date = None

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

            # Holiday greeting — วันเสาร์/อาทิตย์/หยุดราชการ เวลา 08:00
            if now.hour == 8 and now.minute == 0 and holiday_greeted_date != now.date():
                holiday_greeted_date = now.date()
                await send_holiday_greetings(now)

            # Bill reminders — วันละครั้ง เวลา 09:00
            if now.hour == 9 and now.minute == 0 and bill_checked_date != now.date():
                bill_checked_date = now.date()
                await check_bill_reminders()

            # Morning briefing — ส่งตาม hour ของแต่ละ user
            if now.minute == 0:
                try:
                    briefing_users = get_all_briefing_users()
                    for bu in briefing_users:
                        if bu["hour"] == now.hour and briefing_sent.get(bu["user_id"]) != now.date():
                            briefing_sent[bu["user_id"]] = now.date()
                            await send_morning_briefing(bu["user_id"], bu["city"])
                            print(f"[scheduler] Morning briefing sent to {bu['user_id']}")
                except Exception as e:
                    print(f"[scheduler] briefing check error: {e}")

            due = get_pending_reminders()
            print(f"[scheduler] Found {len(due)} pending reminders")

            for reminder in due:
                user_id = reminder["user_id"]
                note = reminder["note"]
                row_index = reminder["row_index"]
                extras_str = reminder.get("reminder_extras", "")
                recurrence = reminder.get("recurrence", "")

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

                    if recurrence:
                        try:
                            reminder_dt_str = reminder.get("reminder_datetime", "")
                            reminder_dt = datetime.fromisoformat(reminder_dt_str) if reminder_dt_str else now
                            create_recurring_reminder(user_id, note, reminder_dt, recurrence, extras_str)
                            print(f"[scheduler] Recurring reminder created: {recurrence}")
                        except Exception as e:
                            print(f"[scheduler] create_recurring_reminder error: {e}")

        except Exception as e:
            print(f"[scheduler] check_reminders error: {e}")
            import traceback
            traceback.print_exc()

        await asyncio.sleep(60)