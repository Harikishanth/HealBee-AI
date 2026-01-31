"""
Supabase client and DB helpers for Phase C: auth + persistent chats/memory.
Uses SUPABASE_URL and SUPABASE_ANON_KEY from env. Graceful fallback if missing or on errors.
"""
import os
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

_supabase_client = None


def get_supabase_client():
    """Returns Supabase client or None if env not set. Cached per process."""
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY")
    if not url or not key:
        return None
    try:
        from supabase import create_client
        _supabase_client = create_client(url, key)
        return _supabase_client
    except Exception:
        return None


def is_supabase_configured() -> bool:
    return get_supabase_client() is not None


# --- Auth (email/password only) ---

def auth_sign_up(email: str, password: str) -> tuple[Optional[Dict], Optional[str]]:
    """Returns (session_dict with user_id, access_token, refresh_token, None) on success, (None, error_message) on failure."""
    sb = get_supabase_client()
    if not sb:
        return None, "Supabase is not configured."
    try:
        r = sb.auth.sign_up({"email": email, "password": password})
        if r.session and r.user:
            return {
                "user_id": str(r.user.id),
                "access_token": r.session.access_token,
                "refresh_token": getattr(r.session, "refresh_token", None) or "",
            }, None
        if r.user and not r.session:
            return None, "Check your email to confirm signup, then log in."
        return None, getattr(r, "message", None) or "Sign up failed."
    except Exception as e:
        return None, str(e)


def auth_sign_in(email: str, password: str) -> tuple[Optional[Dict], Optional[str]]:
    """Returns (session_dict with user_id, access_token, refresh_token, None) on success, (None, error_message) on failure."""
    sb = get_supabase_client()
    if not sb:
        return None, "Supabase is not configured."
    try:
        r = sb.auth.sign_in_with_password({"email": email, "password": password})
        if r.session and r.user:
            return {
                "user_id": str(r.user.id),
                "access_token": r.session.access_token,
                "refresh_token": getattr(r.session, "refresh_token", None) or "",
            }, None
        return None, getattr(r, "message", None) or "Sign in failed."
    except Exception as e:
        return None, str(e)


def auth_sign_out() -> None:
    sb = get_supabase_client()
    if sb:
        try:
            sb.auth.sign_out()
        except Exception:
            pass


def auth_get_session() -> Optional[Dict]:
    """Returns current session dict {user_id, access_token, refresh_token} or None."""
    sb = get_supabase_client()
    if not sb:
        return None
    try:
        s = sb.auth.get_session()
        if s and s.session and s.user:
            return {
                "user_id": str(s.user.id),
                "access_token": s.session.access_token,
                "refresh_token": getattr(s.session, "refresh_token", None) or "",
            }
        return None
    except Exception:
        return None


def auth_set_session_from_tokens(access_token: str, refresh_token: str) -> None:
    """Set client session so table requests use RLS for this user. Call when restoring from st.session_state."""
    sb = get_supabase_client()
    if not sb or not access_token:
        return
    try:
        sb.auth.set_session(access_token, refresh_token)
    except Exception:
        pass


# --- Chats ---

def chats_list(user_id: str) -> List[Dict[str, Any]]:
    """List chats for user, newest first. Returns [] on error."""
    sb = get_supabase_client()
    if not sb:
        return []
    try:
        r = sb.table("chats").select("id, title, created_at").eq("user_id", user_id).order("created_at", desc=True).execute()
        return [{"id": str(row["id"]), "title": row.get("title") or "Chat", "created_at": row.get("created_at")} for row in (r.data or [])]
    except Exception:
        return []


def chat_create(user_id: str, title: str) -> Optional[str]:
    """Create a chat; returns chat_id or None."""
    sb = get_supabase_client()
    if not sb:
        return None
    try:
        r = sb.table("chats").insert({"user_id": user_id, "title": title[:200]}).execute()
        if r.data and len(r.data) > 0:
            return str(r.data[0]["id"])
        return None
    except Exception:
        return None


def chat_update_title(chat_id: str, title: str) -> bool:
    try:
        sb = get_supabase_client()
        if not sb:
            return False
        sb.table("chats").update({"title": title[:200]}).eq("id", chat_id).execute()
        return True
    except Exception:
        return False


# --- Messages ---

def messages_list(chat_id: str) -> List[Dict[str, Any]]:
    """Messages for chat, order by created_at. Returns [] on error."""
    sb = get_supabase_client()
    if not sb:
        return []
    try:
        r = sb.table("messages").select("role, content, created_at").eq("chat_id", chat_id).order("created_at", desc=False).execute()
        return [{"role": row.get("role", "user"), "content": row.get("content") or "", "created_at": row.get("created_at")} for row in (r.data or [])]
    except Exception:
        return []


def message_insert(chat_id: str, role: str, content: str) -> bool:
    try:
        sb = get_supabase_client()
        if not sb:
            return False
        sb.table("messages").insert({"chat_id": chat_id, "role": role, "content": content}).execute()
        return True
    except Exception:
        return False


# --- User memory (key-value for continuity) ---

def user_memory_get_all(user_id: str) -> Dict[str, str]:
    """All keys/values for user. Returns {} on error."""
    sb = get_supabase_client()
    if not sb:
        return {}
    try:
        r = sb.table("user_memory").select("key, value").eq("user_id", user_id).execute()
        return {row["key"]: row.get("value") or "" for row in (r.data or [])}
    except Exception:
        return {}


def user_memory_upsert(user_id: str, key: str, value: str) -> bool:
    try:
        sb = get_supabase_client()
        if not sb:
            return False
        sb.table("user_memory").upsert({
            "user_id": user_id,
            "key": key,
            "value": value[:2000],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, on_conflict="user_id,key").execute()
        return True
    except Exception:
        return False


# --- User profile (persistent; one row per user) ---

def user_profile_get(user_id: str) -> Optional[Dict[str, Any]]:
    """Load user profile. Returns None or {} on error. Keys: name, age, gender, height_cm, weight_kg, medical_history, allergies, chronic_conditions, pregnancy_status, additional_notes."""
    sb = get_supabase_client()
    if not sb:
        return None
    try:
        r = sb.table("user_profile").select("*").eq("user_id", user_id).execute()
        if r.data and len(r.data) > 0:
            row = r.data[0]
            return {
                "name": row.get("name"),
                "age": row.get("age"),
                "gender": row.get("gender"),
                "height_cm": row.get("height_cm"),
                "weight_kg": row.get("weight_kg"),
                "medical_history": list(row.get("medical_history") or []),
                "allergies": list(row.get("allergies") or []),
                "chronic_conditions": list(row.get("chronic_conditions") or []),
                "pregnancy_status": row.get("pregnancy_status"),
                "additional_notes": row.get("additional_notes"),
            }
        return {}
    except Exception:
        return None


def user_profile_upsert(user_id: str, profile: Dict[str, Any]) -> bool:
    """Upsert user profile. profile: name, age, gender (male|female|other|prefer_not_to_say), height_cm, weight_kg, medical_history (list), allergies (list), chronic_conditions (list), pregnancy_status (bool|None), additional_notes."""
    sb = get_supabase_client()
    if not sb:
        return False
    try:
        payload = {
            "user_id": user_id,
            "name": (profile.get("name") or "").strip() or None,
            "age": profile.get("age"),
            "gender": profile.get("gender"),
            "height_cm": profile.get("height_cm"),
            "weight_kg": profile.get("weight_kg"),
            "medical_history": list(profile.get("medical_history") or [])[:50],
            "allergies": list(profile.get("allergies") or [])[:30],
            "chronic_conditions": list(profile.get("chronic_conditions") or [])[:30],
            "pregnancy_status": profile.get("pregnancy_status"),
            "additional_notes": (profile.get("additional_notes") or "").strip() or None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        sb.table("user_profile").upsert(payload, on_conflict="user_id").execute()
        return True
    except Exception:
        return False


def get_recent_messages_from_other_chats(user_id: str, exclude_chat_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Fetch a few recent messages from other chats for context. Returns list of {role, content}."""
    sb = get_supabase_client()
    if not sb:
        return []
    try:
        # Get other chat ids for user
        chats_r = sb.table("chats").select("id").eq("user_id", user_id).neq("id", exclude_chat_id).order("created_at", desc=True).limit(5).execute()
        chat_ids = [c["id"] for c in (chats_r.data or [])]
        if not chat_ids:
            return []
        # Get latest messages from those chats (simple: one message per chat, latest)
        out = []
        for cid in chat_ids[:3]:
            msg_r = sb.table("messages").select("role, content").eq("chat_id", cid).order("created_at", desc=True).limit(2).execute()
            for m in (msg_r.data or []):
                out.append({"role": m.get("role", "user"), "content": (m.get("content") or "")[:500]})
        return out[:limit]
    except Exception:
        return []
