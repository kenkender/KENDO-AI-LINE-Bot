from db import add_watchlist_item, list_watchlist_items, done_watchlist_item


def handle_watch_add(send, user_id, parsed):
    title = parsed.get("note", "").strip()
    category = (parsed.get("category") or "อื่นๆ").strip()
    if not title:
        send("🎬 บอกด้วยนะครับว่าอยากดูอะไร\nเช่น: \"อยากดู Dune 3\"")
        return
    add_watchlist_item(user_id, category, title)
    items = list_watchlist_items(user_id)
    send(
        f"🎬 เพิ่มใน Watchlist แล้วครับ!\n📌 {title}\n\n"
        f"มีทั้งหมด {len(items)} รายการใน watchlist",
        quick_reply=True
    )


def handle_watch_list(send, user_id):
    items = list_watchlist_items(user_id)
    if not items:
        send("🎬 Watchlist ว่างเลยครับ ยังไม่มีรายการ", quick_reply=True)
        return
    lines = [f"🎬 Watchlist ทั้งหมด {len(items)} รายการ\n"]
    cats: dict = {}
    for item in items:
        cats.setdefault(item["category"], []).append(item["title"])
    for cat, titles in cats.items():
        lines.append(f"📂 {cat}:")
        for t in titles:
            lines.append(f"  ☐ {t}")
    lines.append('\nพิมพ์ "ดูแล้ว [ชื่อ]" เมื่อดูเสร็จแล้วนะครับ')
    send("\n".join(lines), quick_reply=True)


def handle_watch_done(send, user_id, parsed):
    keyword = parsed.get("note", "").strip()
    if not keyword:
        send("✅ บอกด้วยนะครับว่าดูอะไรเสร็จแล้ว")
        return
    result = done_watchlist_item(user_id, keyword)
    if result.get("success"):
        remaining = list_watchlist_items(user_id)
        footer = "Watchlist ว่างแล้ว! 🎊" if not remaining else f"ยังมีอีก {len(remaining)} รายการ"
        send(f"✅ เยี่ยม! ดูเสร็จแล้วครับ\n🎬 {result['title']}\n\n{footer}", quick_reply=True)
    elif result.get("ambiguous"):
        lines = ["🔍 เจอหลายรายการ ระบุให้ชัดขึ้นนิดนึงนะครับ:\n"]
        for item in result["ambiguous"]:
            lines.append(f"  • {item['title']} ({item['category']})")
        send("\n".join(lines))
    else:
        send(f"🔍 ไม่เจอ \"{keyword}\" ใน Watchlist ครับ")
