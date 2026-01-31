import streamlit as st
import streamlit.components.v1 as components
import os
import json
import time # For polling audio capture status
import numpy as np # For checking audio data (though not directly used in this version)
from dotenv import load_dotenv
from typing import Optional
import re
from streamlit_mic_recorder import mic_recorder
import soundfile as sf
import io
from datetime import datetime, timedelta
# Firebase removed: HealBee uses Supabase only for auth and persistence.
# Feedback buttons still render; feedback is acknowledged but not persisted.

# Adjust import paths
try:
    from src.nlu_processor import SarvamMNLUProcessor, HealthIntent, NLUResult
    from src.response_generator import HealBeeResponseGenerator
    from src.symptom_checker import SymptomChecker
    from src.audio_capture import AudioCleaner
    from src.utils import HealBeeUtilities, get_relevant_journal_entries
    try:
        from src.utils import detect_and_extract_reminder, detect_and_extract_journal, detect_nearby_places_request, extract_nearby_location
    except ImportError:
        detect_and_extract_reminder = lambda msg: None  # fallback if utils.py is older
        detect_and_extract_journal = lambda msg: None
        detect_nearby_places_request = lambda msg: False
        extract_nearby_location = lambda msg: None
    from src.supabase_client import (
        is_supabase_configured,
        auth_sign_in,
        auth_sign_up,
        auth_sign_out,
        auth_set_session_from_tokens,
        chats_list,
        chat_create,
        messages_list,
        message_insert,
        user_memory_get_all,
        user_memory_upsert,
        get_recent_messages_from_other_chats,
        user_profile_get,
        user_profile_upsert,
        reminders_list as db_reminders_list,
        reminder_insert as db_reminder_insert,
        reminder_update as db_reminder_update,
        reminder_delete as db_reminder_delete,
        journal_entries_list as db_journal_entries_list,
        journal_entry_insert as db_journal_entry_insert,
        journal_entry_delete as db_journal_entry_delete,
    )
    try:
        from src.nominatim_places import search_nearby_health_places, make_osm_link, search_nearby_by_gps, get_condition_hints_from_symptoms
    except ImportError:
        search_nearby_health_places = lambda loc, limit=8: []
        make_osm_link = lambda lat, lon: ""
        search_nearby_by_gps = lambda lat, lon, **kw: []
        get_condition_hints_from_symptoms = lambda s: ["hospital", "clinic"]
except ImportError:
    import sys
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
    from src.nlu_processor import SarvamMNLUProcessor, HealthIntent, NLUResult
    from src.response_generator import HealBeeResponseGenerator
    from src.symptom_checker import SymptomChecker
    from src.audio_capture import AudioCleaner
    from src.utils import HealBeeUtilities, get_relevant_journal_entries
    try:
        from src.utils import detect_and_extract_reminder, detect_and_extract_journal, detect_nearby_places_request, extract_nearby_location
    except ImportError:
        detect_and_extract_reminder = lambda msg: None  # fallback if utils.py is older
        detect_and_extract_journal = lambda msg: None
        detect_nearby_places_request = lambda msg: False
        extract_nearby_location = lambda msg: None
    try:
        from src.supabase_client import (
            is_supabase_configured,
            auth_sign_in,
            auth_sign_up,
            auth_sign_out,
            auth_set_session_from_tokens,
            chats_list,
            chat_create,
            messages_list,
            message_insert,
            user_memory_get_all,
            user_memory_upsert,
            get_recent_messages_from_other_chats,
            user_profile_get,
            user_profile_upsert,
            reminders_list as db_reminders_list,
            reminder_insert as db_reminder_insert,
            reminder_update as db_reminder_update,
            reminder_delete as db_reminder_delete,
            journal_entries_list as db_journal_entries_list,
            journal_entry_insert as db_journal_entry_insert,
            journal_entry_delete as db_journal_entry_delete,
        )
    except ImportError:
        is_supabase_configured = lambda: False
        auth_sign_in = lambda e, p: (None, "Not configured")
        auth_sign_up = lambda e, p: (None, "Not configured")
        auth_sign_out = lambda: None
        auth_set_session_from_tokens = lambda a, r: None
        chats_list = lambda uid: []
        chat_create = lambda uid, t: None
        messages_list = lambda cid: []
        message_insert = lambda cid, role, content: False
        user_memory_get_all = lambda uid: {}
        user_memory_upsert = lambda uid, k, v: False
        get_recent_messages_from_other_chats = lambda uid, cid, limit=10: []
        user_profile_get = lambda uid: None
        user_profile_upsert = lambda uid, p: False
        db_reminders_list = lambda uid: []
        db_reminder_insert = lambda uid, title, when_iso, note="", done=False: None
        db_reminder_update = lambda uid, rid, **kw: False
        db_reminder_delete = lambda uid, rid: False
        db_journal_entries_list = lambda uid: []
        db_journal_entry_insert = lambda uid, entry: None
        db_journal_entry_delete = lambda uid, eid: False
    try:
        from src.nominatim_places import search_nearby_health_places, make_osm_link, search_nearby_by_gps, get_condition_hints_from_symptoms
    except ImportError:
        search_nearby_health_places = lambda loc, limit=8: []
        make_osm_link = lambda lat, lon: ""
        search_nearby_by_gps = lambda lat, lon, **kw: []
        get_condition_hints_from_symptoms = lambda s: ["hospital", "clinic"]

# --- Environment and API Key Setup ---
# Priority: 1) .env (os.environ), 2) Streamlit Cloud secrets (st.secrets). No .streamlit/secrets.toml required locally.
load_dotenv()

def _get_secret(name: str) -> str:
    """Read secret from env first, then from st.secrets (Streamlit Cloud). Safe if st.secrets missing or raises."""
    v = (os.environ.get(name) or "").strip()
    if not v:
        try:
            if hasattr(st, "secrets") and st.secrets:
                v = (st.secrets.get(name) or "").strip()
        except Exception:
            pass
    return v or ""

# Populate env from st.secrets so Supabase client and others see them when deployed on Streamlit Cloud
try:
    for _k in ("SARVAM_API_KEY", "SUPABASE_URL", "SUPABASE_ANON_KEY"):
        _v = _get_secret(_k)
        if _v:
            os.environ[_k] = _v
except Exception:
    pass

try:
    SARVAM_API_KEY = _get_secret("SARVAM_API_KEY")
except Exception:
    SARVAM_API_KEY = ""

# --- Session State Initialization ---
if 'conversation' not in st.session_state:
    st.session_state.conversation = []
if 'current_language_display' not in st.session_state: 
    st.session_state.current_language_display = 'English'
if 'current_language_code' not in st.session_state: 
    st.session_state.current_language_code = 'en-IN'
if 'text_query_input_area' not in st.session_state:
    st.session_state.text_query_input_area = ""

# Symptom Checker states
if 'symptom_checker_active' not in st.session_state:
    st.session_state.symptom_checker_active = False
if 'symptom_checker_instance' not in st.session_state:
    st.session_state.symptom_checker_instance = None
if 'pending_symptom_question_data' not in st.session_state:
    st.session_state.pending_symptom_question_data = None

# Voice Input states
if 'voice_input_stage' not in st.session_state:
    # Stages: None, "arming", "recording", "transcribing", "processing_stt"
    st.session_state.voice_input_stage = None 
if 'audio_capturer' not in st.session_state: 
    st.session_state.audio_capturer = None
if 'captured_audio_data' not in st.session_state:
    st.session_state.captured_audio_data = None
if 'cleaned_audio_data' not in st.session_state:
    st.session_state.cleaned_audio_data = None
if "captured_audio_sample_rate" not in st.session_state:
    st.session_state.captured_audio_sample_rate = 48000

# --- Session memory (Phase A: stateful; resets on page refresh; cleared on language change) ---
# Conversation history: st.session_state.conversation (above)
# Extracted symptoms: NLU + symptom checker; used for continuity in responses
# Follow-up answers: Q&A from symptom flow; used for "last time you mentioned..."
# Last advice given: last assistant health response; used for follow-up context
if "extracted_symptoms" not in st.session_state:
    st.session_state.extracted_symptoms = []
if "follow_up_answers" not in st.session_state:
    st.session_state.follow_up_answers = []
if "last_advice_given" not in st.session_state:
    st.session_state.last_advice_given = ""

# --- User profile (Phase A.1: session-only; no DB/auth/files/env) ---
if "user_profile" not in st.session_state:
    st.session_state.user_profile = {}

# --- Phase C: Auth + persistent chats/memory (Supabase only; fallback to session-only if not configured) ---
if "supabase_session" not in st.session_state:
    st.session_state.supabase_session = None  # {user_id, access_token, refresh_token} or None
if "chat_list" not in st.session_state:
    st.session_state.chat_list = []
if "current_chat_id" not in st.session_state:
    st.session_state.current_chat_id = None
if "persistent_memory" not in st.session_state:
    st.session_state.persistent_memory = {}  # key -> value from user_memory table

# --- App UI navigation and UI language (separate from chatbot language) ---
# Default to chat (no separate Home page; 5 tabs: Chatbot, Maps, Journal, Reminders, Settings)
if "active_page" not in st.session_state:
    st.session_state.active_page = "chat"
# --- Journal: session-only notes (no DB) ---
if "journal_entries" not in st.session_state:
    st.session_state.journal_entries = []
# --- Reminders: session-only (no DB); list of {id, title, when_iso, note, done} ---
if "reminders" not in st.session_state:
    st.session_state.reminders = []
if "reminders_show_add" not in st.session_state:
    st.session_state.reminders_show_add = False
if "app_language" not in st.session_state:
    st.session_state.app_language = "en"

# --- UI copy by language (navbar, page titles, buttons; does NOT translate chat) ---
UI_TEXT = {
    "en": {
        "home": "Home",
        "chatbot": "Chatbot",
        "maps": "Maps",
        "journal": "Journal",
        "settings": "Settings",
        "tagline": "Your health companion",
        "welcome": "Welcome to HealBee",
        "add_note": "Add New Note",
        "save": "Save",
        "empty_notes": "No notes yet. Add one below.",
        "logout": "Logout",
        "confirm_logout": "Are you sure you want to log out?",
        "yes_logout": "Yes, log out",
        "cancel": "Cancel",
        "clear_session": "Clear session data",
        "settings_caption": "App language affects labels and navigation only. Chatbot language is set separately.",
        "chat_title": "Chat with HealBee",
        "chat_caption": "Ask about symptoms, wellness, or general health. For emergencies, please contact a doctor or hospital.",
        "journal_title": "Health Journal",
        "journal_desc": "Your health notes and summaries. Saved to your account when signed in.",
        "journal_empty": "Your health notes and summaries will appear here.",
        "settings_title": "Settings",
        "app_language_label": "App language",
        "maps_title": "Find nearby hospitals / clinics",
        "maps_caption": "Enter your city or locality. Results from OpenStreetMap.",
        "maps_search_placeholder": "e.g. Mumbai, Connaught Place Delhi",
        "search": "Search",
        "open_map": "Open Map",
        "results_for": "Results for",
        "no_results": "No results found for that area. Try another city or locality.",
        "your_chats": "Your Chats",
        "chat_language_label": "Chat language",
        "note_title": "Title",
        "settings_caption_short": "This changes app labels only. Chat language is controlled in Chatbot.",
        "reminders": "Reminders",
        "reminders_title": "Health reminders",
        "reminders_desc": "Medicine, check-ups, or anything you want to be reminded about. Saved to your account when signed in.",
        "add_reminder": "Add reminder",
        "reminder_title": "What to remember",
        "reminder_datetime": "Date & time",
        "reminder_note": "Note (optional)",
        "empty_reminders": "No reminders yet. Add one below.",
        "delete": "Delete",
        "mark_done": "Done",
        "overdue": "overdue",
        "journal_from_chat": "From chat",
    },
    "ta": {
        "home": "முகப்பு",
        "chatbot": "சாட்போட்",
        "maps": "வரைபடம்",
        "journal": "பத்திரிக்கை",
        "settings": "அமைப்புகள்",
        "tagline": "உங்கள் சுகாதார துணை",
        "welcome": "HealBee-க்கு வரவேற்கிறோம்",
        "add_note": "புதிய குறிப்பு சேர்",
        "save": "சேமி",
        "empty_notes": "இன்னும் குறிப்புகள் இல்லை. கீழே ஒன்றைச் சேர்க்கவும்.",
        "logout": "வெளியேறு",
        "confirm_logout": "வெளியேற உறுதியாக உள்ளீர்களா?",
        "yes_logout": "ஆம், வெளியேறு",
        "cancel": "ரத்து",
        "clear_session": "அமர்வு தரவை அழி",
        "settings_caption": "பயன்பாட்டு மொழி லேபிள்கள் மற்றும் செல்லுதலை மட்டுமே பாதிக்கிறது. சாட்போட் மொழி தனித்து அமைக்கப்படுகிறது.",
        "chat_title": "HealBee உடன் அரட்டை",
        "chat_caption": "அறிகுறிகள், நலம் அல்லது பொதுச் சுகாதாரம் பற்றி கேளுங்கள். அவசர நிலையில், மருத்துவர் அல்லது மருத்துவமனையைத் தொடர்பு கொள்ளுங்கள்.",
        "journal_title": "சுகாதார பத்திரிக்கை",
        "journal_desc": "உங்கள் சுகாதார குறிப்புகள் இங்கே தோன்றும்.",
        "journal_empty": "உங்கள் சுகாதார குறிப்புகள் மற்றும் சுருக்கங்கள் இங்கே தோன்றும்.",
        "settings_title": "அமைப்புகள்",
        "app_language_label": "பயன்பாட்டு மொழி",
        "maps_title": "அருகிலுள்ள மருத்துவமனைகள் / மருத்துவமனைகளைக் கண்டறியுங்கள்",
        "maps_caption": "உங்கள் நகரம் அல்லது பகுதியை உள்ளிடுங்கள். OpenStreetMap முடிவுகள்.",
        "maps_search_placeholder": "எ.கா. மும்பை",
        "search": "தேடு",
        "open_map": "வரைபடத்தைத் திற",
        "results_for": "முடிவுகள்",
        "no_results": "அந்த பகுதிக்கு முடிவுகள் இல்லை. மற்றொரு நகரத்தை முயற்சிக்கவும்.",
        "reminders": "நினைவூட்டல்கள்",
        "reminders_title": "சுகாதார நினைவூட்டல்கள்",
        "reminders_desc": "மருந்து, பரிசோதனை அல்லது நினைவில் வைக்க விரும்பும் எதையும். இந்த அமர்வில் மட்டுமே காட்டப்படும்.",
        "add_reminder": "நினைவூட்டல் சேர்",
        "reminder_title": "எதை நினைவில் வைக்க",
        "reminder_datetime": "தேதி மற்றும் நேரம்",
        "reminder_note": "குறிப்பு (விரும்பினால்)",
        "empty_reminders": "இன்னும் நினைவூட்டல்கள் இல்லை. கீழே ஒன்றைச் சேர்க்கவும்.",
        "delete": "அழி",
        "mark_done": "முடிந்தது",
        "overdue": "காலம் கடந்தது",
        "journal_from_chat": "சாட்போடிலிருந்து",
    },
    "ml": {
        "home": "ഹോം",
        "chatbot": "ചാറ്റ്ബോട്ട്",
        "maps": "മാപ്പുകൾ",
        "journal": "ജേണൽ",
        "settings": "ക്രമീകരണങ്ങൾ",
        "tagline": "നിങ്ങളുടെ ആരോഗ്യ കൂട്ടാളി",
        "welcome": "HealBee-യിലേക്ക് സ്വാഗതം",
        "add_note": "പുതിയ നോട്ട് ചേർക്കുക",
        "save": "സംരക്ഷിക്കുക",
        "empty_notes": "ഇതുവരെ നോട്ടുകളില്ല. താഴെ ഒന്ന് ചേർക്കുക.",
        "logout": "ലോഗൗട്ട്",
        "confirm_logout": "ലോഗൗട്ട് ചെയ്യാൻ ഉറപ്പാണോ?",
        "yes_logout": "അതെ, ലോഗൗട്ട്",
        "cancel": "റദ്ദാക്കുക",
        "clear_session": "സെഷൻ ഡാറ്റ മായ്ക്കുക",
        "settings_caption": "ആപ്പ് ഭാഷ ലേബലുകളെയും നാവിഗേഷനെയും മാത്രം ബാധിക്കുന്നു. ചാറ്റ്ബോട്ട് ഭാഷ വെവ്വേറെ സജ്ജമാക്കുന്നു.",
        "chat_title": "HealBee ഉപയോഗിച്ച് ചാറ്റ്",
        "chat_caption": "ലക്ഷണങ്ങൾ, ആരോഗ്യം അല്ലെങ്കിൽ പൊതുആരോഗ്യം സംബന്ധിച്ച് ചോദിക്കുക. അടിയന്തിര സാഹചര്യത്തിൽ ഡോക്ടറെയോ ആശുപത്രിയെയോ ബന്ധപ്പെടുക.",
        "journal_title": "ആരോഗ്യ ജേണൽ",
        "journal_desc": "നിങ്ങളുടെ ആരോഗ്യ കുറിപ്പുകൾ ഇവിടെ ദൃശ്യമാകും.",
        "journal_empty": "നിങ്ങളുടെ ആരോഗ്യ കുറിപ്പുകളും സംഗ്രഹങ്ങളും ഇവിടെ ദൃശ്യമാകും.",
        "settings_title": "ക്രമീകരണങ്ങൾ",
        "app_language_label": "ആപ്പ് ഭാഷ",
        "maps_title": "അടുത്തുള്ള ആശുപത്രികൾ / ക്ലിനിക്കുകൾ കണ്ടെത്തുക",
        "maps_caption": "നിങ്ങളുടെ നഗരം അല്ലെങ്കിൽ പ്രദേശം നൽകുക. OpenStreetMap ഫലങ്ങൾ.",
        "maps_search_placeholder": "ഉദാ. മുംബൈ",
        "search": "തിരയുക",
        "open_map": "മാപ്പ് തുറക്കുക",
        "results_for": "ഫലങ്ങൾ",
        "no_results": "ആ പ്രദേശത്ത് ഫലങ്ങൾ കണ്ടെത്തിയില്ല. മറ്റൊരു നഗരം ശ്രമിക്കുക.",
        "reminders": "ഓർമ്മപ്പെടുത്തലുകൾ",
        "reminders_title": "ആരോഗ്യ ഓർമ്മപ്പെടുത്തലുകൾ",
        "reminders_desc": "മരുന്ന്, പരിശോധന അല്ലെങ്കിൽ ഓർക്കാൻ ആഗ്രഹിക്കുന്നത്. ഈ സെഷനിൽ മാത്രം കാണിക്കും.",
        "add_reminder": "ഓർമ്മപ്പെടുത്തൽ ചേർക്കുക",
        "reminder_title": "എന്ത് ഓർക്കണം",
        "reminder_datetime": "തീയതി സമയം",
        "reminder_note": "കുറിപ്പ് (ഓപ്ഷണൽ)",
        "empty_reminders": "ഇതുവരെ ഓർമ്മപ്പെടുത്തലുകളില്ല. താഴെ ഒന്ന് ചേർക്കുക.",
        "delete": "ഇല്ലാതാക്കുക",
        "mark_done": "പൂർത്തി",
        "overdue": "കാലഹരണപ്പെട്ടത്",
        "journal_from_chat": "ചാറ്റിൽ നിന്ന്",
    },
    "te": {
        "home": "హోమ్",
        "chatbot": "చాట్‌బాట్",
        "maps": "మ్యాప్‌లు",
        "journal": "జర్నల్",
        "settings": "సెట్టింగ్‌లు",
        "tagline": "మీ ఆరోగ్య సహచరుడు",
        "welcome": "HealBee కు స్వాగతం",
        "add_note": "కొత్త నోట్ జోడించండి",
        "save": "సేవ్",
        "empty_notes": "ఇంకా నోట్లు లేవు. క్రింద ఒకటి జోడించండి.",
        "logout": "లాగౌట్",
        "confirm_logout": "లాగౌట్ చేయాలని ఖచ్చితంగా ఉన్నారా?",
        "yes_logout": "అవును, లాగౌట్",
        "cancel": "రద్దు",
        "clear_session": "సెషన్ డేటా క్లియర్ చేయండి",
        "settings_caption": "యాప్ భాష లేబుల్స్ మరియు నావిగేషన్‌ను మాత్రమే ప్రభావితం చేస్తుంది. చాట్‌బాట్ భాష వేరుగా సెట్ చేయబడుతుంది.",
        "chat_title": "HealBee తో చాట్",
        "chat_caption": "లక్షణాలు, ఆరోగ్యం లేదా సాధారణ ఆరోగ్యం గురించి అడగండి. అత్యవసర సందర్భంలో డాక్టర్ లేదా హాస్పిటల్ ని సంప్రదించండి.",
        "journal_title": "ఆరోగ్య జర్నల్",
        "journal_desc": "మీ ఆరోగ్య నోట్లు ఇక్కడ కనిపిస్తాయి.",
        "journal_empty": "మీ ఆరోగ్య నోట్లు మరియు సారాంశాలు ఇక్కడ కనిపిస్తాయి.",
        "settings_title": "సెట్టింగ్‌లు",
        "app_language_label": "యాప్ భాష",
        "maps_title": "దగ్గరి హాస్పిటల్‌లు / క్లినిక్‌లను కనుగొనండి",
        "maps_caption": "మీ నగరం లేదా ప్రాంతాన్ని నమోదు చేయండి. OpenStreetMap ఫలితాలు.",
        "maps_search_placeholder": "ఉదా. ముంబై",
        "search": "వెతకండి",
        "open_map": "మ్యాప్ తెరవండి",
        "results_for": "ఫలితాలు",
        "no_results": "ఆ ప్రాంతానికి ఫలితాలు లేవు. మరొక నగరాన్ని ప్రయత్నించండి.",
        "reminders": "జ్ఞాపకాలు",
        "reminders_title": "ఆరోగ్య జ్ఞాపకాలు",
        "reminders_desc": "మందులు, చెక్-అప్‌లు లేదా గుర్తుకు వచ్చేలా చేయాలనుకునేది. ఈ సెషన్‌లో మాత్రమే చూపిస్తాము.",
        "add_reminder": "జ్ఞాపకం జోడించండి",
        "reminder_title": "ఏమి గుర్తుపెట్టుకోవాలి",
        "reminder_datetime": "తేదీ మరియు సమయం",
        "reminder_note": "నోట్ (ఐచ్ఛికం)",
        "empty_reminders": "ఇంకా జ్ఞాపకాలు లేవు. క్రింద ఒకటి జోడించండి.",
        "delete": "తొలగించు",
        "mark_done": "పూర్తయింది",
        "overdue": "గడువు మించిన",
        "journal_from_chat": "చాట్ నుండి",
    },
    "hi": {
        "home": "होम",
        "chatbot": "चैटबॉट",
        "maps": "मानचित्र",
        "journal": "जर्नल",
        "settings": "सेटिंग्स",
        "tagline": "आपका स्वास्थ्य साथी",
        "welcome": "HealBee में आपका स्वागत है",
        "add_note": "नया नोट जोड़ें",
        "save": "सहेजें",
        "empty_notes": "अभी तक कोई नोट नहीं। नीचे एक जोड़ें।",
        "logout": "लॉगआउट",
        "confirm_logout": "क्या आप वाकई लॉग आउट करना चाहते हैं?",
        "yes_logout": "हाँ, लॉग आउट",
        "cancel": "रद्द करें",
        "clear_session": "सत्र डेटा साफ़ करें",
        "settings_caption": "ऐप भाषा केवल लेबल और नेविगेशन को प्रभावित करती है। चैटबॉट भाषा अलग से सेट की जाती है।",
        "chat_title": "HealBee के साथ चैट",
        "chat_caption": "लक्षण, कल्याण या सामान्य स्वास्थ्य के बारे में पूछें। आपातकाल में कृपया डॉक्टर या अस्पताल से संपर्क करें।",
        "journal_title": "स्वास्थ्य जर्नल",
        "journal_desc": "आपके स्वास्थ्य नोट्स यहाँ दिखाई देंगे।",
        "journal_empty": "आपके स्वास्थ्य नोट्स और सारांश यहाँ दिखाई देंगे।",
        "settings_title": "सेटिंग्स",
        "app_language_label": "ऐप भाषा",
        "maps_title": "पास के अस्पताल / क्लिनिक खोजें",
        "maps_caption": "अपना शहर या इलाका दर्ज करें। OpenStreetMap परिणाम।",
        "maps_search_placeholder": "जैसे मुंबई, दिल्ली",
        "search": "खोजें",
        "open_map": "मानचित्र खोलें",
        "results_for": "परिणाम",
        "no_results": "उस क्षेत्र के लिए कोई परिणाम नहीं मिला। दूसरे शहर को आज़माएं।",
        "reminders": "अनुस्मारक",
        "reminders_title": "स्वास्थ्य अनुस्मारक",
        "reminders_desc": "दवा, चेक-अप या जो भी याद दिलाना हो। सिर्फ इस सत्र में दिखेगा।",
        "add_reminder": "अनुस्मारक जोड़ें",
        "reminder_title": "क्या याद रखना है",
        "reminder_datetime": "तारीख और समय",
        "reminder_note": "नोट (वैकल्पिक)",
        "empty_reminders": "अभी तक कोई अनुस्मारक नहीं। नीचे एक जोड़ें।",
        "delete": "हटाएं",
        "mark_done": "हो गया",
        "overdue": "समय पार",
        "journal_from_chat": "चैट से",
        "your_chats": "आपकी चैट",
        "chat_language_label": "चैट भाषा",
        "note_title": "शीर्षक",
        "settings_caption_short": "यह केवल ऐप लेबल बदलता है। चैट भाषा चैटबॉट में सेट होती है।",
    },
    "kn": {
        "home": "ಮುಖಪುಟ",
        "chatbot": "ಚಾಟ್‌ಬಾಟ್",
        "maps": "ನಕ್ಷೆ",
        "journal": "ಜರ್ನಲ್",
        "settings": "ಸೆಟ್ಟಿಂಗ್‌ಗಳು",
        "tagline": "ನಿಮ್ಮ ಆರೋಗ್ಯ ಸಂಗಾತಿ",
        "welcome": "HealBee ಗೆ ಸ್ವಾಗತ",
        "add_note": "ಹೊಸ ನೋಟ್ ಸೇರಿಸಿ",
        "save": "ಉಳಿಸಿ",
        "empty_notes": "ಇನ್ನೂ ನೋಟ್‌ಗಳಿಲ್ಲ. ಕೆಳಗೆ ಒಂದನ್ನು ಸೇರಿಸಿ.",
        "logout": "ಲಾಗ್‌ಔಟ್",
        "confirm_logout": "ಲಾಗ್‌ಔಟ್ ಮಾಡಲು ಖಚಿತವೇ?",
        "yes_logout": "ಹೌದು, ಲಾಗ್‌ಔಟ್",
        "cancel": "ರದ್ದು",
        "clear_session": "ಸೆಷನ್ ಡೇಟಾ ಅಳಿಸಿ",
        "settings_caption": "ಆ್ಯಪ್ ಭಾಷೆ ಲೇಬಲ್‌ಗಳು ಮತ್ತು ನ್ಯಾವಿಗೇಶನ್‌ನನ್ನು ಮಾತ್ರ ಪರಿಣಾಮ ಬೀರುತ್ತದೆ. ಚಾಟ್‌ಬಾಟ್ ಭಾಷೆ ಪ್ರತ್ಯೇಕವಾಗಿ ಹೊಂದಿಸಲಾಗಿದೆ.",
        "chat_title": "HealBee ಜೊತೆ ಚಾಟ್",
        "chat_caption": "ಲಕ್ಷಣಗಳು, ಯೋಗಕ್ಷೇಮ ಅಥವಾ ಸಾಮಾನ್ಯ ಆರೋಗ್ಯದ ಬಗ್ಗೆ ಕೇಳಿ. ಅತ್ಯವಸರದಲ್ಲಿ ವೈದ್ಯರು ಅಥವಾ ಆಸ್ಪತ್ರೆಗೆ ಸಂಪರ್ಕಿಸಿ.",
        "journal_title": "ಆರೋಗ್ಯ ಜರ್ನಲ್",
        "journal_desc": "ನಿಮ್ಮ ಆರೋಗ್ಯ ನೋಟ್‌ಗಳು ಇಲ್ಲಿ ಕಾಣಿಸಿಕೊಳ್ಳುತ್ತವೆ.",
        "journal_empty": "ನಿಮ್ಮ ಆರೋಗ್ಯ ನೋಟ್‌ಗಳು ಮತ್ತು ಸಾರಾಂಶಗಳು ಇಲ್ಲಿ ಕಾಣಿಸಿಕೊಳ್ಳುತ್ತವೆ.",
        "settings_title": "ಸೆಟ್ಟಿಂಗ್‌ಗಳು",
        "app_language_label": "ಆ್ಯಪ್ ಭಾಷೆ",
        "maps_title": "ಹತ್ತಿರದ ಆಸ್ಪತ್ರೆಗಳು / ಕ್ಲಿನಿಕ್‌ಗಳನ್ನು ಹುಡುಕಿ",
        "maps_caption": "ನಿಮ್ಮ ನಗರ ಅಥವಾ ಪ್ರದೇಶ ನಮೂದಿಸಿ. OpenStreetMap ಫಲಿತಾಂಶಗಳು.",
        "maps_search_placeholder": "ಉದಾ. ಬೆಂಗಳೂರು, ಮುಂಬೈ",
        "search": "ಹುಡುಕಿ",
        "open_map": "ನಕ್ಷೆ ತೆರೆಯಿರಿ",
        "results_for": "ಫಲಿತಾಂಶಗಳು",
        "no_results": "ಆ ಪ್ರದೇಶಕ್ಕೆ ಫಲಿತಾಂಶಗಳು ಕಂಡುಬಂದಿಲ್ಲ. ಇನ್ನೊಂದು ನಗರ ಪ್ರಯತ್ನಿಸಿ.",
        "reminders": "ಜ್ಞಾಪನೆಗಳು",
        "reminders_title": "ಆರೋಗ್ಯ ಜ್ಞಾಪನೆಗಳು",
        "reminders_desc": "ಔಷಧಿ, ಚೆಕ್-ಅಪ್ ಅಥವಾ ನೆನಪಿಸಿಕೊಳ್ಳಲು ಬಯಸುವುದು. ಈ ಸೆಷನ್‌ನಲ್ಲಿ ಮಾತ್ರ ತೋರಿಸಲಾಗುತ್ತದೆ.",
        "add_reminder": "ಜ್ಞಾಪನೆ ಸೇರಿಸಿ",
        "reminder_title": "ಏನು ನೆನಪಿಡಬೇಕು",
        "reminder_datetime": "ದಿನಾಂಕ ಮತ್ತು ಸಮಯ",
        "reminder_note": "ನೋಟ್ (ಐಚ್ಛಿಕ)",
        "empty_reminders": "ಇನ್ನೂ ಜ್ಞಾಪನೆಗಳಿಲ್ಲ. ಕೆಳಗೆ ಒಂದನ್ನು ಸೇರಿಸಿ.",
        "delete": "ಅಳಿಸಿ",
        "mark_done": "ಪೂರ್ಣ",
        "overdue": "ಕಾಲ ಮೀರಿದ",
        "journal_from_chat": "ಚಾಟ್‌ನಿಂದ",
        "your_chats": "ನಿಮ್ಮ ಚಾಟ್‌ಗಳು",
        "chat_language_label": "ಚಾಟ್ ಭಾಷೆ",
        "note_title": "ಶೀರ್ಷಿಕೆ",
        "settings_caption_short": "ಇದು ಆ್ಯಪ್ ಲೇಬಲ್‌ಗಳನ್ನು ಮಾತ್ರ ಬದಲಾಯಿಸುತ್ತದೆ. ಚಾಟ್ ಭಾಷೆ ಚಾಟ್‌ಬಾಟ್‌ನಲ್ಲಿ ಹೊಂದಿಸಲಾಗಿದೆ.",
    },
    "mr": {
        "home": "मुख्यपृष्ठ",
        "chatbot": "चॅटबॉट",
        "maps": "नकाशा",
        "journal": "जर्नल",
        "settings": "सेटिंग्स",
        "tagline": "तुमचा आरोग्य साथी",
        "welcome": "HealBee मध्ये स्वागत आहे",
        "add_note": "नवीन नोट जोडा",
        "save": "जतन करा",
        "empty_notes": "अद्याप नोट्स नाहीत. खाली एक जोडा.",
        "logout": "लॉगआउट",
        "confirm_logout": "लॉगआउट करायचे खात्री आहे?",
        "yes_logout": "होय, लॉगआउट",
        "cancel": "रद्द",
        "clear_session": "सत्र डेटा साफ करा",
        "settings_caption": "अॅप भाषा फक्त लेबल आणि नेव्हिगेशनवर परिणाम करते. चॅटबॉट भाषा वेगळी सेट केली आहे.",
        "chat_title": "HealBee सोबत चॅट",
        "chat_caption": "लक्षणे, कल्याण किंवा सामान्य आरोग्य विषयी विचारा. आणीबाणीत डॉक्टर किंवा रुग्णालयाशी संपर्क करा.",
        "journal_title": "आरोग्य जर्नल",
        "journal_desc": "तुमच्या आरोग्य नोट्स येथे दिसतील.",
        "journal_empty": "तुमच्या आरोग्य नोट्स आणि सारांश येथे दिसतील.",
        "settings_title": "सेटिंग्स",
        "app_language_label": "अॅप भाषा",
        "maps_title": "जवळचे रुग्णालय / क्लिनिक शोधा",
        "maps_caption": "तुमचे शहर किंवा प्रदेश प्रविष्ट करा. OpenStreetMap निकाल.",
        "maps_search_placeholder": "उदा. मुंबई, पुणे",
        "search": "शोधा",
        "open_map": "नकाशा उघडा",
        "results_for": "निकाल",
        "no_results": "त्या क्षेत्रासाठी निकाल सापडले नाहीत. दुसरे शहर वापरून पहा.",
        "reminders": "स्मरणपत्रे",
        "reminders_title": "आरोग्य स्मरणपत्रे",
        "reminders_desc": "औषध, तपासणी किंवा जे काही आठवण करून द्यायचे. फक्त या सत्रात दाखवले जाते.",
        "add_reminder": "स्मरणपत्र जोडा",
        "reminder_title": "काय आठवायचे",
        "reminder_datetime": "तारीख आणि वेळ",
        "reminder_note": "नोट (पर्यायी)",
        "empty_reminders": "अद्याप स्मरणपत्रे नाहीत. खाली एक जोडा.",
        "delete": "हटवा",
        "mark_done": "झाले",
        "overdue": "कालबाह्य",
        "journal_from_chat": "चॅटमधून",
        "your_chats": "तुमचे चॅट",
        "chat_language_label": "चॅट भाषा",
        "note_title": "शीर्षक",
        "settings_caption_short": "हे फक्त अॅप लेबल बदलते. चॅट भाषा चॅटबॉटमध्ये सेट केली आहे.",
    },
    "bn": {
        "home": "হোম",
        "chatbot": "চ্যাটবট",
        "maps": "মানচিত্র",
        "journal": "জার্নাল",
        "settings": "সেটিংস",
        "tagline": "আপনার স্বাস্থ্য সাথী",
        "welcome": "HealBee-তে স্বাগতম",
        "add_note": "নতুন নোট যোগ করুন",
        "save": "সংরক্ষণ করুন",
        "empty_notes": "এখনও কোন নোট নেই। নীচে একটি যোগ করুন।",
        "logout": "লগআউট",
        "confirm_logout": "লগআউট করতে চান?",
        "yes_logout": "হ্যাঁ, লগআউট",
        "cancel": "বাতিল",
        "clear_session": "সেশন ডেটা সাফ করুন",
        "settings_caption": "অ্যাপ ভাষা শুধুমাত্র লেবেল এবং নেভিগেশন প্রভাবিত করে। চ্যাটবট ভাষা আলাদাভাবে সেট করা হয়।",
        "chat_title": "HealBee-এর সাথে চ্যাট",
        "chat_caption": "লক্ষণ, সুস্থতা বা সাধারণ স্বাস্থ্য সম্পর্কে জিজ্ঞাসা করুন। জরুরি অবস্থায় ডাক্তার বা হাসপাতালে যোগাযোগ করুন।",
        "journal_title": "স্বাস্থ্য জার্নাল",
        "journal_desc": "আপনার স্বাস্থ্য নোট এখানে দেখা যাবে।",
        "journal_empty": "আপনার স্বাস্থ্য নোট এবং সারাংশ এখানে দেখা যাবে।",
        "settings_title": "সেটিংস",
        "app_language_label": "অ্যাপ ভাষা",
        "maps_title": "কাছের হাসপাতাল / ক্লিনিক খুঁজুন",
        "maps_caption": "আপনার শহর বা অঞ্চল লিখুন। OpenStreetMap ফলাফল।",
        "maps_search_placeholder": "যেমন কলকাতা, মুম্বাই",
        "search": "খুঁজুন",
        "open_map": "মানচিত্র খুলুন",
        "results_for": "ফলাফল",
        "no_results": "এই অঞ্চলের জন্য কোন ফলাফল নেই। অন্য শহর চেষ্টা করুন।",
        "reminders": "অনুস্মারক",
        "reminders_title": "স্বাস্থ্য অনুস্মারক",
        "reminders_desc": "ওষুধ, চেক-আপ বা যা মনে রাখতে চান। শুধুমাত্র এই সেশনে দেখানো হয়।",
        "add_reminder": "অনুস্মারক যোগ করুন",
        "reminder_title": "কী মনে রাখতে হবে",
        "reminder_datetime": "তারিখ ও সময়",
        "reminder_note": "নোট (ঐচ্ছিক)",
        "empty_reminders": "এখনও কোন অনুস্মারক নেই। নীচে একটি যোগ করুন।",
        "delete": "মুছুন",
        "mark_done": "সম্পন্ন",
        "overdue": "সময় উত্তীর্ণ",
        "journal_from_chat": "চ্যাট থেকে",
        "your_chats": "আপনার চ্যাট",
        "chat_language_label": "চ্যাট ভাষা",
        "note_title": "শিরোনাম",
        "settings_caption_short": "এটি শুধুমাত্র অ্যাপ লেবেল পরিবর্তন করে। চ্যাট ভাষা চ্যাটবটে সেট করা হয়।",
    },
}


def _t(key: str) -> str:
    """Return UI string for current app language. Fallback to English."""
    lang = st.session_state.get("app_language", "en")
    return UI_TEXT.get(lang, UI_TEXT["en"]).get(key, UI_TEXT["en"].get(key, key))


def _leaflet_map_html(places: list, height: int = 500) -> str:
    """
    Phase 4: Embedded Leaflet map with OSM tiles. No API keys.
    places: list of {name, type, address, lat, lon}. JS requests geolocation for "You are here".
    """
    safe_places = []
    for p in (places or []):
        try:
            lat, lon = float(p.get("lat") or 0), float(p.get("lon") or 0)
            if lat and lon:
                safe_places.append({
                    "name": (p.get("name") or "—").replace('"', "'").replace("\n", " "),
                    "type": (p.get("type") or "—").replace('"', "'"),
                    "address": (p.get("address") or "—").replace('"', "'").replace("\n", " ")[:200],
                    "lat": lat,
                    "lon": lon,
                })
        except (TypeError, ValueError):
            continue
    places_json = json.dumps(safe_places)
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <style>#map {{ height: {height}px; width: 100%; }}</style>
    </head>
    <body>
        <div id="map"></div>
        <script>
            var places = {places_json};
            var defaultCenter = [20.59, 78.96];
            var map = L.map("map").setView(defaultCenter, 5);
            L.tileLayer("https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{
                attribution: "© OpenStreetMap"
            }}).addTo(map);
            for (var i = 0; i < places.length; i++) {{
                var p = places[i];
                var popup = "<b>" + p.name + "</b><br><i>" + p.type + "</i><br>" + (p.address || "");
                L.marker([p.lat, p.lon]).addTo(map).bindPopup(popup);
            }}
            if (navigator.geolocation) {{
                navigator.geolocation.getCurrentPosition(
                    function(pos) {{
                        var userLat = pos.coords.latitude;
                        var userLon = pos.coords.longitude;
                        L.marker([userLat, userLon]).addTo(map).bindPopup("You are here").openPopup();
                        if (places.length === 0) map.setView([userLat, userLon], 12);
                        else map.setView([userLat, userLon], 11);
                    }},
                    function() {{ if (places.length > 0) {{ var p = places[0]; map.setView([p.lat, p.lon], 12); }} }}
                );
            }} else {{
                if (places.length > 0) {{ var p = places[0]; map.setView([p.lat, p.lon], 12); }}
            }}
        </script>
    </body>
    </html>
    """


# --- Cached heavy resources (avoid reloading on every interaction) ---
@st.cache_resource
def _get_nlu_processor(api_key: str):
    if not api_key:
        return None
    return SarvamMNLUProcessor(api_key=api_key)


@st.cache_resource
def _get_response_generator(api_key: str):
    if not api_key:
        return None
    return HealBeeResponseGenerator(api_key=api_key)


@st.cache_resource
def _get_utils(api_key: str):
    if not api_key:
        return None
    return HealBeeUtilities(api_key=api_key)


@st.cache_resource
def _get_audio_cleaner():
    return AudioCleaner()


# --- Language Mapping ---
LANGUAGE_MAP = {
    "English": "en-IN", 
    "हिन्दी (Hindi)": "hi-IN", 
    "বাংলা (Bengali)": "bn-IN", 
    "मराठी (Marathi)": "mr-IN", 
    "ಕನ್ನಡ (Kannada)": "kn-IN",
    "தமிழ் (Tamil)": "ta-IN",
    "తెలుగు (Telugu)": "te-IN",
    "മലയാളം (Malayalam)": "ml-IN",
}

DISPLAY_LANGUAGES = list(LANGUAGE_MAP.keys())



# --- Helper Functions ---
def clean_assistant_text(text: str) -> str:
    """
    Removes leaked internal prefixes like 'fever:' or 'cough:' from assistant messages.
    UI-only sanitation. Does NOT affect logic or memory.
    """
    if not text or ":" not in text:
        return text

    left, right = text.split(":", 1)

    # If left side looks like a short internal label, drop it
    if len(left.strip().split()) <= 2:
        return right.strip()

    return text.strip()


def _format_nearby_places_for_chat(places: list, translate_fn, location_name: str = "") -> str:
    """
    Format nearby hospitals/clinics as plain text for chat. No markdown, no HTML.
    location_name: e.g. "Velachery" or "Velachery–Tambaram" for the intro line.
    """
    if not places:
        return translate_fn("I couldn't find clinics near this area. Try a nearby locality.")
    if location_name:
        intro = translate_fn("Here are some clinics and hospitals near {} (within 10 km):").format(location_name)
    else:
        intro = translate_fn("Here are some clinics and hospitals near you (within 10 km):")
    label_address = translate_fn("Address")
    label_contact = translate_fn("Contact")
    contact_na = translate_fn("Not available")
    lines = [intro, ""]
    for i, p in enumerate(places[:8], 1):
        name = (p.get("name") or "—").strip()
        address = (p.get("address") or "—").strip()[:200]
        phone = (p.get("phone") or "").strip()
        lines.append(f"{i}. {name}")
        lines.append(f"   {label_address}: {address}")
        lines.append(f"   {label_contact}: {phone if phone else contact_na}")
        lines.append("")
    lines.append(translate_fn("If you want details about any one place, just tell me the name."))
    return "\n".join(lines).strip()


def markdown_to_html_safe(text: str) -> str:
    """
    Converts basic markdown to HTML for Streamlit-safe rendering. No external dependency.
    Preserves: **bold**, *italic*, line breaks, bullet lines. Escapes HTML for safety.
    """
    if not text:
        return ""
    # Escape HTML first
    s = (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    # **bold** -> <strong>bold</strong> (non-greedy)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    # *italic* (single asterisks, after bold replaced) -> <em>italic</em>
    s = re.sub(r"\*([^*]+?)\*", r"<em>\1</em>", s)
    # Line breaks
    s = s.replace("\n", "<br>")
    return s


def strip_markdown(text: str) -> str:
    """
    Renders assistant content as plain text: no bold/italic, bullet prefixes, or emojis.
    Keeps line breaks. UI-only; does not affect logic or storage.
    """
    if not text:
        return text
    # Remove **bold** and *italic*
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    s = re.sub(r"\*(.+?)\*", r"\1", s)
    s = re.sub(r"__(.+?)__", r"\1", s)
    s = re.sub(r"_(.+?)_", r"\1", s)
    # Remove bullet prefixes at line start (- or •)
    s = re.sub(r"^[\s]*[-•]\s*", "", s, flags=re.MULTILINE)
    # Remove emojis (common Unicode ranges)
    s = re.sub(r"[\U0001F300-\U0001F9FF\U00002600-\U000027BF\U0001F600-\U0001F64F]", "", s)
    return s.strip()


def add_message_to_conversation(role: str, content: str, lang_code: Optional[str] = None):
    message = {"role": role, "content": content}
    if lang_code and role == "user":
        message["lang"] = lang_code 
    st.session_state.conversation.append(message)


def _persist_message_to_db(role: str, content: str) -> None:
    """Phase C: save message to Supabase if logged in. Creates chat on first user message. No-op if DB fails."""
    if not is_supabase_configured() or not st.session_state.get("supabase_session"):
        return
    try:
        uid = st.session_state.supabase_session.get("user_id")
        cid = st.session_state.get("current_chat_id")
        if cid is None:
            title = (content[:50] + "…") if len(content) > 50 else (content or "Chat")
            cid = chat_create(uid, title)
            if cid:
                st.session_state.current_chat_id = cid
                st.session_state.chat_list = chats_list(uid)
        if cid:
            message_insert(cid, role, content)
    except Exception:
        pass


def _save_health_context_to_memory() -> None:
    """Phase C: save important health context to user_memory for continuity across chats. No-op if not logged in or DB fails."""
    if not is_supabase_configured() or not st.session_state.get("supabase_session"):
        return
    try:
        uid = st.session_state.supabase_session.get("user_id")
        symptoms = st.session_state.get("extracted_symptoms") or []
        advice = (st.session_state.get("last_advice_given") or "")[:800]
        if symptoms:
            val = ", ".join(str(s) for s in symptoms[:20])
            user_memory_upsert(uid, "last_symptoms", val)
            st.session_state.persistent_memory["last_symptoms"] = val
        if advice:
            user_memory_upsert(uid, "last_advice", advice)
            st.session_state.persistent_memory["last_advice"] = advice
    except Exception:
        pass


def _save_chat_to_journal(assessment: dict) -> None:
    """Save symptom/condition details from this chat to the Journal in the user's chat language (any of 8 languages)."""
    try:
        symptoms = list(st.session_state.get("extracted_symptoms") or [])[:15]
        follow_answers = list(st.session_state.get("follow_up_answers") or [])
        condition_summary_raw = (assessment.get("assessment_summary") or "").strip()[:500]
        # User experience: short summary of follow-up Q&A (already in user's language)
        exp_parts = []
        for fa in follow_answers[-10:]:
            sym = (fa.get("symptom_name") or "").strip()
            ans = (fa.get("answer") or "").strip()[:80]
            if sym or ans:
                exp_parts.append(f"{sym}: {ans}" if sym else ans)
        user_experience = "; ".join(exp_parts)[:400] if exp_parts else ""
        title_raw = "Symptom check: " + ", ".join(symptoms)[:80] if symptoms else "Symptom check"
        # Store in user's chat language (any of 8)
        user_lang = st.session_state.get("current_language_code") or "en-IN"
        util = _get_utils(SARVAM_API_KEY)
        if user_lang != "en-IN" and util:
            try:
                title = util.translate_text(title_raw, user_lang) or title_raw
                condition_summary = util.translate_text(condition_summary_raw, user_lang) or condition_summary_raw
                label_experience = util.translate_text("User experience:", user_lang) or "User experience:"
            except Exception:
                title = title_raw
                condition_summary = condition_summary_raw
                label_experience = "User experience:"
        else:
            title = title_raw
            condition_summary = condition_summary_raw
            label_experience = "User experience:"
        content_parts = [condition_summary] if condition_summary else []
        if user_experience:
            content_parts.append(label_experience + " " + user_experience)
        content = "\n\n".join(content_parts)
        entry = {
            "source": "chat",
            "title": title,
            "content": content,
            "datetime": datetime.now().isoformat(),
            "symptoms": symptoms,
            "condition_summary": condition_summary,
            "user_experience": user_experience,
        }
        if "journal_entries" not in st.session_state:
            st.session_state.journal_entries = []
        uid = st.session_state.get("supabase_session", {}).get("user_id") if st.session_state.get("supabase_session") else None
        if is_supabase_configured() and uid:
            try:
                db_journal_entry_insert(uid, entry)
                st.session_state.journal_entries = db_journal_entries_list(uid)
            except Exception:
                st.session_state.journal_entries.append(entry)
        else:
            st.session_state.journal_entries.append(entry)
    except Exception:
        pass


# --- Streamlit UI ---
def main_ui():
    st.set_page_config(page_title="HealBee", layout="wide", initial_sidebar_state="collapsed")

    def store_feedback(feedback_text, user_email, ml_generated_text, full_conversation):
        """Feedback UI is shown; feedback is acknowledged but not persisted (Firebase removed)."""
        st.info("Thank you for your feedback.")
        return True

    # --- 1. GLOBAL THEME: light green background #E2F6C6, all text black (nav bar excluded) ---
    theme_css = """
        <style>
            :root {
                --healbee-bg: #E2F6C6;
                --healbee-accent: #0d9488;
                --healbee-mint: #d1fae5;
                --healbee-text: #000000;
                --healbee-card-bg: #ffffff;
                --healbee-shadow: 0 2px 12px rgba(0,0,0,0.06);
            }
            header { visibility: hidden; }
            #MainMenu { visibility: hidden; }
            footer { visibility: hidden; }
            .stApp { background: var(--healbee-bg) !important; }
            .block-container { padding-top: 1rem; padding-bottom: 1rem; font-size: 1.05rem; max-width: 100%%; color: var(--healbee-text) !important; }
            .stMarkdown p, .stMarkdown li, .stMarkdown, .stMarkdown * { color: var(--healbee-text) !important; }
            label, .stTextInput label, .stSelectbox label, p, span, div { color: var(--healbee-text) !important; }
            [data-testid="stButton"] button { border-radius: 12px; box-shadow: var(--healbee-shadow); }
            .healbee-disclaimer { font-size: 0.9rem; color: var(--healbee-text); opacity: 0.9; margin-top: 0.5rem; padding: 0.5rem 0; border-top: 1px solid rgba(13,148,136,0.2); }
            .healbee-welcome { font-size: 1.05rem; line-height: 1.55; color: var(--healbee-text); }
            .healbee-msg-label { font-size: 0.8rem; font-weight: 600; margin-bottom: 0.2rem; color: var(--healbee-text); }
            .healbee-bubble-user { font-size: 1rem; background: #ffffff; border-radius: 14px; padding: 0.65rem 0.9rem; max-width: 78%%; text-align: right; word-wrap: break-word; line-height: 1.5; box-shadow: var(--healbee-shadow); color: var(--healbee-text); border: 2px solid #000000; }
            .healbee-bubble-assistant { font-size: 1rem; background: var(--healbee-mint); border-radius: 14px; padding: 0.65rem 0.9rem; max-width: 78%%; text-align: left; word-wrap: break-word; line-height: 1.5; box-shadow: var(--healbee-shadow); color: var(--healbee-text); border: 1px solid rgba(13,148,136,0.2); }
            .healbee-bubble-system { padding: 0.5rem 0.75rem; font-size: 0.95rem; color: var(--healbee-text); }
            .healbee-card { background: var(--healbee-card-bg); border-radius: 14px; padding: 1rem; margin-bottom: 1rem; box-shadow: var(--healbee-shadow); border: 1px solid rgba(0,0,0,0.06); color: var(--healbee-text); }
            .healbee-nav-active { background: var(--healbee-mint) !important; border-color: var(--healbee-accent) !important; }
            .healbee-nav-inactive { background: #ffffff !important; border: 1px solid #d1d5db !important; }
            /* Auth screen: card-style container (login/register) — entire block gets mint card when marker present */
            .block-container:has(#healbee-auth-page) { background: var(--healbee-mint) !important; border-radius: 14px; padding: 2rem 2.5rem; margin: 1rem 0; box-shadow: var(--healbee-shadow); border: 1px solid rgba(13,148,136,0.2); max-width: 520px; }
            .block-container:has(#healbee-auth-page) [data-testid="stFormSubmitButton"] button { width: 100%; border-radius: 12px; }
            .healbee-auth-title { font-size: 1.75rem; font-weight: 700; color: var(--healbee-text); margin-bottom: 0.25rem; }
            .healbee-auth-caption { font-size: 1rem; color: var(--healbee-text); opacity: 0.9; margin-bottom: 1.5rem; }
            /* Nav bar only: do not apply black text — keep Chatbot/Maps/Journal/Settings button styling */
            [data-testid="stHorizontalBlock"]:first-of-type,
            [data-testid="stHorizontalBlock"]:first-of-type * { color: revert !important; }
            /* Personal information fields (e.g. Your profile): white text on dark background */
            [data-testid="stExpander"] [data-testid="stTextInput"] input,
            [data-testid="stExpander"] [data-testid="stNumberInput"] input,
            [data-testid="stExpander"] [data-testid="stTextArea"] textarea,
            [data-testid="stExpander"] [data-testid="stSelectbox"] input,
            [data-testid="stExpander"] [data-testid="stSelectbox"] [role="combobox"],
            [data-testid="stExpander"] [data-testid="stMultiSelect"] input,
            [data-testid="stExpander"] [data-testid="stMultiSelect"] [role="combobox"] {
                color: #ffffff !important;
                background-color: #374151 !important;
            }
            [data-testid="stExpander"] [data-testid="stTextInput"] input::placeholder,
            [data-testid="stExpander"] [data-testid="stNumberInput"] input::placeholder,
            [data-testid="stExpander"] [data-testid="stTextArea"] textarea::placeholder {
                color: rgba(255,255,255,0.7) !important;
            }
            /* Profile section: labels, captions and button text white */
            [data-testid="stExpander"] label,
            [data-testid="stExpander"] [data-testid="stCaptionContainer"],
            [data-testid="stExpander"] [data-testid="stCaptionContainer"] *,
            [data-testid="stExpander"] [data-testid="stButton"] button {
                color: #ffffff !important;
                background-color: #374151 !important;
            }
            /* Dropdown/multiselect option list text white (options in open list) */
            [data-testid="stSelectbox"] [role="listbox"] [role="option"],
            [data-testid="stSelectbox"] [role="listbox"] div,
            [data-testid="stMultiSelect"] [role="listbox"] [role="option"],
            [data-testid="stMultiSelect"] [role="listbox"] div,
            [data-testid="stSelectbox"] [role="option"],
            [data-testid="stMultiSelect"] [role="option"] {
                color: #ffffff !important;
            }
            /* Profile: soft multiselect pills (neutral, not red) */
            [data-testid="stExpander"] span[data-baseweb="tag"] {
                background-color: #94a3b8 !important;
                color: #ffffff !important;
                border: none !important;
                border-radius: 8px !important;
            }
            [data-testid="stExpander"] span[data-baseweb="tag"] span {
                color: #ffffff !important;
            }
            /* Profile section: lighter labels, more breathing room */
            .healbee-profile-section { margin-top: 1rem; margin-bottom: 0.5rem; font-size: 0.9rem; color: var(--healbee-text); opacity: 0.9; font-weight: 500; }
            .healbee-profile-helper { font-size: 0.8rem; color: var(--healbee-text); opacity: 0.75; margin-top: 0.25rem; margin-bottom: 0.75rem; line-height: 1.4; }
             /* ===============================
   FORCE WHITE TEXT — PROFILE FIELDS ONLY
   =============================== */

/* Inputs, textareas, selectboxes inside Profile expander */
[data-testid="stExpander"] input,
[data-testid="stExpander"] textarea,
[data-testid="stExpander"] [role="combobox"],
[data-testid="stExpander"] [role="listbox"],
[data-testid="stExpander"] [role="option"],
[data-testid="stExpander"] div[data-baseweb="select"] *,
[data-testid="stExpander"] div[data-baseweb="input"] *,
[data-testid="stExpander"] div[data-baseweb="textarea"] * {
    color: #ffffff !important;
}

/* Placeholder text */
[data-testid="stExpander"] input::placeholder,
[data-testid="stExpander"] textarea::placeholder {
    color: rgba(255,255,255,0.7) !important;
}

/* Multiselect pills (Asthma, Hypertension etc.) */
[data-testid="stExpander"] span[data-baseweb="tag"],
[data-testid="stExpander"] span[data-baseweb="tag"] * {
    color: #ffffff !important;
    background-color: #475569 !important; /* neutral slate */
    border-radius: 8px !important;
}

/* Dropdown menu background */
[data-testid="stExpander"] [role="listbox"] {
    background-color: #374151 !important;
}

        </style>
    """
    st.markdown(theme_css, unsafe_allow_html=True)
    
    if not SARVAM_API_KEY:
        st.error(
            "**SARVAM_API_KEY** is required but not set. "
            "For local dev: add it to a `.env` file in the project root. "
            "For Streamlit Cloud: add it in app Settings → Secrets. "
            "Get a key from the [Sarvam AI dashboard](https://dashboard.sarvam.ai)."
        )
        st.stop()

    # --- Phase C: Supabase auth gate (fallback to session-only if not configured) ---
    supabase_ok = is_supabase_configured()
    if supabase_ok and st.session_state.supabase_session is None:
        # Auth UI: login / register — visual polish only; auth logic unchanged
        st.markdown("<span id='healbee-auth-page'></span>", unsafe_allow_html=True)
        st.markdown("<p class='healbee-auth-title'>🐝 Welcome to HealBee</p>", unsafe_allow_html=True)
        st.markdown("<p class='healbee-auth-caption'>Your personal health companion. Sign in to save your chats and health notes across devices.</p>", unsafe_allow_html=True)
        tab_login, tab_register = st.tabs(["Sign in", "Create account"])
        with tab_login:
            with st.form("login_form"):
                login_email = st.text_input("Email address", key="login_email", placeholder="you@example.com")
                login_password = st.text_input("Password", type="password", key="login_password", placeholder="Enter your password")
                st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
                if st.form_submit_button("Sign in", use_container_width=True):
                    if login_email and login_password:
                        session, err = auth_sign_in(login_email.strip(), login_password)
                        if session:
                            st.session_state.supabase_session = session
                            st.success("You're in! Taking you to HealBee.")
                            st.rerun()
                        else:
                            st.error(err or "Sign-in failed. Please check your email and password.")
                    else:
                        st.warning("Please enter your email and password.")
        with tab_register:
            with st.form("register_form"):
                reg_email = st.text_input("Email address", key="reg_email", placeholder="you@example.com")
                reg_password = st.text_input("Password", type="password", key="reg_password", placeholder="Choose a password")
                st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
                if st.form_submit_button("Create account", use_container_width=True):
                    if reg_email and reg_password:
                        session, err = auth_sign_up(reg_email.strip(), reg_password)
                        if session:
                            st.session_state.supabase_session = session
                            st.success("Account created. You're signed in.")
                            st.rerun()
                        else:
                            st.error(err or "Registration failed. Please try again.")
                    else:
                        st.warning("Please enter your email and a password.")
        st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)
        st.caption("Prefer to try without an account? Session-only mode is available when Supabase is not configured.")
        return

    if supabase_ok and st.session_state.supabase_session:
        auth_set_session_from_tokens(
            st.session_state.supabase_session.get("access_token", ""),
            st.session_state.supabase_session.get("refresh_token", ""),
        )
        try:
            uid = st.session_state.supabase_session.get("user_id")
            if uid:
                st.session_state.chat_list = chats_list(uid)
                st.session_state.persistent_memory = user_memory_get_all(uid)
                # Load persistent profile so assistant can use identity/health context
                loaded = user_profile_get(uid)
                st.session_state.user_profile = loaded if loaded is not None else {}
                # Load reminders and journal from DB so they persist across refresh
                try:
                    st.session_state.reminders = db_reminders_list(uid)
                    st.session_state.journal_entries = db_journal_entries_list(uid)
                except Exception:
                    pass
        except Exception:
            pass

    # --- 2. TOP NAVIGATION BAR: 5 tabs, icons above text, active=soft green, inactive=white+gray ---
    ap = st.session_state.active_page
    nav_pages = [
        ("chat", "💬", _t("chatbot")),
        ("maps", "🗺️", _t("maps")),
        ("journal", "📓", _t("journal")),
        ("reminders", "⏰", _t("reminders")),
        ("settings", "⚙️", _t("settings")),
    ]
    nav_cols = st.columns(5)
    for i, (page_key, icon, label) in enumerate(nav_pages):
        with nav_cols[i]:
            is_active = ap == page_key
            # Icons above text (centered) — label on second line
            btn_label = f"**{icon}**\n\n{label}" if is_active else f"{icon}\n\n{label}"
            if st.button(btn_label, key=f"nav_{page_key}", use_container_width=True, type="primary" if is_active else "secondary"):
                st.session_state.active_page = page_key
                st.rerun()
    st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

    # --- 3. CHATBOT PAGE: Left 30% (logo, language, Your Chats), Right 70% (conversation, input) ---
    if st.session_state.active_page == "chat":
        col_left, col_right = st.columns([3, 7])  # 30% / 70%
        with col_left:
            # App logo + name; show user name when profile exists (persistent across sessions)
            profile_for_header = st.session_state.get("user_profile") or {}
            user_name = (profile_for_header.get("name") or "").strip()
            st.markdown("<h2 style='color: var(--healbee-text); margin-bottom: 0;'>🐝 HealBee</h2>", unsafe_allow_html=True)
            if user_name:
                st.markdown("<p style='color: var(--healbee-text); font-size: 1rem; margin-top: 0.25rem;'>Hi, " + user_name.replace("<", "&lt;") + "</p>", unsafe_allow_html=True)
            st.markdown("<p style='color: var(--healbee-text); opacity: 0.85; font-size: 0.95rem; margin-top: 0.25rem;'>" + _t("tagline") + "</p>", unsafe_allow_html=True)
            # Profile Summary Card (age, gender, key conditions) — visible so user sees system "knows" them
            if profile_for_header and (profile_for_header.get("age") or profile_for_header.get("gender") or profile_for_header.get("chronic_conditions") or profile_for_header.get("medical_history")):
                age_s = str(profile_for_header["age"]) if profile_for_header.get("age") is not None else ""
                gender_s = (profile_for_header.get("gender") or "").replace("_", " ").title()
                conds = list(profile_for_header.get("chronic_conditions") or profile_for_header.get("known_conditions") or profile_for_header.get("medical_history") or [])[:5]
                conds_s = ", ".join(str(c) for c in conds) if conds else ""
                lines = [x for x in [("Age: " + age_s) if age_s else "", ("Gender: " + gender_s) if gender_s else "", ("Conditions: " + conds_s) if conds_s else ""] if x]
                if lines:
                    st.markdown("<div class='healbee-card' style='padding: 0.75rem; margin-bottom: 0.75rem;'><div style='font-size: 0.85rem; font-weight: 600; color: var(--healbee-text); margin-bottom: 0.25rem;'>Profile summary</div><div style='font-size: 0.8rem; color: var(--healbee-text); line-height: 1.4;'>" + "<br>".join(lines) + "</div></div>", unsafe_allow_html=True)
            st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)
            # Chatbot language selector (very visible)
            st.markdown("**" + _t("chat_language_label") + "**")
            _lang_idx = DISPLAY_LANGUAGES.index(st.session_state.current_language_display) if st.session_state.current_language_display in DISPLAY_LANGUAGES else 0
            selected_lang_display = st.selectbox(
                "Chat response language",
                options=DISPLAY_LANGUAGES,
                index=_lang_idx,
                key='language_selector_widget',
                label_visibility="collapsed"
            )
            st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)
            # Your Chats — scrollable list
            st.markdown("**" + _t("your_chats") + "**")
            if supabase_ok and st.session_state.supabase_session:
                uid = st.session_state.supabase_session.get("user_id")
                if st.button("➕ New chat", key="new_chat_btn", use_container_width=True):
                    st.session_state.current_chat_id = None
                    st.session_state.conversation = []
                    st.rerun()
                chat_list_container = st.container(height=220)
                with chat_list_container:
                    for c in st.session_state.chat_list:
                        label = (c.get("title") or "Chat")[:40]
                        if st.button(label, key=f"chat_{c.get('id')}", use_container_width=True):
                            try:
                                msgs = messages_list(c["id"])
                                st.session_state.conversation = [{"role": m["role"], "content": m["content"]} for m in msgs]
                                st.session_state.current_chat_id = c["id"]
                                st.rerun()
                            except Exception:
                                pass
            else:
                st.caption("Sign in to save and load chats.")
            st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)
        if selected_lang_display != st.session_state.current_language_display:
            st.session_state.current_language_display = selected_lang_display
            st.session_state.current_language_code = LANGUAGE_MAP[selected_lang_display]
            # Keep same chat and context: do NOT clear conversation, current_chat_id, or profile.
            # From now on, responses will be in the newly selected language.
            st.rerun()

        current_lang_code_for_query = st.session_state.current_language_code
        spinner_placeholder = st.empty()

        # --- User Profile: persistent in Supabase; loaded on login; used for context only, never diagnosis ---
        PROFILE_CONDITIONS = ["Diabetes", "Hypertension (High BP)", "Asthma", "Heart condition", "Thyroid", "Kidney condition", "Alzheimer's / Dementia", "Dandruff", "Hair fall", "Acne/Pimples", "Dry skin", "Dark spots/Pigmentation", "None"]
        profile = st.session_state.get("user_profile") or {}
        # Normalize allergies/conditions from DB (list) to form display (list or comma-separated)
        allergies_display = profile.get("allergies")
        if isinstance(allergies_display, list):
            allergies_display = ", ".join(str(a) for a in allergies_display)
        else:
            allergies_display = (allergies_display or "") if allergies_display else ""
        known_list = profile.get("chronic_conditions") or profile.get("known_conditions") or profile.get("medical_history") or []
        with st.expander("👤 Your profile (optional)", expanded=False):
            st.markdown("<p class='healbee-profile-helper'>Share what you're comfortable with. This helps HealBee give more relevant suggestions — and is never used for diagnosis.</p>", unsafe_allow_html=True)
            # --- Basic info ---
            st.markdown("<p class='healbee-profile-section'>A bit about you</p>", unsafe_allow_html=True)
            name_val = st.text_input("What should we call you? (optional)", value=profile.get("name") or "", key="profile_name", placeholder="e.g. Priya")
            col_basic1, col_basic2 = st.columns(2)
            with col_basic1:
                age_val = st.number_input("Age (optional)", min_value=1, max_value=120, value=profile.get("age"), step=1, key="profile_age", placeholder="Optional")
            with col_basic2:
                gender_options = ["Prefer not to say", "Male", "Female", "Other"]
                db_gender = (profile.get("gender") or "").lower()
                display_gender = {"male": "Male", "female": "Female", "other": "Other", "prefer_not_to_say": "Prefer not to say"}.get(db_gender, "Prefer not to say")
                gender_idx = gender_options.index(display_gender) if display_gender in gender_options else 0
                gender_val = st.selectbox("Gender (optional)", options=gender_options, index=gender_idx, key="profile_gender")
            st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
            # --- Body metrics ---
            st.markdown("<p class='healbee-profile-section'>Height & weight</p>", unsafe_allow_html=True)
            st.caption("Optional — helps with general wellness context.")
            col_ht, col_wt = st.columns(2)
            with col_ht:
                height_val = st.number_input("Height (cm)", min_value=50, max_value=250, value=profile.get("height_cm"), step=1, key="profile_height", placeholder="Optional")
            with col_wt:
                weight_val = st.number_input("Weight (kg)", min_value=1, max_value=300, value=profile.get("weight_kg"), step=1, key="profile_weight", placeholder="Optional")
            st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
            # --- Health context ---
            st.markdown("<p class='healbee-profile-section'>Health context (optional)</p>", unsafe_allow_html=True)
            st.caption("This helps HealBee give more relevant suggestions. This is not used for diagnosis.")
            default_conditions = [c for c in known_list if c in PROFILE_CONDITIONS]
            conditions_val = st.multiselect("Do you have any ongoing health conditions? (optional)", options=PROFILE_CONDITIONS, default=default_conditions, key="profile_conditions")
            other_default = ", ".join(c for c in known_list if c not in PROFILE_CONDITIONS)
            other_conditions = st.text_input("Any other conditions not in the list? (optional)", value=other_default, key="profile_other_conditions", placeholder="e.g. anemia, migraine")
            allergies_val = st.text_input("Any allergies we should know about? (optional)", value=allergies_display, key="profile_allergies", placeholder="e.g. penicillin, nuts")
            # pregnancy_status: only if female and age >= 12
            show_pregnancy = (gender_val == "Female" and age_val is not None and age_val >= 12)
            pregnancy_val = None
            if show_pregnancy:
                preg_options = ["Not specified", "No", "Yes"]
                preg_idx = 0
                if profile.get("pregnancy_status") is True:
                    preg_idx = 2
                elif profile.get("pregnancy_status") is False:
                    preg_idx = 1
                preg_sel = st.radio("Pregnancy status (optional)", options=preg_options, index=preg_idx, key="profile_pregnancy", horizontal=True)
                pregnancy_val = None if preg_sel == "Not specified" else (preg_sel == "Yes")
            additional_notes = st.text_area("Anything else you'd like us to keep in mind? (optional)", value=profile.get("additional_notes") or "", key="profile_notes", placeholder="Any other context for your care", height=60)
            st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
            preferred_lang = st.session_state.current_language_display
            st.caption(f"Preferred language: **{preferred_lang}** (change above)")
            if st.button("Save profile", key="profile_save"):
                other_list = [x.strip() for x in other_conditions.split(",") if x.strip()] if other_conditions else []
                all_conditions = [c for c in conditions_val if c != "None"] + other_list
                allergies_list = [x.strip() for x in (allergies_val or "").split(",") if x.strip()]
                gender_db = {"Male": "male", "Female": "female", "Other": "other", "Prefer not to say": "prefer_not_to_say"}.get(gender_val)
                profile_dict = {
                    "name": (name_val or "").strip() or None,
                    "age": int(age_val) if age_val is not None else None,
                    "gender": gender_db,
                    "height_cm": int(height_val) if height_val is not None else None,
                    "weight_kg": int(weight_val) if weight_val is not None else None,
                    "medical_history": all_conditions if all_conditions else [],
                    "chronic_conditions": all_conditions if all_conditions else [],
                    "allergies": allergies_list,
                    "pregnancy_status": pregnancy_val if show_pregnancy else None,
                    "additional_notes": (additional_notes or "").strip() or None,
                }
                st.session_state.user_profile = {**profile_dict, "known_conditions": all_conditions or None}
                if is_supabase_configured() and st.session_state.get("supabase_session"):
                    uid = st.session_state.supabase_session.get("user_id")
                    if uid and user_profile_upsert(uid, profile_dict):
                        st.success("Profile saved. It will be used for context across sessions.")
                    else:
                        st.success("Profile saved for this session.")
                else:
                    st.success("Profile saved for this session. Sign in to save across sessions.")
                st.rerun()

        # (Hospital finder moved to Maps page)
        if "near_me_results" not in st.session_state:
            st.session_state.near_me_results = []
        if "near_me_query" not in st.session_state:
            st.session_state.near_me_query = ""
        if "nearby_chat_results" not in st.session_state:
            st.session_state.nearby_chat_results = []
        if "user_gps_lat" not in st.session_state:
            st.session_state.user_gps_lat = None
        if "user_gps_lon" not in st.session_state:
            st.session_state.user_gps_lon = None
        if False:  # hospital finder moved to Maps page
            if st.session_state.near_me_results:
                st.markdown(f"**Results for “{st.session_state.near_me_query}”**")
                for p in st.session_state.near_me_results:
                    name = p.get("name") or "—"
                    ptype = p.get("type") or "—"
                    address = p.get("address") or "—"
                    lat, lon = p.get("lat"), p.get("lon")
                    link = make_osm_link(str(lat or ""), str(lon or "")) if lat and lon else ""
                    st.markdown(f"**{name}** — *{ptype}*")
                    st.caption(address)
                    if link:
                        st.markdown(f"[Directions (OpenStreetMap)]({link})")
                    st.markdown("---")
            elif st.session_state.near_me_query:
                st.info("No results found for that area, or the service is temporarily unavailable. Try another city or locality.")

        # All functions which needs time to process and will utilize spinner placeholder for loading screen
        def process_and_display_response(user_query_text: str, lang_code: str):
            if not SARVAM_API_KEY:
                st.error("API Key not configured.")
                add_message_to_conversation("system", "Error: API Key not configured.")
                st.session_state.voice_input_stage = None # Reset voice stage on error
                return

            nlu_processor = _get_nlu_processor(SARVAM_API_KEY)
            response_gen = _get_response_generator(SARVAM_API_KEY)
            util = _get_utils(SARVAM_API_KEY)
            if nlu_processor is None or response_gen is None or util is None:
                st.error("Could not initialize services. Please check API key.")
                st.session_state.voice_input_stage = None
                return
            user_lang = st.session_state.current_language_code
            try:
                # User message is now added *before* calling this function for both text and voice.
                # So, this function should not add the user message again.
                
                with spinner_placeholder.info("Reading your message…"):
                    nlu_output: NLUResult = nlu_processor.process_transcription(user_query_text, source_language=lang_code)
                    # Session memory: store extracted symptom entities from this turn
                    symptom_entities = [e.text for e in nlu_output.entities if e.entity_type == "symptom"]
                    for s in symptom_entities:
                        if s and s not in st.session_state.extracted_symptoms:
                            st.session_state.extracted_symptoms.append(s)

                    # Check for reminder request first (even if NLU classified as symptom). If user clearly asks to set a reminder, handle it and skip symptom checker / LLM.
                    reminder_just_set = None
                    try:
                        extracted = detect_and_extract_reminder(user_query_text)
                        if extracted and extracted.get("title"):
                            title = extracted["title"].strip()[:200]
                            note = (extracted.get("note") or "").strip()[:300]
                            now = datetime.now()
                            when_dt = now.replace(hour=20, minute=0, second=0, microsecond=0)
                            if when_dt <= now:
                                when_dt = when_dt + timedelta(days=1)
                            when_iso = when_dt.isoformat()
                            uid = st.session_state.supabase_session.get("user_id") if st.session_state.get("supabase_session") else None
                            if is_supabase_configured() and uid:
                                rid = db_reminder_insert(uid, title, when_iso, note, False)
                                if rid is not None:
                                    st.session_state.reminders = db_reminders_list(uid)
                                else:
                                    reminders_list = st.session_state.get("reminders") or []
                                    reminders_list.append({"id": f"rem_chat_{len(reminders_list)}_{now.timestamp()}", "title": title, "when_iso": when_iso, "note": note, "done": False})
                                    st.session_state.reminders = reminders_list
                            else:
                                reminders_list = st.session_state.get("reminders") or []
                                reminders_list.append({"id": f"rem_chat_{len(reminders_list)}_{now.timestamp()}", "title": title, "when_iso": when_iso, "note": note, "done": False})
                                st.session_state.reminders = reminders_list
                            reminder_just_set = {"title": title}
                    except Exception:
                        reminder_just_set = None
                    if reminder_just_set and reminder_just_set.get("title"):
                        _title = reminder_just_set["title"]
                        fixed_msg_en = f"I've set a reminder for \"{_title}\". You can view or edit it in the Reminders page."
                        translated_bot_response = util.translate_text(fixed_msg_en, user_lang) if user_lang != "en-IN" else fixed_msg_en
                        add_message_to_conversation("assistant", translated_bot_response)
                        _persist_message_to_db("assistant", translated_bot_response)
                        st.session_state.last_advice_given = translated_bot_response[:800]
                        st.session_state.symptom_checker_active = False
                        _save_health_context_to_memory()
                        st.session_state.voice_input_stage = None
                        return

                    # Add to journal from chat (e.g. "Add to my journal: took medicine at 8 PM")
                    journal_added = None
                    try:
                        extracted = detect_and_extract_journal(user_query_text)
                        if extracted and (extracted.get("title") or extracted.get("content")):
                            title = (extracted.get("title") or "Note from chat").strip()[:500]
                            content = (extracted.get("content") or title).strip()[:5000]
                            entry = {
                                "source": "chat",
                                "title": title,
                                "content": content,
                                "datetime": datetime.now().isoformat(),
                            }
                            if "journal_entries" not in st.session_state:
                                st.session_state.journal_entries = []
                            uid = st.session_state.supabase_session.get("user_id") if st.session_state.get("supabase_session") else None
                            if is_supabase_configured() and uid:
                                db_journal_entry_insert(uid, entry)
                                st.session_state.journal_entries = db_journal_entries_list(uid)
                            else:
                                entry["id"] = f"j_chat_{len(st.session_state.journal_entries)}_{datetime.now().timestamp()}"
                                st.session_state.journal_entries.append(entry)
                            journal_added = {"title": title}
                    except Exception:
                        journal_added = None
                    if journal_added and journal_added.get("title"):
                        _title = journal_added["title"]
                        fixed_msg_en = f"I've added \"{_title}\" to your Journal. You can view or edit it on the Journal page."
                        translated_bot_response = util.translate_text(fixed_msg_en, user_lang) if user_lang != "en-IN" else fixed_msg_en
                        add_message_to_conversation("assistant", translated_bot_response)
                        _persist_message_to_db("assistant", translated_bot_response)
                        st.session_state.last_advice_given = translated_bot_response[:800]
                        st.session_state.symptom_checker_active = False
                        _save_health_context_to_memory()
                        st.session_state.voice_input_stage = None
                        return

                    # Nearby hospitals/clinics: text-only, location from message (no GPS, no buttons)
                    if detect_nearby_places_request(user_query_text):
                        _location = extract_nearby_location(user_query_text)
                        def _nearby_t(s: str) -> str:
                            if user_lang == "en-IN":
                                return s
                            try:
                                return util.translate_text(s, user_lang) or s
                            except Exception:
                                return s
                        if not _location or not _location.strip():
                            need_area_msg = _nearby_t("I need the area name (for example: Velachery, Tambaram, Guindy) to find nearby clinics.")
                            add_message_to_conversation("assistant", need_area_msg)
                            _persist_message_to_db("assistant", need_area_msg)
                            st.session_state.last_advice_given = need_area_msg[:800]
                            st.session_state.symptom_checker_active = False
                            _save_health_context_to_memory()
                            st.session_state.voice_input_stage = None
                            return
                        _places = search_nearby_health_places(_location.strip(), 6)
                        st.session_state.nearby_chat_results = _places
                        nearby_response = _format_nearby_places_for_chat(_places, _nearby_t, location_name=_location.strip())
                        add_message_to_conversation("assistant", nearby_response)
                        _persist_message_to_db("assistant", nearby_response)
                        st.session_state.last_advice_given = nearby_response[:800]
                        st.session_state.symptom_checker_active = False
                        _save_health_context_to_memory()
                        st.session_state.voice_input_stage = None
                        return

                    # Use symptom checker when NLU says symptom_query, or when the message clearly
                    # describes symptoms (fever, cough, etc.) and is not a reminder request.
                    _qt_lower = (user_query_text or "").lower()
                    _symptom_words = ("fever", "cough", "headache", "pain", "stomach", "cold", "throat", "nausea", "dizzy", "fatigue", "rash", "vomit", "diarrhea", "chest", "breath", "body ache")
                    _has_symptom = any(w in _qt_lower for w in _symptom_words)
                    _has_reminder_word = "remind" in _qt_lower or "reminder" in _qt_lower
                    _treat_as_symptom = (nlu_output.intent == HealthIntent.SYMPTOM_QUERY) or (_has_symptom and not _has_reminder_word)
                    if _treat_as_symptom and not nlu_output.is_emergency:
                        st.session_state.symptom_checker_active = True
                        st.session_state.symptom_checker_instance = SymptomChecker(nlu_result=nlu_output, api_key=SARVAM_API_KEY)
                        st.session_state.symptom_checker_instance.prepare_follow_up_questions()
                        st.session_state.pending_symptom_question_data = st.session_state.symptom_checker_instance.get_next_question()
                        if st.session_state.pending_symptom_question_data:
                            question_to_ask_raw = st.session_state.pending_symptom_question_data['question']
                            symptom_context_raw = st.session_state.pending_symptom_question_data['symptom_name']
                            question_to_ask_translated = util.translate_text(question_to_ask_raw, user_lang)
                            add_message_to_conversation("assistant", question_to_ask_translated)
                            _persist_message_to_db("assistant", question_to_ask_translated)
                        else:
                            generate_and_display_assessment()
                    else:
                        journal_entries = st.session_state.get("journal_entries") or []
                        relevant_journal = get_relevant_journal_entries(user_query_text, journal_entries, max_entries=5)
                        session_context = {
                            "extracted_symptoms": list(st.session_state.extracted_symptoms),
                            "follow_up_answers": list(st.session_state.follow_up_answers),
                            "last_advice_given": (st.session_state.last_advice_given or "")[:800],
                            "user_profile": dict(st.session_state.user_profile) if st.session_state.get("user_profile") else None,
                            "user_memory": dict(st.session_state.persistent_memory) if st.session_state.get("persistent_memory") else None,
                            "past_messages": [],
                            "relevant_journal_entries": relevant_journal,
                        }
                        if is_supabase_configured() and st.session_state.get("supabase_session") and st.session_state.get("current_chat_id"):
                            try:
                                uid = st.session_state.supabase_session.get("user_id")
                                session_context["past_messages"] = get_recent_messages_from_other_chats(uid, st.session_state.current_chat_id, limit=8)
                            except Exception:
                                pass
                        bot_response = response_gen.generate_response(user_query_text, nlu_output, session_context=session_context)
                        translated_bot_response = util.translate_text(bot_response, user_lang)
                        add_message_to_conversation("assistant", translated_bot_response)
                        _persist_message_to_db("assistant", translated_bot_response)
                        st.session_state.last_advice_given = translated_bot_response[:800]
                        st.session_state.symptom_checker_active = False
                        _save_health_context_to_memory()
            except Exception as e:
                st.error("Something went wrong while processing your message. Please try again or rephrase your question.")
                add_message_to_conversation("system", "Sorry, an error occurred while processing your request. Please try rephrasing or try again later.")
                st.session_state.symptom_checker_active = False # Reset states on error
                st.session_state.symptom_checker_instance = None
                st.session_state.pending_symptom_question_data = None
            finally:
                st.session_state.voice_input_stage = None # Always reset voice stage after processing or error

        def handle_follow_up_answer(answer_text: str):
            util = _get_utils(SARVAM_API_KEY)
            user_lang = st.session_state.current_language_code
            if st.session_state.symptom_checker_instance and st.session_state.pending_symptom_question_data:
                # Add user's follow-up answer to conversation log
                add_message_to_conversation("user", answer_text, lang_code=st.session_state.current_language_code.split('-')[0])
                _persist_message_to_db("user", answer_text)

                question_asked = st.session_state.pending_symptom_question_data['question']
                symptom_name = st.session_state.pending_symptom_question_data['symptom_name']
                # Session memory: store follow-up answer
                st.session_state.follow_up_answers.append({
                    "symptom_name": symptom_name,
                    "question": question_asked,
                    "answer": answer_text,
                })
                with spinner_placeholder.info("Noting your answer…"):
                    st.session_state.symptom_checker_instance.record_answer(symptom_name, question_asked, answer_text)
                    st.session_state.pending_symptom_question_data = st.session_state.symptom_checker_instance.get_next_question()
                if st.session_state.pending_symptom_question_data:
                    question_to_ask_raw = st.session_state.pending_symptom_question_data['question']
                    symptom_context_raw = st.session_state.pending_symptom_question_data['symptom_name']
                    question_to_ask_translated = util.translate_text(question_to_ask_raw, user_lang)
                    add_message_to_conversation("assistant", question_to_ask_translated)
                    _persist_message_to_db("assistant", question_to_ask_translated)
                else:
                    generate_and_display_assessment()
            else: 
                st.warning("No pending question to answer or symptom checker not active.")
                st.session_state.symptom_checker_active = False
            st.session_state.voice_input_stage = None # Reset voice stage

        # New callback function for text submission
        def handle_text_submission():
            user_input = str(st.session_state.text_query_input_area).strip() # Read from session state key
            current_lang_code = st.session_state.current_language_code

            if not user_input: # Do nothing if input is empty
                return

            # Add the current user input to conversation log REGARDLESS of whether it's new or follow-up
            
            if st.session_state.symptom_checker_active and st.session_state.pending_symptom_question_data:
                # handle_follow_up_answer will process the answer.
                # It should NOT add the user message again as it's already added above.
                handle_follow_up_answer(user_input) 
            else: 
                add_message_to_conversation("user", user_input, lang_code=current_lang_code.split('-')[0])
                _persist_message_to_db("user", user_input)
                if st.session_state.symptom_checker_active: # Reset if symptom checker was active but no pending q
                    st.session_state.symptom_checker_active = False 
                    st.session_state.symptom_checker_instance = None
                    st.session_state.pending_symptom_question_data = None
                # process_and_display_response will process the new query.
                # It should NOT add the user message again.
                process_and_display_response(user_input, current_lang_code)
            
            st.session_state.text_query_input_area = "" # Clear the text area state for next render
            # If called from a non-button context that needs immediate UI update, rerun might be needed.

        def generate_and_display_assessment():
            util = _get_utils(SARVAM_API_KEY)
            user_lang = st.session_state.current_language_code
            if st.session_state.symptom_checker_instance:
                with spinner_placeholder.info("Preparing a summary for you…"):
                    assessment = st.session_state.symptom_checker_instance.generate_preliminary_assessment()
                    # Session memory: update extracted symptoms from symptom checker collected details
                    sc = st.session_state.symptom_checker_instance
                    for sym_name in (sc.collected_symptom_details or {}).keys():
                        if sym_name and sym_name not in st.session_state.extracted_symptoms:
                            st.session_state.extracted_symptoms.append(sym_name)
                    try:
                        assessment_str = f"<h4> {util.translate_text('Preliminary Health Assessment', user_lang)}:</h4>\n\n"
                        assessment_str += f"**{util.translate_text('Summary', user_lang)}:** {util.translate_text(assessment.get('assessment_summary', 'N/A'), user_lang)}\n\n"
                        assessment_str += f"**{util.translate_text('Suggested Severity', user_lang)}:** {util.translate_text(assessment.get('suggested_severity', 'N/A'), user_lang)}\n\n"
                        assessment_str += f"**{util.translate_text('Recommended Next Steps', user_lang)}:**\n"
                        next_steps = assessment.get('recommended_next_steps', 'N/A')
                        if isinstance(next_steps, list): 
                            for step in next_steps: assessment_str += f"- {util.translate_text(step, user_lang)}\n"
                        elif isinstance(next_steps, str): # This is the block to modify
                            ### Replace the original problematic f-string line here
                            # Split on punctuation marks (., !, ?) followed by whitespace
                            sentences = re.split(r'(?<=[.!?])\s+', next_steps.strip())
                            # Add bullet to each sentence
                            temp_steps = '\n- '.join(sentences).strip()
                            # remove leading bullet if present (e.g. if next_steps started with punctuation)
                            temp_steps = temp_steps.lstrip('- ')
                            # Append to assessment_str
                            assessment_str += f"{util.translate_text(temp_steps, user_lang)}\n"
                        else: 
                            assessment_str += f"- {util.translate_text('N/A', user_lang)}\n"
                        warnings = assessment.get('potential_warnings')
                        if warnings and isinstance(warnings, list) and len(warnings) > 0 :
                            assessment_str += f"\n**{util.translate_text('Potential Warnings', user_lang)}:**\n"
                            for warning in warnings: assessment_str += f"- {util.translate_text(warning, user_lang)}\n"
                        kb_points = assessment.get('relevant_kb_triage_points')
                        if kb_points and isinstance(kb_points, list) and len(kb_points) > 0:
                            assessment_str += f"\n**{util.translate_text('Relevant Triage Points from Knowledge Base', user_lang)}:**\n"
                            for point in kb_points: assessment_str += f"- {util.translate_text(point, user_lang)}\n"
                        assessment_str += f"\n\n**{util.translate_text('Disclaimer', user_lang)}:** {util.translate_text(assessment.get('disclaimer', 'Always consult a doctor for medical advice.'), user_lang)}"
                        add_message_to_conversation("assistant", assessment_str)
                        _persist_message_to_db("assistant", assessment_str)
                        # Session memory: store last advice (summary for continuity)
                        summary = assessment.get("assessment_summary", "")
                        # Phase C: save health context to user_memory
                        _save_health_context_to_memory()
                        st.session_state.last_advice_given = (summary or assessment_str[:800])[:800]
                        # Save symptom/condition summary to Journal (per-chat, for retrieval when user says "last week" etc.)
                        _save_chat_to_journal(assessment)
                    except Exception as e:
                        st.error(f"Error formatting assessment: {e}")
                        try:
                            raw_assessment_json = json.dumps(assessment, indent=2)
                            add_message_to_conversation("assistant", f"Could not format assessment. Raw data:\n```json\n{raw_assessment_json}\n```")
                            _persist_message_to_db("assistant", raw_assessment_json[:2000])
                        except Exception as json_e:
                            add_message_to_conversation("assistant", f"Could not format or serialize assessment: {json_e}")
                            _persist_message_to_db("assistant", str(json_e)[:500])
                st.session_state.symptom_checker_active = False
                st.session_state.symptom_checker_instance = None
                st.session_state.pending_symptom_question_data = None
            st.session_state.voice_input_stage = None # Reset voice stage

        # Capture and Process audio
        if st.session_state.captured_audio_data is not None:
            with spinner_placeholder.info("Preparing your recording…"):
                with io.BytesIO(st.session_state.captured_audio_data) as buffer:
                    data, sr = sf.read(buffer)
                # Clean audio (cached cleaner)
                cleaner = _get_audio_cleaner()
                cleaned_data, cleaned_sr = cleaner.get_cleaned_audio(data, sr)
            ### To test captured and cleaned audio
            # audio_buffer = io.BytesIO()
            # sf.write(audio_buffer, cleaned_data, cleaned_sr, format='WAV')
            # audio_buffer.seek(0)
            # st.audio(audio_buffer.getvalue(), format="audio/wav")
            st.session_state.cleaned_audio_data = cleaned_data
            st.session_state.captured_audio_sample_rate = cleaned_sr
            st.session_state.voice_input_stage = "processing_stt"
        
        if st.session_state.voice_input_stage == "processing_stt":
            if st.session_state.cleaned_audio_data is not None:
                util = _get_utils(SARVAM_API_KEY)
                lang_for_stt = st.session_state.current_language_code 
                try:
                    with spinner_placeholder.info("Listening…"):
                        stt_result = util.transcribe_audio(
                            st.session_state.cleaned_audio_data, sample_rate=st.session_state.captured_audio_sample_rate, source_language=lang_for_stt
                        )
                    transcribed_text = stt_result.get("transcription")
                    if lang_for_stt != stt_result.get("language_detected"):
                        if lang_for_stt == "en-IN":
                            transcribed_text = util.translate_text_to_english(transcribed_text)
                        else:
                            transcribed_text = util.translate_text(transcribed_text, lang_for_stt)
                    if transcribed_text and transcribed_text.strip():
                        add_message_to_conversation("user", transcribed_text, lang_code=lang_for_stt.split('-')[0])
                        _persist_message_to_db("user", transcribed_text)
                        process_and_display_response(transcribed_text, lang_for_stt) 
                    else:
                        add_message_to_conversation("system", "⚠️ STT failed to transcribe audio or returned empty. Please try again.")
                except Exception as e:
                    st.error(f"STT Error: {e}")
                    add_message_to_conversation("system", f"Sorry, an error occurred during voice transcription. Please try again. (Details: {e})")
                st.session_state.captured_audio_data = None 
                st.session_state.cleaned_audio_data = None 
                st.session_state.voice_input_stage = None 
                st.rerun()
            else: 
                st.session_state.voice_input_stage = None
                st.rerun()

        with col_right:
            # Right column: conversation area, input, mic + send
            def handle_good_feedback(idx, content):
                store_feedback("It's a good feedback", "", content, st.session_state.conversation)

            st.markdown("**" + _t("chat_title") + "**")
            st.caption(_t("chat_caption"))
            chat_container = st.container(height=360)
            with chat_container:
                util = _get_utils(SARVAM_API_KEY)
                user_lang = st.session_state.current_language_code
                if not st.session_state.conversation:
                    st.markdown("<p class='healbee-welcome'>👋 <strong>Hi there.</strong> Tell me what’s on your mind — a symptom, a question about health, or how you’re feeling. I’ll do my best to help with information and next steps. If something feels urgent, please see a doctor.</p>", unsafe_allow_html=True)
                for idx, msg_data in enumerate(st.session_state.conversation):
                    role = msg_data.get("role", "system")
                    content = msg_data.get("content", "")
                    lang_display = msg_data.get('lang', st.session_state.current_language_code.split('-')[0])
                    # For assistant: remove symptom_name: prefix, strip **/bullets/emojis — clean paragraphs only (UI fix).
                    # For user/system: escape HTML only.
                    if role == "assistant":
                        cleaned = clean_assistant_text(content)
                        content_safe = markdown_to_html_safe(cleaned)
                    else:
                        content_safe = (
                            content
                            .replace("&", "&amp;")
                            .replace("<", "&lt;")
                            .replace(">", "&gt;")
                            .replace("\n", "<br>")
                        )

                    if role == "user":
                        st.markdown(f"""
                        <div style="display: flex; justify-content: flex-end; align-items: flex-start; gap: 0.5rem; margin-bottom: 0.6rem;">
                            <div style="flex: 0 0 auto; text-align: right;">
                                <div class="healbee-msg-label">You</div>
                                <div class="healbee-bubble-user">{content_safe}</div>
                            </div>
                            <div style="width: 28px; height: 28px; border-radius: 50%; border: 1px solid rgba(128,128,128,0.4); display: flex; align-items: center; justify-content: center; font-size: 14px; flex-shrink: 0;">👤</div>
                        </div>
                    """, unsafe_allow_html=True)
                    elif role == "assistant":
                        st.markdown(f"""
                        <div style="display: flex; justify-content: flex-start; align-items: flex-start; gap: 0.5rem; margin-bottom: 0.6rem;">
                            <div style="width: 28px; height: 28px; border-radius: 50%; border: 1px solid rgba(34,197,94,0.4); display: flex; align-items: center; justify-content: center; font-size: 14px; flex-shrink: 0;">🩺</div>
                            <div style="flex: 0 1 auto;">
                                <div class="healbee-msg-label">HealBee</div>
                                <div class="healbee-bubble-assistant">{content_safe}</div>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
                        clutter, col1, col2, col3, clutter = st.columns([1.75, 1, 1, 1, 30])
                        audio_bytes = None
                        good_feedback = False
                        with col1:
                            if st.button("👍", key=f"good_{idx}", type="tertiary", help="Helpful"):
                                good_feedback = True
                        with col2:
                            if st.button("👎", key=f"bad_{idx}", type="tertiary", help="Not helpful"):
                                st.session_state[f"negetive_feedback_{idx}"] = True

                        with col3:
                            if st.button("🔊", key=f"read_{idx}", type="tertiary", help="Listen"):
                                try:
                                    with spinner_placeholder.info("Speaking…"):
                                        audio_bytes = util.synthesize_speech(content, user_lang)
                                except Exception as e:
                                    audio_bytes = None
                                    st.warning("Voice playback is temporarily unavailable. Please try again later.")
                                
                        if good_feedback is True:
                            handle_good_feedback(idx, content)
                        if audio_bytes is not None:
                            st.audio(audio_bytes, format="audio/wav")
                        if st.session_state.get(f"negetive_feedback_{idx}", False):
                            with st.expander("What could we do better?", expanded=True):
                                user_email = st.text_input("Your Email Id", key=f"user_email_{idx}")
                                feedback_text = st.text_area("Your feedback", key=f"feedback_text_{idx}")
                                if st.button("Submit Feedback", key=f"submit_feedback_{idx}"):
                                    feedback_response = store_feedback(feedback_text, user_email, content, st.session_state.conversation)
                                    if feedback_response is True:
                                        st.session_state[f"negetive_feedback_{idx}"] = False  # Reset if needed after submission
                                        st.rerun()
                    else:
                        st.markdown(f"""
                        <div style="display: flex; justify-content: flex-start; align-items: flex-start; gap: 0.5rem; margin-bottom: 0.6rem;">
                            <div style="width: 28px; height: 28px; flex-shrink: 0;">ℹ️</div>
                            <div class="healbee-bubble-system">{content_safe}</div>
                        </div>
                    """, unsafe_allow_html=True)
                
            st.markdown("""
                <style>
                    button[kind="tertiary"] {
                        background: none !important; border: none !important; color: inherit !important;
                        padding: 0 !important; margin: 0 !important; font-size: 0rem !important;
                        line-height: 0 !important; width: auto !important; height: auto !important;
                    }
                </style>
            """, unsafe_allow_html=True)

            st.markdown("<p class='healbee-disclaimer'>This is general guidance only, not a diagnosis. When in doubt, see a doctor.</p>", unsafe_allow_html=True)
            st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
            is_recording = st.session_state.voice_input_stage == "recording"

            if st.session_state.symptom_checker_active and st.session_state.pending_symptom_question_data:
                input_label = "Your answer (Ctrl+Enter to send)"
            else:
                input_label = "What would you like to ask? Type or use the mic below."
        
            # Text area: no on_change to avoid duplicate messages (Enter + Send both firing). Submit only via Send button.
            st.text_area(input_label, height=70, key="text_query_input_area", disabled=is_recording)
            COLUMN_WIDTHS = [1, 1]
            col21, col22 = st.columns(COLUMN_WIDTHS)
            with col21:
                st.button("📤 Send", use_container_width=True, key="send_button_widget", disabled=is_recording, on_click=handle_text_submission)

            with col22:
                audio = mic_recorder(
                    start_prompt="🎙️ Record",
                    stop_prompt="⏹️ Stop",
                    just_once=True,  # Only returns audio once after recording
                    use_container_width=True,
                    format="wav",    # Or "webm" if you prefer
                    key="voice_recorder"
                )
            
            if audio:
                st.session_state.captured_audio_data = audio['bytes']
                st.rerun()

    elif st.session_state.active_page == "maps":
        st.subheader(_t("maps_title"))
        st.caption(_t("maps_caption"))
        # Ensure session state for map results
        if "near_me_results" not in st.session_state:
            st.session_state.near_me_results = []
        if "near_me_query" not in st.session_state:
            st.session_state.near_me_query = ""
        near_location = st.text_input("City or locality", key="maps_location_input", placeholder=_t("maps_search_placeholder"))
        if st.button(_t("search"), key="near_me_search"):
            if near_location and near_location.strip():
                with st.spinner("Searching…"):
                    try:
                        places = search_nearby_health_places(near_location.strip(), limit_per_type=8)
                    except Exception:
                        places = []
                st.session_state.near_me_results = places
                st.session_state.near_me_query = near_location.strip()
                st.rerun()
            else:
                st.warning("Enter a city or locality to search.")
        # Phase 4: Embedded Leaflet map (no redirect to OSM). White card styling via theme.
        map_html = _leaflet_map_html(st.session_state.near_me_results, height=480)
        components.html(map_html, height=500, scrolling=False)
        if st.session_state.get("near_me_results"):
            st.markdown(f"**{_t('results_for')} \"{st.session_state.near_me_query}\"**")
            for p in st.session_state.near_me_results:
                name = p.get("name") or "—"
                ptype = p.get("type") or "—"
                address = p.get("address") or "—"
                lat, lon = p.get("lat"), p.get("lon")
                link = make_osm_link(str(lat or ""), str(lon or "")) if lat and lon else ""
                st.markdown("""<div class="healbee-card">""", unsafe_allow_html=True)
                st.markdown(f"**{name}** — *{ptype}*")
                st.caption(address)
                if link:
                    st.markdown(f"[{_t('open_map')}]({link})")
                st.markdown("""</div>""", unsafe_allow_html=True)
        elif st.session_state.get("near_me_query"):
            st.info(_t("no_results"))

    elif st.session_state.active_page == "journal":
        st.subheader(_t("journal_title"))
        st.caption(_t("journal_desc"))
        # Journal: Add New Note — Title + Notes, session-only (no DB)
        if st.session_state.get("journal_show_add"):
            note_title = st.text_input(_t("note_title"), key="journal_title_input", placeholder="e.g. Check-up summary")
            note_text = st.text_area("Notes", key="journal_note_input", height=120, placeholder="Write your health note here…")
            sc1, sc2 = st.columns([1, 3])
            with sc1:
                if st.button(_t("save"), key="journal_save_btn"):
                    if (note_text or "").strip() or (note_title or "").strip():
                        entry = {
                            "source": "manual",
                            "title": (note_title or "").strip() or "Untitled",
                            "content": (note_text or "").strip(),
                            "datetime": datetime.now().isoformat(),
                        }
                        if "journal_entries" not in st.session_state:
                            st.session_state.journal_entries = []
                        uid = st.session_state.supabase_session.get("user_id") if st.session_state.get("supabase_session") else None
                        if is_supabase_configured() and uid:
                            db_journal_entry_insert(uid, entry)
                            st.session_state.journal_entries = db_journal_entries_list(uid)
                        else:
                            st.session_state.journal_entries.append(entry)
                    st.session_state.journal_show_add = False
                    for k in ("journal_note_input", "journal_title_input"):
                        if k in st.session_state:
                            del st.session_state[k]
                    st.rerun()
            with sc2:
                if st.button(_t("cancel"), key="journal_cancel_btn"):
                    st.session_state.journal_show_add = False
                    st.rerun()
        else:
            if st.button("➕ " + _t("add_note"), key="journal_add_btn"):
                st.session_state.journal_show_add = True
                st.rerun()
        entries = st.session_state.get("journal_entries") or []
        if not entries:
            st.markdown("""<div class="healbee-card"><p style="color: var(--healbee-text); opacity: 0.9;">""" + _t("empty_notes") + """</p></div>""", unsafe_allow_html=True)
        else:
            _from_chat_label = _t("journal_from_chat")
            for i, e in enumerate(reversed(entries)):
                dt_str = e.get("datetime", "")
                try:
                    dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                    if getattr(dt, "tzinfo", None):
                        dt = dt.replace(tzinfo=None)
                    dt_display = dt.strftime("%d %b %Y, %I:%M %p")
                except Exception:
                    dt_display = dt_str or "—"
                title = (e.get("title") or "Untitled").replace("<", "&lt;").replace(">", "&gt;")
                content = (e.get("content") or "").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
                from_chat = e.get("source") == "chat"
                badge = f'<span style="font-size: 0.75rem; background: var(--healbee-accent); color: white; padding: 2px 6px; border-radius: 4px; margin-left: 6px;">{_from_chat_label}</span>' if from_chat else ""
                st.markdown(f"""
                    <div class="healbee-card">
                        <div style="font-weight: 600; color: var(--healbee-text); margin-bottom: 0.25rem;">{title}{badge}</div>
                        <div style="font-size: 0.85rem; color: var(--healbee-accent); margin-bottom: 0.5rem;">{dt_display}</div>
                        <div style="color: var(--healbee-text); line-height: 1.5;">{content}</div>
                    </div>
                """, unsafe_allow_html=True)

    elif st.session_state.active_page == "reminders":
        st.subheader(_t("reminders_title"))
        st.caption(_t("reminders_desc"))
        reminders_list = st.session_state.get("reminders") or []
        if st.session_state.get("reminders_show_add"):
            rt = st.text_input(_t("reminder_title"), key="reminder_title_input", placeholder="e.g. Take medicine, Doctor visit")
            rd = st.date_input(_t("reminder_datetime"), key="reminder_date_input", value=datetime.now().date())
            rtime = st.time_input("Time", key="reminder_time_input", value=datetime.now().time())
            rn = st.text_input(_t("reminder_note"), key="reminder_note_input", placeholder="Optional note")
            rc1, rc2 = st.columns([1, 3])
            with rc1:
                if st.button(_t("save"), key="reminder_save_btn"):
                    title_clean = (rt or "").strip() or "Reminder"
                    when_iso = datetime(rd.year, rd.month, rd.day, rtime.hour, rtime.minute, rtime.second).isoformat()
                    note_clean = (rn or "").strip()
                    uid = st.session_state.supabase_session.get("user_id") if st.session_state.get("supabase_session") else None
                    if is_supabase_configured() and uid:
                        db_reminder_insert(uid, title_clean, when_iso, note_clean, False)
                        st.session_state.reminders = db_reminders_list(uid)
                    else:
                        reminders_list.append({
                            "id": f"rem_{len(reminders_list)}_{datetime.now().timestamp()}",
                            "title": title_clean,
                            "when_iso": when_iso,
                            "note": note_clean,
                            "done": False,
                        })
                        st.session_state.reminders = reminders_list
                    st.session_state.reminders_show_add = False
                    for k in ("reminder_title_input", "reminder_note_input", "reminder_date_input", "reminder_time_input"):
                        if k in st.session_state:
                            del st.session_state[k]
                    st.rerun()
            with rc2:
                if st.button(_t("cancel"), key="reminder_cancel_btn"):
                    st.session_state.reminders_show_add = False
                    st.rerun()
        else:
            if st.button("➕ " + _t("add_reminder"), key="reminders_add_btn"):
                st.session_state.reminders_show_add = True
                st.rerun()
        if not reminders_list:
            st.markdown("""<div class="healbee-card"><p style="color: var(--healbee-text); opacity: 0.9;">""" + _t("empty_reminders") + """</p></div>""", unsafe_allow_html=True)
        else:
            now = datetime.now()
            for r in reminders_list:
                when_str = r.get("when_iso", "")
                try:
                    when_dt = datetime.fromisoformat(when_str)
                    when_display = when_dt.strftime("%d %b %Y, %I:%M %p")
                    is_past = when_dt < now
                except Exception:
                    when_display = when_str or "—"
                    is_past = False
                title_safe = (r.get("title") or "—").replace("<", "&lt;").replace(">", "&gt;")
                note_safe = (r.get("note") or "").replace("<", "&lt;").replace(">", "&gt;").replace("\n", " ")
                rid = r.get("id", "")
                done = r.get("done", False)
                status = " ✓ " + _t("mark_done") if done else (" (" + _t("overdue") + ")" if is_past else "")
                st.markdown(f"""
                    <div class="healbee-card" style="margin-bottom: 0.75rem;">
                        <div style="font-weight: 600; color: var(--healbee-text);">{title_safe}{status}</div>
                        <div style="font-size: 0.85rem; color: var(--healbee-accent); margin-bottom: 0.25rem;">{when_display}</div>
                        <div style="font-size: 0.85rem; color: var(--healbee-text); opacity: 0.9;">{note_safe}</div>
                    </div>
                """, unsafe_allow_html=True)
                row1, row2 = st.columns([1, 4])
                with row1:
                    if st.button(_t("delete"), key=f"rem_del_{rid}"):
                        uid = st.session_state.supabase_session.get("user_id") if st.session_state.get("supabase_session") else None
                        if is_supabase_configured() and uid:
                            db_reminder_delete(uid, rid)
                            st.session_state.reminders = db_reminders_list(uid)
                        else:
                            st.session_state.reminders = [x for x in reminders_list if x.get("id") != rid]
                        st.rerun()
                with row2:
                    if not done and st.button(_t("mark_done"), key=f"rem_done_{rid}"):
                        uid = st.session_state.supabase_session.get("user_id") if st.session_state.get("supabase_session") else None
                        if is_supabase_configured() and uid:
                            db_reminder_update(uid, rid, done=True)
                            st.session_state.reminders = db_reminders_list(uid)
                        else:
                            for x in st.session_state.reminders:
                                if x.get("id") == rid:
                                    x["done"] = True
                                    break
                        st.rerun()

    elif st.session_state.active_page == "settings":
        st.subheader(_t("settings_title"))
        st.markdown(f"**{_t('app_language_label')}**")
        app_lang_options = {
            "en": "English",
            "ta": "தமிழ் (Tamil)",
            "ml": "മലയാളം (Malayalam)",
            "te": "తెలుగు (Telugu)",
            "hi": "हिन्दी (Hindi)",
            "kn": "ಕನ್ನಡ (Kannada)",
            "mr": "मराठी (Marathi)",
            "bn": "বাংলা (Bengali)",
        }
        current = st.session_state.get("app_language", "en")
        idx = list(app_lang_options.keys()).index(current) if current in app_lang_options else 0
        selected = st.selectbox(_t("app_language_label"), options=list(app_lang_options.keys()), format_func=lambda k: app_lang_options[k], index=idx, key="app_lang_select")
        if selected != current:
            st.session_state.app_language = selected
            st.rerun()
        st.caption(_t("settings_caption_short"))
        st.markdown("<div style='height: 24px;'></div>", unsafe_allow_html=True)
        # Logout only in Settings (Phase 3); with confirmation (Phase 6)
        if supabase_ok and st.session_state.supabase_session:
            if st.session_state.get("show_logout_confirm"):
                st.warning(_t("confirm_logout"))
                c1, c2 = st.columns(2)
                with c1:
                    if st.button(_t("yes_logout"), key="logout_confirm_yes"):
                        auth_sign_out()
                        st.session_state.supabase_session = None
                        st.session_state.chat_list = []
                        st.session_state.current_chat_id = None
                        st.session_state.conversation = []
                        st.session_state.reminders = []
                        st.session_state.journal_entries = []
                        st.session_state.persistent_memory = {}
                        st.session_state.show_logout_confirm = False
                        st.rerun()
                with c2:
                    if st.button(_t("cancel"), key="logout_confirm_cancel"):
                        st.session_state.show_logout_confirm = False
                        st.rerun()
            else:
                if st.button(_t("logout"), key="logout_btn_settings"):
                    st.session_state.show_logout_confirm = True
                    st.rerun()
        # Optional: clear session data (conversation, journal, etc.) — UI only
        st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)
        if st.button(_t("clear_session"), key="clear_session_btn"):
            st.session_state.conversation = []
            st.session_state.journal_entries = []
            st.session_state.extracted_symptoms = []
            st.session_state.follow_up_answers = []
            st.session_state.last_advice_given = ""
            st.session_state.user_profile = {}
            st.session_state.symptom_checker_active = False
            st.session_state.symptom_checker_instance = None
            st.session_state.pending_symptom_question_data = None
            st.success("Session data cleared.")
            st.rerun()


if __name__ == "__main__":
    main_ui()