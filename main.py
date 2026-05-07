"""
main.py
FastAPI webhook รับข้อความจาก LINE แล้ว route ไปยัง service ที่เหมาะสม
"""

import re

from fastapi import FastAPI, Request, HTTPException
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
    QuickReply,
    QuickReplyItem,
    MessageAction
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.exceptions import InvalidSignatureError
from contextlib import asynccontextmanager
import os
import asyncio
import json
from dotenv import load_dotenv

from parser import parse_message, analyze_with_ai
from sheets import (
    append_transaction, append_note, get_summary,
    format_summary_message, format_quick_summary,
    get_active_reminders, cancel_reminder,
    delete_last_transaction, search_transactions,
    set_budget, get_budget_status,
    set_savings_goal, get_savings_status,
    add_task, list_tasks, complete_task,
    get_today_summary,
    set_briefing, get_briefing,
    add_bill, list_bills, delete_bill,
    add_watchlist_item, list_watchlist_items, done_watchlist_item,
)
from calendar_service import create_reminder_event, delete_calendar_event
from scheduler import check_reminders
from news_service import get_thai_news, get_world_news, get_tech_news, search_news
from weather_service import get_weather
from airquality_service import get_air_quality
from holiday_service import get_holidays, format_holidays_message
from oilprice_service import get_oil_prices, format_oil_price_message

load_dotenv()

# เก็บ conversation history ของแต่ละ user ใน memory
# format: {user_id: [{"role": "user"|"model", "parts": ["..."]}, ...]}
conversation_history: dict = {}
MAX_HISTORY_PAIRS = 10  # จำนวน message pairs (user+model) ที่จำ

user_name_cache: dict = {}


def get_user_name(user_id: str) -> str:
    if user_id in user_name_cache:
        return user_name_cache[user_id]
    try:
        with ApiClient(configuration) as api_client:
            profile = MessagingApi(api_client).get_profile(user_id)
            name = profile.display_name or ""
            user_name_cache[user_id] = name
            return name
    except Exception as e:
        print(f"[main] get_user_name error: {e}")
        return ""


@asynccontextmanager
async def lifespan(app: FastAPI):
    """รัน scheduler ตอน startup และหยุดตอน shutdown"""
    task = asyncio.create_task(check_reminders())
    print("[main] Scheduler started with server ✅")
    yield
    task.cancel()
    print("[main] Scheduler stopped")


app = FastAPI(lifespan=lifespan)

configuration = Configuration(access_token=os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

def get_help_message() -> str:
    """ข้อความช่วยเหลือพร้อมตัวอย่าง"""
    return (
        "🤖 KENDO AI พร้อมช่วยแล้ว! นี่คือสิ่งที่ทำได้:\n\n"
        "💸 บันทึกรายจ่าย:\n"
        "  • หิวข้าว ไปกินมา 80\n"
        "  • ชาเย็นแก้วนึง 35\n"
        "  • เติมน้ำมัน 200\n\n"
        "💰 บันทึกรายรับ:\n"
        "  • เงินเดือนออกแล้ว ได้มา 18500\n"
        "  • ลูกค้าโอนมา 2000\n\n"
        "📝 จดโน้ต:\n"
        "  • โน้ต: ต้องซื้อยา\n"
        "  • จำไว้: ต่อ พรบ เดือนหน้า\n\n"
        "⏰ ตั้งเตือน:\n"
        "  • เตือนพรุ่งนี้ 9 โมง ประชุม\n"
        "  • เตือนทุกวัน 8 โมง กินยา\n"
        "  • เตือนทุกวันที่ 25 บ่าย 2 จ่ายค่าเช่า\n\n"
        "📊 ดูสรุป:\n"
        "  • วันนี้ใช้ไปเท่าไหร่\n"
        "  • สรุปเดือนนี้\n\n"
        "💳 บิลประจำ:\n"
        "  • ตั้งบิล ค่าไฟ 800 บาท ทุกวันที่ 20\n"
        "  • บิลประจำมีอะไรบ้าง\n\n"
        "🎬 Watchlist:\n"
        "  • อยากดู Dune 3\n"
        "  • watchlist มีอะไรบ้าง\n\n"
        "🧾 หารบิล:\n"
        "  • หารค่าอาหาร 480 บาท 3 คน\n\n"
        "🌅 Morning Briefing:\n"
        "  • เปิด briefing 7 โมงเช้า กรุงเทพ\n\n"
        "พิมพ์มาได้เลยครับ ภาษาพูดปกติก็เข้าใจ 😊")

MAIN_QUICK_REPLY = QuickReply(items=[
    QuickReplyItem(action=MessageAction(label="📊 สรุปเดือนนี้", text="สรุปเดือนนี้")),
    QuickReplyItem(action=MessageAction(label="🧠 วิเคราะห์", text="วิเคราะห์การใช้จ่าย")),
    QuickReplyItem(action=MessageAction(label="💰 รายรับ", text="รายรับ")),
    QuickReplyItem(action=MessageAction(label="💸 รายจ่าย", text="รายจ่าย")),
    QuickReplyItem(action=MessageAction(label="📋 Task", text="ดู task")),
    QuickReplyItem(action=MessageAction(label="💼 งบประมาณ", text="ดูงบประมาณ")),
    QuickReplyItem(action=MessageAction(label="⏰ ตั้งเตือน", text="เตือน")),
    QuickReplyItem(action=MessageAction(label="❓ ช่วยเหลือ", text="ช่วยด้วย")),
])


def reply(reply_token: str, message: str, quick_reply: bool = False, name: str = ""):
    """ส่งข้อความตอบกลับไปยัง LINE"""
    if name:
        message = re.sub(r"ครับ(?=[!\n\".]|$)", f"ครับ {name}", message)
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        msg = TextMessage(
            text=message,
            quick_reply=MAIN_QUICK_REPLY if quick_reply else None
        )
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[msg]
            )
        )

@app.get("/")
def health_check():
    return {"status": "KENDO AI Bot is running ✅"}

@app.head("/")
def health_check_head():
    # UptimeRobot free plan ส่ง HEAD เท่านั้น — ต้องรองรับแยกต่างหาก
    from fastapi.responses import Response
    return Response(status_code=200)

@app.post("/webhook/verify")
async def webhook_verify():
    return {"status": "ok"}

@app.post("/webhook")
async def webhook(request: Request):
    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body()

    # ถ้าไม่มี signature = LINE Verify request → ตอบ 200 ทันที
    if not signature:
        return {"status": "ok"}

    try:
        handler.handle(body.decode("utf-8"), signature)
    except InvalidSignatureError:
        # Log ไว้แต่ไม่ raise error เพื่อให้ LINE Verify ผ่าน
        print(f"[webhook] InvalidSignature — body length: {len(body)}")
        return {"status": "ok"}
    except Exception as e:
        print(f"[webhook] Unexpected error: {e}")
        return {"status": "ok"}

    return {"status": "ok"}


MENU_PROMPTS = {
    "รายรับ": (
        "💰 จะบันทึกรายรับอะไรครับ?\n\n"
        "พิมพ์มาได้เลย เช่น:\n"
        "  • เงินเดือน 15000\n"
        "  • ลูกค้าโอนมา 2000\n"
        "  • ขายของได้ 500\n"
        "  • รับโบนัส 3000"
    ),
    "รายจ่าย": (
        "💸 จะบันทึกรายจ่ายอะไรครับ?\n\n"
        "พิมพ์มาได้เลย เช่น:\n"
        "  • กินข้าว 80\n"
        "  • ค่าน้ำมัน 200\n"
        "  • ชาเย็น 35\n"
        "  • ค่าไฟ 850"
    ),
    "โน้ต": (
        "📝 จะบันทึกอะไรครับ?\n\n"
        "โน้ตทั่วไป — พิมพ์ว่า:\n"
        "  • โน้ต: ต้องซื้อยา\n"
        "  • จำไว้ว่า ต่อ พรบ เดือนหน้า\n\n"
        "ตั้งเตือน (มีวันเวลา) — พิมพ์ว่า:\n"
        "  • เตือนพรุ่งนี้ 9 โมง ประชุม\n"
        "  • แจ้งเตือน วันศุกร์ 6 โมงเย็น จ่ายค่าเช่า"
    ),
    "เตือน": (
        "⏰ จะตั้งเตือนเรื่องอะไรครับ?\n\n"
        "พิมพ์มาได้เลย เช่น:\n"
        "  • เตือนพรุ่งนี้ 9 โมง ประชุม\n"
        "  • แจ้งเตือน วันศุกร์ 6 โมงเย็น จ่ายค่าเช่า\n"
        "  • เตือน 25 พ.ค. บ่าย 2 ต่อประกัน\n\n"
        "รูปแบบเวลา:\n"
        "  9 โมง = 09:00 | บ่าย 3 = 15:00\n"
        "  6 โมงเย็น = 18:00 | ทุ่มครึ่ง = 19:30"
    ),
    "ดู task": None,         # ส่งต่อไป parser (TASK_LIST intent)
    "ดูงบประมาณ": None,      # ส่งต่อไป parser (BUDGET intent)
    "วิเคราะห์การใช้จ่าย": None,  # ส่งต่อไป parser (ANALYZE intent)
    "ช่วยด้วย": "HELP",      # ใช้ get_help_message()
}


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event: MessageEvent):
    try:
        user_id = event.source.user_id
        raw_text = event.message.text.strip()
        reply_token = event.reply_token
        name = get_user_name(user_id)

        def send(message, quick_reply=False):
            reply(reply_token, message, quick_reply=quick_reply, name=name)

        print(f"[handle_message] Received: '{raw_text}' from {user_id}")

        # ── Menu shortcut: ดัก keyword จาก Rich Menu / Quick Reply ──
        if raw_text in MENU_PROMPTS:
            prompt_text = MENU_PROMPTS[raw_text]
            if prompt_text == "HELP":
                send(get_help_message(), quick_reply=True)
                return
            elif prompt_text is not None:
                # มี prompt สำเร็จรูป → ตอบกลับแล้วรอ user พิมพ์ต่อ
                send(prompt_text, quick_reply=True)
                return
            # prompt_text = None → ส่งต่อให้ parser จัดการตามปกติ

        # ── Step 1: Parse ข้อความด้วย Gemini (พร้อม history) ──
        user_history = conversation_history.get(user_id, [])
        result = parse_message(raw_text, history=user_history)
        print(f"[handle_message] Parse result: {result}")

        if not result["success"]:
            if result.get("error") == "quota_exceeded":
                send(
                    "⚠️ AI ใช้งานเกิน limit แป๊บนึงนะครับ\n"
                    "รอสัก 1 นาทีแล้วลองใหม่ได้เลย 🙏")
            else:
                send(
                    "😅 ระบบมีปัญหาแป๊บนึง ลองส่งใหม่อีกทีนะครับ")
            return

        parsed = result["data"]
        intent = parsed.get("intent", "UNKNOWN")
        confidence = float(parsed.get("confidence", 0))

        print(f"[handle_message] Intent: {intent}, Confidence: {confidence}")

        # ── อัปเดต Conversation History ──
        updated_history = user_history + [
            {"role": "user", "parts": [raw_text]},
            {"role": "model", "parts": [json.dumps(parsed, ensure_ascii=False)]}
        ]
        # ตัดให้เหลือแค่ MAX_HISTORY_PAIRS คู่ล่าสุด
        max_entries = MAX_HISTORY_PAIRS * 2
        if len(updated_history) > max_entries:
            updated_history = updated_history[-max_entries:]
        conversation_history[user_id] = updated_history

        # ── Confidence Check ──
        if confidence < 0.7 and intent not in ["SUMMARY"]:
            send(
                  f"🤔 งงนิดนึงครับ ลองพิมพ์ใหม่ได้เลย\n"
                  f"(ความมั่นใจ: {int(confidence*100)}%)\n\n"
                  f"{get_help_message()}")
            return

        # ── Amount Check สำหรับ EXPENSE/INCOME ──
        if intent in ["EXPENSE", "INCOME"] and not parsed.get("amount"):
            send(
                  f"💬 บอกจำนวนเงินด้วยนะครับ\n\n"
                  f"เช่น:\n"
                  f"  • \"{'กินข้าว 80' if intent == 'EXPENSE' else 'ได้เงินเดือน 15000'}\"\n"
                  f"  • \"{'ชาเย็น 35 บาท' if intent == 'EXPENSE' else 'รับโบนัส 5000'}\"\n")
            return

        # ── Step 2: Route ตาม Intent ──
        if intent == "EXPENSE":
            success = append_transaction(user_id, raw_text, parsed)
            if success:
                amount = parsed.get("amount", 0)
                category = parsed.get("category", "อื่นๆ")
                note = parsed.get("note", "")
                summary = get_summary()
                summary_text = format_quick_summary(summary) if summary["success"] else ""
                send(
                      f"💸 จดให้แล้วครับ!\n"
                      f"📝 {note}\n"
                      f"💰 {amount:,.2f} บาท\n"
                      f"📂 หมวด: {category}"
                      f"{summary_text}",
                      quick_reply=True)
            else:
                send("😓 บันทึกไม่ได้ครับ ลองใหม่นะ")

        elif intent == "INCOME":
            success = append_transaction(user_id, raw_text, parsed)
            if success:
                amount = parsed.get("amount", 0)
                note = parsed.get("note", "")
                summary = get_summary()
                summary_text = format_quick_summary(summary) if summary["success"] else ""
                send(
                      f"💰 เย่! บันทึกรายรับแล้วครับ\n"
                      f"📝 {note}\n"
                      f"✅ +{amount:,.2f} บาท"
                      f"{summary_text}",
                      quick_reply=True)
            else:
                send("😓 บันทึกไม่ได้ครับ ลองใหม่นะ")

        elif intent == "NOTE":
            success = append_note(user_id, raw_text, parsed)
            if success:
                note = parsed.get("note", "")
                send(f"📝 จดไว้ให้แล้วครับ\n\"{note}\"")
            else:
                send("😓 บันทึกโน้ตไม่ได้ครับ ลองใหม่นะ")

        elif intent == "REMINDER":
            reminder_dt = parsed.get("reminder_datetime")
            note = parsed.get("note", "")
            extras = parsed.get("reminder_extras", "") or ""
            recurrence = parsed.get("recurrence", "") or ""
            calendar_event_id = ""

            if reminder_dt:
                cal_result = create_reminder_event(note, reminder_dt)
                if cal_result["success"]:
                    calendar_event_id = cal_result["event_id"]

            success = append_note(user_id, raw_text, parsed, calendar_event_id)

            extras_labels = []
            for part in (p.strip() for p in extras.split(",")) if extras else []:
                if part.startswith("weather:"):
                    extras_labels.append(f"🌤 อากาศ ({part[8:]})")
                elif part.startswith("air_quality:"):
                    extras_labels.append(f"💨 ค่าฝุ่น PM2.5 ({part[12:]})")
                elif part == "tasks":
                    extras_labels.append("📋 Task checklist")
            extras_line = "\n📦 จะแนบมาด้วย: " + ", ".join(extras_labels) if extras_labels else ""

            _day_th = {1:"จันทร์",2:"อังคาร",3:"พุธ",4:"พฤหัสบดี",5:"ศุกร์",6:"เสาร์",7:"อาทิตย์"}
            if recurrence == "daily":
                recur_line = "\n🔁 ทำซ้ำ: ทุกวัน"
            elif recurrence.startswith("weekly:"):
                recur_line = f"\n🔁 ทำซ้ำ: ทุกวัน{_day_th.get(int(recurrence.split(':')[1]), '')}"
            elif recurrence.startswith("monthly:"):
                recur_line = f"\n🔁 ทำซ้ำ: ทุกวันที่ {recurrence.split(':')[1]}"
            else:
                recur_line = ""

            if success and calendar_event_id:
                send(
                      f"⏰ ตั้งเตือนไว้แล้วครับ!\n"
                      f"📝 {note}\n"
                      f"🗓 {reminder_dt}"
                      f"{recur_line}{extras_line}\n"
                      f"✅ เพิ่มใน Google Calendar แล้วด้วยนะ")
            elif success:
                send(
                      f"⏰ ตั้งเตือนไว้แล้วครับ!\n"
                      f"📝 {note}\n"
                      f"🗓 {reminder_dt}"
                      f"{recur_line}{extras_line}")
            else:
                send("😓 บันทึกไม่ได้ครับ ลองใหม่นะ")

        elif intent == "CANCEL":
                keyword = parsed.get("note", "").strip()
                active = get_active_reminders(user_id)

                if not active:
                    send(
                        "📭 ไม่มีการแจ้งเตือนที่ค้างอยู่เลยครับ")
                    return

                # ถ้าไม่ระบุ keyword → ยกเลิกทั้งหมด
                if not keyword or keyword == "ทั้งหมด":
                    cancelled_count = 0
                    for reminder in active:
                        if cancel_reminder(reminder["row_index"]):
                            cancelled_count += 1
                            if reminder["calendar_event_id"]:
                                delete_calendar_event(reminder["calendar_event_id"])

                    send(
                        f"✅ ยกเลิกทั้งหมด {cancelled_count} รายการแล้วครับ!")
                    return

                # ค้นหา reminder ที่ตรงกับ keyword
                matched = [r for r in active
                        if keyword.lower() in r["note"].lower()]

                if not matched:
                    lines = ["🔍 หาไม่เจอครับ มีรายการเหล่านี้อยู่:\n"]
                    for r in active:
                        lines.append(f"  • {r['note']} ({r['reminder_datetime'][:16].replace('T', ' ')})")
                    lines.append("\nพิมพ์ว่า \"ยกเลิกเตือน [ชื่อ]\" หรือ \"ยกเลิกเตือนทั้งหมด\" นะครับ")
                    send("\n".join(lines))

                elif len(matched) == 1:
                    r = matched[0]
                    cancel_reminder(r["row_index"])
                    if r["calendar_event_id"]:
                        delete_calendar_event(r["calendar_event_id"])
                    send(
                        f"✅ ยกเลิกแล้วครับ!\n"
                        f"📝 {r['note']}\n"
                        f"🗓 {r['reminder_datetime'][:16].replace('T', ' ')}")

                else:
                    lines = [f"🔍 เจอ {len(matched)} รายการที่ตรงกัน ระบุให้ชัดขึ้นนิดนึงนะครับ:\n"]
                    for r in matched:
                        lines.append(f"  • {r['note']} ({r['reminder_datetime'][:16].replace('T', ' ')})")
                    send("\n".join(lines))

        elif intent == "SUMMARY":
            summary_month = parsed.get("summary_month")
            summary_year = parsed.get("summary_year")
            summary = get_summary(month=summary_month, year=summary_year)
            if summary["success"]:
                message = format_summary_message(summary)
                send(message, quick_reply=True)
            else:
                send("❌ ไม่สามารถดึงข้อมูลสรุปได้ กรุณาลองใหม่ครับ")

        elif intent == "ANALYZE":
            summary = get_summary()
            if summary["success"]:
                analysis = analyze_with_ai(summary)
                send(f"🧠 วิเคราะห์การใช้จ่ายของคุณ\n\n{analysis}", quick_reply=True)
            else:
                send("❌ ไม่มีข้อมูลการใช้จ่ายเดือนนี้ครับ")

        elif intent == "DELETE":
            result = delete_last_transaction(user_id)
            if result["success"]:
                icon = "💸" if result["intent"] == "EXPENSE" else "💰"
                send(
                      f"🗑 ลบรายการล่าสุดแล้วครับ\n"
                      f"{icon} {result['note']} — {result['amount']:,.2f} บาท",
                      quick_reply=True)
            else:
                send("❌ ไม่พบรายการที่จะลบครับ")

        elif intent == "SEARCH":
            keyword = parsed.get("note", "").strip()
            if not keyword:
                send("🔍 บอกด้วยนะครับว่าจะค้นหาอะไร\nเช่น \"ค้นหากาแฟ\"")
            else:
                results = search_transactions(user_id, keyword)
                if not results:
                    send(f"🔍 ไม่พบรายการที่มีคำว่า \"{keyword}\" ครับ")
                else:
                    total = sum(r["amount"] for r in results)
                    lines = [f"🔍 ผลการค้นหา \"{keyword}\" — {len(results)} รายการ\n"]
                    for r in results[-10:]:
                        icon = "💸" if r["intent"] == "EXPENSE" else "💰"
                        lines.append(f"  {icon} {r['note']} {r['amount']:,.0f} บาท ({r['timestamp']})")
                    lines.append(f"\nรวม: {total:,.2f} บาท")
                    send("\n".join(lines), quick_reply=True)

        elif intent == "BUDGET":
            amount = parsed.get("amount")
            if amount:
                set_budget(user_id, float(amount))
                status = get_budget_status(user_id)
                send(
                      f"✅ ตั้งงบประมาณเดือนนี้แล้วครับ\n"
                      f"💼 งบ:     {status['budget']:,.2f} บาท\n"
                      f"💸 ใช้ไป:  {status['expense']:,.2f} บาท\n"
                      f"{'✅' if status['remaining'] >= 0 else '⚠️'} เหลือ:   {status['remaining']:,.2f} บาท",
                      quick_reply=True)
            else:
                status = get_budget_status(user_id)
                if status["budget"] == 0:
                    send(
                          "📊 ยังไม่ได้ตั้งงบประมาณครับ\nพิมพ์ว่า \"ตั้งงบ 8000\" ได้เลย")
                else:
                    pct = (status["expense"] / status["budget"] * 100) if status["budget"] > 0 else 0
                    bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
                    send(
                          f"💼 งบประมาณเดือนนี้\n\n"
                          f"งบ:    {status['budget']:,.2f} บาท\n"
                          f"ใช้ไป: {status['expense']:,.2f} บาท ({pct:.1f}%)\n"
                          f"[{bar}]\n"
                          f"{'✅ เหลือ' if status['remaining'] >= 0 else '⚠️ เกินงบ'}: {abs(status['remaining']):,.2f} บาท",
                          quick_reply=True)

        elif intent == "SAVINGS":
            amount = parsed.get("amount")
            if amount:
                set_savings_goal(user_id, float(amount))
                status = get_savings_status(user_id)
                send(
                      f"🎯 ตั้งเป้าออมแล้วครับ!\n"
                      f"🎯 เป้า:  {status['goal']:,.2f} บาท\n"
                      f"💰 ออมได้: {status['saved']:,.2f} บาท\n"
                      f"📌 ขาดอีก: {status['remaining']:,.2f} บาท",
                      quick_reply=True)
            else:
                status = get_savings_status(user_id)
                if status["goal"] == 0:
                    send(
                          "🎯 ยังไม่ได้ตั้งเป้าออมครับ\nพิมพ์ว่า \"ตั้งเป้าออม 3000\" ได้เลย")
                else:
                    pct = (status["saved"] / status["goal"] * 100) if status["goal"] > 0 else 0
                    bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
                    savings_footer = "🎉 ถึงเป้าแล้ว!" if status["remaining"] <= 0 else f"📌 ขาดอีก {status['remaining']:,.2f} บาท"
                    send(
                          f"🎯 เป้าหมายการออมเดือนนี้\n\n"
                          f"เป้า:   {status['goal']:,.2f} บาท\n"
                          f"ออมได้: {status['saved']:,.2f} บาท ({pct:.1f}%)\n"
                          f"[{bar}]\n"
                          f"{savings_footer}",
                          quick_reply=True)

        elif intent == "TASK_ADD":
            task = parsed.get("note", "").strip()
            if not task:
                send("📋 บอกด้วยนะครับว่าจะเพิ่ม task อะไร")
            else:
                add_task(user_id, task)
                tasks = list_tasks(user_id)
                send(
                      f"✅ เพิ่ม task แล้วครับ!\n📋 {task}\n\n"
                      f"มี task ค้างอยู่ {len(tasks)} รายการ",
                      quick_reply=True)

        elif intent == "TASK_DONE":
            keyword = parsed.get("note", "").strip()
            if not keyword:
                send("✅ บอกด้วยนะครับว่า task ไหนเสร็จแล้ว")
            else:
                result = complete_task(user_id, keyword)
                if result.get("success"):
                    remaining = list_tasks(user_id)
                    task_footer = "ไม่มี task ค้างแล้ว! 🎊" if not remaining else f"ยังมีอีก {len(remaining)} รายการ"
                    send(
                          f"🎉 เยี่ยมมาก! ทำเสร็จแล้วครับ\n✅ {result['task']}\n\n"
                          f"{task_footer}",
                          quick_reply=True)
                elif result.get("ambiguous"):
                    lines = ["🔍 เจอหลายรายการ ระบุให้ชัดขึ้นนิดนึงนะครับ:\n"]
                    for t in result["ambiguous"]:
                        lines.append(f"  • {t}")
                    send("\n".join(lines))
                else:
                    pending = result.get("pending", [])
                    if pending:
                        lines = [f"🔍 ไม่เจอ task \"{keyword}\" ครับ มีอยู่:\n"]
                        for t in pending:
                            lines.append(f"  • {t}")
                        send("\n".join(lines))
                    else:
                        send("📭 ไม่มี task ค้างอยู่เลยครับ")

        elif intent == "TASK_LIST":
            tasks = list_tasks(user_id)
            if not tasks:
                send("🎊 ไม่มี task ค้างอยู่เลยครับ! ว่างสบายใจ 😊",
                      quick_reply=True)
            else:
                lines = [f"📋 Task ที่ยังค้างอยู่ {len(tasks)} รายการ\n"]
                for i, t in enumerate(tasks, 1):
                    lines.append(f"  {i}. {t['task']} ({t['timestamp']})")
                lines.append("\nพิมพ์ \"เสร็จแล้ว [ชื่อ task]\" เมื่อทำเสร็จนะครับ")
                send("\n".join(lines), quick_reply=True)

        elif intent == "NEWS_THAI":
            category = parsed.get("news_query") or "ทั่วไป"
            result = get_thai_news(category)
            send(result["message"], quick_reply=True)

        elif intent == "NEWS_WORLD":
            result = get_world_news()
            send(result["message"], quick_reply=True)

        elif intent == "NEWS_TECH":
            result = get_tech_news()
            send(result["message"], quick_reply=True)

        elif intent == "NEWS_SEARCH":
            query = parsed.get("news_query", "").strip()
            if not query:
                send("🔍 บอกด้วยนะครับว่าอยากค้นข่าวเรื่องอะไร\nเช่น \"ข่าวน้ำท่วม\" หรือ \"ข่าวหุ้น\"")
            else:
                result = search_news(query)
                send(result["message"], quick_reply=True)

        elif intent == "WEATHER":
            province = parsed.get("note", "").strip()
            if not province:
                send(
                    "🌏 บอกด้วยนะครับว่าจะดูอากาศที่จังหวัดไหน\n"
                    "เช่น: \"พยากรณ์อากาศวันนี้ที่เชียงใหม่\""
                )
            else:
                result = get_weather(province)
                send(result["message"], quick_reply=True)

        elif intent == "AIR_QUALITY":
            place = (parsed.get("note") or "กรุงเทพ").strip()
            result = get_air_quality(place)
            send(result["message"], quick_reply=True)

        elif intent == "TODAY_EXPENSE":
            data = get_today_summary(user_id)
            if not data["success"] or (data["total_income"] == 0 and data["total_expense"] == 0):
                send("📭 ยังไม่มีรายการวันนี้เลยครับ", quick_reply=True)
            else:
                lines = [f"📊 สรุปวันนี้ ({data['date']})\n"]
                if data["total_income"] > 0:
                    lines.append(f"💰 รายรับ:   {data['total_income']:,.0f} บาท")
                if data["total_expense"] > 0:
                    lines.append(f"💸 รายจ่าย:  {data['total_expense']:,.0f} บาท")
                balance = data["balance"]
                lines.append(f"{'✅' if balance >= 0 else '⚠️'} คงเหลือ:   {balance:,.0f} บาท")
                if data["expense_by_category"]:
                    lines.append("\n📂 แยกตามหมวด:")
                    for cat, amt in sorted(data["expense_by_category"].items(), key=lambda x: -x[1]):
                        lines.append(f"  • {cat}: {amt:,.0f} บาท")
                send("\n".join(lines), quick_reply=True)

        elif intent == "SPLIT_BILL":
            amount = parsed.get("amount")
            split_count = parsed.get("split_count")
            if not amount or not split_count or int(split_count) <= 0:
                send("🧾 บอกด้วยนะครับว่าหารเท่าไหร่ กี่คน\nเช่น: \"หารค่าอาหาร 480 บาท 3 คน\"")
            else:
                per_person = float(amount) / int(split_count)
                send(
                    f"🧾 หารบิล {float(amount):,.0f} บาท ÷ {int(split_count)} คน\n\n"
                    f"💵 คนละ {per_person:,.2f} บาท",
                    quick_reply=True)

        elif intent == "WATCH_ADD":
            title = parsed.get("note", "").strip()
            category = (parsed.get("category") or "อื่นๆ").strip()
            if not title:
                send("🎬 บอกด้วยนะครับว่าอยากดูอะไร\nเช่น: \"อยากดู Dune 3\"")
            else:
                add_watchlist_item(user_id, category, title)
                items = list_watchlist_items(user_id)
                send(
                    f"🎬 เพิ่มใน Watchlist แล้วครับ!\n📌 {title}\n\n"
                    f"มีทั้งหมด {len(items)} รายการใน watchlist",
                    quick_reply=True)

        elif intent == "WATCH_LIST":
            items = list_watchlist_items(user_id)
            if not items:
                send("🎬 Watchlist ว่างเลยครับ ยังไม่มีรายการ", quick_reply=True)
            else:
                lines = [f"🎬 Watchlist ทั้งหมด {len(items)} รายการ\n"]
                cats: dict = {}
                for item in items:
                    cats.setdefault(item["category"], []).append(item["title"])
                for cat, titles in cats.items():
                    lines.append(f"📂 {cat}:")
                    for t in titles:
                        lines.append(f"  ☐ {t}")
                lines.append('\nพิมพ์ "ดูแล้ว [ชื่อ]" เมื่อดูเสร็จแล้วนะครับ')
                send("\n".join(lines), quick_reply=True)

        elif intent == "WATCH_DONE":
            keyword = parsed.get("note", "").strip()
            if not keyword:
                send("✅ บอกด้วยนะครับว่าดูอะไรเสร็จแล้ว")
            else:
                result = done_watchlist_item(user_id, keyword)
                if result.get("success"):
                    remaining = list_watchlist_items(user_id)
                    footer = "Watchlist ว่างแล้ว! 🎊" if not remaining else f"ยังมีอีก {len(remaining)} รายการ"
                    send(
                        f"✅ เยี่ยม! ดูเสร็จแล้วครับ\n🎬 {result['title']}\n\n{footer}",
                        quick_reply=True)
                elif result.get("ambiguous"):
                    lines = ["🔍 เจอหลายรายการ ระบุให้ชัดขึ้นนิดนึงนะครับ:\n"]
                    for item in result["ambiguous"]:
                        lines.append(f"  • {item['title']} ({item['category']})")
                    send("\n".join(lines))
                else:
                    send(f"🔍 ไม่เจอ \"{keyword}\" ใน Watchlist ครับ")

        elif intent == "BILL_ADD":
            name = parsed.get("note", "").strip()
            amount = parsed.get("amount")
            due_day = parsed.get("bill_due_day")
            if not name or not amount or not due_day:
                send(
                    "💳 บอกรายละเอียดบิลด้วยนะครับ\n"
                    "เช่น: \"ตั้งบิล ค่าไฟ 800 บาท ทุกวันที่ 20\"")
            else:
                add_bill(user_id, name, float(amount), int(due_day))
                send(
                    f"💳 ตั้งบิลประจำแล้วครับ!\n"
                    f"📋 {name}\n"
                    f"💸 {float(amount):,.0f} บาท\n"
                    f"📅 ครบกำหนดวันที่ {int(due_day)} ของทุกเดือน\n\n"
                    f"ผมจะแจ้งเตือนก่อน 3 วัน และวันครบกำหนดนะครับ",
                    quick_reply=True)

        elif intent == "BILL_LIST":
            bills = list_bills(user_id)
            if not bills:
                send(
                    "💳 ยังไม่มีบิลประจำครับ\n"
                    "พิมพ์ \"ตั้งบิล ค่าไฟ 800 ทุกวันที่ 20\" ได้เลย",
                    quick_reply=True)
            else:
                lines = [f"💳 บิลประจำทั้งหมด {len(bills)} รายการ\n"]
                for b in sorted(bills, key=lambda x: x["due_day"]):
                    lines.append(f"  • {b['name']} — {b['amount']:,.0f} บาท (วันที่ {b['due_day']})")
                total = sum(b["amount"] for b in bills)
                lines.append(f"\n💸 รวมต่อเดือน: {total:,.0f} บาท")
                send("\n".join(lines), quick_reply=True)

        elif intent == "BILL_DELETE":
            keyword = parsed.get("note", "").strip()
            if not keyword:
                send("💳 บอกด้วยนะครับว่าจะลบบิลอะไร\nเช่น: \"ลบบิลค่าไฟ\"")
            else:
                result = delete_bill(user_id, keyword)
                if result.get("success"):
                    send(f"🗑 ลบบิล \"{result['name']}\" แล้วครับ", quick_reply=True)
                else:
                    bills = list_bills(user_id)
                    if bills:
                        lines = [f"🔍 ไม่เจอบิล \"{keyword}\" ครับ มีอยู่:\n"]
                        for b in bills:
                            lines.append(f"  • {b['name']}")
                        send("\n".join(lines))
                    else:
                        send("💳 ยังไม่มีบิลประจำเลยครับ")

        elif intent == "BRIEFING_SET":
            briefing_hour = parsed.get("briefing_hour")
            city = parsed.get("note", "").strip() or "กรุงเทพ"
            if briefing_hour is None:
                send(
                    "🌅 บอกเวลาด้วยนะครับ\n"
                    "เช่น: \"เปิด morning briefing 7 โมงเช้า กรุงเทพ\"")
            else:
                set_briefing(user_id, int(briefing_hour), city)
                hour_display = f"{int(briefing_hour):02d}:00 น."
                send(
                    f"🌅 เปิด Morning Briefing แล้วครับ!\n"
                    f"⏰ เวลา {hour_display}\n"
                    f"📍 สถานที่: {city}\n\n"
                    f"ทุกเช้าจะส่งสรุปอากาศ + ค่าฝุ่น + เตือนวันนี้ให้ครับ",
                    quick_reply=True)

        elif intent == "HOLIDAY":
            year = parsed.get("holiday_year")
            month = parsed.get("holiday_month")
            near_only = bool(parsed.get("near_only", False))
            result = get_holidays(year=year, month=month)
            msg = format_holidays_message(result, near_only=near_only)
            send(msg, quick_reply=True)

        elif intent == "OIL_PRICE":
            result = get_oil_prices()
            send(format_oil_price_message(result), quick_reply=True)

        elif intent == "CHAT":
            response = parsed.get("response", "").strip()
            if response:
                send(response, quick_reply=True)
            else:
                send(
                      "🤖 KENDO AI พร้อมช่วยครับ ลองถามใหม่ได้เลย",
                      quick_reply=True)

        elif intent == "UNKNOWN":
            amount = parsed.get("amount")
            if amount:
                send(
                      f"🤔 \"{raw_text}\" — นี่คือรายรับหรือรายจ่ายครับ?\n\n"
                      f"พิมพ์ต่อได้เลย เช่น:\n"
                      f"  • \"รายจ่าย {amount}\"\n"
                      f"  • \"รายรับ {amount}\"",
                      quick_reply=True)
            else:
                send(
                      f"🤔 งงนิดนึงครับ ลองใหม่ได้เลย!\n\n"
                      f"{get_help_message()}",
                      quick_reply=True)
        else:
            send("🤔 ไม่เข้าใจครับ ลองพิมพ์ใหม่นะ")

    except Exception as e:
        print(f"[handle_message] CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
