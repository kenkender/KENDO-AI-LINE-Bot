"""
weather_service.py
พยากรณ์อากาศไทย รองรับจังหวัด อำเภอ เขต และสถานที่ทั่วไป
Layer 1: ตาราง hardcode 77 จังหวัด (เร็ว)
Layer 2: Nominatim (OpenStreetMap) geocoding (รองรับทุกระดับ)
Layer 3: Open-Meteo API (ฟรี ไม่ต้อง API key)
"""

import httpx
import time
from datetime import datetime
import pytz

_cache: dict = {}
CACHE_TTL_WEATHER = 30 * 60   # อากาศ 30 นาที
CACHE_TTL_GEO     = 24 * 3600  # geocoding 24 ชั่วโมง


def _cache_get(key: str):
    e = _cache.get(key)
    if e and time.time() < e["expires_at"]:
        return e["data"]
    return None


def _cache_set(key: str, data, ttl: int = CACHE_TTL_WEATHER):
    _cache[key] = {"data": data, "expires_at": time.time() + ttl}


# ── Layer 1: ตารางพิกัด 77 จังหวัด (ค้นหาได้ทันที) ───────────────────────────
PROVINCES: dict[str, tuple[float, float]] = {
    "กรุงเทพ": (13.7563, 100.5018),
    "กรุงเทพมหานคร": (13.7563, 100.5018),
    "กทม": (13.7563, 100.5018),
    "นนทบุรี": (13.8621, 100.5144),
    "ปทุมธานี": (14.0208, 100.5250),
    "สมุทรปราการ": (13.5990, 100.5998),
    "สมุทรสาคร": (13.5472, 100.2744),
    "สมุทรสงคราม": (13.4098, 100.0023),
    "นครปฐม": (13.8199, 100.0624),
    "อ่างทอง": (14.5896, 100.4550),
    "พระนครศรีอยุธยา": (14.3532, 100.5659),
    "อยุธยา": (14.3532, 100.5659),
    "สระบุรี": (14.5289, 100.9101),
    "ลพบุรี": (14.7995, 100.6534),
    "สิงห์บุรี": (14.8936, 100.3977),
    "ชัยนาท": (15.1851, 100.1297),
    "นครสวรรค์": (15.7030, 100.1372),
    "อุทัยธานี": (15.3835, 100.0255),
    "กำแพงเพชร": (16.4827, 99.5226),
    "พิจิตร": (16.4417, 100.3487),
    "พิษณุโลก": (16.8211, 100.2659),
    "เพชรบูรณ์": (16.4189, 101.1590),
    "สุโขทัย": (17.0071, 99.8265),
    "อุตรดิตถ์": (17.6200, 100.0993),
    "แพร่": (18.1446, 100.1408),
    "น่าน": (18.7756, 100.7730),
    "พะเยา": (19.1664, 99.9044),
    "เชียงราย": (19.9105, 99.8406),
    "เชียงใหม่": (18.7883, 98.9853),
    "ลำพูน": (18.5745, 98.9868),
    "ลำปาง": (18.2888, 99.4921),
    "แม่ฮ่องสอน": (19.2989, 97.9657),
    "ตาก": (16.8798, 99.1257),
    "สุพรรณบุรี": (14.4744, 100.1177),
    "กาญจนบุรี": (14.0023, 99.5483),
    "ราชบุรี": (13.5282, 99.8134),
    "เพชรบุรี": (13.1119, 99.9390),
    "ประจวบคีรีขันธ์": (11.8126, 99.7975),
    "ชุมพร": (10.4930, 99.1800),
    "ระนอง": (9.9529, 98.6084),
    "สุราษฎร์ธานี": (9.1382, 99.3217),
    "สุราษฎร์": (9.1382, 99.3217),
    "นครศรีธรรมราช": (8.4304, 99.9633),
    "นครศรี": (8.4304, 99.9633),
    "กระบี่": (8.0863, 98.9063),
    "พังงา": (8.4509, 98.5255),
    "ภูเก็ต": (7.8804, 98.3923),
    "ตรัง": (7.5593, 99.6113),
    "พัทลุง": (7.6167, 100.0740),
    "สตูล": (6.6238, 100.0674),
    "สงขลา": (7.1756, 100.6142),
    "หาดใหญ่": (7.0086, 100.4747),
    "ปัตตานี": (6.8691, 101.2508),
    "ยะลา": (6.5412, 101.2810),
    "นราธิวาส": (6.4254, 101.8253),
    "ชลบุรี": (13.3611, 100.9847),
    "พัทยา": (12.9236, 100.8825),
    "ระยอง": (12.6814, 101.2816),
    "จันทบุรี": (12.6091, 102.1039),
    "ตราด": (12.2436, 102.5134),
    "ฉะเชิงเทรา": (13.6904, 101.0778),
    "ปราจีนบุรี": (14.0512, 101.3745),
    "สระแก้ว": (13.8235, 102.0645),
    "นครราชสีมา": (14.9799, 102.0978),
    "โคราช": (14.9799, 102.0978),
    "บุรีรัมย์": (14.9933, 103.1029),
    "สุรินทร์": (14.8819, 103.4933),
    "ศรีสะเกษ": (15.1175, 104.3220),
    "อุบลราชธานี": (15.2448, 104.8473),
    "อุบล": (15.2448, 104.8473),
    "ยโสธร": (15.7925, 104.1446),
    "อำนาจเจริญ": (15.8657, 104.6257),
    "มุกดาหาร": (16.5430, 104.7233),
    "นครพนม": (17.4077, 104.7783),
    "สกลนคร": (17.1546, 104.1348),
    "กาฬสินธุ์": (16.4314, 103.5060),
    "มหาสารคาม": (16.1851, 103.3004),
    "ร้อยเอ็ด": (16.0538, 103.6520),
    "ขอนแก่น": (16.4419, 102.8360),
    "อุดรธานี": (17.4138, 102.7870),
    "หนองบัวลำภู": (17.2060, 102.4430),
    "เลย": (17.4860, 101.7230),
    "หนองคาย": (17.8782, 102.7415),
    "บึงกาฬ": (18.3609, 103.6466),
}

WMO_CODES: dict[int, tuple[str, str]] = {
    0:  ("☀️", "ท้องฟ้าแจ่มใส"),
    1:  ("🌤", "ส่วนใหญ่แจ่มใส"),
    2:  ("⛅️", "มีเมฆบางส่วน"),
    3:  ("☁️", "เมฆมาก"),
    45: ("🌫", "มีหมอก"),
    48: ("🌫", "หมอกน้ำค้างแข็ง"),
    51: ("🌦", "ฝนปรอยเบา"),
    53: ("🌦", "ฝนปรอยปานกลาง"),
    55: ("🌧", "ฝนปรอยหนัก"),
    61: ("🌧", "ฝนเบา"),
    63: ("🌧", "ฝนปานกลาง"),
    65: ("🌧", "ฝนหนัก"),
    71: ("🌨", "หิมะเบา"),
    73: ("🌨", "หิมะปานกลาง"),
    75: ("🌨", "หิมะหนัก"),
    80: ("🌦", "ฝนตกเป็นพักๆ เบา"),
    81: ("🌦", "ฝนตกเป็นพักๆ ปานกลาง"),
    82: ("⛈", "ฝนตกหนักเป็นพักๆ"),
    95: ("⛈", "พายุฝนฟ้าคะนอง"),
    96: ("⛈", "พายุฝนฟ้าคะนองพร้อมลูกเห็บ"),
    99: ("⛈", "พายุรุนแรง"),
}


# ── Layer 1: ค้นหาจากตาราง hardcode ─────────────────────────────────────────
def _lookup_province(name: str) -> tuple[str | None, tuple | None]:
    name = name.strip()
    if name in PROVINCES:
        return name, PROVINCES[name]
    for pname, coords in PROVINCES.items():
        if name in pname or pname in name:
            return pname, coords
    return None, None


# ── Layer 2: Nominatim geocoding (รองรับอำเภอ/เขต/สถานที่) ──────────────────
def _geocode(place: str) -> tuple[str | None, tuple | None]:
    """แปลงชื่อสถานที่ → (display_name, (lat, lon)) ผ่าน Nominatim"""
    cache_key = f"geo_{place}"
    cached = _cache_get(cache_key)
    if cached:
        return cached["display"], (cached["lat"], cached["lon"])

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": place,
                    "format": "json",
                    "countrycodes": "th",
                    "limit": 1,
                    "accept-language": "th",
                },
                headers={"User-Agent": "KENDO-AI-LINE-Bot/1.0"},
            )
        if resp.status_code != 200 or not resp.json():
            return None, None

        result = resp.json()[0]
        lat = float(result["lat"])
        lon = float(result["lon"])
        display = result.get("display_name", place).split(",")[0].strip()

        _cache_set(cache_key, {"display": display, "lat": lat, "lon": lon}, ttl=CACHE_TTL_GEO)
        return display, (lat, lon)

    except Exception as e:
        print(f"[weather_service] geocode error: {e}")
        return None, None


# ── Public API ────────────────────────────────────────────────────────────────
def get_weather(place: str) -> dict:
    """ดึงพยากรณ์อากาศของสถานที่ที่ระบุ (จังหวัด/อำเภอ/เขต/สถานที่)"""
    place = place.strip()

    # Layer 1: ตาราง hardcode
    display_name, coords = _lookup_province(place)

    # Layer 2: Nominatim fallback
    if not coords:
        display_name, coords = _geocode(place)

    if not coords:
        return {
            "success": False,
            "message": (
                f"❌ ไม่พบสถานที่ \"{place}\" ครับ\n"
                "ลองพิมพ์ให้ชัดขึ้น เช่น:\n"
                "  • อำเภอบางพลี สมุทรปราการ\n"
                "  • เขตลาดกระบัง กรุงเทพ\n"
                "  • เกาะสมุย สุราษฎร์ธานี"
            ),
        }

    lat, lon = coords
    cache_key = f"weather_{round(lat,3)}_{round(lon,3)}"
    cached = _cache_get(cache_key)
    if cached:
        return _format_weather(cached, display_name or place)

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": ",".join([
                        "temperature_2m",
                        "apparent_temperature",
                        "relative_humidity_2m",
                        "precipitation_probability",
                        "weathercode",
                        "windspeed_10m",
                    ]),
                    "daily": ",".join([
                        "temperature_2m_max",
                        "temperature_2m_min",
                        "precipitation_probability_max",
                    ]),
                    "timezone": "Asia/Bangkok",
                    "forecast_days": 1,
                },
            )
        if resp.status_code != 200:
            return {"success": False, "message": "❌ ไม่สามารถดึงข้อมูลอากาศได้ครับ"}

        data = resp.json()
        _cache_set(cache_key, data, ttl=CACHE_TTL_WEATHER)
        return _format_weather(data, display_name or place)

    except Exception as e:
        print(f"[weather_service] open-meteo error: {e}")
        return {"success": False, "message": "❌ ดึงข้อมูลพยากรณ์อากาศไม่ได้ครับ ลองใหม่อีกทีนะครับ"}


def _format_weather(data: dict, place: str) -> dict:
    cur   = data.get("current", {})
    daily = data.get("daily", {})

    temp       = cur.get("temperature_2m")
    feels_like = cur.get("apparent_temperature")
    humidity   = cur.get("relative_humidity_2m")
    wcode      = cur.get("weathercode", 0)
    wind       = cur.get("windspeed_10m")

    temp_max = (daily.get("temperature_2m_max") or [None])[0]
    temp_min = (daily.get("temperature_2m_min") or [None])[0]
    rain_max = (daily.get("precipitation_probability_max") or [0])[0]

    emoji, desc = WMO_CODES.get(wcode, ("🌡", "ไม่ทราบสภาพอากาศ"))

    bkk_tz = pytz.timezone("Asia/Bangkok")
    now_str = datetime.now(bkk_tz).strftime("%H:%M น.")

    lines = [
        f"🌏 พยากรณ์อากาศ {place}",
        f"🕐 ข้อมูล ณ {now_str}\n",
        f"{emoji} สภาพอากาศ: {desc}",
        f"🌡 อุณหภูมิ: {temp:.1f}°C",
        f"🥵 ความรู้สึก (ดัชนีความร้อน): {feels_like:.1f}°C",
    ]

    if temp_max is not None and temp_min is not None:
        lines.append(f"🔺 สูงสุด {temp_max:.1f}°C  🔻 ต่ำสุด {temp_min:.1f}°C")

    lines += [
        f"💧 ความชื้นสัมพัทธ์: {humidity}%",
        f"🌧 โอกาสฝนตก: {rain_max}%",
        f"💨 ความเร็วลม: {wind:.1f} km/h",
    ]

    tips = []
    if rain_max >= 70:
        tips.append("☂️ ฝนตกหนัก พกร่มด้วยนะครับ!")
    elif rain_max >= 40:
        tips.append("🌂 มีโอกาสฝน เตรียมร่มไว้หน่อยนะครับ")
    if feels_like is not None and feels_like >= 35:
        tips.append("🥵 อากาศร้อนมาก ดื่มน้ำบ่อยๆ นะครับ")
    if tips:
        lines.append("")
        lines += tips

    return {"success": True, "message": "\n".join(lines)}


if __name__ == "__main__":
    tests = [
        "สมุทรปราการ",          # hardcode
        "อำเภอบางพลี สมุทรปราการ",  # geocoding อำเภอ
        "เขตลาดกระบัง",         # geocoding เขต กทม
        "เกาะสมุย",             # geocoding สถานที่ท่องเที่ยว
    ]
    for t in tests:
        r = get_weather(t)
        print(f"\n=== {t} ===")
        print("success:", r["success"])
