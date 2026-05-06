"""
parser.py
รับข้อความดิบจาก LINE แล้วใช้ Groq API (Llama 3.3) วิเคราะห์ intent และ extract ข้อมูล
"""

import httpx
import json
import re
import os
from datetime import datetime
import pytz
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM_PROMPT = """
คุณคือ AI parser ของ KENDO AI ระบบ financial tracker และ note-taker ส่วนตัว
หน้าที่ของคุณคือ วิเคราะห์ข้อความภาษาไทย (ทั้งแบบทางการและภาษาพูดชีวิตประจำวัน)
แล้วแปลงเป็น JSON เท่านั้น — ห้ามตอบข้อความอื่นเด็ดขาด

กฎเหล็ก:
1. ตอบเป็น JSON เท่านั้น ห้ามมีข้อความอื่นนำหน้าหรือต่อท้าย
2. ห้ามคาดเดา amount ถ้าไม่มีตัวเลขในข้อความ ให้ใส่ null
3. วันเวลาให้แปลงเป็น ISO 8601 เสมอ โดยใช้ timezone Asia/Bangkok (UTC+7)
4. ถ้าไม่แน่ใจ intent ให้ใช้ UNKNOWN
5. ภาษาพูดที่บอกเล่าการใช้จ่ายโดยปริยาย → EXPENSE เสมอ ไม่ต้องมีคำว่า "จ่าย" หรือ "ซื้อ"
6. ภาษาพูดที่บอกว่าได้รับเงินมา → INCOME เสมอ

Intent ที่รองรับ พร้อมตัวอย่างภาษาพูด:
- EXPENSE  = รายจ่าย
    ตัวอย่างทางการ: "กินข้าว 50" "ซื้อของ 200 บาท" "จ่ายค่าน้ำ 300"
    ตัวอย่างภาษาพูด:
      "หิวข้าวแล้ว ไปกินมา 80" → EXPENSE 80 (อาหาร)
      "แวะปั๊มมา เติมน้ำมันไป 200" → EXPENSE 200 (เดินทาง)
      "โดนค่าจอดรถ 30" → EXPENSE 30 (เดินทาง)
      "ชาเย็นแก้วนึง 35" → EXPENSE 35 (อาหาร)
      "ไปซื้อยามา ราคา 120" → EXPENSE 120 (สุขภาพ)
      "ค่ากาแฟ 65" → EXPENSE 65 (อาหาร)
      "ออกไปกินข้าวเที่ยง 90 บาท" → EXPENSE 90 (อาหาร)
      "เติมเงินมือถือ 100" → EXPENSE 100 (บิล)
      "จ่ายค่าไฟเดือนนี้ 850" → EXPENSE 850 (บิล)

- INCOME   = รายรับ
    ตัวอย่างทางการ: "ได้เงินเดือน 15000" "รับเงินค่าจ้าง 500"
    ตัวอย่างภาษาพูด:
      "เงินเดือนออกแล้ว ได้มา 18500" → INCOME 18500
      "ลูกค้าโอนมาแล้ว 2000" → INCOME 2000
      "ขายของได้ 350" → INCOME 350
      "รับโบนัสมา 5000" → INCOME 5000
      "เพื่อนคืนเงินมา 200" → INCOME 200

- NOTE     = บันทึกทั่วไปที่ไม่มีวันเวลาแจ้งเตือน
    ตัวอย่าง: "โน้ต: ต้องซื้อยา" "จำไว้ว่า ต้องโทรหาหมอ" "อย่าลืม ต่อ พรบ"

- REMINDER = บันทึกที่มีวันเวลาและต้องการแจ้งเตือน
    ตัวอย่าง: "เตือนพรุ่งนี้ 9 โมง ต่อ พรบ" "แจ้งเตือนวันศุกร์ 6 โมงเย็น จ่ายค่าเช่า"
    การแปลงเวลา: "9 โมง" = 09:00, "บ่าย 3" = 15:00, "6 โมงเย็น" = 18:00, "ทุ่มครึ่ง" = 19:30

- SUMMARY  = ขอดูสรุปรายรับรายจ่าย
    ตัวอย่าง: "สรุปเดือนนี้" "ใช้ไปเท่าไหร่" "ดูยอดหน่อย" "เงินเหลือเท่าไหร่"
    การระบุเดือน:
      "สรุปเดือนนี้" → summary_month=null, summary_year=null
      "สรุปเดือนที่แล้ว" → summary_month=(เดือนที่แล้ว), summary_year=(ปีที่ถูกต้อง)
      "สรุปเดือนมกราคม" → summary_month=1
      "ดูยอดเดือน 3" → summary_month=3
      "สรุปเดือนเมษายน 2025" → summary_month=4, summary_year=2025

- CANCEL   = ยกเลิก reminder หรือโน้ต
    ตัวอย่าง: "ยกเลิกเตือน ต่อ พรบ" "ลบนัด ประชุม" "ยกเลิกการแจ้งเตือนทั้งหมด"

- CHAT     = คำถามทั่วไป, ขอคำแนะนำ, ทักทาย, หรือคุยเรื่องอื่นที่ไม่ใช่การเงิน
    ตัวอย่าง: "สวัสดี" "วันนี้อากาศเป็นยังไง" "ช่วยแปลภาษาอังกฤษหน่อย"
              "กินอะไรดี" "ขอคำแนะนำหน่อย" "คุณคือใคร" "ทำอะไรได้บ้าง"
    กฎ: ต้องตอบใน response field เป็นภาษาไทย กระชับ เป็นกันเอง ไม่เกิน 200 คำ
        ใช้บุคลิก KENDO AI — ผู้ช่วยส่วนตัวที่ฉลาด เป็นมิตร และพร้อมช่วยเสมอ

- UNKNOWN  = ไม่สามารถจำแนกได้

หมวดหมู่ category ที่อนุญาต (เลือกที่เหมาะสมที่สุด):
อาหาร, เดินทาง, สุขภาพ, ช้อปปิ้ง, บิล, บันเทิง, รายได้, อื่นๆ

โครงสร้าง JSON ที่ต้องตอบ:
{
  "intent": "EXPENSE | INCOME | NOTE | REMINDER | SUMMARY | CANCEL | CHAT | UNKNOWN",
  "amount": float หรือ null,
  "currency": "THB" หรือ null,
  "category": "string หรือ null",
  "note": "string อธิบายรายการสั้นๆ เป็นภาษาไทยกระชับ",
  "reminder_datetime": "ISO8601 string หรือ null",
  "summary_month": int (1-12) หรือ null — ใช้เฉพาะ SUMMARY intent เท่านั้น,
  "summary_year": int (ปี ค.ศ.) หรือ null — ใช้เฉพาะ SUMMARY intent เท่านั้น,
  "response": "string คำตอบสำหรับ CHAT intent เท่านั้น, null สำหรับ intent อื่น",
  "confidence": 0.0-1.0
}
"""


def _build_history_context(history: list) -> str:
    """แปลง history เป็นข้อความ context สำหรับใส่ใน prompt"""
    if not history:
        return ""
    lines = ["บริบทการสนทนาก่อนหน้า (ใช้เพื่อเข้าใจ context เท่านั้น):"]
    for i in range(0, len(history) - 1, 2):
        user_msg = history[i]["parts"][0]
        model_msg = history[i + 1]["parts"][0] if i + 1 < len(history) else ""
        lines.append(f"- ผู้ใช้พูดว่า: \"{user_msg}\" → ระบบแปลได้: {model_msg}")
    return "\n".join(lines) + "\n\n"


def parse_message(user_text: str, history: list = None) -> dict:
    """
    เรียก Groq API (Llama 3.3 70B) ผ่าน httpx
    history: list of {"role": "user"|"model", "parts": ["..."]}
    """
    try:
        bangkok_tz = pytz.timezone("Asia/Bangkok")
        now = datetime.now(bangkok_tz)

        history_context = _build_history_context(history)
        user_content = f"""{history_context}วันเวลาปัจจุบัน: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}
ข้อความจากผู้ใช้: "{user_text}"
"""

        models_to_try = [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
        ]

        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }

        last_error = None
        for model_name in models_to_try:
            try:
                payload = {
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_content}
                    ],
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"}
                }

                with httpx.Client(timeout=30) as client:
                    resp = client.post(GROQ_API_URL, headers=headers, json=payload)

                if resp.status_code == 429:
                    print(f"[parser] {model_name} quota exceeded, trying next...")
                    last_error = "quota_exceeded"
                    continue

                if resp.status_code == 401:
                    print(f"[parser] GROQ_API_KEY ไม่ถูกต้อง (401)")
                    return {"success": False, "error": "auth_error",
                            "message": "GROQ_API_KEY ไม่ถูกต้อง"}

                resp.raise_for_status()

                data = resp.json()
                text = data["choices"][0]["message"]["content"].strip()
                text = re.sub(r"```json|```", "", text).strip()
                parsed = json.loads(text)

                print(f"[parser] Used model: {model_name}, history_len: {len(history or [])}")
                return {"success": True, "data": parsed}

            except (httpx.TimeoutException, httpx.ConnectError) as e:
                print(f"[parser] {model_name} connection error: {e}, trying next...")
                last_error = str(e)
                continue

        if last_error == "quota_exceeded":
            return {"success": False, "error": "quota_exceeded",
                    "message": "Groq quota หมดทุก model"}

        return {"success": False, "error": "api_error",
                "message": f"ไม่สามารถเรียก Groq API ได้: {last_error}"}

    except json.JSONDecodeError as e:
        return {"success": False, "error": "parse_error",
                "message": f"ตอบกลับในรูปแบบที่ไม่ถูกต้อง: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": "api_error",
                "message": f"เกิดข้อผิดพลาด: {str(e)}"}


# ทดสอบ
if __name__ == "__main__":
    tests = [
        "กินกะเพรา 60 บาท",
        "หิวข้าวแล้ว ไปกินมา 80",
        "เงินเดือนออกแล้ว ได้มา 18500",
        "เตือนพรุ่งนี้ 9 โมง ประชุม",
        "สรุปเดือนนี้",
    ]
    for t in tests:
        result = parse_message(t)
        print(f"\nInput: {t}")
        print(f"Output: {json.dumps(result, ensure_ascii=False, indent=2)}")
