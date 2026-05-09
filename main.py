"""
main.py — FastAPI webhook + intent router
"""

import re
import os
import asyncio
import json
import pytz
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import Response
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    ReplyMessageRequest, PushMessageRequest, TextMessage, FlexMessage,
    QuickReply, QuickReplyItem, MessageAction
)
from linebot.v3.messaging.models import FlexContainer
from linebot.v3.webhooks import MessageEvent, TextMessageContent, LocationMessageContent
from linebot.v3.exceptions import InvalidSignatureError
from dotenv import load_dotenv

from parser import parse_message
from scheduler import check_reminders

from handlers.finance import (
    handle_expense, handle_income, handle_delete,
    handle_search, handle_today_expense, handle_split_bill
)
from handlers.budget import handle_budget, handle_savings
from handlers.task import handle_task_add, handle_task_done, handle_task_list
from handlers.reminder import handle_note, handle_reminder, handle_cancel
from handlers.bill import handle_bill_add, handle_bill_list, handle_bill_delete
from handlers.watchlist import handle_watch_add, handle_watch_list, handle_watch_done
from handlers.summary import handle_summary, handle_analyze, handle_briefing_set, handle_compare
from handlers.info import (
    handle_news_thai, handle_news_world, handle_news_tech, handle_news_search,
    handle_weather, handle_air_quality, handle_holiday, handle_oil_price,
    handle_gold_price, handle_lottery, handle_trends, handle_smart_search
)
from weather_service import get_weather_by_coords
from handlers.recurring import handle_recurring_add, handle_recurring_list, handle_recurring_delete, handle_recurring_set_remind

load_dotenv()

conversation_history: dict = {}
MAX_HISTORY_PAIRS = 5
user_name_cache: dict = {}
_fallback_alerted: set = set()  # เก็บ user_id ที่แจ้งเตือนไปแล้วในรอบนี้

MODEL_INFO = {
    "deepseek-chat":           ("DeepSeek", "ไม่จำกัด (paid)", "ไม่มีการรีเซ็ต"),
    "llama-3.3-70b-versatile": ("Groq", "14,400 req/วัน", "รีเซ็ต 07:00 น. ทุกวัน"),
    "llama-3.1-8b-instant":    ("Groq", "14,400 req/วัน", "รีเซ็ต 07:00 น. ทุกวัน"),
    "llama3.1-8b":             ("Cerebras", "ไม่จำกัด (free tier)", "ไม่มีการรีเซ็ต"),
    "llama3.1-70b":            ("Cerebras", "ไม่จำกัด (free tier)", "ไม่มีการรีเซ็ต"),
    "gemini-1.5-flash":        ("Google Gemini", "1,500 req/วัน", "รีเซ็ต 07:00 น. ทุกวัน"),
}


def send_fallback_alert(user_id: str, model_name: str):
    if user_id in _fallback_alerted:
        return
    _fallback_alerted.add(user_id)

    bangkok_tz = pytz.timezone("Asia/Bangkok")
    now = datetime.now(bangkok_tz)
    reset_hour = 7
    if now.hour < reset_hour:
        reset_in = reset_hour - now.hour
    else:
        reset_in = 24 - now.hour + reset_hour
    reset_str = f"อีกประมาณ {reset_in} ชั่วโมง (07:00 น.)"

    provider, quota, reset_info = MODEL_INFO.get(model_name, ("Unknown", "-", "-"))
    msg = (
        f"⚠️ แจ้งเตือน: โควต้า Groq หมดแล้ว\n\n"
        f"🔄 ตอนนี้ใช้โมเดล: {model_name}\n"
        f"🏢 Provider: {provider}\n"
        f"📊 โควต้า: {quota}\n"
        f"⏰ {reset_info}\n\n"
        f"🕐 Groq จะรีเซ็ตใน {reset_str}"
    )
    try:
        with ApiClient(configuration) as api_client:
            MessagingApi(api_client).push_message(
                PushMessageRequest(to=user_id, messages=[TextMessage(text=msg)])
            )
        print(f"[alert] Sent fallback alert to {user_id}: using {model_name}")
    except Exception as e:
        print(f"[alert] Failed to send fallback alert: {e}")


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
    task = asyncio.create_task(check_reminders())
    print("[main] Scheduler started ✅")
    yield
    task.cancel()
    print("[main] Scheduler stopped")


app = FastAPI(lifespan=lifespan)
configuration = Configuration(access_token=os.getenv("LINE_CHANNEL_ACCESS_TOKEN"))
handler = WebhookHandler(os.getenv("LINE_CHANNEL_SECRET"))

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

HELP_MESSAGE = (
    "🤖 KENDO AI พร้อมช่วยแล้ว! นี่คือสิ่งที่ทำได้:\n\n"
    "💸 บันทึกรายจ่าย:\n"
    "  • หิวข้าว ไปกินมา 80\n"
    "  • ชาเย็นแก้วนึง 35\n\n"
    "💰 บันทึกรายรับ:\n"
    "  • เงินเดือนออกแล้ว ได้มา 18500\n\n"
    "📝 จดโน้ต / ⏰ ตั้งเตือน:\n"
    "  • เตือนพรุ่งนี้ 9 โมง ประชุม\n\n"
    "📊 สรุป / 🧠 วิเคราะห์:\n"
    "  • สรุปเดือนนี้ | วิเคราะห์การใช้จ่าย\n\n"
    "💳 บิลประจำ / 🎬 Watchlist / ✅ Task\n\n"
    "🌤 อากาศ | 📰 ข่าว | ⛽ น้ำมัน | 🗓 วันหยุด\n\n"
    "พิมพ์มาได้เลยครับ ภาษาพูดปกติก็เข้าใจ 😊"
)

MENU_PROMPTS = {
    "รายรับ": (
        "💰 จะบันทึกรายรับอะไรครับ?\n\n"
        "เช่น: เงินเดือน 15000 | ลูกค้าโอนมา 2000"
    ),
    "รายจ่าย": (
        "💸 จะบันทึกรายจ่ายอะไรครับ?\n\n"
        "เช่น: กินข้าว 80 | ค่าน้ำมัน 200"
    ),
    "โน้ต": (
        "📝 จะบันทึกอะไรครับ?\n\n"
        "โน้ต: โน้ต: ต้องซื้อยา\n"
        "เตือน: เตือนพรุ่งนี้ 9 โมง ประชุม"
    ),
    "เตือน": (
        "⏰ จะตั้งเตือนเรื่องอะไรครับ?\n\n"
        "เช่น: เตือนพรุ่งนี้ 9 โมง ประชุม\n"
        "      เตือน 25 พ.ค. บ่าย 2 ต่อประกัน"
    ),
    "ดู task": None,
    "ดูงบประมาณ": None,
    "วิเคราะห์การใช้จ่าย": None,
    "ช่วยด้วย": "HELP",
}


class Sender:
    """Wrapper ที่ส่งได้ทั้ง text และ Flex Message โดย backward compatible กับ send(text)"""

    def __init__(self, reply_token: str, name: str):
        self._reply_token = reply_token
        self._name = name

    def __call__(self, message: str, quick_reply: bool = False):
        self.text(message, quick_reply)

    def text(self, message: str, quick_reply: bool = False):
        if self._name:
            message = re.sub(r"ครับ(?=[!\n\".]|$)", f"ครับ {self._name}", message)
        with ApiClient(configuration) as api_client:
            MessagingApi(api_client).reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=self._reply_token,
                    messages=[TextMessage(
                        text=message,
                        quick_reply=MAIN_QUICK_REPLY if quick_reply else None
                    )]
                )
            )

    def flex(self, alt_text: str, flex_dict: dict, quick_reply: bool = False):
        try:
            flex_msg = FlexMessage(
                alt_text=alt_text,
                contents=FlexContainer.from_dict(flex_dict),
                quick_reply=MAIN_QUICK_REPLY if quick_reply else None
            )
            with ApiClient(configuration) as api_client:
                MessagingApi(api_client).reply_message_with_http_info(
                    ReplyMessageRequest(
                        reply_token=self._reply_token,
                        messages=[flex_msg]
                    )
                )
        except Exception as e:
            print(f"[Sender.flex] error: {e}, falling back to text")
            self.text(alt_text, quick_reply)


@app.get("/")
def health_check():
    return {"status": "KENDO AI Bot is running ✅"}


@app.head("/")
def health_check_head():
    return Response(status_code=200)


@app.post("/webhook/verify")
async def webhook_verify():
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(request: Request):
    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body()
    if not signature:
        return {"status": "ok"}
    try:
        handler.handle(body.decode("utf-8"), signature)
    except InvalidSignatureError:
        print(f"[webhook] InvalidSignature — body length: {len(body)}")
    except Exception as e:
        print(f"[webhook] Unexpected error: {e}")
    return {"status": "ok"}


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event: MessageEvent):
    try:
        user_id = event.source.user_id
        raw_text = event.message.text.strip()
        reply_token = event.reply_token
        name = get_user_name(user_id)

        send = Sender(reply_token, name)

        print(f"[handle_message] '{raw_text}' from {user_id}")

        # ── Menu shortcuts ──
        if raw_text in MENU_PROMPTS:
            prompt_text = MENU_PROMPTS[raw_text]
            if prompt_text == "HELP":
                send(HELP_MESSAGE, quick_reply=True)
                return
            if prompt_text is not None:
                send(prompt_text, quick_reply=True)
                return

        # ── Parse ──
        user_history = conversation_history.get(user_id, [])
        result = parse_message(raw_text, history=user_history)
        print(f"[handle_message] Parse result: {result}")

        if not result["success"]:
            if result.get("error") == "quota_exceeded":
                send("⚠️ AI ใช้งานเกิน limit แป๊บนึงนะครับ\nรอสัก 1 นาทีแล้วลองใหม่ได้เลย 🙏")
            else:
                send("😅 ระบบมีปัญหาแป๊บนึง ลองส่งใหม่อีกทีนะครับ")
            return

        if result.get("fallback"):
            send_fallback_alert(user_id, result.get("model", "unknown"))
        else:
            _fallback_alerted.discard(user_id)

        parsed = result["data"]
        intent = parsed.get("intent", "UNKNOWN")
        confidence = float(parsed.get("confidence", 0))
        print(f"[handle_message] Intent: {intent}, Confidence: {confidence}")

        # ── Update history ──
        updated = user_history + [
            {"role": "user", "parts": [raw_text]},
            {"role": "model", "parts": [json.dumps(parsed, ensure_ascii=False)]}
        ]
        max_entries = MAX_HISTORY_PAIRS * 4
        conversation_history[user_id] = updated[-max_entries:]

        # ── Confidence check ──
        if confidence < 0.7 and intent not in ["SUMMARY"]:
            send(
                f"🤔 งงนิดนึงครับ ลองพิมพ์ใหม่ได้เลย\n"
                f"(ความมั่นใจ: {int(confidence*100)}%)\n\n{HELP_MESSAGE}"
            )
            return

        # ── Amount check ──
        if intent in ["EXPENSE", "INCOME"] and not parsed.get("amount"):
            ex = "กินข้าว 80" if intent == "EXPENSE" else "ได้เงินเดือน 15000"
            ex2 = "ชาเย็น 35 บาท" if intent == "EXPENSE" else "รับโบนัส 5000"
            send(f"💬 บอกจำนวนเงินด้วยนะครับ\n\nเช่น:\n  • \"{ex}\"\n  • \"{ex2}\"")
            return

        # ── Route ──
        match intent:
            case "EXPENSE":         handle_expense(send, user_id, raw_text, parsed)
            case "INCOME":          handle_income(send, user_id, raw_text, parsed)
            case "NOTE":            handle_note(send, user_id, raw_text, parsed)
            case "REMINDER":        handle_reminder(send, user_id, raw_text, parsed)
            case "CANCEL":          handle_cancel(send, user_id, parsed)
            case "SUMMARY":         handle_summary(send, parsed, user_id)
            case "ANALYZE":         handle_analyze(send)
            case "DELETE":          handle_delete(send, user_id)
            case "SEARCH":          handle_search(send, user_id, parsed)
            case "BUDGET":          handle_budget(send, user_id, parsed)
            case "SAVINGS":         handle_savings(send, user_id, parsed)
            case "TASK_ADD":        handle_task_add(send, user_id, parsed)
            case "TASK_DONE":       handle_task_done(send, user_id, parsed)
            case "TASK_LIST":       handle_task_list(send, user_id)
            case "NEWS_THAI":       handle_news_thai(send, parsed)
            case "NEWS_WORLD":      handle_news_world(send)
            case "NEWS_TECH":       handle_news_tech(send)
            case "NEWS_SEARCH":     handle_news_search(send, parsed)
            case "WEATHER":         handle_weather(send, parsed)
            case "AIR_QUALITY":     handle_air_quality(send, parsed)
            case "TODAY_EXPENSE":   handle_today_expense(send, user_id)
            case "SPLIT_BILL":      handle_split_bill(send, parsed)
            case "WATCH_ADD":       handle_watch_add(send, user_id, parsed)
            case "WATCH_LIST":      handle_watch_list(send, user_id)
            case "WATCH_DONE":      handle_watch_done(send, user_id, parsed)
            case "BILL_ADD":        handle_bill_add(send, user_id, parsed)
            case "BILL_LIST":       handle_bill_list(send, user_id)
            case "BILL_DELETE":     handle_bill_delete(send, user_id, parsed)
            case "BRIEFING_SET":    handle_briefing_set(send, user_id, parsed)
            case "HOLIDAY":         handle_holiday(send, parsed)
            case "OIL_PRICE":       handle_oil_price(send)
            case "GOLD_PRICE":      handle_gold_price(send)
            case "LOTTERY":         handle_lottery(send)
            case "TRENDS":          handle_trends(send)
            case "SMART_SEARCH":    handle_smart_search(send, parsed)
            case "COMPARE":         handle_compare(send, parsed)
            case "RECURRING_ADD":   handle_recurring_add(send, user_id, parsed)
            case "RECURRING_LIST":  handle_recurring_list(send, user_id)
            case "RECURRING_DELETE": handle_recurring_delete(send, user_id, parsed)
            case "RECURRING_SET_REMIND": handle_recurring_set_remind(send, user_id, parsed)
            case "CHAT":
                response = parsed.get("response", "").strip()
                send(response if response else "🤖 KENDO AI พร้อมช่วยครับ ลองถามใหม่ได้เลย", quick_reply=True)
            case "UNKNOWN":
                if parsed.get("amount"):
                    send(
                        f"🤔 \"{raw_text}\" — นี่คือรายรับหรือรายจ่ายครับ?\n\n"
                        f"พิมพ์ต่อได้เลย เช่น:\n"
                        f"  • \"รายจ่าย {parsed['amount']}\"\n"
                        f"  • \"รายรับ {parsed['amount']}\"",
                        quick_reply=True
                    )
                else:
                    send(f"🤔 งงนิดนึงครับ ลองใหม่ได้เลย!\n\n{HELP_MESSAGE}", quick_reply=True)
            case _:
                send("🤔 ไม่เข้าใจครับ ลองพิมพ์ใหม่นะ")

    except Exception as e:
        print(f"[handle_message] CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()


@handler.add(MessageEvent, message=LocationMessageContent)
def handle_location_message(event: MessageEvent):
    """รับ location message จาก LINE → ดึงพยากรณ์อากาศตามพิกัด GPS"""
    try:
        user_id = event.source.user_id
        reply_token = event.reply_token
        name = get_user_name(user_id)
        send = Sender(reply_token, name)

        lat = event.message.latitude
        lon = event.message.longitude
        print(f"[handle_location] GPS ({lat}, {lon}) from {user_id}")

        result = get_weather_by_coords(lat, lon)
        send(result["message"], quick_reply=True)

    except Exception as e:
        print(f"[handle_location] error: {e}")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
