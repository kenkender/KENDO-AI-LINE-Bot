"""
main.py
FastAPI webhook รับข้อความจาก LINE แล้ว route ไปยัง service ที่เหมาะสม
"""

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
)
from calendar_service import create_reminder_event, delete_calendar_event
from scheduler import check_reminders

load_dotenv()

# เก็บ conversation history ของแต่ละ user ใน memory
# format: {user_id: [{"role": "user"|"model", "parts": ["..."]}, ...]}
conversation_history: dict = {}
MAX_HISTORY_PAIRS = 10  # จำนวน message pairs (user+model) ที่จำ


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
        "  • แจ้งเตือน วันศุกร์ 6 โมงเย็น จ่ายค่าเช่า\n\n"
        "📊 ดูสรุป:\n"
        "  • สรุปเดือนนี้\n"
        "  • ใช้ไปเท่าไหร่\n\n"
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


def reply(reply_token: str, message: str, quick_reply: bool = False):
    """ส่งข้อความตอบกลับไปยัง LINE"""
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

        print(f"[handle_message] Received: '{raw_text}' from {user_id}")

        # ── Menu shortcut: ดัก keyword จาก Rich Menu / Quick Reply ──
        if raw_text in MENU_PROMPTS:
            prompt_text = MENU_PROMPTS[raw_text]
            if prompt_text == "HELP":
                reply(reply_token, get_help_message(), quick_reply=True)
                return
            elif prompt_text is not None:
                # มี prompt สำเร็จรูป → ตอบกลับแล้วรอ user พิมพ์ต่อ
                reply(reply_token, prompt_text, quick_reply=True)
                return
            # prompt_text = None → ส่งต่อให้ parser จัดการตามปกติ

        # ── Step 1: Parse ข้อความด้วย Gemini (พร้อม history) ──
        user_history = conversation_history.get(user_id, [])
        result = parse_message(raw_text, history=user_history)
        print(f"[handle_message] Parse result: {result}")

        if not result["success"]:
            if result.get("error") == "quota_exceeded":
                reply(reply_token,
                    "⚠️ AI ใช้งานเกิน limit แป๊บนึงนะครับ\n"
                    "รอสัก 1 นาทีแล้วลองใหม่ได้เลย 🙏")
            else:
                reply(reply_token,
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
            reply(reply_token,
                  f"🤔 งงนิดนึงครับ ลองพิมพ์ใหม่ได้เลย\n"
                  f"(ความมั่นใจ: {int(confidence*100)}%)\n\n"
                  f"{get_help_message()}")
            return

        # ── Amount Check สำหรับ EXPENSE/INCOME ──
        if intent in ["EXPENSE", "INCOME"] and not parsed.get("amount"):
            reply(reply_token,
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
                reply(reply_token,
                      f"💸 จดให้แล้วครับ!\n"
                      f"📝 {note}\n"
                      f"💰 {amount:,.2f} บาท\n"
                      f"📂 หมวด: {category}"
                      f"{summary_text}",
                      quick_reply=True)
            else:
                reply(reply_token, "😓 บันทึกไม่ได้ครับ ลองใหม่นะ")

        elif intent == "INCOME":
            success = append_transaction(user_id, raw_text, parsed)
            if success:
                amount = parsed.get("amount", 0)
                note = parsed.get("note", "")
                summary = get_summary()
                summary_text = format_quick_summary(summary) if summary["success"] else ""
                reply(reply_token,
                      f"💰 เย่! บันทึกรายรับแล้วครับ\n"
                      f"📝 {note}\n"
                      f"✅ +{amount:,.2f} บาท"
                      f"{summary_text}",
                      quick_reply=True)
            else:
                reply(reply_token, "😓 บันทึกไม่ได้ครับ ลองใหม่นะ")

        elif intent == "NOTE":
            success = append_note(user_id, raw_text, parsed)
            if success:
                note = parsed.get("note", "")
                reply(reply_token, f"📝 จดไว้ให้แล้วครับ\n\"{note}\"")
            else:
                reply(reply_token, "😓 บันทึกโน้ตไม่ได้ครับ ลองใหม่นะ")

        elif intent == "REMINDER":
            reminder_dt = parsed.get("reminder_datetime")
            note = parsed.get("note", "")
            calendar_event_id = ""

            if reminder_dt:
                cal_result = create_reminder_event(note, reminder_dt)
                if cal_result["success"]:
                    calendar_event_id = cal_result["event_id"]

            success = append_note(user_id, raw_text, parsed, calendar_event_id)

            if success and calendar_event_id:
                reply(reply_token,
                      f"⏰ ตั้งเตือนไว้แล้วครับ!\n"
                      f"📝 {note}\n"
                      f"🗓 {reminder_dt}\n"
                      f"✅ เพิ่มใน Google Calendar แล้วด้วยนะ")
            elif success:
                reply(reply_token,
                      f"📝 จดเตือนความจำไว้แล้วครับ\n\"{note}\"\n"
                      f"⚠️ แต่เพิ่ม Google Calendar ไม่ได้นะ")
            else:
                reply(reply_token, "😓 บันทึกไม่ได้ครับ ลองใหม่นะ")

        elif intent == "CANCEL":
                keyword = parsed.get("note", "").strip()
                active = get_active_reminders(user_id)

                if not active:
                    reply(reply_token,
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

                    reply(reply_token,
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
                    reply(reply_token, "\n".join(lines))

                elif len(matched) == 1:
                    r = matched[0]
                    cancel_reminder(r["row_index"])
                    if r["calendar_event_id"]:
                        delete_calendar_event(r["calendar_event_id"])
                    reply(reply_token,
                        f"✅ ยกเลิกแล้วครับ!\n"
                        f"📝 {r['note']}\n"
                        f"🗓 {r['reminder_datetime'][:16].replace('T', ' ')}")

                else:
                    lines = [f"🔍 เจอ {len(matched)} รายการที่ตรงกัน ระบุให้ชัดขึ้นนิดนึงนะครับ:\n"]
                    for r in matched:
                        lines.append(f"  • {r['note']} ({r['reminder_datetime'][:16].replace('T', ' ')})")
                    reply(reply_token, "\n".join(lines))

        elif intent == "SUMMARY":
            summary_month = parsed.get("summary_month")
            summary_year = parsed.get("summary_year")
            summary = get_summary(month=summary_month, year=summary_year)
            if summary["success"]:
                message = format_summary_message(summary)
                reply(reply_token, message, quick_reply=True)
            else:
                reply(reply_token, "❌ ไม่สามารถดึงข้อมูลสรุปได้ กรุณาลองใหม่ครับ")

        elif intent == "ANALYZE":
            summary = get_summary()
            if summary["success"]:
                analysis = analyze_with_ai(summary)
                reply(reply_token, f"🧠 วิเคราะห์การใช้จ่ายของคุณ\n\n{analysis}", quick_reply=True)
            else:
                reply(reply_token, "❌ ไม่มีข้อมูลการใช้จ่ายเดือนนี้ครับ")

        elif intent == "DELETE":
            result = delete_last_transaction(user_id)
            if result["success"]:
                icon = "💸" if result["intent"] == "EXPENSE" else "💰"
                reply(reply_token,
                      f"🗑 ลบรายการล่าสุดแล้วครับ\n"
                      f"{icon} {result['note']} — {result['amount']:,.2f} บาท",
                      quick_reply=True)
            else:
                reply(reply_token, "❌ ไม่พบรายการที่จะลบครับ")

        elif intent == "SEARCH":
            keyword = parsed.get("note", "").strip()
            if not keyword:
                reply(reply_token, "🔍 บอกด้วยนะครับว่าจะค้นหาอะไร\nเช่น \"ค้นหากาแฟ\"")
            else:
                results = search_transactions(user_id, keyword)
                if not results:
                    reply(reply_token, f"🔍 ไม่พบรายการที่มีคำว่า \"{keyword}\" ครับ")
                else:
                    total = sum(r["amount"] for r in results)
                    lines = [f"🔍 ผลการค้นหา \"{keyword}\" — {len(results)} รายการ\n"]
                    for r in results[-10:]:
                        icon = "💸" if r["intent"] == "EXPENSE" else "💰"
                        lines.append(f"  {icon} {r['note']} {r['amount']:,.0f} บาท ({r['timestamp']})")
                    lines.append(f"\nรวม: {total:,.2f} บาท")
                    reply(reply_token, "\n".join(lines), quick_reply=True)

        elif intent == "BUDGET":
            amount = parsed.get("amount")
            if amount:
                set_budget(user_id, float(amount))
                status = get_budget_status(user_id)
                reply(reply_token,
                      f"✅ ตั้งงบประมาณเดือนนี้แล้วครับ\n"
                      f"💼 งบ:     {status['budget']:,.2f} บาท\n"
                      f"💸 ใช้ไป:  {status['expense']:,.2f} บาท\n"
                      f"{'✅' if status['remaining'] >= 0 else '⚠️'} เหลือ:   {status['remaining']:,.2f} บาท",
                      quick_reply=True)
            else:
                status = get_budget_status(user_id)
                if status["budget"] == 0:
                    reply(reply_token,
                          "📊 ยังไม่ได้ตั้งงบประมาณครับ\nพิมพ์ว่า \"ตั้งงบ 8000\" ได้เลย")
                else:
                    pct = (status["expense"] / status["budget"] * 100) if status["budget"] > 0 else 0
                    bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
                    reply(reply_token,
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
                reply(reply_token,
                      f"🎯 ตั้งเป้าออมแล้วครับ!\n"
                      f"🎯 เป้า:  {status['goal']:,.2f} บาท\n"
                      f"💰 ออมได้: {status['saved']:,.2f} บาท\n"
                      f"📌 ขาดอีก: {status['remaining']:,.2f} บาท",
                      quick_reply=True)
            else:
                status = get_savings_status(user_id)
                if status["goal"] == 0:
                    reply(reply_token,
                          "🎯 ยังไม่ได้ตั้งเป้าออมครับ\nพิมพ์ว่า \"ตั้งเป้าออม 3000\" ได้เลย")
                else:
                    pct = (status["saved"] / status["goal"] * 100) if status["goal"] > 0 else 0
                    bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
                    reply(reply_token,
                          f"🎯 เป้าหมายการออมเดือนนี้\n\n"
                          f"เป้า:   {status['goal']:,.2f} บาท\n"
                          f"ออมได้: {status['saved']:,.2f} บาท ({pct:.1f}%)\n"
                          f"[{bar}]\n"
                          f"{'🎉 ถึงเป้าแล้ว!' if status['remaining'] <= 0 else f'📌 ขาดอีก {status[\"remaining\"]:,.2f} บาท'}",
                          quick_reply=True)

        elif intent == "TASK_ADD":
            task = parsed.get("note", "").strip()
            if not task:
                reply(reply_token, "📋 บอกด้วยนะครับว่าจะเพิ่ม task อะไร")
            else:
                add_task(user_id, task)
                tasks = list_tasks(user_id)
                reply(reply_token,
                      f"✅ เพิ่ม task แล้วครับ!\n📋 {task}\n\n"
                      f"มี task ค้างอยู่ {len(tasks)} รายการ",
                      quick_reply=True)

        elif intent == "TASK_DONE":
            keyword = parsed.get("note", "").strip()
            if not keyword:
                reply(reply_token, "✅ บอกด้วยนะครับว่า task ไหนเสร็จแล้ว")
            else:
                result = complete_task(user_id, keyword)
                if result.get("success"):
                    remaining = list_tasks(user_id)
                    reply(reply_token,
                          f"🎉 เยี่ยมมาก! ทำเสร็จแล้วครับ\n✅ {result['task']}\n\n"
                          f"{'ไม่มี task ค้างแล้ว! 🎊' if not remaining else f'ยังมีอีก {len(remaining)} รายการ'}",
                          quick_reply=True)
                elif result.get("ambiguous"):
                    lines = ["🔍 เจอหลายรายการ ระบุให้ชัดขึ้นนิดนึงนะครับ:\n"]
                    for t in result["ambiguous"]:
                        lines.append(f"  • {t}")
                    reply(reply_token, "\n".join(lines))
                else:
                    pending = result.get("pending", [])
                    if pending:
                        lines = [f"🔍 ไม่เจอ task \"{keyword}\" ครับ มีอยู่:\n"]
                        for t in pending:
                            lines.append(f"  • {t}")
                        reply(reply_token, "\n".join(lines))
                    else:
                        reply(reply_token, "📭 ไม่มี task ค้างอยู่เลยครับ")

        elif intent == "TASK_LIST":
            tasks = list_tasks(user_id)
            if not tasks:
                reply(reply_token, "🎊 ไม่มี task ค้างอยู่เลยครับ! ว่างสบายใจ 😊",
                      quick_reply=True)
            else:
                lines = [f"📋 Task ที่ยังค้างอยู่ {len(tasks)} รายการ\n"]
                for i, t in enumerate(tasks, 1):
                    lines.append(f"  {i}. {t['task']} ({t['timestamp']})")
                lines.append("\nพิมพ์ \"เสร็จแล้ว [ชื่อ task]\" เมื่อทำเสร็จนะครับ")
                reply(reply_token, "\n".join(lines), quick_reply=True)

        elif intent == "CHAT":
            response = parsed.get("response", "").strip()
            if response:
                reply(reply_token, response, quick_reply=True)
            else:
                reply(reply_token,
                      "🤖 KENDO AI พร้อมช่วยครับ ลองถามใหม่ได้เลย",
                      quick_reply=True)

        elif intent == "UNKNOWN":
            amount = parsed.get("amount")
            if amount:
                reply(reply_token,
                      f"🤔 \"{raw_text}\" — นี่คือรายรับหรือรายจ่ายครับ?\n\n"
                      f"พิมพ์ต่อได้เลย เช่น:\n"
                      f"  • \"รายจ่าย {amount}\"\n"
                      f"  • \"รายรับ {amount}\"",
                      quick_reply=True)
            else:
                reply(reply_token,
                      f"🤔 งงนิดนึงครับ ลองใหม่ได้เลย!\n\n"
                      f"{get_help_message()}",
                      quick_reply=True)
        else:
            reply(reply_token, "🤔 ไม่เข้าใจครับ ลองพิมพ์ใหม่นะ")

    except Exception as e:
        print(f"[handle_message] CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
