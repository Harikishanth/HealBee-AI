import json
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import requests
import numpy as np
import base64
from pydub import AudioSegment
import io
import soundfile as sf

class HealBeeUtilities:
    """Core utilities for HealBee healthcare application"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_api_url = "https://api.sarvam.ai"
        self._initialize_language_support()

    def _initialize_language_support(self):
        """Initialize language configurations"""
        self.LANGUAGE_MAP = {
            "en-IN": {
                "display": "English",
                "disclaimer": "This information is for general knowledge and informational purposes only, and does not constitute professional advice."
            },
            "hi-IN": {
                "display": "हिन्दी",
                "disclaimer": "यह जानकारी केवल सामान्य ज्ञान और सूचनात्मक उद्देश्यों के लिए है, और इसे पेशेवर सलाह नहीं माना जाना चाहिए।"
            },
            "bn-IN": {
                "display": "বাংলা",
                "disclaimer": "এই তথ্য শুধুমাত্র সাধারণ জ্ঞান এবং তথ্যের উদ্দেশ্যে, এবং পেশাদারী পরামর্শ হিসাবে গণ্য করা উচিত নয়।"
            },
            "mr-IN": {
                "display": "मराठी",
                "disclaimer": "ही माहिती केवळ सामान्य ज्ञान आणि माहितीच्या उद्देशाने आहे आणि याला व्यावसायिक सल्ला मानले जाऊ नये."
            },
            "kn-IN": {
                "display": "ಕನ್ನಡ",
                "disclaimer": "ಈ ಮಾಹಿತಿಯು ಸಾಮಾನ್ಯ ಜ್ಞಾನ ಮತ್ತು ಮಾಹಿತಿ ಉದ್ದೇಶಗಳಿಗಾಗಿ ಮಾತ್ರ, ಮತ್ತು ಇದನ್ನು ವೃತ್ತಿಪರ ಸಲಹೆಯೆಂದು ಪರಿಗಣಿಸಬಾರದು."
            },
            "ta-IN": {
                "display": "தமிழ்",
                "disclaimer": "இந்தத் தகவல் பொது அறிவு மற்றும் தகவல் நோக்கங்களுக்காக மட்டுமே, மேலும் இது தொழில்முறை ஆலோசனை எனக் கருதப்படக்கூடாது."
            },
            "te-IN": {
                "display": "తెలుగు",
                "disclaimer": "ఈ సమాచారం సాధారణ జ్ఞానం మరియు సమాచార ప్రయోజనాల కోసం మాత్రమే, మరియు దీనిని వృత్తిపరమైన సలహాగా పరిగణించరాదు."
            },
            "ml-IN": {
                "display": "മലയാളം",
                "disclaimer": "ഈ വിവരങ്ങൾ പൊതുവായ അറിവിനും വിവരങ്ങൾക്കും മാത്രമുള്ളതാണ്, ഇത് ഒരു പ്രൊഫഷണൽ ഉപദേശമായി കണക്കാക്കരുത്."
            }
            # Add other supported Indian languages
        }

    def clean_whitespace(self, text:str):
        # Replace multiple whitespace characters (spaces, tabs, etc.) with a single space
        cleaned = re.sub(r'\s+', ' ', text)
        return cleaned.strip()  # Remove leading/trailing spaces

    def translate_text(self, text: str, target_lang: str) -> str:
        """
        Translate text to target language using Sarvam-M
        Args:
            text: Text to translate
            target_lang: Target language code (e.g., 'hi-IN')
        """
        if target_lang.startswith("en"):
            return text  # No translation needed for English

        headers = {"api-subscription-key": self.api_key}
        payload = {
            "input": text,
            "target_language_code": target_lang,
            "source_language_code": 'auto',
            "mode": "formal",
            "model": "mayura:v1",
        }

        try:
            response = requests.post(
                f"{self.base_api_url}/translate",
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            return self.clean_whitespace(response.json()["translated_text"])
        except Exception as e:
            print(f"Translation error: {e}")
            return text  # Fallback to original

    def translate_text_to_english(self, text: str) -> str:
        """
        Translate text to target language using Sarvam-M
        Args:
            text: Text to translate
        """
        
        headers = {"api-subscription-key": self.api_key}
        payload = {
            "input": text,
            "target_language_code": 'en-IN',
            "source_language_code": 'auto',
            "mode": "formal",
            "model": "mayura:v1",
        }

        try:
            response = requests.post(
                f"{self.base_api_url}/translate",
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            return self.clean_whitespace(response.json()["translated_text"])
        except Exception as e:
            print(f"Translation error: {e}")
            return text  # Fallback to original

    def synthesize_speech(self, text, language_code):
        """
        Synthesize speech using Sarvam or another TTS API.
        Returns audio bytes (e.g., MP3 or WAV).
        """
        
        headers = {"api-subscription-key": self.api_key}
        payload = {
            "text": text,
            "target_language_code": language_code,
            "speaker": 'abhilash',
            "pitch": 0,
            "pace": 1.0,
            "loudness": 1.0,
            "speech_sample_rate": 22050,
        }

        try:
            response = requests.post(
                f"{self.base_api_url}/text-to-speech",
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            segments = []
            for b64_wav in result["audios"]:
                # Decode base64 to bytes
                audio_bytes = base64.b64decode(b64_wav)
                
                # Create in-memory file-like object
                audio_file = io.BytesIO(audio_bytes)
                
                # Load audio segment
                segment = AudioSegment.from_wav(audio_file)
                segments.append(segment)

            # Concatenate all segments
            merged_audio = sum(segments[1:], segments[0])

            # Export to bytes
            output = io.BytesIO()
            merged_audio.export(output, format="wav")
            return output.getvalue()
        except Exception as e:
            print(f"Speech synthesis error: {e}")
            return None

    def transcribe_audio(self, audio_data, sample_rate=48000, source_language="hi-IN"):
        """
        Send cleaned audio to Sarvam's Saarika v2 for transcription
        
        Args:
            audio_data: Cleaned audio data (int16)
            sample_rate: Audio sample rate
            source_language: Source language code (e.g., "hi-IN", "ta-IN", etc.)
        """
        
        audio_buffer = io.BytesIO()
        sf.write(audio_buffer, audio_data, sample_rate, format='WAV')
        audio_buffer.seek(0)

        headers = {
            "api-subscription-key": self.api_key
        }
        files = {
            "file": ("audio.wav", audio_buffer, "audio/wav")
        }
        payload = {
            "language_code": source_language
        }

        try:
            response = requests.post(
                f"{self.base_api_url}/speech-to-text",
                headers=headers,
                data=payload,
                files=files,
                timeout=60
            )
            response.raise_for_status()
            result = response.json()
            transcription = result.get("transcript", "")
            language_detected = result.get("language_code", source_language)
            return {
                "transcription": transcription,
                "language_detected": language_detected
            }
        except requests.RequestException as e:
            print(f"❌ Sarvam STT API call failed: {e}")
            return {
                "transcription": "",
                "language_detected": source_language
            }


    def batch_translate(self, texts: List[str], target_lang: str) -> List[str]:
        """Optimized batch translation for multiple texts"""
        if target_lang.startswith("en"):
            return texts

        headers = {"api-subscription-key": self.api_key}
        payload = {
            "texts": texts,
            "target_lang": target_lang,
            "context": "healthcare"
        }

        try:
            response = requests.post(
                f"{self.base_api_url}/translate/batch",
                headers=headers,
                json=payload,
                timeout=45
            )
            response.raise_for_status()
            return response.json()["translations"]
        except Exception as e:
            print(f"Batch translation error: {e}")
            return texts

    def detect_language(self, text: str) -> str:
        """Robust language detection with code-mixing support"""
        # First check for strong indicators
        if re.search(r"[\u0900-\u097F]", text):  # Hindi/Sanskrit Unicode range
            return "hi-IN"
        if re.search(r"[\u0B80-\u0BFF]", text):  # Tamil
            return "ta-IN"
        
        # Fallback to API detection
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            response = requests.post(
                f"{self.base_api_url}/detect-language",
                headers=headers,
                json={"text": text},
                timeout=15
            )
            response.raise_for_status()
            return response.json().get("language", "en-IN")
        except Exception as e:
            print(f"Language detection error: {e}")
            return "en-IN"

    def get_display_language(self, lang_code: str) -> str:
        """Get user-friendly language name"""
        return self.LANGUAGE_MAP.get(lang_code, {}).get("display", "English")

    def get_disclaimer(self, lang_code: str) -> str:
        """Get localized disclaimer text"""
        return self.LANGUAGE_MAP.get(lang_code, {}).get("disclaimer", "")

    @staticmethod
    def normalize_audio(audio_data: np.ndarray, target_db: float = -20.0) -> np.ndarray:
        """Normalize audio to target decibel level"""
        if audio_data.size == 0:
            return audio_data
            
        rms = np.sqrt(np.mean(audio_data**2))
        if rms == 0:
            return audio_data
            
        target_linear = 10 ** (target_db / 20)
        return audio_data * (target_linear / rms)

@dataclass
class HealthSafetyResult:
    is_emergency: bool
    requires_redirect: bool
    message: str
    detected_issues: List[str]

def create_safety_layer() -> HealthSafetyResult:
    """Factory for health safety result objects"""
    return HealthSafetyResult(
        is_emergency=False,
        requires_redirect=False,
        message="",
        detected_issues=[]
    )


# --- Journal: time-reference parsing and relevant-entry retrieval ---

def _parse_time_reference_from_message(message: str) -> Optional[tuple]:
    """
    Parse user message for time references like "last week", "yesterday", "a few days ago".
    Returns (start_dt, end_dt) as datetime objects (both inclusive) or None if no clear reference.
    """
    if not message or not isinstance(message, str):
        return None
    text = message.lower().strip()
    now = datetime.now()
    # "yesterday" -> 1–2 days ago
    if re.search(r"\byesterday\b", text):
        end = now - timedelta(days=1)
        start = now - timedelta(days=2)
        return (start, end)
    # "last week" / "past week" -> 7–14 days ago (previous calendar week) or last 7 days
    if re.search(r"\blast\s+week\b|\bpast\s+week\b|\bprevious\s+week\b", text):
        end = now - timedelta(days=7)
        start = now - timedelta(days=14)
        return (start, end)
    # "a few days ago" / "few days back"
    if re.search(r"\bfew\s+days\s+ago\b|\bfew\s+days\s+back\b|\ba\s+couple\s+of\s+days\b", text):
        end = now - timedelta(days=2)
        start = now - timedelta(days=10)
        return (start, end)
    # "last month"
    if re.search(r"\blast\s+month\b|\bpast\s+month\b|\bprevious\s+month\b", text):
        end = now - timedelta(days=30)
        start = now - timedelta(days=60)
        return (start, end)
    # "last time" / "that time" / "before" / "previously" / "earlier" -> no specific range; caller can use recent entries
    if re.search(r"\blast\s+time\b|\bthat\s+time\b|\bbefore\b|\bpreviously\b|\bearlier\b|\bthat\s+problem\b|\bsame\s+(issue|problem)\b|\bi\s+had\s+this\b", text):
        # Return "recent" window: last 30 days
        end = now
        start = now - timedelta(days=30)
        return (start, end)
    return None


def get_relevant_journal_entries(user_message: str, journal_entries: List[Dict[str, Any]], max_entries: int = 5) -> List[Dict[str, Any]]:
    """
    Return journal entries relevant to the user message (e.g. "I had this problem last week").
    - If message contains a time reference (last week, yesterday, etc.), filter entries by that date range.
    - If no time reference but message suggests past context (previously, that problem), return recent entries.
    - Otherwise return up to max_entries most recent entries for continuity.
    """
    if not journal_entries:
        return []
    # Parse datetime for each entry
    now = datetime.now()
    entries_with_dt: List[tuple] = []
    for e in journal_entries:
        dt_str = e.get("datetime") or ""
        try:
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            if dt.tzinfo:
                dt = dt.replace(tzinfo=None)  # naive compare with now
            entries_with_dt.append((dt, e))
        except Exception:
            entries_with_dt.append((now, e))
    time_range = _parse_time_reference_from_message(user_message)
    if time_range:
        start_dt, end_dt = time_range
        # Include entries whose datetime is in [start_dt, end_dt]
        in_range = [(dt, e) for dt, e in entries_with_dt if start_dt <= dt <= end_dt]
        if in_range:
            in_range.sort(key=lambda x: x[0], reverse=True)
            return [e for _, e in in_range[:max_entries]]
    # No time range or no matches: return most recent entries
    entries_with_dt.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in entries_with_dt[:max_entries]]


# --- Reminders: detect "set a reminder for X" from chat (multilingual) ---
# Triggers in 8 languages: English, Hindi, Tamil, Malayalam, Telugu, Kannada, Marathi, Bengali.
# Reminder text is stored as-is in the user's language (no translation).
REMINDER_TRIGGER_PHRASES = [
    # English
    "set a medication reminder for",
    "set medication reminder for",
    "medication reminder for",
    "i want to set a reminder for",
    "i'd like to set a reminder for",
    "can you set a reminder for",
    "could you set a reminder for",
    "can you remind me to",
    "could you remind me to",
    "set a reminder for",
    "set reminder for",
    "remind me to",
    "remind me for",
    "add a reminder for",
    "add reminder for",
    "create a reminder for",
    "remember to",
    "please remind me to",
    "please set a reminder for",
    "i need a reminder for",
    "i need to be reminded to",
    "reminder for",
    # Hindi (romanized / Devanagari)
    "reminder set karo",
    "reminder add karo",
    "mujhe yaad dilana",
    "yaad dilana",
    "reminder set karo for",
    "reminder add karo for",
    "मुझे याद दिलाना",
    "रिमाइंडर सेट करो",
    "रिमाइंडर एड करो",
    # Tamil
    "நினைவூட்டல் வைக்க",
    "நினைவூட்டல் சேர்",
    "எனக்கு நினைவூட்டல்",
    "reminder set",
    # Malayalam
    "ഓർമ്മപ്പെടുത്തൽ വയ്ക്കുക",
    "ഓർമ്മപ്പെടുത്തൽ ചേർക്കുക",
    "reminder add",
    # Telugu
    "జ్ఞాపకం పెట్టండి",
    "జ్ఞాపకం జోడించండి",
    "reminder పెట్టండి",
    # Kannada
    "ಜ್ಞಾಪನೆ ಹಾಕಿ",
    "ಜ್ಞಾಪನೆ ಸೇರಿಸಿ",
    # Marathi
    "स्मरणपत्र सेट करा",
    "स्मरणपत्र जोडा",
    "मला आठवण करून द्या",
    # Bengali
    "অনুস্মারক সেট করুন",
    "অনুস্মারক যোগ করুন",
    "আমাকে মনে করিয়ে দিন",
]


def detect_and_extract_reminder(message: str) -> Optional[Dict[str, str]]:
    """
    Detect if the user message is asking to set a reminder and extract the reminder text.
    Works in any of the 8 supported languages; the extracted title is stored as-is (user's language).
    Returns None if no reminder intent, else {"title": "...", "note": "..."}.
    """
    if not message or not isinstance(message, str):
        return None
    text = message.strip()
    if len(text) < 5:
        return None
    text_lower = text.lower()
    # Do not treat symptom descriptions as reminder requests: if the message clearly describes
    # symptoms (fever, cough, headache, etc.) and has no reminder wording, return None so the
    # symptom checker can handle it.
    symptom_like = any(
        w in text_lower
        for w in (
            "fever", "cough", "headache", "pain", "stomach", "cold", "throat", "nausea",
            "dizzy", "fatigue", "rash", "vomit", "diarrhea", "chest", "breath", "body ache",
        )
    )
    reminder_wording = "remind" in text_lower or "reminder" in text_lower
    if symptom_like and not reminder_wording:
        return None
    best_match: Optional[tuple] = None  # (trigger, position)
    for trigger in REMINDER_TRIGGER_PHRASES:
        if len(trigger) < 2:
            continue
        if trigger.isascii():
            pos = text_lower.find(trigger.lower())
        else:
            pos = text.find(trigger)
        if pos == -1:
            continue
        # Prefer longer trigger match so "set a reminder for" wins over "reminder for"
        if best_match is None or len(trigger) > len(best_match[0]):
            best_match = (trigger, pos)
    if best_match is None:
        return None
    trigger, pos = best_match
    remainder = text[pos + len(trigger):].strip()
    # Remove leading "to " / "for " / ":" if present for cleaner title
    for prefix in ("to ", "for ", ": ", " - ", " – "):
        if remainder.lower().startswith(prefix):
            remainder = remainder[len(prefix):].strip()
            break
    if len(remainder) < 2:
        return None
    title = remainder[:200].strip()
    return {"title": title, "note": ""}


# --- Journal: detect "add to my journal: X" from chat (multilingual) ---
JOURNAL_TRIGGER_PHRASES = [
    # English
    "add to my journal",
    "add to journal",
    "save to my journal",
    "save to journal",
    "save this to my journal",
    "add this to my journal",
    "write in my journal",
    "note in my journal",
    "record in my journal",
    "put this in my journal",
    "journal this",
    "add a journal entry for",
    "save a note for",
    "remember this in my journal",
    "add a health note for",
    "save a health note for",
    "add to my journal:",
    "save to my journal:",
    "add to journal:",
    "save to journal:",
    # Hindi (romanized / Devanagari)
    "journal mein add karo",
    "journal mein save karo",
    "is ko journal mein likho",
    "जर्नल में जोड़ें",
    "जर्नल में सहेजें",
    # Tamil
    "ஜர்னலில் சேர்",
    "ஜர்னலில் எழுது",
    # Malayalam
    "ജേണലിൽ ചേർക്കുക",
    "ജേണലിൽ എഴുതുക",
    # Telugu
    "జర్నల్‌లో చేర్చండి",
    "జర్నల్‌లో ఇవ్వండి",
    # Kannada
    "ಜರ್ನಲ್‌ಗೆ ಸೇರಿಸಿ",
    "ಜರ್ನಲ್‌ಗೆ ಬರೆಯಿರಿ",
    # Marathi
    "जर्नल मध्ये जोडा",
    "जर्नल मध्ये लिहा",
    # Bengali
    "জার্নালে যোগ করুন",
    "জার্নালে লিখুন",
]


def detect_and_extract_journal(message: str) -> Optional[Dict[str, str]]:
    """
    Detect if the user message is asking to add something to their journal and extract the note.
    Returns None if no journal intent, else {"title": "...", "content": "..."}.
    Title is first line or first 80 chars; content is full remainder (user's language, stored as-is).
    """
    if not message or not isinstance(message, str):
        return None
    text = message.strip()
    if len(text) < 5:
        return None
    text_lower = text.lower()
    best_match: Optional[tuple] = None  # (trigger, position)
    for trigger in JOURNAL_TRIGGER_PHRASES:
        if len(trigger) < 2:
            continue
        if trigger.isascii():
            pos = text_lower.find(trigger.lower())
        else:
            pos = text.find(trigger)
        if pos == -1:
            continue
        if best_match is None or len(trigger) > len(best_match[0]):
            best_match = (trigger, pos)
    if best_match is None:
        return None
    trigger, pos = best_match
    remainder = text[pos + len(trigger):].strip()
    for prefix in ("this:", "that:", ":", " - ", " – ", "for ", "to "):
        if remainder.lower().startswith(prefix):
            remainder = remainder[len(prefix):].strip()
            break
    if len(remainder) < 2:
        return None
    content = remainder[:5000].strip()
    first_line = content.split("\n")[0].strip() if content else ""
    title = (first_line[:80] if first_line else content[:80] or "Note from chat").strip()
    return {"title": title, "content": content}


# --- Nearby hospitals/clinics: detect "find nearby hospitals" from chat (multilingual) ---
# Common typos for nearby/hospital/clinic (normalized before matching)
NEARBY_PLACES_TYPO_MAP = [
    ("neraby", "nearby"),
    ("near by", "nearby"),
    ("hosptial", "hospital"),
    ("hosptials", "hospitals"),
    ("hospial", "hospital"),
    ("clininc", "clinic"),
]

NEARBY_PLACES_TRIGGER_PHRASES = [
    # English
    "find the nearby hospitals",
    "find the nearby clinics",
    "find nearby hospitals",
    "find nearby clinics",
    "nearby hospitals to me",
    "nearby clinics to me",
    "nearby hospitals",
    "nearby clinics",
    "hospitals near me",
    "clinics near me",
    "find hospitals near me",
    "find clinics near me",
    "where are the nearest hospitals",
    "where are the nearest clinics",
    "nearest hospital",
    "nearest clinic",
    "hospitals within 10 km",
    "clinics within 10 km",
    "show me nearby hospitals",
    "show me nearby clinics",
    "list nearby hospitals",
    "list nearby clinics",
    # Hindi (romanized / Devanagari)
    "paas ke hospital",
    "paas ke clinic",
    "nazdeek hospital",
    "nazdeek clinic",
    "मेरे पास अस्पताल",
    "नजदीकी अस्पताल",
    "नजदीकी क्लिनिक",
    # Tamil
    "அருகிலுள்ள மருத்துவமனை",
    "அருகிலுள்ள கிளினிக்",
    "பக்கத்தில் இருக்கிற மருத்துவமனை",
    "பக்கத்தில் இருக்கிற கிளினிக்",
    "எனக்கு அருகிலுள்ள மருத்துவமனைகள்",
    "எனக்கு அருகிலுள்ள கிளினிக்",
    "பெரும்பாலான மருத்துவமனைகள்",
    # Malayalam
    "അടുത്തുള്ള ആശുപത്രി",
    "അടുത്തുള്ള ക്ലിനിക്",
    # Telugu
    "దగ్గరి హాస్పిటల్",
    "దగ్గరి క్లినిక్",
    # Kannada
    "ಹತ್ತಿರದ ಆಸ್ಪತ್ರೆ",
    "ಹತ್ತಿರದ ಕ್ಲಿನಿಕ್",
    # Marathi
    "जवळचे रुग्णालय",
    "जवळचे क्लिनिक",
    # Bengali
    "কাছের হাসপাতাল",
    "কাছের ক্লিনিক",
]


def detect_nearby_places_request(message: str) -> bool:
    """
    Detect if the user is explicitly asking to find nearby hospitals or clinics.
    Returns True if the message clearly requests nearby hospitals/clinics (in any supported language).
    Normalizes common typos (e.g. neraby -> nearby) before matching.
    """
    if not message or not isinstance(message, str):
        return False
    text = message.strip()
    if len(text) < 4:
        return False
    text_lower = text.lower()
    for wrong, right in NEARBY_PLACES_TYPO_MAP:
        text_lower = text_lower.replace(wrong, right)
    for trigger in NEARBY_PLACES_TRIGGER_PHRASES:
        if len(trigger) < 2:
            continue
        if trigger.isascii():
            if trigger.lower() in text_lower:
                return True
        else:
            if trigger in text:
                return True
    # Standalone location name (e.g. "வேளச்சேரி", "Velachery") = nearby request with that location
    if len(text) <= 60 and extract_nearby_location(message) is not None:
        return True
    return False


def extract_nearby_location(message: str) -> Optional[str]:
    """
    Extract a location name from a message that is a nearby-places request.
    E.g. "find nearby clinics in Velachery" -> "Velachery",
         "find nearby clinics in Velachery–Tambaram area" -> "Velachery–Tambaram",
         "near Guindy" -> "Guindy".
    Returns None if no location found (e.g. "near me", "to me") or message is not relevant.
    """
    if not message or not isinstance(message, str):
        return None
    text = message.strip()
    if len(text) < 4:
        return None
    text_lower = text.lower()
    for wrong, right in NEARBY_PLACES_TYPO_MAP:
        text_lower = text_lower.replace(wrong, right)
    # "near me" / "to me" without a place name -> no location
    if "near me" in text_lower or text_lower.rstrip().endswith("to me"):
        return None
    # Prefer " in X" then " near X" (X != me) then " at X"
    for sep in (" in ", " near ", " at "):
        idx = text_lower.find(sep)
        if idx == -1:
            continue
        after = text[idx + len(sep):].strip()
        if not after:
            continue
        if sep == " near " and after.lower().split()[0] == "me":
            continue
        # Take up to " area", " locality", " region", " place" or end; limit length
        for suffix in (" area", " locality", " region", " place"):
            if after.lower().endswith(suffix):
                after = after[: -len(suffix)].strip()
            elif suffix in after.lower():
                pos = after.lower().find(suffix)
                after = after[:pos].strip()
        after = after.strip(".,;:-").strip()
        if len(after) >= 2 and len(after) <= 120:
            return after
    # Standalone location name: whole message is the place (e.g. "வேளச்சேரி", "Velachery")
    if len(text) <= 50 and "near me" not in text_lower and "to me" not in text_lower.rstrip():
        if " in " not in text_lower and " near " not in text_lower and " at " not in text_lower:
            words = text.split()
            if 1 <= len(words) <= 4:
                # Do not treat symptom words as location
                symptom_blocklist = (
                    "fever", "cough", "headache", "pain", "cold", "throat", "nausea", "dizzy",
                    "fatigue", "rash", "vomit", "diarrhea", "chest", "stomach", "breath", "body",
                    "காய்ச்சல்", "இருமல்", "தலைவலி", "வயிறு", "மூக்கு",
                )
                first_lower = words[0].lower() if words else ""
                if first_lower not in symptom_blocklist and not first_lower.isdigit():
                    return text.strip()
    return None
