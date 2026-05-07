from db import add_task, list_tasks, complete_task


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
    if not tasks:
        send("🎊 ไม่มี task ค้างอยู่เลยครับ! ว่างสบายใจ 😊", quick_reply=True)
    else:
        lines = [f"📋 Task ที่ยังค้างอยู่ {len(tasks)} รายการ\n"]
        for i, t in enumerate(tasks, 1):
            lines.append(f"  {i}. {t['task']} ({t['timestamp']})")
        lines.append("\nพิมพ์ \"เสร็จแล้ว [ชื่อ task]\" เมื่อทำเสร็จนะครับ")
        send("\n".join(lines), quick_reply=True)
