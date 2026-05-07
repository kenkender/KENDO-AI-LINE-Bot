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

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY")
CEREBRAS_API_URL = "https://api.cerebras.ai/v1/chat/completions"

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
    recurrence = รูปแบบการทำซ้ำ (null = ครั้งเดียว):
      "daily"        = ทุกวัน เช่น "เตือนทุกวัน 8 โมง กินยา"
      "weekly:N"     = ทุกวัน N (1=จันทร์ … 7=อาทิตย์) เช่น "เตือนทุกวันจันทร์ 9 โมง ประชุม" → weekly:1
      "monthly:N"    = ทุกวันที่ N เช่น "เตือนทุกวันที่ 25 บ่าย 2 จ่ายค่าเช่า" → monthly:25
      reminder_datetime ให้ใส่ครั้งแรกที่จะเกิดขึ้น (ใกล้ที่สุดในอนาคต)
    reminder_extras: ถ้า user ขอให้แนบข้อมูลพิเศษมาด้วยตอนแจ้งเตือน ให้ใส่ใน reminder_extras เป็น comma-separated:
      - "weather:{สถานที่}" เช่น weather:กรุงเทพ, weather:เชียงใหม่
      - "air_quality:{สถานที่}" เช่น air_quality:กรุงเทพ
      - "tasks" = แสดง task checklist ที่ค้างอยู่
      ตัวอย่าง:
        "แจ้งเตือนพรุ่งนี้ 8 โมง รายงานอากาศและฝุ่น pm2.5" → reminder_extras: "weather:กรุงเทพ,air_quality:กรุงเทพ"
        "เตือนวันศุกร์ 7 โมงเช้า อากาศที่เชียงใหม่และ task วันนี้" → reminder_extras: "weather:เชียงใหม่,air_quality:เชียงใหม่,tasks"
        "แจ้งเตือน 9 โมง ดูรายการที่ต้องทำ" → reminder_extras: "tasks"
        "เตือนพรุ่งนี้ 10 โมง ประชุม" (ไม่ขอข้อมูลพิเศษ) → reminder_extras: null

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

- WEATHER  = ขอพยากรณ์อากาศของจังหวัดในไทย
    ตัวอย่าง: "พยากรณ์อากาศวันนี้ที่เชียงใหม่" "อากาศที่ภูเก็ตเป็นยังไง" "วันนี้ฝนตกไหมที่สมุทรปราการ"
              "อุณหภูมิที่ขอนแก่นวันนี้" "อากาศกรุงเทพ" "อากาศวันนี้ที่เลย"
    note = ชื่อสถานที่ เช่น "เชียงใหม่" "ภูเก็ต" "อำเภอบางพลี สมุทรปราการ"

- AIR_QUALITY = ขอดูค่าฝุ่น PM2.5 หรือคุณภาพอากาศ
    ตัวอย่าง: "ค่าฝุ่นวันนี้ที่เชียงใหม่" "pm2.5 กรุงเทพ" "ฝุ่นที่สมุทรปราการเป็นยังไง"
              "คุณภาพอากาศวันนี้" "อากาศเป็นพิษไหมที่เลย" "ฝุ่นควัน"
    note = ชื่อสถานที่ (ถ้าไม่ระบุให้ใช้ "กรุงเทพ" เป็น default)

- TODAY_EXPENSE = ดูรายรับรายจ่ายวันนี้เท่านั้น
    ตัวอย่าง: "วันนี้ใช้ไปเท่าไหร่" "ยอดวันนี้" "วันนี้จ่ายอะไรไปบ้าง" "รายการวันนี้" "ค่าใช้จ่ายวันนี้"

- SPLIT_BILL = หารค่าใช้จ่ายกับเพื่อน
    ตัวอย่าง: "หารกับเพื่อน 3 คน ค่าอาหาร 480" "หาร 480 บาท 4 คน" "หารบิล 600 บาท 3 คน" "แบ่ง 900 สามคน"
    amount = ยอดรวม, split_count = จำนวนคน (รวมตัวเอง, ต้อง >= 2)

- WATCH_ADD = เพิ่มรายการใน watchlist สิ่งที่อยากดู/เล่น/ฟัง
    ตัวอย่าง: "อยากดู Dune 3" "เพิ่ม watchlist One Piece" "อยากเล่น Elden Ring" "อยากฟัง Linkin Park" "จด watchlist หนังสือ Atomic Habits"
    note = ชื่อเรื่อง/เพลง/เกม/หนังสือ
    category = "หนัง" | "ซีรีส์" | "เพลง" | "เกม" | "หนังสือ" | "อื่นๆ" (เลือกจาก context)

- WATCH_LIST = ดูรายการ watchlist ที่ยังไม่ได้ดู/เล่น/ฟัง
    ตัวอย่าง: "watchlist มีอะไรบ้าง" "อยากดูอะไรบ้าง" "อยากเล่นเกมอะไร" "รายการที่ยังไม่ได้ดู"

- WATCH_DONE = mark รายการใน watchlist ว่าดู/เล่น/ฟังแล้ว
    ตัวอย่าง: "ดูแล้ว Dune 3" "เล่นแล้ว Elden Ring" "ฟังแล้ว Linkin Park" "เสร็จแล้ว One Piece"
    note = ชื่อที่ต้องการ mark

- BILL_ADD = เพิ่มบิลประจำเดือน (recurring bill)
    ตัวอย่าง: "ตั้งบิล ค่าไฟ 800 บาท ทุกวันที่ 20" "บันทึกบิล ค่าน้ำ 200 วันที่ 15" "บิลประจำ ค่าเน็ต 600 วันที่ 1"
    note = ชื่อบิล, amount = ยอดบิล, bill_due_day = วันที่ครบกำหนด (1-31)

- BILL_LIST = ดูบิลประจำที่มีอยู่ทั้งหมด
    ตัวอย่าง: "บิลประจำมีอะไรบ้าง" "ดูบิล" "มีบิลอะไรต้องจ่ายบ้าง" "บิลเดือนนี้"

- BILL_DELETE = ลบบิลประจำ
    ตัวอย่าง: "ลบบิล ค่าไฟ" "ยกเลิกบิล ค่าน้ำ" "เอาบิล ค่าเน็ต ออก"
    note = ชื่อบิลที่ต้องการลบ

- BRIEFING_SET = ตั้งค่า morning briefing (ข้อความสรุปเช้า)
    ตัวอย่าง: "เปิด briefing 7 โมงเช้า" "ตั้ง briefing เชียงใหม่ 6 โมง" "ปิด briefing" "ตั้งเวลา briefing 8 โมง ที่กรุงเทพ"
    briefing_hour = เวลา 0-23 (null ถ้าต้องการปิด briefing), note = ชื่อเมืองสำหรับอากาศ (null ถ้าไม่ระบุ)
    "ปิด briefing" → briefing_hour: null

- HOLIDAY  = ดูวันหยุดนักขัตฤกษ์ไทย
    ตัวอย่าง: "วันหยุดเดือนนี้มีอะไรบ้าง" "วันหยุดที่ใกล้จะมาถึง" "วันหยุดเดือนมิถุนายน" "วันหยุดปีนี้ทั้งหมด" "วันหยุดราชการเดือนหน้า"
    holiday_year = ปี ค.ศ. (null = ปีปัจจุบัน)
    holiday_month = เดือน 1-12 (null = ทั้งปี)
    near_only = true ถ้า user ถามว่าวันหยุดใกล้ๆ / วันหยุดที่จะมาถึง (false ถ้าระบุเดือน/ปีชัดเจน)

- OIL_PRICE = ดูราคาน้ำมัน
    ตัวอย่าง: "ราคาน้ำมันวันนี้" "น้ำมันราคาเท่าไหร่" "ดีเซลราคาเท่าไหร่" "แก๊สโซฮอล์ 91 ราคาเท่าไหร่" "เติมน้ำมันวันนี้ราคายังไง"

- GOLD_PRICE = ดูราคาทองคำวันนี้
    ตัวอย่าง: "ราคาทองวันนี้" "ทองราคาเท่าไหร่" "ทองขึ้นหรือลง" "ซื้อทองวันนี้ราคาเท่าไหร่" "ทองรูปพรรณราคาเท่าไหร่" "ราคาทองคำแท่ง" "ทองวันนี้"

- LOTTERY = ดูผลสลากกินแบ่งรัฐบาล
    ตัวอย่าง: "ผลสลากวันนี้" "ผลหวย" "ออกสลากงวดล่าสุด" "เช็คหวย" "ผลสลากกินแบ่ง" "หวยออกอะไรบ้าง" "เลขที่ออก"

- RECURRING_ADD = เพิ่มรายจ่ายซ้ำประจำเดือนหลายรายการพร้อมกัน (subscriptions, ค่าบริการ)
    ตัวอย่าง:
      "เพิ่มรายจ่ายซ้ำ Netflix 299 Spotify 99"
      "รายจ่ายซ้ำ 1.Netflix 299 2.Spotify 99 3.ค่าเน็ตบ้าน 599"
      "เตือนรายจ่ายประจำเดือน มีรายการ Netflix 299, Spotify 99"
      "บันทึกค่า subscription Netflix 299 YouTube 219"
    items = array ของ {name, amount, category} — parse ทุกรายการในข้อความ
    category ให้เดาจาก context: Netflix/YouTube/Disney+ → "บันเทิง", ค่าเน็ต/โทรศัพท์ → "บิล" ฯลฯ

- RECURRING_LIST = ดูรายจ่ายซ้ำทั้งหมด
    ตัวอย่าง: "รายจ่ายซ้ำมีอะไรบ้าง" "ดูรายจ่ายประจำ" "subscription ที่มีอยู่"

- RECURRING_DELETE = ลบรายจ่ายซ้ำรายการใดรายการหนึ่ง
    ตัวอย่าง: "ลบรายจ่ายซ้ำ Netflix" "เอา Spotify ออกจากรายจ่ายประจำ"
    note = ชื่อรายการที่ต้องการลบ

- RECURRING_SET_REMIND = ตั้งวันแจ้งเตือนรายจ่ายซ้ำ (วันที่ต้องการรับแจ้งเตือนทุกเดือน)
    ตัวอย่าง: "เตือนรายจ่ายซ้ำทุกวันที่ 25" "ตั้งแจ้งเตือนรายจ่ายประจำวันที่ 28" "แจ้งเตือน subscription วันที่ 1"
              "ปิดแจ้งเตือนรายจ่ายซ้ำ" "ยกเลิกการแจ้งเตือนรายจ่ายประจำ"
    remind_day = วันที่ต้องการ (1-31) หรือ 0 ถ้าต้องการปิดแจ้งเตือน

- COMPARE = เปรียบเทียบรายรับรายจ่ายระหว่าง 2 เดือน
    ตัวอย่าง: "เปรียบเทียบเดือนนี้กับเดือนที่แล้ว" "เดือนนี้ใช้เงินมากกว่าเดือนที่แล้วไหม" "compare เดือน 4 กับ เดือน 5" "เดือนที่แล้วกับเดือนนี้ต่างกันยังไง"
    summary_month = เดือนอ้างอิง (เดือนปัจจุบัน ถ้าไม่ระบุ)
    summary_year = ปีอ้างอิง (ปีปัจจุบัน ถ้าไม่ระบุ)

- CHAT     = คำถามทั่วไป ขอคำแนะนำ ทักทาย หรือคุยเรื่องอื่นที่ไม่ใช่การเงิน
    ตัวอย่าง: "สวัสดี" "แปลญี่ปุ่นให้" "คอมช้าทำไง" "แมวกินอะไรได้บ้าง"
              "แนะนำเกมหน่อย" "อยากออกกำลังกายแต่ขี้เกียจ" "วิเคราะห์ข่าวนี้"

    ⚠️ ถ้า Kendo ถามว่า "บอทนี้ทำ X ได้ไหม" หรือ "คุณเก็บ X ได้ไหม" หรือ "มีฟีเจอร์ Y ไหม":
       ให้ตอบตรงๆ ว่าทำได้หรือไม่ได้ โดยอ้างอิงจากฟีเจอร์ที่มีจริงเท่านั้น
       ห้ามแนะนำให้ไปใช้แอปอื่นหรือเว็บไซต์อื่นแทน
       ฟีเจอร์ที่บอทนี้ทำได้:
         💰 บันทึกรายรับ-รายจ่าย, สรุปรายการ, วิเคราะห์การใช้จ่าย, ตั้งงบประมาณ
         📊 เปรียบเทียบรายจ่ายระหว่าง 2 เดือน
         📋 จดโน้ต, สร้าง task / checklist, ตั้งการเตือน (reminder)
         🌤 ดูสภาพอากาศ + ค่าฝุ่น PM2.5
         📰 ดูข่าว (ไทย/โลก/เทคโนโลยี)
         💳 บันทึกบิลประจำ (bill), แจ้งเตือนบิล, หารบิล
         🌅 ตั้ง Morning Briefing อัตโนมัติ
         📅 ดูวันหยุดนักขัตฤกษ์ไทย
         ⛽ ดูราคาน้ำมัน (OR/PTT)
         🏅 ดูราคาทองคำ (ทองแท่ง/ทองรูปพรรณ)
         🎫 ตรวจผลสลากกินแบ่งรัฐบาล
         🌐 แปลภาษา, คุยทั่วไป, ถามเรื่อง IT/แมว/เกม/งานตำรวจ
       ฟีเจอร์ที่บอทนี้ทำไม่ได้: การติดตามแคลอรี่/อาหาร, การจัดการสุขภาพ,
         การซื้อ-ขายหุ้น, การเชื่อมต่อบัญชีธนาคาร, อื่นๆ ที่ไม่ได้ระบุข้างบน

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
  "intent": "EXPENSE | INCOME | NOTE | REMINDER | SUMMARY | CANCEL | ANALYZE | DELETE | SEARCH | BUDGET | SAVINGS | TASK_ADD | TASK_DONE | TASK_LIST | NEWS_THAI | NEWS_WORLD | NEWS_TECH | NEWS_SEARCH | WEATHER | AIR_QUALITY | TODAY_EXPENSE | SPLIT_BILL | WATCH_ADD | WATCH_LIST | WATCH_DONE | BILL_ADD | BILL_LIST | BILL_DELETE | BRIEFING_SET | HOLIDAY | OIL_PRICE | GOLD_PRICE | LOTTERY | COMPARE | RECURRING_ADD | RECURRING_LIST | RECURRING_DELETE | RECURRING_SET_REMIND | CHAT | UNKNOWN",
  "amount": float หรือ null,
  "currency": "THB" หรือ null,
  "category": "string หรือ null",
  "note": "string อธิบายรายการสั้นๆ เป็นภาษาไทยกระชับ",
  "reminder_datetime": "ISO8601 string หรือ null",
  "summary_month": int (1-12) หรือ null — ใช้เฉพาะ SUMMARY intent เท่านั้น,
  "summary_year": int (ปี ค.ศ.) หรือ null — ใช้เฉพาะ SUMMARY intent เท่านั้น,
  "response": "string คำตอบสำหรับ CHAT intent เท่านั้น, null สำหรับ intent อื่น",
  "news_query": "string หมวดหรือคำค้นข่าว ใช้เฉพาะ NEWS_THAI และ NEWS_SEARCH เท่านั้น, null สำหรับ intent อื่น",
  "reminder_extras": "string comma-separated extras ใช้เฉพาะ REMINDER intent เมื่อ user ขอข้อมูลพิเศษ เช่น 'weather:กรุงเทพ,air_quality:กรุงเทพ,tasks' — null ถ้าไม่ได้ขอ",
  "recurrence": "string | null — ใช้เฉพาะ REMINDER: 'daily' | 'weekly:N' | 'monthly:N' | null",
  "split_count": "int | null — ใช้เฉพาะ SPLIT_BILL: จำนวนคนที่หาร (>= 2)",
  "bill_due_day": "int (1-31) | null — ใช้เฉพาะ BILL_ADD: วันที่ครบกำหนดในแต่ละเดือน",
  "briefing_hour": "int (0-23) | null — ใช้เฉพาะ BRIEFING_SET: ชั่วโมงที่ต้องการรับ briefing, null = ปิด",
  "holiday_year": "int (ปี ค.ศ.) | null — ใช้เฉพาะ HOLIDAY: ปีที่ต้องการดู (null = ปีปัจจุบัน)",
  "holiday_month": "int (1-12) | null — ใช้เฉพาะ HOLIDAY: เดือนที่ต้องการดู (null = ทั้งปี)",
  "near_only": "bool | null — ใช้เฉพาะ HOLIDAY: true ถ้าถามวันหยุดใกล้ๆ ที่จะมาถึง",
  "items": [{"name": "string", "amount": float, "category": "string"}] หรือ null — ใช้เฉพาะ RECURRING_ADD: รายการซ้ำทั้งหมดที่ user พิมพ์มา,
  "remind_day": int (1-31) หรือ 0 (ปิด) หรือ null — ใช้เฉพาะ RECURRING_SET_REMIND: วันที่ต้องการรับแจ้งเตือน,
  "confidence": 0.0-1.0
}
"""


def _build_history_context(history: list) -> str:
    """แปลง history เป็นข้อความ context กระชับสำหรับใส่ใน prompt"""
    if not history:
        return ""
    lines = ["บริบทก่อนหน้า:"]
    for i in range(0, len(history) - 1, 2):
        user_msg = history[i]["parts"][0]
        model_raw = history[i + 1]["parts"][0] if i + 1 < len(history) else ""
        try:
            m = json.loads(model_raw)
            intent = m.get("intent", "?")
            note = m.get("note") or m.get("response", "")
            if note and len(note) > 60:
                note = note[:60] + "…"
            model_summary = f"{intent}: {note}" if note else intent
        except Exception:
            model_summary = model_raw[:80]
        lines.append(f"- \"{user_msg}\" → {model_summary}")
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

        providers = [
            {
                "key": GROQ_API_KEY,
                "url": GROQ_API_URL,
                "headers": {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                "models": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "llama3-8b-8192", "deepseek-r1-distill-llama-70b"],
            },
            {
                "key": CEREBRAS_API_KEY,
                "url": CEREBRAS_API_URL,
                "headers": {"Authorization": f"Bearer {CEREBRAS_API_KEY}", "Content-Type": "application/json"},
                "models": ["llama-3.3-70b"],
            },
            {
                "key": GEMINI_API_KEY,
                "url": GEMINI_API_URL,
                "headers": {"Authorization": f"Bearer {GEMINI_API_KEY}", "Content-Type": "application/json"},
                "models": ["gemini-2.0-flash", "gemini-1.5-flash"],
            },
        ]

        last_error = None
        for provider in providers:
            if not provider["key"]:
                continue
            for model_name in provider["models"]:
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
                        resp = client.post(provider["url"], headers=provider["headers"], json=payload)

                    if resp.status_code == 429:
                        print(f"[parser] {model_name} quota exceeded, trying next...")
                        last_error = "quota_exceeded"
                        continue

                    if resp.status_code == 413:
                        print(f"[parser] {model_name} payload too large, trying next...")
                        last_error = "payload_too_large"
                        continue

                    if resp.status_code in (400, 422):
                        print(f"[parser] {model_name} bad request ({resp.status_code}), trying next...")
                        last_error = "bad_request"
                        continue

                    if resp.status_code == 401:
                        print(f"[parser] {model_name} auth error (401), trying next...")
                        last_error = "auth_error"
                        continue

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

        if last_error in ("quota_exceeded", "payload_too_large"):
            return {"success": False, "error": "quota_exceeded",
                    "message": "AI quota หมดทุก provider"}

        return {"success": False, "error": "api_error",
                "message": f"ไม่สามารถเรียก AI API ได้: {last_error}"}

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
