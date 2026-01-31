from typing import Optional, Dict, List, Any

from src.nlu_processor import NLUResult, HealthIntent, SarvamAPIClient
from src.prompts import HEALTHCARE_SYSTEM_PROMPT


def build_user_context(session_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    TASK 1 — Build user_context before every AI call.
    Source: st.session_state.user_profile, persistent_memory, past_messages (summaries only).
    EXACT SHAPE: identity, health_profile, conversation_memory. Omit empty/None. No raw DB, no full chats, ~200-300 tokens.
    """
    if not session_context:
        return {}
    profile = session_context.get("user_profile") or {}
    mem = session_context.get("user_memory") or {}
    past = session_context.get("past_messages") or []
    if not profile and not mem and not past:
        return {}

    user_context = {}

    # identity: name, age, gender ("male"|"female"|"other"|None)
    identity = {}
    if profile.get("name"):
        identity["name"] = (profile["name"] or "").strip() or None
    if profile.get("age") is not None:
        identity["age"] = profile["age"]
    g = (profile.get("gender") or "").strip().lower()
    if g in ("male", "female", "other"):
        identity["gender"] = g
    elif g == "prefer_not_to_say":
        identity["gender"] = None
    elif g:
        identity["gender"] = g
    if identity:
        user_context["identity"] = identity

    # health_profile: chronic_conditions, allergies (list), pregnancy_status, additional_notes
    health = {}
    chronic = list(profile.get("chronic_conditions") or []) + [
        c for c in (profile.get("medical_history") or profile.get("known_conditions") or []) if c
    ]
    if chronic:
        health["chronic_conditions"] = chronic[:15]
    allergies_list = profile.get("allergies")
    if isinstance(allergies_list, str) and allergies_list.strip():
        health["allergies"] = [a.strip() for a in allergies_list.split(",") if a.strip()][:10]
    elif isinstance(allergies_list, list) and allergies_list:
        health["allergies"] = allergies_list[:10]
    if profile.get("pregnancy_status") is not None:
        health["pregnancy_status"] = bool(profile["pregnancy_status"])
    notes = (profile.get("additional_notes") or "").strip()
    if notes:
        health["additional_notes"] = notes[:300]
    if health:
        user_context["health_profile"] = health

    # conversation_memory: recent_health_summary (str) — summarized only, no dump, cap tokens
    parts = []
    if mem.get("last_symptoms"):
        parts.append((mem["last_symptoms"] or "")[:200])
    if mem.get("last_advice"):
        parts.append("Last advice: " + (mem["last_advice"] or "")[:150])
    if past:
        for m in past[:5]:
            role = m.get("role") or "user"
            content = (m.get("content") or "").strip()[:100]
            if content:
                parts.append(f"{role}: {content}")
    summary = " ".join(parts)[:400] if parts else None
    if summary:
        user_context["conversation_memory"] = {"recent_health_summary": summary}

    return user_context


def user_context_to_prompt_text(user_context: Dict[str, Any]) -> str:
    """
    TASK 2 — Convert user_context to plain English bullet-point text for the system prompt.
    Human-readable, bullet points only, neutral tone, no assumptions, no medical conclusions.
    """
    if not user_context:
        return ""
    lines = ["KNOWN USER INFORMATION (use only when relevant):", ""]

    identity = user_context.get("identity") or {}
    if identity:
        lines.append("Identity:")
        if identity.get("name"):
            lines.append("- Name: " + str(identity["name"]).strip())
        if identity.get("age") is not None:
            lines.append("- Age: " + str(identity["age"]))
        if identity.get("gender"):
            g = str(identity["gender"]).strip().lower()
            if g == "male":
                lines.append("- Gender: Male")
            elif g == "female":
                lines.append("- Gender: Female")
            elif g == "other":
                lines.append("- Gender: Other")
            else:
                lines.append("- Gender: " + g)
        lines.append("")

    health = user_context.get("health_profile") or {}
    if health:
        lines.append("Health background:")
        if health.get("chronic_conditions"):
            for c in health["chronic_conditions"][:10]:
                if c:
                    lines.append("- Chronic condition: " + str(c).strip())
        if health.get("allergies"):
            for a in health["allergies"][:10]:
                if a:
                    lines.append("- Allergy: " + str(a).strip())
        if health.get("pregnancy_status") is True:
            lines.append("- Pregnancy status: Yes")
        elif health.get("pregnancy_status") is False:
            lines.append("- Pregnancy status: No")
        if health.get("additional_notes"):
            lines.append("- Additional notes: " + (str(health["additional_notes"])[:200]).strip())
        lines.append("")

    conv = user_context.get("conversation_memory") or {}
    summary = conv.get("recent_health_summary")
    if summary and str(summary).strip():
        lines.append("Recent health history:")
        lines.append("- " + str(summary).strip()[:300])
        lines.append("")

    if len(lines) <= 2:
        return ""
    return "\n".join(lines).strip()

class HealBeeResponseGenerator:
    def __init__(self, api_key: Optional[str] = None):
        self.sarvam_client = SarvamAPIClient(api_key=api_key)

    def _get_hardcoded_safety_response(self, nlu_result: NLUResult) -> Optional[str]:
        """
        Provides immediate hardcoded responses for critical safety scenarios
        based on NLU output.
        """
        # Determine language for response (simplified, assumes NLU provides it or defaults)
        lang = nlu_result.language_detected.split('-')[0] if nlu_result.language_detected else "en"

        if nlu_result.is_emergency:
            if lang == "hi":
                return "आपके द्वारा बताए गए लक्षण गंभीर लग रहे हैं और इसके लिए तत्काल चिकित्सा ध्यान देने की आवश्यकता हो सकती है। कृपया तुरंत डॉक्टर से सलाह लें या नजदीकी अस्पताल जाएँ। मैं आपातकालीन चिकित्सा सहायता प्रदान करने के लिए सुसज्जित नहीं हूँ।"
            else: # Default to English
                return "The symptoms you're describing sound serious and may require immediate medical attention. Please consult a doctor or go to the nearest hospital right away. I am not equipped to provide emergency medical assistance."

        if nlu_result.intent == HealthIntent.DIAGNOSIS_REQUEST:
            if lang == "hi":
                return "मैं समझता/सकती हूँ कि आप उत्तर ढूंढ रहे हैं, लेकिन मैं मेडिकल निदान प्रदान नहीं कर सकता/सकती। किसी भी स्वास्थ्य चिंता या निदान के लिए, कृपया एक योग्य स्वास्थ्य पेशेवर से सलाह लें।"
            else: # Default to English
                return "I understand you're looking for answers, but I cannot provide a medical diagnosis. For any health concerns or to get a diagnosis, it's very important to consult a qualified healthcare professional."

        if nlu_result.intent == HealthIntent.MEDICATION_INFO and "advice" in nlu_result.original_text.lower(): # Simple check
             # More robust check for treatment/medication advice needed in NLU
            if lang == "hi":
                return "मैं उपचार सलाह या विशिष्ट दवाएं सुझाने में असमर्थ हूँ। उपचार, दवाओं या अपनी स्वास्थ्य स्थिति के प्रबंधन के बारे में किसी भी प्रश्न के लिए, कृपया अपने डॉक्टर या एक योग्य स्वास्थ्य सेवा प्रदाता से सलाह लें।"
            else: # Default to English
                return "I am unable to offer treatment advice or suggest specific medications. Please consult with your doctor or a qualified healthcare provider for any questions about treatments, medications, or managing your health condition."
        return None

    def generate_response(
        self,
        user_query: str,
        nlu_result: NLUResult,
        session_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Generates a response based on the user query and NLU result.
        Applies a two-layer safety check.
        session_context: optional dict with extracted_symptoms, follow_up_answers, last_advice_given,
        and user_profile (age, gender, weight_kg, known_conditions, preferred_language) for
        tone, follow-up relevance, and continuity only; never for diagnosis or medical conclusions.
        """
        # Layer 1: Application-level hardcoded safety responses
        safety_response = self._get_hardcoded_safety_response(nlu_result)
        if safety_response:
            print("ℹ️ Applying hardcoded safety response.")
            return safety_response

        # TASK 3 — Build user_context, convert to text, inject into SYSTEM prompt (not user message)
        user_context = build_user_context(session_context)
        formatted = user_context_to_prompt_text(user_context)
        system_content = HEALTHCARE_SYSTEM_PROMPT
        if formatted:
            system_content += "\n\n---\n\nCURRENT USER CONTEXT (trusted information):\n\n" + formatted

        # Layer 3: LLM-level response generation with system prompt including user_context
        print(f"💬 Generating response for query: '{user_query}' using LLM.")

        user_content = f"User query: \"{user_query}\"\nDetected language: {nlu_result.language_detected}\nNLU Intent: {nlu_result.intent.value}\nNLU Entities: {[e.text for e in nlu_result.entities]}"
        if session_context:
            parts = []
            if session_context.get("extracted_symptoms"):
                parts.append(f"Previously mentioned symptoms in this session: {', '.join(session_context['extracted_symptoms'][:20])}")
            if session_context.get("follow_up_answers"):
                fa = session_context["follow_up_answers"][-10:]
                parts.append("Follow-up answers from this session: " + "; ".join(
                    f"{x.get('symptom_name', '')}: {x.get('answer', '')[:80]}" for x in fa
                ))
            if session_context.get("last_advice_given"):
                parts.append(f"Last advice given (summary): {session_context['last_advice_given'][:400]}")
            # User profile: for tone, follow-up relevance, continuity only; do NOT use for diagnosis or medical conclusions
            up = session_context.get("user_profile") or {}
            if up and any(up.get(k) for k in ("name", "age", "gender", "height_cm", "weight_kg", "location", "known_conditions", "allergies", "preferred_language")):
                profile_parts = []
                if up.get("name"):
                    profile_parts.append(f"Name: {up['name']}")
                if up.get("age") is not None:
                    profile_parts.append(f"Age: {up['age']}")
                if up.get("gender"):
                    profile_parts.append(f"Gender: {up['gender']}")
                if up.get("height_cm") is not None:
                    profile_parts.append(f"Height: {up['height_cm']} cm")
                if up.get("weight_kg") is not None:
                    profile_parts.append(f"Weight: {up['weight_kg']} kg")
                if up.get("location"):
                    profile_parts.append(f"Location: {up['location']}")
                if up.get("known_conditions"):
                    profile_parts.append(f"Known conditions (user-reported): {', '.join(up['known_conditions'][:15])}")
                if up.get("allergies"):
                    profile_parts.append(f"Allergies (user-reported): {up['allergies'][:200]}")
                if up.get("preferred_language"):
                    profile_parts.append(f"Preferred language: {up['preferred_language']}")
                if profile_parts:
                    parts.append("[User profile – use ONLY for tone, follow-up relevance, and continuity; do NOT use for diagnosis or medical conclusions.] " + " | ".join(profile_parts))
            # Phase C: persistent user_memory (e.g. last_symptoms, last_advice across chats)
            um = session_context.get("user_memory") or {}
            if um:
                um_str = "; ".join(f"{k}: {str(v)[:200]}" for k, v in list(um.items())[:10])
                parts.append("[User memory across chats – use ONLY for continuity, e.g. 'You previously mentioned…'; do NOT use for diagnosis.] " + um_str)
            # Phase C: selected past messages from other chats
            pm = session_context.get("past_messages") or []
            if pm:
                pm_str = " | ".join(f"{m.get('role', 'user')}: {(m.get('content') or '')[:150]}" for m in pm[:8])
                parts.append("[Past messages from other chats – for continuity only; do not diagnose from these.] " + pm_str)
            if parts:
                user_content += "\n\n[Session context – use only for continuity and follow-up, e.g. 'Last time you mentioned…'; do not diagnose from this alone.]\n" + "\n".join(parts)

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ]

        try:
            llm_response_data = self.sarvam_client.chat_completion(
                messages=messages,
                temperature=0.5, # Adjust for desired creativity/factuality
                max_tokens=500  # Adjust as needed
            )

            if llm_response_data and "choices" in llm_response_data and llm_response_data["choices"]:
                generated_text = llm_response_data["choices"][0]["message"]["content"]
                # The system prompt instructs the LLM to include disclaimers.
                return generated_text.strip()
            else:
                print("⚠️ LLM response was empty or malformed.")
                # Fallback response if LLM fails
                if nlu_result.language_detected.startswith("hi"):
                    return "माफ़ कीजिए, मैं अभी आपकी मदद नहीं कर सकता। कृपया बाद में प्रयास करें।"
                return "Sorry, I am unable to assist you at the moment. Please try again later."

        except Exception as e:
            print(f"❌ Error during LLM call: {e}")
            if nlu_result.language_detected.startswith("hi"):
                return "क्षमा करें, प्रतिक्रिया उत्पन्न करते समय एक त्रुटि हुई।"
            return "Sorry, an error occurred while generating the response."