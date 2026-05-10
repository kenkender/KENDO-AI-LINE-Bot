from db import get_summary, format_summary_message, get_compare_summary, get_compare_days_summary, get_budget_status
from parser import analyze_with_ai
from db import set_briefing
from flex_builder import build_summary_card

_THAI_MONTHS_FULL = {
    1: "มกราคม", 2: "กุมภาพันธ์", 3: "มีนาคม", 4: "เมษายน",
    5: "พฤษภาคม", 6: "มิถุนายน", 7: "กรกฎาคม", 8: "สิงหาคม",
    9: "กันยายน", 10: "ตุลาคม", 11: "พฤศจิกายน", 12: "ธันวาคม"
}


def handle_summary(send, parsed, user_id=None):
    summary = get_summary(
        month=parsed.get("summary_month"),
        year=parsed.get("summary_year")
    )
    if not summary["success"]:
        send("❌ ไม่สามารถดึงข้อมูลสรุปได้ กรุณาลองใหม่ครับ")
        return

    budget_status = None
    if user_id:
        bs = get_budget_status(user_id)
        if bs.get("budget", 0) > 0:
            budget_status = bs

    month_name = _THAI_MONTHS_FULL.get(summary["month"], str(summary["month"]))
    flex = build_summary_card(summary, budget_status)
    send.flex(f"📊 สรุป{month_name} {summary['year']}", flex, quick_reply=True)


def handle_analyze(send):
    summary = get_summary()
    if summary["success"]:
        analysis = analyze_with_ai(summary)
        send(f"🧠 วิเคราะห์การใช้จ่ายของคุณ\n\n{analysis}", quick_reply=True)
    else:
        send("❌ ไม่มีข้อมูลการใช้จ่ายเดือนนี้ครับ")


def handle_compare(send, parsed):
    from datetime import datetime
    import pytz
    now = datetime.now(pytz.timezone("Asia/Bangkok"))

    month_b = parsed.get("summary_month") or now.month
    year_b = parsed.get("summary_year") or now.year

    if month_b == 1:
        month_a, year_a = 12, year_b - 1
    else:
        month_a, year_a = month_b - 1, year_b

    compare = get_compare_summary(month_a, year_a, month_b, year_b)
    a = compare["a"]
    b = compare["b"]

    if not a["success"] or not b["success"]:
        send("❌ ไม่สามารถดึงข้อมูลเพื่อเปรียบเทียบได้ครับ")
        return

    name_a = _THAI_MONTHS_FULL.get(month_a, str(month_a))
    name_b = _THAI_MONTHS_FULL.get(month_b, str(month_b))

    def _arrow(val_b, val_a):
        if val_b > val_a:
            return "📈"
        if val_b < val_a:
            return "📉"
        return "➡️"

    def _diff(val_b, val_a):
        d = val_b - val_a
        sign = "+" if d >= 0 else ""
        return f"{sign}{d:,.0f}"

    inc_arrow = _arrow(b["total_income"], a["total_income"])
    exp_arrow = _arrow(b["total_expense"], a["total_expense"])
    bal_arrow = _arrow(b["balance"], a["balance"])

    lines = [
        f"📊 เปรียบเทียบ {name_a} vs {name_b}",
        "",
        f"{'':10s}  {name_a:>10s}  {name_b:>10s}  เปลี่ยน",
        f"{'─'*46}",
        f"💰 รายรับ   {a['total_income']:>10,.0f}  {b['total_income']:>10,.0f}  {inc_arrow} {_diff(b['total_income'], a['total_income'])}",
        f"💸 รายจ่าย  {a['total_expense']:>10,.0f}  {b['total_expense']:>10,.0f}  {exp_arrow} {_diff(b['total_expense'], a['total_expense'])}",
        f"{'✅' if b['balance']>=0 else '⚠️'} คงเหลือ   {a['balance']:>10,.0f}  {b['balance']:>10,.0f}  {bal_arrow} {_diff(b['balance'], a['balance'])}",
    ]

    all_cats = set(a["expense_by_category"]) | set(b["expense_by_category"])
    diffs = {
        cat: b["expense_by_category"].get(cat, 0) - a["expense_by_category"].get(cat, 0)
        for cat in all_cats
    }
    top_increase = sorted(diffs.items(), key=lambda x: -x[1])[:2]
    top_decrease = sorted(diffs.items(), key=lambda x: x[1])[:2]

    if top_increase and top_increase[0][1] > 0:
        lines.append("")
        lines.append("📈 หมวดที่ใช้เพิ่มขึ้น:")
        for cat, d in top_increase:
            if d > 0:
                lines.append(f"  • {cat}: +{d:,.0f} บาท")

    if top_decrease and top_decrease[0][1] < 0:
        lines.append("📉 หมวดที่ใช้ลดลง:")
        for cat, d in top_decrease:
            if d < 0:
                lines.append(f"  • {cat}: {d:,.0f} บาท")

    flex_dict = {
        "type": "bubble",
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "contents": [
                {
                    "type": "text",
                    "text": f"📊 เปรียบเทียบ {name_a} vs {name_b}",
                    "weight": "bold",
                    "size": "lg",
                    "color": "#1DB446"
                },
                {
                    "type": "separator",
                    "margin": "md"
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "margin": "md",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "box",
                            "layout": "baseline",
                            "contents": [
                                {"type": "text", "text": "💰 รายรับ", "flex": 2, "weight": "bold"},
                                {"type": "text", "text": f"{a['total_income']:,.0f}", "flex": 1, "align": "end", "size": "sm", "color": "#666666"},
                                {"type": "text", "text": f"{b['total_income']:,.0f}", "flex": 1, "align": "end", "weight": "bold"},
                                {"type": "text", "text": _arrow(b['total_income'], a['total_income']), "flex": 0, "align": "end", "margin": "sm"}
                            ]
                        },
                        {
                            "type": "box",
                            "layout": "baseline",
                            "contents": [
                                {"type": "text", "text": "💸 รายจ่าย", "flex": 2, "weight": "bold"},
                                {"type": "text", "text": f"{a['total_expense']:,.0f}", "flex": 1, "align": "end", "size": "sm", "color": "#666666"},
                                {"type": "text", "text": f"{b['total_expense']:,.0f}", "flex": 1, "align": "end", "weight": "bold"},
                                {"type": "text", "text": _arrow(b['total_expense'], a['total_expense']), "flex": 0, "align": "end", "margin": "sm"}
                            ]
                        },
                        {
                            "type": "box",
                            "layout": "baseline",
                            "contents": [
                                {"type": "text", "text": f"{'✅' if b['balance']>=0 else '⚠️'} คงเหลือ", "flex": 2, "weight": "bold"},
                                {"type": "text", "text": f"{a['balance']:,.0f}", "flex": 1, "align": "end", "size": "sm", "color": "#666666"},
                                {"type": "text", "text": f"{b['balance']:,.0f}", "flex": 1, "align": "end", "weight": "bold", "color": "#FF0000" if b['balance']<0 else "#1DB446"},
                                {"type": "text", "text": _arrow(b['balance'], a['balance']), "flex": 0, "align": "end", "margin": "sm"}
                            ]
                        }
                    ]
                }
            ]
        }
    }

    if top_increase or top_decrease:
        footer_items = []
        if top_increase and top_increase[0][1] > 0:
            for cat, d in top_increase:
                if d > 0:
                    footer_items.append({"type": "text", "text": f"📈 {cat}: +{d:,.0f} บาท", "size": "xs", "color": "#FF0000", "margin": "xs"})
        if top_decrease and top_decrease[0][1] < 0:
            for cat, d in top_decrease:
                if d < 0:
                    footer_items.append({"type": "text", "text": f"📉 {cat}: {d:,.0f} บาท", "size": "xs", "color": "#1DB446", "margin": "xs"})
        if footer_items:
            flex_dict["footer"] = {"type": "box", "layout": "vertical", "spacing": "xs", "contents": footer_items}

    send.flex(f"📊 เปรียบเทียบ {name_a} vs {name_b}", flex_dict, quick_reply=True)


def handle_compare_days(send, user_id, parsed):
    from datetime import datetime, timedelta
    import pytz

    _BKK = pytz.timezone("Asia/Bangkok")
    now = datetime.now(_BKK)

    raw_a = parsed.get("date_a")
    raw_b = parsed.get("date_b")

    date_a = datetime.fromisoformat(raw_a) if raw_a else now - timedelta(days=1)
    date_b = datetime.fromisoformat(raw_b) if raw_b else now

    compare = get_compare_days_summary(user_id, date_a, date_b)
    a = compare["a"]
    b = compare["b"]

    if not a["success"] or not b["success"]:
        send("❌ ไม่สามารถดึงข้อมูลเพื่อเปรียบเทียบได้ครับ")
        return

    _THAI_MONTHS_SHORT = {
        1: "ม.ค.", 2: "ก.พ.", 3: "มี.ค.", 4: "เม.ย.",
        5: "พ.ค.", 6: "มิ.ย.", 7: "ก.ค.", 8: "ส.ค.",
        9: "ก.ย.", 10: "ต.ค.", 11: "พ.ย.", 12: "ธ.ค."
    }

    def _fmt_date(dt):
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt)
            except:
                return dt
        return f"{dt.day} {_THAI_MONTHS_SHORT[dt.month]} {dt.year}"

    label_a = _fmt_date(date_a)
    label_b = _fmt_date(date_b)

    def _arrow(val_b, val_a):
        if val_b > val_a:
            return "📈"
        if val_b < val_a:
            return "📉"
        return "➡️"

    def _diff(val_b, val_a):
        d = val_b - val_a
        sign = "+" if d >= 0 else ""
        return f"{sign}{d:,.0f}"

    flex_dict = {
        "type": "bubble",
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "contents": [
                {
                    "type": "text",
                    "text": f"📅 {label_a}  vs  {label_b}",
                    "weight": "bold",
                    "size": "md",
                    "color": "#1DB446",
                    "wrap": True
                },
                {
                    "type": "separator",
                    "margin": "md"
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "margin": "sm",
                    "contents": [
                        {"type": "filler", "flex": 2},
                        {"type": "text", "text": label_a, "flex": 2, "align": "end", "size": "xs", "color": "#888888", "wrap": True},
                        {"type": "text", "text": label_b, "flex": 2, "align": "end", "size": "xs", "weight": "bold", "wrap": True},
                        {"type": "text", "text": "+/-", "flex": 1, "align": "end", "size": "xs", "color": "#888888"}
                    ]
                },
                {
                    "type": "separator",
                    "margin": "sm"
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "margin": "sm",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "box",
                            "layout": "horizontal",
                            "contents": [
                                {"type": "text", "text": "💰 รายรับ", "flex": 2, "weight": "bold", "size": "sm"},
                                {"type": "text", "text": f"{a['total_income']:,.0f}", "flex": 2, "align": "end", "size": "sm", "color": "#888888"},
                                {"type": "text", "text": f"{b['total_income']:,.0f}", "flex": 2, "align": "end", "size": "sm", "weight": "bold"},
                                {"type": "text", "text": f"{_arrow(b['total_income'],a['total_income'])} {_diff(b['total_income'],a['total_income'])}", "flex": 2, "align": "end", "size": "xs", "wrap": True}
                            ]
                        },
                        {
                            "type": "box",
                            "layout": "horizontal",
                            "contents": [
                                {"type": "text", "text": "💸 รายจ่าย", "flex": 2, "weight": "bold", "size": "sm"},
                                {"type": "text", "text": f"{a['total_expense']:,.0f}", "flex": 2, "align": "end", "size": "sm", "color": "#888888"},
                                {"type": "text", "text": f"{b['total_expense']:,.0f}", "flex": 2, "align": "end", "size": "sm", "weight": "bold"},
                                {"type": "text", "text": f"{_arrow(b['total_expense'],a['total_expense'])} {_diff(b['total_expense'],a['total_expense'])}", "flex": 2, "align": "end", "size": "xs", "wrap": True}
                            ]
                        },
                        {
                            "type": "box",
                            "layout": "horizontal",
                            "contents": [
                                {"type": "text", "text": f"{'✅' if b['balance']>=0 else '⚠️'} คงเหลือ", "flex": 2, "weight": "bold", "size": "sm"},
                                {"type": "text", "text": f"{a['balance']:,.0f}", "flex": 2, "align": "end", "size": "sm", "color": "#888888"},
                                {"type": "text", "text": f"{b['balance']:,.0f}", "flex": 2, "align": "end", "size": "sm", "weight": "bold",
                                 "color": "#FF0000" if b['balance'] < 0 else "#1DB446"},
                                {"type": "text", "text": f"{_arrow(b['balance'],a['balance'])} {_diff(b['balance'],a['balance'])}", "flex": 2, "align": "end", "size": "xs", "wrap": True}
                            ]
                        }
                    ]
                }
            ]
        }
    }

    all_cats = set(a["expense_by_category"]) | set(b["expense_by_category"])
    if all_cats:
        diffs = {
            cat: b["expense_by_category"].get(cat, 0) - a["expense_by_category"].get(cat, 0)
            for cat in all_cats
        }
        top_increase = [(c, d) for c, d in sorted(diffs.items(), key=lambda x: -x[1]) if d > 0][:2]
        top_decrease = [(c, d) for c, d in sorted(diffs.items(), key=lambda x: x[1]) if d < 0][:2]
        footer_items = []
        for cat, d in top_increase:
            footer_items.append({"type": "text", "text": f"📈 {cat}: +{d:,.0f} บาท", "size": "xs", "color": "#FF6B6B", "margin": "xs"})
        for cat, d in top_decrease:
            footer_items.append({"type": "text", "text": f"📉 {cat}: {d:,.0f} บาท", "size": "xs", "color": "#1DB446", "margin": "xs"})
        if footer_items:
            flex_dict["footer"] = {"type": "box", "layout": "vertical", "spacing": "xs", "contents": footer_items}

    send.flex(f"📅 เปรียบเทียบ {label_a} vs {label_b}", flex_dict, quick_reply=True)


def handle_briefing_set(send, user_id, parsed):
    briefing_hour = parsed.get("briefing_hour")
    briefing_minute = int(parsed.get("briefing_minute") or 0)
    city = (parsed.get("note") or "").strip() or "กรุงเทพ"
    if briefing_hour is None:
        send(
            "🌅 บอกเวลาด้วยนะครับ\n"
            "เช่น: \"เปิด morning briefing 7 โมงเช้า กรุงเทพ\" หรือ \"briefing 08:30น.\""
        )
        return
    set_briefing(user_id, int(briefing_hour), city, briefing_minute)
    send(
        f"🌅 เปิด Morning Briefing แล้วครับ!\n"
        f"⏰ เวลา {int(briefing_hour):02d}:{briefing_minute:02d} น.\n"
        f"📍 สถานที่: {city}\n\n"
        f"ทุกเช้าจะส่งสรุปอากาศ + ค่าฝุ่น + เตือนวันนี้ให้ครับ",
        quick_reply=True
    )
