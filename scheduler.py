"""
scheduler.py
ตรวจสอบ reminder ทุก 60 วินาที
ถ้าถึงเวลาแล้ว → ส่ง LINE Push Message
"""

import asyncio
import os
import httpx
from dotenv import load_dotenv
from sheets import get_pending_reminders, mark_reminder_sent
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


async def check_reminders():
    """Loop หลัก: check ทุก 60 วินาที"""
    print("[scheduler] Reminder scheduler started ✅")

    while True:
        try:
            bangkok_tz = pytz.timezone("Asia/Bangkok")
            now = datetime.now(bangkok_tz)
            print(f"[scheduler] Checking at: {now.isoformat()}")

            due = get_pending_reminders()
            print(f"[scheduler] Found {len(due)} pending reminders")

            for reminder in due:
                user_id = reminder["user_id"]
                note = reminder["note"]
                row_index = reminder["row_index"]

                message = (
                    f"⏰ ถึงเวลาแล้วนะครับ!\n"
                    f"📝 {note}\n\n"
                    f"— KENDO AI 🤖"
                )

                success = await send_push_message(user_id, message)
                if success:
                    mark_reminder_sent(row_index)
                    print(f"[scheduler] Reminder sent & marked SENT: row {row_index}")

        except Exception as e:
            print(f"[scheduler] check_reminders error: {e}")
            import traceback
            traceback.print_exc()

        await asyncio.sleep(60)