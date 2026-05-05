# LINE Finance Bot 🤖

Personal finance tracker และ note-taker ผ่าน LINE

## โครงสร้างไฟล์

```
line-finance-bot/
├── main.py              ← FastAPI webhook (entry point)
├── parser.py            ← Gemini AI parser
├── sheets.py            ← Google Sheets integration
├── calendar_service.py  ← Google Calendar integration
├── requirements.txt     ← Python dependencies
├── .env                 ← API Keys (ห้าม upload GitHub)
├── .env.example         ← Template .env
└── credentials.json     ← Google Service Account key (ห้าม upload GitHub)
```

## Setup

### 1. ติดตั้ง Dependencies
```bash
pip install -r requirements.txt
```

### 2. สร้างไฟล์ .env
```bash
cp .env.example .env
```
แล้วแก้ไขค่าใน .env ให้ครบ

### 3. วาง credentials.json
วางไฟล์ credentials.json จาก Google Cloud Console ไว้ใน root folder

### 4. รัน Server (local)
```bash
python main.py
```
Server จะรันที่ http://localhost:8000

### 5. ทดสอบ Webhook (ใช้ ngrok)
```bash
ngrok http 8000
```
Copy HTTPS URL → วางใน LINE Developer Console → Webhook URL

## คำสั่งที่รองรับ

| ตัวอย่างข้อความ | Intent |
|----------------|--------|
| กินกะเพรา 60 บาท | EXPENSE |
| ได้เงินเดือน 18500 | INCOME |
| โน้ต: ต้องซื้อยา | NOTE |
| เตือนพรุ่งนี้ 9 โมง ต่อ พรบ | REMINDER |
| สรุปเดือนนี้ | SUMMARY |
