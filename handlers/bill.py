from db import add_bill, list_bills, delete_bill
from flex_builder import build_bill_list_carousel


def handle_bill_add(send, user_id, parsed):
    name = parsed.get("note", "").strip()
    amount = parsed.get("amount")
    due_day = parsed.get("bill_due_day")
    if not name or not amount or not due_day:
        send(
            "💳 บอกรายละเอียดบิลด้วยนะครับ\n"
            "เช่น: \"ตั้งบิล ค่าไฟ 800 บาท ทุกวันที่ 20\""
        )
        return
    add_bill(user_id, name, float(amount), int(due_day))
    send(
        f"💳 ตั้งบิลประจำแล้วครับ!\n"
        f"📋 {name}\n"
        f"💸 {float(amount):,.0f} บาท\n"
        f"📅 ครบกำหนดวันที่ {int(due_day)} ของทุกเดือน\n\n"
        f"ผมจะแจ้งเตือนก่อน 3 วัน และวันครบกำหนดนะครับ",
        quick_reply=True
    )


def handle_bill_list(send, user_id):
    bills = list_bills(user_id)
    if not bills:
        send.flex(
            "💳 บิลประจำ",
            build_bill_list_carousel([]),
            quick_reply=True
        )
        return
    flex = build_bill_list_carousel(bills)
    total = sum(b["amount"] for b in bills)
    send.flex(
        f"💳 บิลประจำ {len(bills)} รายการ รวม {total:,.0f} บาท/เดือน",
        flex,
        quick_reply=True
    )


def handle_bill_delete(send, user_id, parsed):
    keyword = parsed.get("note", "").strip()
    if not keyword:
        send("💳 บอกด้วยนะครับว่าจะลบบิลอะไร\nเช่น: \"ลบบิลค่าไฟ\"")
        return
    result = delete_bill(user_id, keyword)
    if result.get("success"):
        send(f"🗑 ลบบิล \"{result['name']}\" แล้วครับ", quick_reply=True)
    else:
        bills = list_bills(user_id)
        if bills:
            lines = [f"🔍 ไม่เจอบิล \"{keyword}\" ครับ มีอยู่:\n"]
            for b in bills:
                lines.append(f"  • {b['name']}")
            send("\n".join(lines))
        else:
            send("💳 ยังไม่มีบิลประจำเลยครับ")
