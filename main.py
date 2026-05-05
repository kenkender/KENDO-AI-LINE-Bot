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
    TextMessage
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.exceptions import InvalidSignatureError
from contextlib import asynccontextmanager
import os
import asyncio
import json
from dotenv import load_dotenv

from parser import parse_message
from sheets import (append_transaction, append_note, get_summary,
                    format_summary_message, get_active_reminders,
                    cancel_reminder)
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

def reply(reply_token: str, message: str):
    """ส่งข้อความตอบกลับไปยัง LINE"""
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message_with_http_info(
            ReplyMessageRequest(
                reply_token=reply_token,
                messages=[TextMessage(text=message)]
            )
        )

@app.get("/")
def health_check():
    return {"status": "LINE Finance Bot is running ✅"}

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


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event: MessageEvent):
    try:
        user_id = event.source.user_id
        raw_text = event.message.text.strip()
        reply_token = event.reply_token

        print(f"[handle_message] Received: '{raw_text}' from {user_id}")

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
                reply(reply_token,
                      f"💸 จดให้แล้วครับ!\n"
                      f"📝 {note}\n"
                      f"💰 {amount:,.2f} บาท\n"
                      f"📂 หมวด: {category}")
            else:
                reply(reply_token, "😓 บันทึกไม่ได้ครับ ลองใหม่นะ")

        elif intent == "INCOME":
            success = append_transaction(user_id, raw_text, parsed)
            if success:
                amount = parsed.get("amount", 0)
                note = parsed.get("note", "")
                reply(reply_token,
                      f"💰 เย่! บันทึกรายรับแล้วครับ\n"
                      f"📝 {note}\n"
                      f"✅ +{amount:,.2f} บาท")
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
            summary = get_summary()
            if summary["success"]:
                message = format_summary_message(summary)
                reply(reply_token, message)
            else:
                reply(reply_token, "❌ ไม่สามารถดึงข้อมูลสรุปได้ กรุณาลองใหม่ครับ")

        elif intent == "UNKNOWN":
            amount = parsed.get("amount")
            if amount:
                reply(reply_token,
                      f"🤔 \"{raw_text}\" — นี่คือรายรับหรือรายจ่ายครับ?\n\n"
                      f"พิมพ์ต่อได้เลย เช่น:\n"
                      f"  • \"รายจ่าย {amount}\"\n"
                      f"  • \"รายรับ {amount}\"")
            else:
                reply(reply_token,
                      f"🤔 งงนิดนึงครับ ลองใหม่ได้เลย!\n\n"
                      f"{get_help_message()}")
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
