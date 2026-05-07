from db import (
    append_transaction, delete_last_transaction, search_transactions,
    get_summary, format_quick_summary,
)


def handle_expense(send, user_id, raw_text, parsed):
    success = append_transaction(user_id, raw_text, parsed)
    if success:
        summary = get_summary()
        summary_text = format_quick_summary(summary) if summary["success"] else ""
        send(
            f"💸 จดให้แล้วครับ!\n"
            f"📝 {parsed.get('note', '')}\n"
            f"💰 {parsed.get('amount', 0):,.2f} บาท\n"
            f"📂 หมวด: {parsed.get('category', 'อื่นๆ')}"
            f"{summary_text}",
            quick_reply=True
        )
    else:
        send("😓 บันทึกไม่ได้ครับ ลองใหม่นะ")


def handle_income(send, user_id, raw_text, parsed):
    success = append_transaction(user_id, raw_text, parsed)
    if success:
        summary = get_summary()
        summary_text = format_quick_summary(summary) if summary["success"] else ""
        send(
            f"💰 เย่! บันทึกรายรับแล้วครับ\n"
            f"📝 {parsed.get('note', '')}\n"
            f"✅ +{parsed.get('amount', 0):,.2f} บาท"
            f"{summary_text}",
            quick_reply=True
        )
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


def handle_today_expense(send, user_id):
    from db import get_today_summary
    data = get_today_summary(user_id)
    if not data["success"] or (data["total_income"] == 0 and data["total_expense"] == 0):
        send("📭 ยังไม่มีรายการวันนี้เลยครับ", quick_reply=True)
        return
    lines = [f"📊 สรุปวันนี้ ({data['date']})\n"]
    if data["total_income"] > 0:
        lines.append(f"💰 รายรับ:   {data['total_income']:,.0f} บาท")
    if data["total_expense"] > 0:
        lines.append(f"💸 รายจ่าย:  {data['total_expense']:,.0f} บาท")
    balance = data["balance"]
    lines.append(f"{'✅' if balance >= 0 else '⚠️'} คงเหลือ:   {balance:,.0f} บาท")
    if data["expense_by_category"]:
        lines.append("\n📂 แยกตามหมวด:")
        for cat, amt in sorted(data["expense_by_category"].items(), key=lambda x: -x[1]):
            lines.append(f"  • {cat}: {amt:,.0f} บาท")
    send("\n".join(lines), quick_reply=True)


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
