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
            "bounds": {"x": 0, "y": 0, "width": 833, "height": 843},
            "action": {"type": "message", "label": "สรุปเดือนนี้", "text": "สรุปเดือนนี้"}
        },
        {
            "bounds": {"x": 833, "y": 0, "width": 834, "height": 843},
            "action": {"type": "message", "label": "บันทึกรายรับ", "text": "รายรับ"}
        },
        {
            "bounds": {"x": 1667, "y": 0, "width": 833, "height": 843},
            "action": {"type": "message", "label": "บันทึกรายจ่าย", "text": "รายจ่าย"}
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


def upload_image(rich_menu_id: str):
    """สร้างภาพ Rich Menu แบบ programmatic ด้วย Pillow"""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("กรุณาติดตั้ง Pillow: pip install Pillow")
        print(f"ข้ามการอัปโหลดภาพ — Rich Menu ID: {rich_menu_id}")
        print("คุณสามารถอัปโหลดภาพผ่าน LINE OA Manager ทีหลังได้ครับ")
        return

    W, H = 2500, 843
    img = Image.new("RGB", (W, H), color="#1A1A2E")
    draw = ImageDraw.Draw(img)

    # Grid lines
    draw.line([(833, 0), (833, H)], fill="#2D2D4E", width=4)
    draw.line([(1667, 0), (1667, H)], fill="#2D2D4E", width=4)

    panels = [
        (416, "📊", "สรุปเดือนนี้", "#4A90D9"),
        (1250, "💰", "บันทึกรายรับ", "#27AE60"),
        (2084, "💸", "บันทึกรายจ่าย", "#E74C3C"),
    ]

    try:
        font_emoji = ImageFont.truetype("seguiemj.ttf", 140)
        font_text = ImageFont.truetype("THSarabunNew Bold.ttf", 90)
    except Exception:
        font_emoji = ImageFont.load_default()
        font_text = font_emoji

    for cx, emoji, label, color in panels:
        draw.rectangle([(cx - 350, 80), (cx + 350, 500)], fill=color, outline=None)
        draw.text((cx, 200), emoji, font=font_emoji, anchor="mm", fill="white")
        draw.text((cx, 660), label, font=font_text, anchor="mm", fill="white")

    img_path = "richmenu_image.png"
    img.save(img_path)
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
