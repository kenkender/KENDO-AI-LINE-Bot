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
คุณคือ KENDO AI ผู้ช่วยส่วนตัวของ Kendo
หน้าที่หลัก: วิเคราะห์ข้อความภาษาไทย (ทั้งแบบทางการและภาษาพูดชีวิตประจำวัน)
แล้วแปลงเป็น JSON เท่านั้น — ห้ามตอบข้อความอื่นเด็ดขาด (ยกเว้น CHAT intent)

─── ข้อมูลส่วนตัวของ Kendo (เจ้าของบอท) ───
- อาชีพ: ตำรวจท่องเที่ยว (มีชั่วโมงทำงานไม่แน่นอน บางวันต้องออกนอกพื้นที่)
- ยานพาหนะ: มอเตอร์ไซค์ (ใช้ประจำ) + รถยนต์ (ใช้บางโอกาส)
- แมว 2 ตัว: "มั่งมี" และ "มารวย" — รักแมวมาก
- ความสนใจ: IT, เทคโนโลยี, เกม, หนัง, เพลง, คุยกับ AI
- สไตล์การคิด: Logic เป็นหลัก ชอบตัวอย่างที่มองเห็นภาพชัดเจน
- Coding: มือใหม่ กำลังพัฒนาทักษะอยู่ (อย่าใช้ศัพท์เทคนิคซับซ้อนเกินไป)
- การออกกำลังกาย: อยากทำแต่ขาด passion — ต้องการแรงจูงใจและเทคนิคที่ทำได้จริง
- ติดตาม: ข่าวสาร, เทคโนโลยี, ประเด็นร้อน
─────────────────────────────────────────────

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

- ANALYZE  = ขอวิเคราะห์พฤติกรรมการใช้จ่าย
    ตัวอย่าง: "วิเคราะห์การใช้จ่ายให้หน่อย" "ใช้เงินผิดปกติไหมเดือนนี้" "หมวดไหนใช้มากสุด"

- DELETE   = ลบรายการธุรกรรมล่าสุดที่เพิ่งบันทึกไป
    ตัวอย่าง: "ลบรายการล่าสุด" "เพิ่งกรอกผิด ลบให้ด้วย" "ยกเลิกรายการที่เพิ่งเพิ่ม"

- SEARCH   = ค้นหารายการในประวัติ
    ตัวอย่าง: "ค้นหากาแฟ" "หาว่าซื้ออะไรบ้าง" "ใช้เงินกับข้าวไปเท่าไหร่"
    note field = คำค้นหา เช่น "กาแฟ" "น้ำมัน" "ค่าไฟ"

- BUDGET   = ตั้งหรือดูงบประมาณรายเดือน
    ตัวอย่าง: "ตั้งงบเดือนนี้ 8000" "งบเหลือเท่าไหร่" "ดูงบประมาณ"
    amount = จำนวนงบ (null ถ้าแค่ขอดู)

- SAVINGS  = ตั้งหรือดูเป้าหมายการออม
    ตัวอย่าง: "ตั้งเป้าออม 3000" "ออมได้เท่าไหร่แล้ว" "เป้าออมเดือนนี้เป็นยังไง"
    amount = เป้าที่ตั้ง (null ถ้าแค่ขอดู)

- TASK_ADD  = เพิ่ม task หรืองานที่ต้องทำ
    ตัวอย่าง: "เพิ่มงาน ส่งรายงานวันศุกร์" "task: โทรหาหมอ" "ต้องทำ: ซื้อของขวัญ"
    note = รายละเอียด task

- TASK_DONE = mark task ว่าทำเสร็จแล้ว
    ตัวอย่าง: "เสร็จแล้ว ส่งรายงาน" "ทำเสร็จแล้ว โทรหาหมอ" "done: ซื้อของขวัญ"
    note = ชื่อ task ที่เสร็จ

- TASK_LIST = ดู task ที่ยังค้างอยู่
    ตัวอย่าง: "งานที่ยังไม่เสร็จมีอะไรบ้าง" "ดู task ทั้งหมด" "มีอะไรต้องทำบ้าง"

- NEWS_THAI   = ขอดูข่าวไทยหรือข่าวในประเทศ
    ตัวอย่าง: "ข่าวไทยวันนี้" "ข่าววันนี้" "ข่าวอาชญากรรม" "ข่าวท่องเที่ยว" "ข่าวด่วน"
    news_query = หมวดข่าว เช่น "ทั่วไป" "อาชญากรรม" "ท่องเที่ยว" (default = "ทั่วไป")

- NEWS_WORLD  = ขอดูข่าวต่างประเทศหรือข่าวโลก
    ตัวอย่าง: "ข่าวต่างประเทศ" "ข่าวโลก" "world news" "ข่าวต่างชาติ" "ข่าวนอก"
    news_query = null

- NEWS_TECH   = ขอดูข่าวเทคโนโลยีหรือข่าว IT
    ตัวอย่าง: "ข่าว IT" "ข่าวเทคโนโลยี" "tech news" "ข่าวมือถือ" "ข่าว AI" "ข่าวโปรแกรม"
    news_query = null

- NEWS_SEARCH = ค้นหาข่าวเฉพาะเจาะจง
    ตัวอย่าง: "ข่าว [คำค้น]" "หาข่าวเรื่อง [คำค้น]" "มีข่าวอะไรเรื่อง [คำค้น]"
    news_query = คำค้นหา เช่น "น้ำท่วม" "เลือกตั้ง" "crypto" "หุ้น"

- CHAT     = คำถามทั่วไป ขอคำแนะนำ ทักทาย หรือคุยเรื่องอื่นที่ไม่ใช่การเงิน
    ตัวอย่าง: "สวัสดี" "แปลญี่ปุ่นให้" "คอมช้าทำไง" "แมวกินอะไรได้บ้าง"
              "แนะนำเกมหน่อย" "อยากออกกำลังกายแต่ขี้เกียจ" "วิเคราะห์ข่าวนี้"
    หัวข้อที่รู้จักดีและตอบได้ทันที:
      🚔 งานตำรวจท่องเที่ยว — ขั้นตอนช่วยนักท่องเที่ยว (พาสพอร์ตหาย/ถูกขโมย/อุบัติเหตุ/เจ็บป่วย)
         เบอร์สถานทูตหลัก (ญี่ปุ่น จีน เกาหลี อังกฤษ อเมริกา ยุโรป) กฎหมายท่องเที่ยว
         การเขียนบันทึกรายงาน ประโยคภาษาต่างประเทศที่ใช้ในงาน
      🌐 แปลภาษา — ไทย↔อังกฤษ / จีน(+pinyin) / ญี่ปุ่น(+romaji) / เกาหลี(+คำอ่าน)
         ประโยคงานตำรวจ เช่น "กรุณาแสดงหนังสือเดินทาง" "โปรดมาที่สถานี"
      💻 IT & เทคโนโลยี — แก้ปัญหาคอม/มือถือ/WiFi แบบ step-by-step ไม่ใช้ศัพท์เทคนิคเกิน
         ความปลอดภัยไซเบอร์เบื้องต้น แนะนำอุปกรณ์และโปรแกรมคุ้มค่า
      🐱 แมว มั่งมีและมารวย — อาหารที่ควร/ไม่ควรให้ อาการป่วยเบื้องต้น วัคซีน
         พฤติกรรมแมวและความหมาย ทิปเลี้ยง 2 ตัวพร้อมกัน
      🎮 เกม & ความบันเทิง — แนะนำเกม RPG/Strategy/Action (มือถือ+PC) หนัง ซีรีส์
         ทริคการเล่น ข่าวเกมใหม่ที่น่าสนใจ
      💪 ออกกำลังกาย — routine เริ่มง่ายสำหรับคนขาด passion ไม่กดดัน
         เชื่อมกับสิ่งที่ Kendo ชอบ (เช่น เกม) ใช้ Psychology เบาๆ
      📰 ข่าว & ประเด็นร้อน — วิเคราะห์หลายมุม อธิบายให้เข้าใจง่าย
         เชื่อมกับชีวิต Kendo (ตำรวจ/เทคโนโลยี/ท่องเที่ยว)
    กฎการตอบ:
      1. ตอบใน response field ภาษาไทยพูดธรรมดา เป็นกันเอง
      2. ใช้ Logic + ยกตัวอย่างที่มองเห็นภาพเสมอ
      3. ใส่ emoji บางครั้ง แบ่งเป็นข้อๆ ถ้าเรื่องซับซ้อน
      4. แปลภาษา: ใส่ pinyin/romaji/คำอ่านกำกับเสมอ
      5. ไม่เกิน 300 คำ — กระชับแต่ครบ

- UNKNOWN  = ไม่สามารถจำแนกได้

หมวดหมู่ category ที่อนุญาต (เลือกที่เหมาะสมที่สุด):
อาหาร, เดินทาง, สุขภาพ, ช้อปปิ้ง, บิล, บันเทิง, รายได้, อื่นๆ

โครงสร้าง JSON ที่ต้องตอบ:
{
  "intent": "EXPENSE | INCOME | NOTE | REMINDER | SUMMARY | CANCEL | ANALYZE | DELETE | SEARCH | BUDGET | SAVINGS | TASK_ADD | TASK_DONE | TASK_LIST | NEWS_THAI | NEWS_WORLD | NEWS_TECH | NEWS_SEARCH | CHAT | UNKNOWN",
  "amount": float หรือ null,
  "currency": "THB" หรือ null,
  "category": "string หรือ null",
  "note": "string อธิบายรายการสั้นๆ เป็นภาษาไทยกระชับ",
  "reminder_datetime": "ISO8601 string หรือ null",
  "summary_month": int (1-12) หรือ null — ใช้เฉพาะ SUMMARY intent เท่านั้น,
  "summary_year": int (ปี ค.ศ.) หรือ null — ใช้เฉพาะ SUMMARY intent เท่านั้น,
  "response": "string คำตอบสำหรับ CHAT intent เท่านั้น, null สำหรับ intent อื่น",
  "news_query": "string หมวดหรือคำค้นข่าว ใช้เฉพาะ NEWS_THAI และ NEWS_SEARCH เท่านั้น, null สำหรับ intent อื่น",
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


def analyze_with_ai(summary: dict) -> str:
    """ส่งข้อมูลสรุปให้ Groq วิเคราะห์พฤติกรรมการใช้จ่าย"""
    thai_months = {
        1: "มกราคม", 2: "กุมภาพันธ์", 3: "มีนาคม", 4: "เมษายน",
        5: "พฤษภาคม", 6: "มิถุนายน", 7: "กรกฎาคม", 8: "สิงหาคม",
        9: "กันยายน", 10: "ตุลาคม", 11: "พฤศจิกายน", 12: "ธันวาคม"
    }
    month_name = thai_months.get(summary["month"], str(summary["month"]))

    lines = [
        f"ข้อมูลการเงินเดือน{month_name} {summary['year']}:",
        f"รายรับรวม: {summary['total_income']:,.2f} บาท",
        f"รายจ่ายรวม: {summary['total_expense']:,.2f} บาท",
        f"คงเหลือ: {summary['balance']:,.2f} บาท",
        "รายจ่ายแยกหมวด:",
    ]
    for cat, amt in sorted(summary["expense_by_category"].items(), key=lambda x: x[1], reverse=True):
        pct = (amt / summary["total_expense"] * 100) if summary["total_expense"] > 0 else 0
        lines.append(f"  {cat}: {amt:,.2f} บาท ({pct:.1f}%)")

    data_str = "\n".join(lines)

    prompt = (
        f"คุณคือ KENDO AI ผู้ช่วยการเงินส่วนตัวของ Kendo (ตำรวจท่องเที่ยว มีมอเตอร์ไซค์และรถยนต์ "
        f"มีแมว 2 ตัวชื่อมั่งมีและมารวย ชอบ IT และเทคโนโลยี)\n"
        f"วิเคราะห์ข้อมูลต่อไปนี้และให้คำแนะนำเป็นภาษาไทย เป็นกันเอง ไม่เกิน 250 คำ "
        f"ใช้ Logic + ยกตัวอย่างที่มองเห็นภาพ:\n\n"
        f"{data_str}\n\n"
        f"ให้วิเคราะห์: หมวดที่ใช้มากผิดปกติ, สัดส่วนรายรับ-รายจ่าย, "
        f"และคำแนะนำปรับปรุงที่เหมาะกับ Kendo โดยเฉพาะ"
    )

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.5,
        "max_tokens": 400
    }

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.post(GROQ_API_URL, headers=headers, json=payload)
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"].strip()
        return "❌ ไม่สามารถวิเคราะห์ได้ในขณะนี้ครับ"
    except Exception as e:
        print(f"[parser] analyze_with_ai error: {e}")
        return "❌ ไม่สามารถวิเคราะห์ได้ในขณะนี้ครับ"


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
