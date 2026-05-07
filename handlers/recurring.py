from db import (add_recurring_items, list_recurring_items, delete_recurring_item,
                set_recurring_remind_day, get_recurring_remind_day)
from flex_builder import build_recurring_card


def _remind_label(remind_day: int | None) -> str:
    if remind_day and 1 <= remind_day <= 31:
        return f"แจ้งเตือนทุกวันที่ {remind_day} ของเดือน"
    return ""


def handle_recurring_add(send, user_id, parsed):
    items = parsed.get("items") or []
    valid = [i for i in items if i.get("name") and float(i.get("amount") or 0) > 0]
    if not valid:
        send(
            "🔄 บอกรายการด้วยนะครับ\n\n"
            "ตัวอย่าง:\n"
            "  \"เพิ่มรายจ่ายซ้ำ Netflix 299 Spotify 99\"\n"
            "  \"รายจ่ายซ้ำ 1.Netflix 299 2.Spotify 99 3.ค่าเน็ต 599\""
        )
        return

    added = add_recurring_items(user_id, valid)
    if added == 0:
        send("😓 บันทึกไม่ได้ครับ ลองใหม่นะ")
        return

    all_items = list_recurring_items(user_id)
    remind_day = get_recurring_remind_day(user_id)
    remind_label = _remind_label(remind_day)
    flex = build_recurring_card(
        items=all_items,
        payday_str=remind_label,
        header=f"🔄 เพิ่ม {added} รายการแล้วครับ!"
    )
    send.flex(f"🔄 เพิ่มรายจ่ายซ้ำ {added} รายการ", flex, quick_reply=True)


def handle_recurring_list(send, user_id):
    items = list_recurring_items(user_id)
    remind_day = get_recurring_remind_day(user_id)
    remind_label = _remind_label(remind_day)

    if not items:
        body = "🔄 รายจ่ายประจำทุกเดือน"
        if not remind_label:
            body += "\n\nยังไม่ได้ตั้งวันแจ้งเตือนครับ\nพิมพ์ \"ตั้งเตือนรายจ่ายซ้ำวันที่ 25\" ได้เลย"
        send.flex("🔄 รายจ่ายประจำ", build_recurring_card([], header=body), quick_reply=True)
        return

    flex = build_recurring_card(
        items=items,
        payday_str=remind_label,
        header=f"🔄 รายจ่ายประจำ {len(items)} รายการ"
    )
    send.flex(f"🔄 รายจ่ายประจำ {len(items)} รายการ", flex, quick_reply=True)


def handle_recurring_delete(send, user_id, parsed):
    keyword = parsed.get("note", "").strip()
    if not keyword:
        send("🔄 บอกด้วยนะครับว่าจะลบรายการอะไร\nเช่น: \"ลบรายจ่ายซ้ำ Netflix\"")
        return
    result = delete_recurring_item(user_id, keyword)
    if result.get("success"):
        remaining = list_recurring_items(user_id)
        send(
            f"🗑 ลบ \"{result['name']}\" ออกจากรายจ่ายซ้ำแล้วครับ\n"
            f"ยังมีอีก {len(remaining)} รายการ",
            quick_reply=True
        )
    else:
        items = list_recurring_items(user_id)
        if items:
            lines = [f"🔍 ไม่เจอ \"{keyword}\" ครับ มีอยู่:\n"]
            for it in items:
                lines.append(f"  • {it['name']}")
            send("\n".join(lines))
        else:
            send("🔄 ยังไม่มีรายจ่ายซ้ำเลยครับ")


def handle_recurring_set_remind(send, user_id, parsed):
    remind_day = parsed.get("remind_day")

    # ปิดแจ้งเตือน
    if remind_day is not None and int(remind_day) == 0:
        set_recurring_remind_day(user_id, 0)
        send("🔕 ปิดแจ้งเตือนรายจ่ายซ้ำแล้วครับ", quick_reply=True)
        return

    if not remind_day or not (1 <= int(remind_day) <= 31):
        send(
            "📅 บอกวันที่ต้องการด้วยนะครับ\n\n"
            "เช่น: \"ตั้งเตือนรายจ่ายซ้ำทุกวันที่ 25\"\n"
            "      \"แจ้งเตือน subscription วันที่ 1\""
        )
        return

    day = int(remind_day)
    set_recurring_remind_day(user_id, day)
    items = list_recurring_items(user_id)
    total = sum(i["amount"] for i in items) if items else 0

    msg = (
        f"✅ ตั้งแจ้งเตือนรายจ่ายซ้ำแล้วครับ!\n\n"
        f"📅 จะแจ้งเตือนทุกวันที่ {day} ของเดือน"
    )
    if items:
        msg += f"\n💸 รวม {len(items)} รายการ  {total:,.0f} บาท/เดือน"
    else:
        msg += "\n\n(ยังไม่มีรายการ ลองเพิ่มด้วย \"เพิ่มรายจ่ายซ้ำ Netflix 299\" ครับ)"
    send(msg, quick_reply=True)
