from db import (append_note, get_active_reminders, cancel_reminder,
                 add_interval_reminder, get_active_interval_reminders,
                 cancel_interval_reminder_by_label, cancel_all_interval_reminders)
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
        try:
            cal_result = create_reminder_event(note, reminder_dt)
            if cal_result["success"]:
                calendar_event_id = cal_result["event_id"]
        except Exception as e:
            print(f"[reminder] Google Calendar error (skipping): {e}")

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


def _format_interval(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} นาที"
    hours, mins = divmod(minutes, 60)
    return f"{hours} ชั่วโมง" + (f" {mins} นาที" if mins else "")


def handle_interval_set(send, user_id, parsed):
    label = (parsed.get("note") or "").strip()
    interval_minutes = parsed.get("interval_minutes")

    if not label or not interval_minutes:
        send(
            "⏱ บอกด้วยนะครับว่าจะเตือนเรื่องอะไร และทุกกี่นาที/ชั่วโมง\n\n"
            "ตัวอย่าง:\n"
            "  • \"ตั้งเตือนดื่มน้ำทุก 30 นาที\"\n"
            "  • \"เตือนกินยาทุก 4 ชั่วโมง\"\n"
            "  • \"เตือนขยับตัวทุก 1 ชั่วโมงครึ่ง\""
        )
        return

    interval_minutes = int(interval_minutes)
    if interval_minutes < 1:
        send("⏱ ระยะเวลาต้องไม่น้อยกว่า 1 นาทีนะครับ")
        return

    result = add_interval_reminder(user_id, label, interval_minutes)
    if not result["success"]:
        send(f"❌ {result['message']}")
        return

    interval_text = _format_interval(interval_minutes)
    send(
        f"⏱ ตั้งเตือน \"{label}\" ทุก {interval_text} แล้วครับ!\n\n"
        f"ผมจะแจ้งเตือนจนกว่าคุณจะสั่งให้ผมหยุดการแจ้งเตือนในครั้งนี้ครับ "
        f"ถ้าอยากให้ผมหยุดการแจ้งเตือน แค่บอกผมว่า "
        f"\"หยุดการแจ้งเตือน {label}\" นะครับ",
        quick_reply=True
    )


def handle_interval_list(send, user_id):
    items = get_active_interval_reminders(user_id)
    if not items:
        send(
            "📭 ไม่มีการแจ้งเตือนซ้ำที่ใช้งานอยู่เลยครับ\n\n"
            "ตั้งใหม่ได้เลยนะครับ เช่น \"เตือนดื่มน้ำทุก 30 นาที\""
        )
        return
    lines = [f"⏱ การแจ้งเตือนซ้ำที่ใช้งานอยู่ ({len(items)}/{5}):\n"]
    for i, item in enumerate(items, 1):
        interval_text = _format_interval(item["interval_minutes"])
        lines.append(f"{i}. {item['label']} — ทุก {interval_text}")
    lines.append("\nพิมพ์ \"หยุดการแจ้งเตือน [ชื่อ]\" เพื่อยกเลิกครับ")
    send("\n".join(lines), quick_reply=True)


def handle_interval_cancel(send, user_id, parsed):
    label = (parsed.get("note") or "").strip()

    if not label or label in ("ทั้งหมด", "all"):
        count = cancel_all_interval_reminders(user_id)
        if count:
            send(f"✅ ยกเลิกการแจ้งเตือนซ้ำทั้งหมด {count} รายการแล้วครับ!")
        else:
            send("📭 ไม่มีการแจ้งเตือนซ้ำที่ต้องยกเลิกครับ")
        return

    result = cancel_interval_reminder_by_label(user_id, label)
    if result["cancelled_count"] > 0:
        send(f"✅ หยุดการแจ้งเตือน \"{label}\" แล้วครับ!")
    else:
        items = get_active_interval_reminders(user_id)
        if not items:
            send("📭 ไม่มีการแจ้งเตือนซ้ำที่ใช้งานอยู่เลยครับ")
        else:
            lines = [f"🔍 หาไม่เจอครับ มีรายการเหล่านี้อยู่:\n"]
            for item in items:
                lines.append(f"  • {item['label']} (ทุก {_format_interval(item['interval_minutes'])})")
            lines.append("\nพิมพ์ \"หยุดการแจ้งเตือน [ชื่อ]\" หรือ \"หยุดการแจ้งเตือนทั้งหมด\" นะครับ")
            send("\n".join(lines))
