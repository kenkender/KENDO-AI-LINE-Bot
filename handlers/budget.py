from db import set_budget, get_budget_status, set_savings_goal, get_savings_status


def handle_budget(send, user_id, parsed):
    amount = parsed.get("amount")
    if amount:
        set_budget(user_id, float(amount))
        status = get_budget_status(user_id)
        send(
            f"✅ ตั้งงบประมาณเดือนนี้แล้วครับ\n"
            f"💼 งบ:     {status['budget']:,.2f} บาท\n"
            f"💸 ใช้ไป:  {status['expense']:,.2f} บาท\n"
            f"{'✅' if status['remaining'] >= 0 else '⚠️'} เหลือ:   {status['remaining']:,.2f} บาท",
            quick_reply=True
        )
    else:
        status = get_budget_status(user_id)
        if status["budget"] == 0:
            send("📊 ยังไม่ได้ตั้งงบประมาณครับ\nพิมพ์ว่า \"ตั้งงบ 8000\" ได้เลย")
        else:
            pct = (status["expense"] / status["budget"] * 100) if status["budget"] > 0 else 0
            bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
            send(
                f"💼 งบประมาณเดือนนี้\n\n"
                f"งบ:    {status['budget']:,.2f} บาท\n"
                f"ใช้ไป: {status['expense']:,.2f} บาท ({pct:.1f}%)\n"
                f"[{bar}]\n"
                f"{'✅ เหลือ' if status['remaining'] >= 0 else '⚠️ เกินงบ'}: {abs(status['remaining']):,.2f} บาท",
                quick_reply=True
            )


def handle_savings(send, user_id, parsed):
    amount = parsed.get("amount")
    if amount:
        set_savings_goal(user_id, float(amount))
        status = get_savings_status(user_id)
        send(
            f"🎯 ตั้งเป้าออมแล้วครับ!\n"
            f"🎯 เป้า:  {status['goal']:,.2f} บาท\n"
            f"💰 ออมได้: {status['saved']:,.2f} บาท\n"
            f"📌 ขาดอีก: {status['remaining']:,.2f} บาท",
            quick_reply=True
        )
    else:
        status = get_savings_status(user_id)
        if status["goal"] == 0:
            send("🎯 ยังไม่ได้ตั้งเป้าออมครับ\nพิมพ์ว่า \"ตั้งเป้าออม 3000\" ได้เลย")
        else:
            pct = (status["saved"] / status["goal"] * 100) if status["goal"] > 0 else 0
            bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
            footer = "🎉 ถึงเป้าแล้ว!" if status["remaining"] <= 0 else f"📌 ขาดอีก {status['remaining']:,.2f} บาท"
            send(
                f"🎯 เป้าหมายการออมเดือนนี้\n\n"
                f"เป้า:   {status['goal']:,.2f} บาท\n"
                f"ออมได้: {status['saved']:,.2f} บาท ({pct:.1f}%)\n"
                f"[{bar}]\n"
                f"{footer}",
                quick_reply=True
            )
