"""
db_supabase/watchlist.py — หนัง/เกม/เพลง/หนังสือ
"""
from db_supabase.client import get_supabase
from db_supabase.users import get_user_id, get_or_create_user


def add_watchlist_item(line_user_id: str, category: str, title: str) -> bool:
    try:
        user_id = get_or_create_user(line_user_id)
        if not user_id:
            return False
        sb = get_supabase()
        sb.table("watchlist").insert({
            "user_id": user_id,
            "category": category or "อื่นๆ",
            "title": title,
            "status": "PENDING",
        }).execute()
        return True
    except Exception as e:
        print(f"[db_supabase.watchlist] add error: {e}")
        return False


def list_watchlist_items(line_user_id: str) -> list:
    try:
        user_id = get_user_id(line_user_id)
        if not user_id:
            return []
        sb = get_supabase()
        result = sb.table("watchlist").select("id,category,title") \
            .eq("user_id", user_id).eq("status", "PENDING") \
            .order("ts").execute()
        return [
            {
                "row_index": r["id"],
                "category": r.get("category", "อื่นๆ"),
                "title": r.get("title", ""),
            }
            for r in (result.data or [])
        ]
    except Exception as e:
        print(f"[db_supabase.watchlist] list error: {e}")
        return []


def done_watchlist_item(line_user_id: str, keyword: str) -> dict:
    try:
        user_id = get_user_id(line_user_id)
        if not user_id:
            return {"success": False}

        sb = get_supabase()
        kw = (keyword or "").lower()
        result = sb.table("watchlist").select("id,title,category") \
            .eq("user_id", user_id).eq("status", "PENDING") \
            .ilike("title", f"%{kw}%").execute()
        matched = result.data or []
        if not matched:
            return {"success": False}
        if len(matched) == 1:
            sb.table("watchlist").update({"status": "DONE"}).eq("id", matched[0]["id"]).execute()
            return {
                "success": True,
                "title": matched[0].get("title", ""),
                "category": matched[0].get("category", ""),
            }
        return {
            "success": False,
            "ambiguous": [
                {"title": r.get("title"), "category": r.get("category")}
                for r in matched
            ],
        }
    except Exception as e:
        print(f"[db_supabase.watchlist] done error: {e}")
        return {"success": False}
