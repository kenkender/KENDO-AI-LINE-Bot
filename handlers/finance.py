from db import (
    append_transaction, delete_last_transaction, search_transactions,
    get_summary, format_quick_summary, get_budget_status,
    get_today_summary, get_date_summary,
)
from flex_builder import build_expense_card, build_income_card, build_today_card


def handle_expense(send, user_id, raw_text, parsed):
    success = append_transaction(user_id, raw_text, parsed)
    if success:
        summary = get_summary()
        budget_status = get_budget_status(user_id)
        flex = build_expense_card(
            note=parsed.get("note", ""),
            amount=parsed.get("amount", 0),
            category=parsed.get("category", "อื่นๆ"),
            summary=summary if summary["success"] else None,
            budget_status=budget_status if budget_status.get("budget", 0) > 0 else None
        )
        send.flex(f"💸 {parsed.get('note', 'รายจ่าย')} {parsed.get('amount', 0):,.0f} บาท",
                  flex, quick_reply=True)
    else:
        send("😓 บันทึกไม่ได้ครับ ลองใหม่นะ")


def handle_income(send, user_id, raw_text, parsed):
    success = append_transaction(user_id, raw_text, parsed)
    if success:
        summary = get_summary()
        flex = build_income_card(
            note=parsed.get("note", ""),
            amount=parsed.get("amount", 0),
            summary=summary if summary["success"] else None
        )
        send.flex(f"💰 {parsed.get('note', 'รายรับ')} +{parsed.get('amount', 0):,.0f} บาท",
                  flex, quick_reply=True)
    else:
        send("😓 บันทึกไม่ได้ครับ ลองใหม่นะ")


def handle_delete(send, user_id):
    result = delete_last_transaction(user_id)
    if result["success"]:
        icon = "💸" if result["intent"] == "EXPENSE" else "💰"
        send(
            f"🗑 ลบรายการล่าสุดแล้วครับ\n"
            f"{icon} {result['note']} — {result['amount']:,.2f} บาท",
            quick_reply=True
        )
    else:
        send("❌ ไม่พบรายการที่จะลบครับ")


def handle_search(send, user_id, parsed):
    keyword = parsed.get("note", "").strip()
    if not keyword:
        send("🔍 บอกด้วยนะครับว่าจะค้นหาอะไร\nเช่น \"ค้นหากาแฟ\"")
        return
    results = search_transactions(user_id, keyword)
    if not results:
        send(f"🔍 ไม่พบรายการที่มีคำว่า \"{keyword}\" ครับ")
    else:
        total = sum(r["amount"] for r in results)
        lines = [f"🔍 ผลการค้นหา \"{keyword}\" — {len(results)} รายการ\n"]
        for r in results[-10:]:
            icon = "💸" if r["intent"] == "EXPENSE" else "💰"
            lines.append(f"  {icon} {r['note']} {r['amount']:,.0f} บาท ({r['timestamp']})")
        lines.append(f"\nรวม: {total:,.2f} บาท")
        send("\n".join(lines), quick_reply=True)


def handle_today_expense(send, user_id, parsed=None):
    from datetime import datetime, timedelta
    import pytz

    bangkok_tz = pytz.timezone("Asia/Bangkok")
    target_date = None

    if parsed and parsed.get("reminder_datetime"):
        try:
            target_date = datetime.fromisoformat(parsed["reminder_datetime"])
            if target_date.tzinfo is None:
                target_date = bangkok_tz.localize(target_date)
        except:
            pass

    if not target_date:
        target_date = datetime.now(bangkok_tz)

    data = get_date_summary(user_id, target_date)
    date_display = target_date.strftime("%d/%m/%Y")

    if not data["success"] or (data["total_income"] == 0 and data["total_expense"] == 0):
        send(f"📭 ยังไม่มีรายการเมื่อวันที่ {date_display} เลยครับ", quick_reply=True)
        return
    flex = build_today_card(data)
    title = f"📊 สรุปวันที่ {date_display}"
    send.flex(title, flex, quick_reply=True)


def handle_split_bill(send, parsed):
    amount = parsed.get("amount")
    split_count = parsed.get("split_count")
    if not amount or not split_count or int(split_count) <= 0:
        send("🧾 บอกด้วยนะครับว่าหารเท่าไหร่ กี่คน\nเช่น: \"หารค่าอาหาร 480 บาท 3 คน\"")
    else:
        per_person = float(amount) / int(split_count)
        send(
            f"🧾 หารบิล {float(amount):,.0f} บาท ÷ {int(split_count)} คน\n\n"
            f"💵 คนละ {per_person:,.2f} บาท",
            quick_reply=True
        )
