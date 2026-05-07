"""
flex_builder.py — สร้าง LINE Flex Message JSON templates
"""

from datetime import datetime
import pytz

_THAI_MONTHS_SHORT = {
    1: "ม.ค.", 2: "ก.พ.", 3: "มี.ค.", 4: "เม.ย.",
    5: "พ.ค.", 6: "มิ.ย.", 7: "ก.ค.", 8: "ส.ค.",
    9: "ก.ย.", 10: "ต.ค.", 11: "พ.ย.", 12: "ธ.ค."
}
_THAI_MONTHS_FULL = {
    1: "มกราคม", 2: "กุมภาพันธ์", 3: "มีนาคม", 4: "เมษายน",
    5: "พฤษภาคม", 6: "มิถุนายน", 7: "กรกฎาคม", 8: "สิงหาคม",
    9: "กันยายน", 10: "ตุลาคม", 11: "พฤศจิกายน", 12: "ธันวาคม"
}


def _progress_bar(pct: float, color_used: str = "#E74C3C",
                  color_empty: str = "#EEEEEE") -> dict:
    """Progress bar แบบ horizontal box สำหรับ Flex Message"""
    pct = max(0.0, min(100.0, pct))
    used = max(1, int(round(pct)))
    empty = max(1, 100 - used)
    return {
        "type": "box",
        "layout": "horizontal",
        "paddingAll": "0px",
        "height": "8px",
        "contents": [
            {
                "type": "box",
                "layout": "vertical",
                "flex": used,
                "backgroundColor": color_used,
                "contents": [{"type": "filler"}]
            },
            {
                "type": "box",
                "layout": "vertical",
                "flex": empty,
                "backgroundColor": color_empty,
                "contents": [{"type": "filler"}]
            }
        ]
    }


def build_expense_card(note: str, amount: float, category: str,
                       summary: dict = None, budget_status: dict = None) -> dict:
    """Flex Bubble สำหรับบันทึกรายจ่าย"""
    body_contents = [
        {
            "type": "text",
            "text": note or "รายจ่าย",
            "size": "xl",
            "weight": "bold",
            "wrap": True,
            "color": "#222222"
        },
        {
            "type": "text",
            "text": f"{amount:,.2f} บาท",
            "size": "xxl",
            "weight": "bold",
            "color": "#E74C3C",
            "margin": "sm"
        },
        {
            "type": "text",
            "text": f"📂 {category or 'อื่นๆ'}",
            "size": "sm",
            "color": "#888888",
            "margin": "sm"
        }
    ]

    # Budget progress bar
    if budget_status and budget_status.get("budget", 0) > 0:
        budget = budget_status["budget"]
        expense = budget_status["expense"]
        remaining = budget_status["remaining"]
        pct = min((expense / budget) * 100, 100)
        bar_color = "#E74C3C" if pct >= 90 else "#F39C12" if pct >= 75 else "#27AE60"
        body_contents += [
            {"type": "separator", "margin": "md", "color": "#EEEEEE"},
            {
                "type": "text",
                "text": f"งบเดือนนี้  {pct:.1f}%",
                "size": "xs",
                "color": "#888888",
                "margin": "md"
            },
            _progress_bar(pct, bar_color),
            {
                "type": "box",
                "layout": "horizontal",
                "margin": "xs",
                "contents": [
                    {
                        "type": "text",
                        "text": f"ใช้ {expense:,.0f}",
                        "size": "xs", "color": "#888888", "flex": 1
                    },
                    {
                        "type": "text",
                        "text": f"เหลือ {remaining:,.0f}",
                        "size": "xs", "color": "#888888",
                        "align": "end", "flex": 1
                    }
                ]
            }
        ]

    # Monthly quick summary
    if summary and summary.get("success"):
        month_name = _THAI_MONTHS_SHORT.get(summary["month"], "")
        body_contents += [
            {"type": "separator", "margin": "md", "color": "#EEEEEE"},
            {
                "type": "box",
                "layout": "horizontal",
                "margin": "sm",
                "contents": [
                    {
                        "type": "text",
                        "text": f"📊 รายจ่าย {month_name}",
                        "size": "xs", "color": "#888888", "flex": 1
                    },
                    {
                        "type": "text",
                        "text": f"{summary['total_expense']:,.0f} บาท",
                        "size": "xs", "color": "#E74C3C",
                        "align": "end", "flex": 1
                    }
                ]
            }
        ]

    return {
        "type": "bubble",
        "size": "kilo",
        "header": {
            "type": "box",
            "layout": "horizontal",
            "backgroundColor": "#E74C3C",
            "paddingAll": "12px",
            "contents": [
                {
                    "type": "text",
                    "text": "💸 จดรายจ่ายแล้วครับ!",
                    "color": "#FFFFFF",
                    "weight": "bold",
                    "size": "sm"
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "16px",
            "contents": body_contents
        }
    }


def build_income_card(note: str, amount: float, summary: dict = None) -> dict:
    """Flex Bubble สำหรับบันทึกรายรับ"""
    body_contents = [
        {
            "type": "text",
            "text": note or "รายรับ",
            "size": "xl",
            "weight": "bold",
            "wrap": True,
            "color": "#222222"
        },
        {
            "type": "text",
            "text": f"+{amount:,.2f} บาท",
            "size": "xxl",
            "weight": "bold",
            "color": "#27AE60",
            "margin": "sm"
        }
    ]

    if summary and summary.get("success") and summary["total_income"] > 0:
        month_name = _THAI_MONTHS_SHORT.get(summary["month"], "")
        body_contents += [
            {"type": "separator", "margin": "md", "color": "#EEEEEE"},
            {
                "type": "box",
                "layout": "horizontal",
                "margin": "sm",
                "contents": [
                    {
                        "type": "text",
                        "text": f"💰 รายรับ {month_name}",
                        "size": "xs", "color": "#888888", "flex": 1
                    },
                    {
                        "type": "text",
                        "text": f"{summary['total_income']:,.0f} บาท",
                        "size": "xs", "color": "#27AE60",
                        "align": "end", "flex": 1
                    }
                ]
            }
        ]

    return {
        "type": "bubble",
        "size": "kilo",
        "header": {
            "type": "box",
            "layout": "horizontal",
            "backgroundColor": "#27AE60",
            "paddingAll": "12px",
            "contents": [
                {
                    "type": "text",
                    "text": "💰 เย่! บันทึกรายรับแล้วครับ",
                    "color": "#FFFFFF",
                    "weight": "bold",
                    "size": "sm"
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "16px",
            "contents": body_contents
        }
    }


def build_summary_card(summary: dict, budget_status: dict = None) -> dict:
    """Flex Bubble สำหรับสรุปรายรับรายจ่ายเดือน"""
    month_name = _THAI_MONTHS_FULL.get(summary["month"], str(summary["month"]))
    balance = summary["balance"]
    is_positive = balance >= 0

    body_contents = [
        {
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {
                    "type": "text",
                    "text": "💰 รายรับ",
                    "size": "sm", "color": "#444444", "flex": 2
                },
                {
                    "type": "text",
                    "text": f"{summary['total_income']:,.2f}",
                    "size": "sm", "color": "#27AE60",
                    "align": "end", "flex": 3
                },
                {
                    "type": "text",
                    "text": "บาท",
                    "size": "xs", "color": "#888888",
                    "align": "end", "flex": 1
                }
            ]
        },
        {
            "type": "box",
            "layout": "horizontal",
            "margin": "xs",
            "contents": [
                {
                    "type": "text",
                    "text": "💸 รายจ่าย",
                    "size": "sm", "color": "#444444", "flex": 2
                },
                {
                    "type": "text",
                    "text": f"{summary['total_expense']:,.2f}",
                    "size": "sm", "color": "#E74C3C",
                    "align": "end", "flex": 3
                },
                {
                    "type": "text",
                    "text": "บาท",
                    "size": "xs", "color": "#888888",
                    "align": "end", "flex": 1
                }
            ]
        },
        {"type": "separator", "margin": "sm", "color": "#EEEEEE"},
        {
            "type": "box",
            "layout": "horizontal",
            "margin": "sm",
            "contents": [
                {
                    "type": "text",
                    "text": "✅ คงเหลือ" if is_positive else "⚠️ ติดลบ",
                    "size": "sm", "weight": "bold",
                    "color": "#27AE60" if is_positive else "#E74C3C",
                    "flex": 2
                },
                {
                    "type": "text",
                    "text": f"{abs(balance):,.2f}",
                    "size": "sm", "weight": "bold",
                    "color": "#27AE60" if is_positive else "#E74C3C",
                    "align": "end", "flex": 3
                },
                {
                    "type": "text",
                    "text": "บาท",
                    "size": "xs", "color": "#888888",
                    "align": "end", "flex": 1
                }
            ]
        }
    ]

    # Category breakdown (top 5)
    if summary.get("expense_by_category"):
        sorted_cats = sorted(
            summary["expense_by_category"].items(), key=lambda x: -x[1]
        )[:5]
        total_exp = summary["total_expense"]
        body_contents.append({"type": "separator", "margin": "md", "color": "#EEEEEE"})
        body_contents.append({
            "type": "text",
            "text": "📂 รายจ่ายแยกหมวด",
            "size": "sm", "weight": "bold",
            "color": "#444444", "margin": "md"
        })
        for cat, amt in sorted_cats:
            pct_cat = (amt / total_exp * 100) if total_exp > 0 else 0
            body_contents.append({
                "type": "box",
                "layout": "horizontal",
                "margin": "xs",
                "contents": [
                    {"type": "text", "text": cat, "size": "xs", "color": "#666666", "flex": 3},
                    {
                        "type": "text",
                        "text": f"{amt:,.0f}",
                        "size": "xs", "color": "#E74C3C",
                        "align": "end", "flex": 2
                    },
                    {
                        "type": "text",
                        "text": f"({pct_cat:.0f}%)",
                        "size": "xs", "color": "#AAAAAA",
                        "align": "end", "flex": 1
                    }
                ]
            })

    # Budget bar
    if budget_status and budget_status.get("budget", 0) > 0:
        budget = budget_status["budget"]
        expense = budget_status["expense"]
        remaining = budget_status["remaining"]
        pct = min((expense / budget) * 100, 100)
        bar_color = "#E74C3C" if pct >= 90 else "#F39C12" if pct >= 75 else "#27AE60"
        body_contents += [
            {"type": "separator", "margin": "md", "color": "#EEEEEE"},
            {
                "type": "text",
                "text": f"💼 งบประมาณ  {pct:.1f}%",
                "size": "xs", "color": "#888888", "margin": "md"
            },
            _progress_bar(pct, bar_color),
            {
                "type": "box",
                "layout": "horizontal",
                "margin": "xs",
                "contents": [
                    {
                        "type": "text",
                        "text": f"ใช้ {expense:,.0f}",
                        "size": "xs", "color": "#888888", "flex": 1
                    },
                    {
                        "type": "text",
                        "text": f"งบ {budget:,.0f}",
                        "size": "xs", "color": "#888888",
                        "align": "end", "flex": 1
                    }
                ]
            }
        ]

    return {
        "type": "bubble",
        "size": "kilo",
        "header": {
            "type": "box",
            "layout": "horizontal",
            "backgroundColor": "#3498DB",
            "paddingAll": "12px",
            "contents": [
                {
                    "type": "text",
                    "text": f"📊 สรุป{month_name} {summary['year']}",
                    "color": "#FFFFFF",
                    "weight": "bold",
                    "size": "sm"
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "16px",
            "spacing": "none",
            "contents": body_contents
        }
    }


def build_today_card(data: dict) -> dict:
    """Flex Bubble สำหรับสรุปวันนี้"""
    balance = data["balance"]
    is_positive = balance >= 0
    date_str = data.get("date", "วันนี้")

    body_contents = [
        {
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {"type": "text", "text": "💰 รายรับ", "size": "sm", "color": "#444444", "flex": 2},
                {
                    "type": "text",
                    "text": f"{data['total_income']:,.0f}",
                    "size": "sm", "color": "#27AE60", "align": "end", "flex": 2
                },
                {"type": "text", "text": "บาท", "size": "xs", "color": "#888888", "align": "end", "flex": 1}
            ]
        },
        {
            "type": "box",
            "layout": "horizontal",
            "margin": "xs",
            "contents": [
                {"type": "text", "text": "💸 รายจ่าย", "size": "sm", "color": "#444444", "flex": 2},
                {
                    "type": "text",
                    "text": f"{data['total_expense']:,.0f}",
                    "size": "sm", "color": "#E74C3C", "align": "end", "flex": 2
                },
                {"type": "text", "text": "บาท", "size": "xs", "color": "#888888", "align": "end", "flex": 1}
            ]
        },
        {"type": "separator", "margin": "sm", "color": "#EEEEEE"},
        {
            "type": "box",
            "layout": "horizontal",
            "margin": "sm",
            "contents": [
                {
                    "type": "text",
                    "text": "✅ คงเหลือ" if is_positive else "⚠️ ติดลบ",
                    "size": "sm", "weight": "bold",
                    "color": "#27AE60" if is_positive else "#E74C3C",
                    "flex": 2
                },
                {
                    "type": "text",
                    "text": f"{abs(balance):,.0f}",
                    "size": "sm", "weight": "bold",
                    "color": "#27AE60" if is_positive else "#E74C3C",
                    "align": "end", "flex": 2
                },
                {"type": "text", "text": "บาท", "size": "xs", "color": "#888888", "align": "end", "flex": 1}
            ]
        }
    ]

    if data.get("expense_by_category"):
        body_contents.append({"type": "separator", "margin": "md", "color": "#EEEEEE"})
        body_contents.append({
            "type": "text",
            "text": "📂 แยกตามหมวด",
            "size": "xs", "weight": "bold",
            "color": "#666666", "margin": "md"
        })
        for cat, amt in sorted(data["expense_by_category"].items(), key=lambda x: -x[1]):
            body_contents.append({
                "type": "box",
                "layout": "horizontal",
                "margin": "xs",
                "contents": [
                    {"type": "text", "text": cat, "size": "xs", "color": "#666666", "flex": 3},
                    {
                        "type": "text",
                        "text": f"{amt:,.0f} บาท",
                        "size": "xs", "color": "#E74C3C",
                        "align": "end", "flex": 2
                    }
                ]
            })

    return {
        "type": "bubble",
        "size": "kilo",
        "header": {
            "type": "box",
            "layout": "horizontal",
            "backgroundColor": "#7F8C8D",
            "paddingAll": "12px",
            "contents": [
                {
                    "type": "text",
                    "text": f"📊 สรุปวันนี้  {date_str}",
                    "color": "#FFFFFF",
                    "weight": "bold",
                    "size": "sm"
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "16px",
            "spacing": "none",
            "contents": body_contents
        }
    }


def build_budget_card(status: dict) -> dict:
    """Flex Bubble สำหรับงบประมาณ"""
    budget = status["budget"]
    expense = status["expense"]
    remaining = status["remaining"]
    pct = (expense / budget * 100) if budget > 0 else 0
    bar_color = "#E74C3C" if pct >= 90 else "#F39C12" if pct >= 75 else "#3498DB"

    return {
        "type": "bubble",
        "size": "kilo",
        "header": {
            "type": "box",
            "layout": "horizontal",
            "backgroundColor": "#9B59B6",
            "paddingAll": "12px",
            "contents": [
                {
                    "type": "text",
                    "text": "💼 งบประมาณเดือนนี้",
                    "color": "#FFFFFF", "weight": "bold", "size": "sm"
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "16px",
            "contents": [
                {
                    "type": "text",
                    "text": f"{pct:.1f}%",
                    "size": "xxl", "weight": "bold",
                    "color": bar_color, "align": "center"
                },
                {
                    "type": "text",
                    "text": "ใช้ไปแล้ว",
                    "size": "xs", "color": "#888888", "align": "center"
                },
                {"type": "separator", "margin": "md", "color": "#EEEEEE"},
                _progress_bar(pct, bar_color),
                {
                    "type": "box",
                    "layout": "horizontal",
                    "margin": "xs",
                    "contents": [
                        {
                            "type": "text",
                            "text": f"ใช้ {expense:,.0f}",
                            "size": "xs", "color": "#888888", "flex": 1
                        },
                        {
                            "type": "text",
                            "text": f"งบ {budget:,.0f}",
                            "size": "xs", "color": "#888888",
                            "align": "end", "flex": 1
                        }
                    ]
                },
                {"type": "separator", "margin": "md", "color": "#EEEEEE"},
                {
                    "type": "box",
                    "layout": "horizontal",
                    "margin": "sm",
                    "contents": [
                        {
                            "type": "text",
                            "text": "✅ เหลือ" if remaining >= 0 else "⚠️ เกิน",
                            "size": "sm", "weight": "bold",
                            "color": "#27AE60" if remaining >= 0 else "#E74C3C",
                            "flex": 1
                        },
                        {
                            "type": "text",
                            "text": f"{abs(remaining):,.0f} บาท",
                            "size": "sm", "weight": "bold",
                            "color": "#27AE60" if remaining >= 0 else "#E74C3C",
                            "align": "end", "flex": 1
                        }
                    ]
                }
            ]
        }
    }


def build_savings_card(status: dict) -> dict:
    """Flex Bubble สำหรับเป้าออม"""
    goal = status["goal"]
    saved = status["saved"]
    remaining = status["remaining"]
    pct = min((saved / goal * 100) if goal > 0 else 0, 100)

    return {
        "type": "bubble",
        "size": "kilo",
        "header": {
            "type": "box",
            "layout": "horizontal",
            "backgroundColor": "#16A085",
            "paddingAll": "12px",
            "contents": [
                {
                    "type": "text",
                    "text": "🎯 เป้าหมายการออม",
                    "color": "#FFFFFF", "weight": "bold", "size": "sm"
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "16px",
            "contents": [
                {
                    "type": "text",
                    "text": f"{pct:.1f}%",
                    "size": "xxl", "weight": "bold",
                    "color": "#16A085", "align": "center"
                },
                {
                    "type": "text",
                    "text": "🎉 สำเร็จแล้ว!" if remaining <= 0 else f"ขาดอีก {remaining:,.0f} บาท",
                    "size": "xs", "color": "#888888", "align": "center"
                },
                {"type": "separator", "margin": "md", "color": "#EEEEEE"},
                _progress_bar(pct, "#16A085"),
                {
                    "type": "box",
                    "layout": "horizontal",
                    "margin": "xs",
                    "contents": [
                        {
                            "type": "text",
                            "text": f"ออมได้ {saved:,.0f}",
                            "size": "xs", "color": "#888888", "flex": 1
                        },
                        {
                            "type": "text",
                            "text": f"เป้า {goal:,.0f}",
                            "size": "xs", "color": "#888888",
                            "align": "end", "flex": 1
                        }
                    ]
                }
            ]
        }
    }


def build_task_list_card(tasks: list) -> dict:
    """Flex Bubble สำหรับ task list"""
    if not tasks:
        items = [
            {
                "type": "text",
                "text": "🎊 ไม่มี task ค้างอยู่เลยครับ!",
                "size": "sm", "color": "#27AE60",
                "align": "center", "wrap": True
            },
            {
                "type": "text",
                "text": "ว่างสบายใจ 😊",
                "size": "xs", "color": "#888888",
                "align": "center", "margin": "sm"
            }
        ]
    else:
        items = []
        for i, t in enumerate(tasks[:10], 1):
            items.append({
                "type": "box",
                "layout": "horizontal",
                "margin": "xs" if i > 1 else "none",
                "contents": [
                    {
                        "type": "text",
                        "text": "☐",
                        "size": "sm", "color": "#F39C12",
                        "flex": 0
                    },
                    {
                        "type": "text",
                        "text": t["task"],
                        "size": "sm", "color": "#333333",
                        "flex": 1, "wrap": True, "margin": "sm"
                    }
                ]
            })
        if len(tasks) > 10:
            items.append({
                "type": "text",
                "text": f"... และอีก {len(tasks) - 10} รายการ",
                "size": "xs", "color": "#AAAAAA", "margin": "sm"
            })
        items.append({"type": "separator", "margin": "md", "color": "#EEEEEE"})
        items.append({
            "type": "text",
            "text": "พิมพ์ \"เสร็จแล้ว [ชื่อ task]\" เมื่อทำเสร็จ",
            "size": "xs", "color": "#AAAAAA",
            "wrap": True, "margin": "sm"
        })

    count_label = f"  ({len(tasks)} รายการ)" if tasks else ""
    return {
        "type": "bubble",
        "size": "kilo",
        "header": {
            "type": "box",
            "layout": "horizontal",
            "backgroundColor": "#1ABC9C",
            "paddingAll": "12px",
            "contents": [
                {
                    "type": "text",
                    "text": f"📋 Task ที่ต้องทำ{count_label}",
                    "color": "#FFFFFF", "weight": "bold", "size": "sm"
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "16px",
            "contents": items
        }
    }


def build_recurring_card(items: list, payday_str: str = "", header: str = "") -> dict:
    """Flex Bubble สำหรับรายจ่ายซ้ำ — ใช้ทั้ง handle_recurring_add/list และ push notification"""
    if not items:
        body_contents = [
            {
                "type": "text",
                "text": "ยังไม่มีรายจ่ายซ้ำครับ",
                "size": "sm", "color": "#888888",
                "align": "center", "wrap": True
            },
            {
                "type": "text",
                "text": "พิมพ์ \"เพิ่มรายจ่ายซ้ำ Netflix 299 Spotify 99\" ได้เลยครับ",
                "size": "xs", "color": "#AAAAAA",
                "align": "center", "wrap": True, "margin": "sm"
            }
        ]
    else:
        total = sum(i["amount"] for i in items)
        body_contents = []
        for idx, item in enumerate(items):
            body_contents.append({
                "type": "box",
                "layout": "horizontal",
                "margin": "xs" if idx > 0 else "none",
                "contents": [
                    {
                        "type": "text",
                        "text": f"{idx + 1}. {item['name']}",
                        "size": "sm", "color": "#333333",
                        "flex": 3, "wrap": True
                    },
                    {
                        "type": "text",
                        "text": f"{item['amount']:,.0f} บาท",
                        "size": "sm", "color": "#E74C3C",
                        "align": "end", "flex": 2
                    }
                ]
            })
        body_contents.append({"type": "separator", "margin": "md", "color": "#EEEEEE"})
        body_contents.append({
            "type": "box",
            "layout": "horizontal",
            "margin": "sm",
            "contents": [
                {
                    "type": "text",
                    "text": "💸 รวมทั้งหมด",
                    "size": "sm", "weight": "bold",
                    "color": "#444444", "flex": 2
                },
                {
                    "type": "text",
                    "text": f"{total:,.0f} บาท",
                    "size": "sm", "weight": "bold",
                    "color": "#E74C3C", "align": "end", "flex": 2
                }
            ]
        })
        if payday_str:
            body_contents.append({
                "type": "text",
                "text": f"📅 จ่ายตาม: {payday_str}",
                "size": "xs", "color": "#888888",
                "margin": "sm", "wrap": True
            })

    header_text = header or "🔄 รายจ่ายประจำทุกเดือน"
    return {
        "type": "bubble",
        "size": "kilo",
        "header": {
            "type": "box",
            "layout": "horizontal",
            "backgroundColor": "#8E44AD",
            "paddingAll": "12px",
            "contents": [
                {
                    "type": "text",
                    "text": header_text,
                    "color": "#FFFFFF",
                    "weight": "bold",
                    "size": "sm",
                    "wrap": True
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "16px",
            "contents": body_contents
        }
    }


def build_bill_list_carousel(bills: list) -> dict:
    """Flex Carousel สำหรับ bill list (แต่ละบิลเป็น 1 bubble micro)"""
    if not bills:
        return {
            "type": "bubble",
            "size": "kilo",
            "body": {
                "type": "box",
                "layout": "vertical",
                "paddingAll": "20px",
                "contents": [
                    {
                        "type": "text",
                        "text": "💳 ยังไม่มีบิลประจำครับ",
                        "size": "md", "color": "#888888", "align": "center"
                    },
                    {
                        "type": "text",
                        "text": "พิมพ์ \"ตั้งบิล ค่าไฟ 800 ทุกวันที่ 20\"",
                        "size": "xs", "color": "#AAAAAA",
                        "align": "center", "wrap": True, "margin": "sm"
                    }
                ]
            }
        }

    today_day = datetime.now(pytz.timezone("Asia/Bangkok")).day
    bubbles = []

    for b in sorted(bills, key=lambda x: x["due_day"]):
        due = b["due_day"]
        days_left = due - today_day if due >= today_day else (31 - today_day + due)
        bg_color = "#E74C3C" if days_left <= 3 else "#F39C12" if days_left <= 7 else "#3498DB"
        urgency_text = "🔴 ใกล้แล้ว!" if days_left <= 3 else f"อีก {days_left} วัน"

        bubbles.append({
            "type": "bubble",
            "size": "micro",
            "header": {
                "type": "box",
                "layout": "vertical",
                "backgroundColor": bg_color,
                "paddingAll": "10px",
                "contents": [
                    {
                        "type": "text",
                        "text": f"วันที่ {due}",
                        "size": "xs", "color": "#FFFFFF",
                        "align": "center", "weight": "bold"
                    }
                ]
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "paddingAll": "12px",
                "contents": [
                    {
                        "type": "text",
                        "text": b["name"],
                        "size": "sm", "weight": "bold",
                        "color": "#222222", "wrap": True, "align": "center"
                    },
                    {
                        "type": "text",
                        "text": f"{b['amount']:,.0f}",
                        "size": "xl", "weight": "bold",
                        "color": bg_color, "align": "center", "margin": "sm"
                    },
                    {
                        "type": "text",
                        "text": "บาท",
                        "size": "xs", "color": "#888888", "align": "center"
                    },
                    {
                        "type": "text",
                        "text": urgency_text,
                        "size": "xs",
                        "color": "#E74C3C" if days_left <= 3 else "#888888",
                        "align": "center", "margin": "sm"
                    }
                ]
            }
        })

    total = sum(b["amount"] for b in bills)
    bubbles.append({
        "type": "bubble",
        "size": "micro",
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "12px",
            "justifyContent": "center",
            "contents": [
                {
                    "type": "text",
                    "text": "💸 รวมทั้งหมด",
                    "size": "xs", "color": "#888888", "align": "center"
                },
                {
                    "type": "text",
                    "text": f"{total:,.0f}",
                    "size": "xl", "weight": "bold",
                    "color": "#E74C3C", "align": "center", "margin": "sm"
                },
                {
                    "type": "text",
                    "text": "บาท/เดือน",
                    "size": "xs", "color": "#888888", "align": "center"
                },
                {
                    "type": "text",
                    "text": f"{len(bills)} รายการ",
                    "size": "xs", "color": "#AAAAAA",
                    "align": "center", "margin": "xs"
                }
            ]
        }
    })

    return {"type": "carousel", "contents": bubbles}
