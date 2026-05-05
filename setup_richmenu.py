"""
setup_richmenu.py
รัน script นี้ครั้งเดียวเพื่อสร้าง Rich Menu ให้บอท LINE
"""

import httpx
import json
import os
from dotenv import load_dotenv

load_dotenv()

ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
HEADERS = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

RICH_MENU = {
    "size": {"width": 2500, "height": 843},
    "selected": True,
    "name": "KENDO AI Menu",
    "chatBarText": "เมนูหลัก 📋",
    "areas": [
        {
            "bounds": {"x": 0, "y": 0, "width": 625, "height": 843},
            "action": {"type": "message", "label": "สรุปเดือนนี้", "text": "สรุปเดือนนี้"}
        },
        {
            "bounds": {"x": 625, "y": 0, "width": 625, "height": 843},
            "action": {"type": "message", "label": "บันทึกรายรับ", "text": "รายรับ"}
        },
        {
            "bounds": {"x": 1250, "y": 0, "width": 625, "height": 843},
            "action": {"type": "message", "label": "บันทึกรายจ่าย", "text": "รายจ่าย"}
        },
        {
            "bounds": {"x": 1875, "y": 0, "width": 625, "height": 843},
            "action": {"type": "message", "label": "บันทึกโน้ต/เตือน", "text": "โน้ต"}
        }
    ]
}

def create_rich_menu():
    resp = httpx.post(
        "https://api.line.me/v2/bot/richmenu",
        headers=HEADERS,
        json=RICH_MENU
    )
    print(f"Create: {resp.status_code} — {resp.text}")
    if resp.status_code != 200:
        return None
    return resp.json().get("richMenuId")


def hex_to_rgb(hex_color: str):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def draw_icon(draw, cx: int, cy: int, icon_type: str, color: tuple, size: int = 85):
    """วาด icon แบบ geometric แทน emoji"""
    if icon_type == "chart":
        bars = [
            (cx - 80, cy - 70, cx - 35, cy + 55),
            (cx - 15, cy - 15, cx + 30, cy + 55),
            (cx + 45, cy - 95, cx + 90, cy + 55),
        ]
        for bx1, by1, bx2, by2 in bars:
            draw.rectangle([bx1, by1, bx2, by2], fill=color)
        draw.line([(cx - 95, cy + 55), (cx + 95, cy + 55)], fill=color, width=7)
    elif icon_type == "plus":
        r = size
        draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], outline=color, width=9)
        draw.line([(cx, cy - 60), (cx, cy + 60)], fill=color, width=12)
        draw.line([(cx - 60, cy), (cx + 60, cy)], fill=color, width=12)
    elif icon_type == "minus":
        r = size
        draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], outline=color, width=9)
        draw.line([(cx - 60, cy), (cx + 60, cy)], fill=color, width=12)
        draw.line([(cx - 38, cy - 38), (cx + 38, cy - 38)], fill=color, width=7)
    elif icon_type == "note":
        draw.rectangle([(cx - 70, cy - 90), (cx + 80, cy + 90)], outline=color, width=7)
        draw.polygon([(cx + 80, cy - 90), (cx + 80, cy - 45), (cx + 35, cy - 90)], fill=color)
        for y_off in [-35, 5, 45]:
            draw.line([(cx - 48, cy + y_off), (cx + 52, cy + y_off)], fill=color, width=7)


def upload_image(rich_menu_id: str):
    """สร้างภาพ Rich Menu แบบ programmatic ด้วย Pillow"""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("กรุณาติดตั้ง Pillow: pip install Pillow")
        print(f"ข้ามการอัปโหลดภาพ — Rich Menu ID: {rich_menu_id}")
        return

    FONT_DIR = r"C:/Windows/Fonts"

    def load_font(size: int):
        for name in ["leelawdb.ttf", "leelawad.ttf", "LeelawUI.ttf", "arial.ttf"]:
            try:
                return ImageFont.truetype(f"{FONT_DIR}/{name}", size)
            except Exception:
                continue
        return ImageFont.load_default()

    W, H = 2500, 843
    # 4 panels — แต่ละช่องกว้าง 625px, center ที่ 312, 937, 1562, 2187
    panels = [
        (312,  "chart", "สรุปเดือนนี้",   "#4A90D9"),
        (937,  "plus",  "บันทึกรายรับ",   "#27AE60"),
        (1562, "minus", "บันทึกรายจ่าย",  "#E74C3C"),
        (2187, "note",  "โน้ต & เตือน",   "#F0A500"),
    ]

    img = Image.new("RGB", (W, H), color="#0D1117")
    draw = ImageDraw.Draw(img)

    # Dividers ระหว่าง 4 panels
    for x in [625, 1250, 1875]:
        draw.line([(x, 20), (x, H - 20)], fill="#30363D", width=3)

    font_label = load_font(76)
    font_sub = load_font(48)

    for cx, icon_type, label, color_hex in panels:
        rgb = hex_to_rgb(color_hex)
        draw.rectangle([(cx - 312, 0), (cx + 313, 8)], fill=rgb)
        draw.ellipse([(cx - 130, 165), (cx + 130, 425)], outline=rgb, width=4)
        draw_icon(draw, cx, 295, icon_type, rgb, size=85)
        draw.text((cx, 570), label, font=font_label, anchor="mm", fill="white")
        draw.text((cx, 700), "แตะเพื่อเลือก", font=font_sub, anchor="mm", fill="#8B949E")

    img_path = "richmenu_image.png"
    img.save(img_path, "PNG")
    print(f"สร้างภาพ Rich Menu แล้ว: {img_path}")

    with open(img_path, "rb") as f:
        resp = httpx.post(
            f"https://api-data.line.me/v2/bot/richmenu/{rich_menu_id}/content",
            headers={
                "Authorization": f"Bearer {ACCESS_TOKEN}",
                "Content-Type": "image/png"
            },
            content=f.read()
        )
    print(f"Upload image: {resp.status_code} — {resp.text}")


def set_default(rich_menu_id: str):
    resp = httpx.post(
        f"https://api.line.me/v2/bot/user/all/richmenu/{rich_menu_id}",
        headers=HEADERS
    )
    print(f"Set default: {resp.status_code} — {resp.text}")


def list_existing():
    resp = httpx.get("https://api.line.me/v2/bot/richmenu/list", headers=HEADERS)
    print(f"Existing menus: {resp.text}")


def delete_all():
    resp = httpx.get("https://api.line.me/v2/bot/richmenu/list", headers=HEADERS)
    menus = resp.json().get("richmenus", [])
    for m in menus:
        mid = m["richMenuId"]
        d = httpx.delete(f"https://api.line.me/v2/bot/richmenu/{mid}", headers=HEADERS)
        print(f"Deleted {mid}: {d.status_code}")


if __name__ == "__main__":
    print("=== KENDO AI Rich Menu Setup ===\n")

    print("1. ตรวจสอบเมนูที่มีอยู่...")
    list_existing()

    print("\n2. ลบเมนูเก่า (ถ้ามี)...")
    delete_all()

    print("\n3. สร้าง Rich Menu ใหม่...")
    menu_id = create_rich_menu()
    if not menu_id:
        print("❌ สร้างไม่ได้ ตรวจสอบ LINE_CHANNEL_ACCESS_TOKEN ใน .env")
        exit(1)

    print(f"\n✅ Rich Menu ID: {menu_id}")

    print("\n4. อัปโหลดภาพ...")
    upload_image(menu_id)

    print("\n5. ตั้งเป็น default menu...")
    set_default(menu_id)

    print(f"\n🎉 เสร็จแล้ว! Rich Menu ID: {menu_id}")
    print("เปิด LINE แล้วลองกดที่ chat บอทได้เลยครับ")
