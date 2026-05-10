from db import get_summary, format_summary_message, get_compare_summary, get_budget_status, get_compare_days_summary
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

    send("\n".join(lines), quick_reply=True)


def handle_compare_days(send, user_id, parsed):
    """เปรียบเทียบรายรับ-รายจ่ายระหว่าง 2 วันที่ระบุ"""
    from datetime import datetime
    import pytz
    bkk = pytz.timezone("Asia/Bangkok")
    now = datetime.now(bkk)

    date_a_str = parsed.get("date_a", "")
    date_b_str = parsed.get("date_b", "")

    def _parse_date(s):
        if not s:
            return None
        try:
            d = datetime.fromisoformat(s)
            return bkk.localize(d) if d.tzinfo is None else d.astimezone(bkk)
        except Exception:
            return None

    date_a = _parse_date(date_a_str) or now
    date_b = _parse_date(date_b_str) or now

    compare = get_compare_days_summary(user_id, date_a, date_b)
    a = compare["a"]
    b = compare["b"]

    if not a["success"] or not b["success"]:
        send("❌ ไม่สามารถดึงข้อมูลเปรียบเทียบได้ครับ")
        return

    label_a = date_a.strftime("%d/%m/%Y")
    label_b = date_b.strftime("%d/%m/%Y")

    def _arrow(val_b, val_a):
        if val_b > val_a: return "📈"
        if val_b < val_a: return "📉"
        return "➡️"

    def _diff(val_b, val_a):
        d = val_b - val_a
        return f"{'+'if d>=0 else ''}{d:,.0f}"

    lines = [
        f"📊 เปรียบเทียบ {label_a} vs {label_b}",
        "",
        f"{'':8s}  {'วันที่ก่อน':>12s}  {'วันที่หลัง':>12s}  เปลี่ยน",
        f"{'─'*52}",
        f"💰 รายรับ  {a['total_income']:>12,.0f}  {b['total_income']:>12,.0f}  {_arrow(b['total_income'],a['total_income'])} {_diff(b['total_income'],a['total_income'])}",
        f"💸 รายจ่าย {a['total_expense']:>12,.0f}  {b['total_expense']:>12,.0f}  {_arrow(b['total_expense'],a['total_expense'])} {_diff(b['total_expense'],a['total_expense'])}",
        f"{'✅'if b['balance']>=0 else '⚠️'} คงเหลือ  {a['balance']:>12,.0f}  {b['balance']:>12,.0f}  {_arrow(b['balance'],a['balance'])} {_diff(b['balance'],a['balance'])}",
    ]

    all_cats = set(a["expense_by_category"]) | set(b["expense_by_category"])
    if all_cats:
        diffs = {
            cat: b["expense_by_category"].get(cat, 0) - a["expense_by_category"].get(cat, 0)
            for cat in all_cats
        }
        top_increase = [(c, d) for c, d in sorted(diffs.items(), key=lambda x: -x[1]) if d > 0][:2]
        top_decrease = [(c, d) for c, d in sorted(diffs.items(), key=lambda x: x[1]) if d < 0][:2]
        if top_increase:
            lines.append("\n📈 หมวดที่ใช้เพิ่มขึ้น:")
            for cat, d in top_increase:
                lines.append(f"  • {cat}: +{d:,.0f} บาท")
        if top_decrease:
            lines.append("📉 หมวดที่ใช้ลดลง:")
            for cat, d in top_decrease:
                lines.append(f"  • {cat}: {d:,.0f} บาท")

    send("\n".join(lines), quick_reply=True)


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
