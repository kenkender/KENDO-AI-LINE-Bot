from db import add_task, list_tasks, complete_task
from flex_builder import build_task_list_card


def handle_task_add(send, user_id, parsed):
    task = parsed.get("note", "").strip()
    if not task:
        send("📋 บอกด้วยนะครับว่าจะเพิ่ม task อะไร")
        return
    add_task(user_id, task)
    tasks = list_tasks(user_id)
    send(
        f"✅ เพิ่ม task แล้วครับ!\n📋 {task}\n\n"
        f"มี task ค้างอยู่ {len(tasks)} รายการ",
        quick_reply=True
    )


def handle_task_done(send, user_id, parsed):
    keyword = parsed.get("note", "").strip()
    if not keyword:
        send("✅ บอกด้วยนะครับว่า task ไหนเสร็จแล้ว")
        return
    result = complete_task(user_id, keyword)
    if result.get("success"):
        remaining = list_tasks(user_id)
        footer = "ไม่มี task ค้างแล้ว! 🎊" if not remaining else f"ยังมีอีก {len(remaining)} รายการ"
        send(
            f"🎉 เยี่ยมมาก! ทำเสร็จแล้วครับ\n✅ {result['task']}\n\n{footer}",
            quick_reply=True
        )
    elif result.get("ambiguous"):
        lines = ["🔍 เจอหลายรายการ ระบุให้ชัดขึ้นนิดนึงนะครับ:\n"]
        for t in result["ambiguous"]:
            lines.append(f"  • {t}")
        send("\n".join(lines))
    else:
        pending = result.get("pending", [])
        if pending:
            lines = [f"🔍 ไม่เจอ task \"{keyword}\" ครับ มีอยู่:\n"]
            for t in pending:
                lines.append(f"  • {t}")
            send("\n".join(lines))
        else:
            send("📭 ไม่มี task ค้างอยู่เลยครับ")


def handle_task_list(send, user_id):
    tasks = list_tasks(user_id)
    flex = build_task_list_card(tasks)
    send.flex("📋 Task ที่ต้องทำ", flex, quick_reply=True)
