from db import set_budget, get_budget_status, set_savings_goal, get_savings_status
from flex_builder import build_budget_card, build_savings_card


def handle_budget(send, user_id, parsed):
    amount = parsed.get("amount")
    if amount:
        set_budget(user_id, float(amount))

    status = get_budget_status(user_id)
    if status["budget"] == 0:
        send("📊 ยังไม่ได้ตั้งงบประมาณครับ\nพิมพ์ว่า \"ตั้งงบ 8000\" ได้เลย")
        return

    header = "✅ ตั้งงบประมาณเดือนนี้แล้วครับ" if amount else "💼 งบประมาณเดือนนี้"
    flex = build_budget_card(status)
    send.flex(header, flex, quick_reply=True)


def handle_savings(send, user_id, parsed):
    amount = parsed.get("amount")
    if amount:
        set_savings_goal(user_id, float(amount))

    status = get_savings_status(user_id)
    if status["goal"] == 0:
        send("🎯 ยังไม่ได้ตั้งเป้าออมครับ\nพิมพ์ว่า \"ตั้งเป้าออม 3000\" ได้เลย")
        return

    header = "🎯 ตั้งเป้าออมแล้วครับ!" if amount else "🎯 เป้าหมายการออมเดือนนี้"
    flex = build_savings_card(status)
    send.flex(header, flex, quick_reply=True)
