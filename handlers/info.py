from news_service import get_thai_news, get_world_news, get_tech_news, search_news
from serpapi_trends_service import get_trending_now
from serpapi_search_service import smart_search
from weather_service import get_weather
from airquality_service import get_air_quality
from holiday_service import get_holidays, format_holidays_message
from oilprice_service import get_oil_prices, format_oil_price_message
from gold_service import get_gold_prices, format_gold_message
from lottery_service import get_lottery_result, format_lottery_message


def handle_news_thai(send, parsed):
    result = get_thai_news(parsed.get("news_query") or "ทั่วไป")
    send(result["message"], quick_reply=True)


def handle_news_world(send):
    send(get_world_news()["message"], quick_reply=True)


def handle_news_tech(send):
    send(get_tech_news()["message"], quick_reply=True)


def handle_news_search(send, parsed):
    query = parsed.get("news_query", "").strip()
    if not query:
        send("🔍 บอกด้วยนะครับว่าอยากค้นข่าวเรื่องอะไร\nเช่น \"ข่าวน้ำท่วม\" หรือ \"ข่าวหุ้น\"")
    else:
        send(search_news(query)["message"], quick_reply=True)


def handle_weather(send, parsed):
    province = parsed.get("note", "").strip()
    if not province:
        send(
            "🌏 บอกด้วยนะครับว่าจะดูอากาศที่จังหวัดไหน\n"
            "เช่น: \"พยากรณ์อากาศวันนี้ที่เชียงใหม่\""
        )
    else:
        send(get_weather(province)["message"], quick_reply=True)


def handle_air_quality(send, parsed):
    place = (parsed.get("note") or "กรุงเทพ").strip()
    send(get_air_quality(place)["message"], quick_reply=True)


def handle_holiday(send, parsed):
    result = get_holidays(
        year=parsed.get("holiday_year"),
        month=parsed.get("holiday_month")
    )
    send(format_holidays_message(result, near_only=bool(parsed.get("near_only", False))), quick_reply=True)


def handle_oil_price(send):
    send(format_oil_price_message(get_oil_prices()), quick_reply=True)


def handle_gold_price(send):
    send(format_gold_message(get_gold_prices()), quick_reply=True)


def handle_lottery(send):
    send(format_lottery_message(get_lottery_result()), quick_reply=True)


def handle_trends(send):
    result = get_trending_now()
    send(result["message"], quick_reply=True)


def handle_smart_search(send, parsed):
    query = (parsed.get("note") or "").strip()
    if not query:
        send(
            "🔍 บอกด้วยนะครับว่าอยากค้นหาเรื่องอะไร\n\n"
            "เช่น:\n"
            "  • \"ค้นหา วิธีต่อใบขับขี่\"\n"
            "  • \"เสิร์ช ราคาทองวันนี้\"\n"
            "  • \"หาข้อมูล สถานทูตญี่ปุ่น\""
        )
        return
    send(smart_search(query)["message"], quick_reply=True)
