from db import append_note, get_active_reminders, cancel_reminder
from calendar_service import create_reminder_event, delete_calendar_event

_DAY_TH = {1: "จันทร์", 2: "อังคาร", 3: "พุธ", 4: "พฤหัสบดี",
           5: "ศุกร์", 6: "เสาร์", 7: "อาทิตย์"}


def handle_note(send, user_id, raw_text, parsed):
    success = append_note(user_id, raw_text, parsed)
    if success:
        send(f"📝 จดไว้ให้แล้วครับ\n\"{parsed.get('note', '')}\"")
    else:
        send("😓 บันทึกโน้ตไม่ได้ครับ ลองใหม่นะ")


def handle_reminder(send, user_id, raw_text, parsed):
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

    if recurrence == "daily":
        recur_line = "\n🔁 ทำซ้ำ: ทุกวัน"
    elif recurrence.startswith("weekly:"):
        recur_line = f"\n🔁 ทำซ้ำ: ทุกวัน{_DAY_TH.get(int(recurrence.split(':')[1]), '')}"
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
            f"✅ เพิ่มใน Google Calendar แล้วด้วยนะ"
        )
    elif success:
        send(
            f"⏰ ตั้งเตือนไว้แล้วครับ!\n"
            f"📝 {note}\n"
            f"🗓 {reminder_dt}"
            f"{recur_line}{extras_line}"
        )
    else:
        send("😓 บันทึกไม่ได้ครับ ลองใหม่นะ")


def handle_cancel(send, user_id, parsed):
    keyword = parsed.get("note", "").strip()
    active = get_active_reminders(user_id)

    if not active:
        send("📭 ไม่มีการแจ้งเตือนที่ค้างอยู่เลยครับ")
        return

    if not keyword or keyword == "ทั้งหมด":
        count = 0
        for r in active:
            if cancel_reminder(r["row_index"]):
                count += 1
                if r["calendar_event_id"]:
                    delete_calendar_event(r["calendar_event_id"])
        send(f"✅ ยกเลิกทั้งหมด {count} รายการแล้วครับ!")
        return

    matched = [r for r in active if keyword.lower() in r["note"].lower()]

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
            f"🗓 {r['reminder_datetime'][:16].replace('T', ' ')}"
        )
    else:
        lines = [f"🔍 เจอ {len(matched)} รายการที่ตรงกัน ระบุให้ชัดขึ้นนิดนึงนะครับ:\n"]
        for r in matched:
            lines.append(f"  • {r['note']} ({r['reminder_datetime'][:16].replace('T', ' ')})")
        send("\n".join(lines))
