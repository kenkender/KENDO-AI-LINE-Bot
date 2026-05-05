"""
calendar_service.py
สร้าง Google Calendar event สำหรับ REMINDER intent
"""

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from datetime import datetime, timedelta
import pytz
import os
import json
from dotenv import load_dotenv

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/calendar"]
CREDENTIALS_FILE = "credentials.json"
CALENDAR_ID = "emptyken37@gmail.com"


def get_calendar_service():
    """สร้าง authenticated Google Calendar service"""
    credentials_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if credentials_json:
        # Render: อ่านจาก environment variable
        info = json.loads(credentials_json)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        # Local dev: อ่านจากไฟล์ credentials.json
        creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
    service = build("calendar", "v3", credentials=creds)
    return service


def create_reminder_event(note: str, reminder_datetime_str: str) -> dict:
    """
    สร้าง Google Calendar event จาก reminder
    คืนค่า event_id ถ้าสำเร็จ
    """
    try:
        service = get_calendar_service()

        # แปลง ISO string เป็น datetime object
        reminder_dt = datetime.fromisoformat(reminder_datetime_str)
        end_dt = reminder_dt + timedelta(minutes=30)

        event = {
            "summary": f"⏰ {note}",
            "description": f"แจ้งเตือนจาก LINE Finance Bot\nรายละเอียด: {note}",
            "start": {
                "dateTime": reminder_dt.isoformat(),
                "timeZone": "Asia/Bangkok"
            },
            "end": {
                "dateTime": end_dt.isoformat(),
                "timeZone": "Asia/Bangkok"
            },
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": 30},
                    {"method": "popup", "minutes": 0}
                ]
            }
        }

        created_event = service.events().insert(
            calendarId=CALENDAR_ID,
            body=event
        ).execute()

        return {
            "success": True,
            "event_id": created_event.get("id"),
            "event_link": created_event.get("htmlLink")
        }

    except Exception as e:
        print(f"[calendar_service.py] create_reminder_event error: {e}")
        return {"success": False, "error": str(e)}

def delete_calendar_event(event_id: str) -> bool:
    """
    ลบ Google Calendar event ตาม event_id
    """
    try:
        service = get_calendar_service()
        service.events().delete(
            calendarId=CALENDAR_ID,
            eventId=event_id
        ).execute()
        print(f"[calendar] Deleted event: {event_id}")
        return True
    except Exception as e:
        print(f"[calendar_service.py] delete_calendar_event error: {e}")
        return False