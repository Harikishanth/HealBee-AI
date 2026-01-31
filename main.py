import os
import time
from dotenv import load_dotenv

# Assuming audio_capture.py contains CleanAudioCapture and a mock/real STT class
# For this example, we'll mock STT if SarvamSTTIntegration isn't fully defined.
try:
    # from src.audio_capture import CleanAudioCapture, SarvamSTTIntegration # Assuming STT class
    raise ImportError("Mocking CleanAudioCapture, SarvamSTTIntegration for this example")  # Mock import for demonstration
except ImportError:
    print("Warning: src.audio_capture not fully available. Mocking audio capture components.")
    # Mock CleanAudioCapture if not found, for basic testing
    class CleanAudioCapture:
        def __init__(self, sample_rate=16000): self.sample_rate = sample_rate; self.is_recording = False
        def start_recording(self): print("Mock: Start recording..."); self.is_recording = True; time.sleep(1) # Simulate recording
        def stop_recording(self): print("Mock: Stop recording..."); self.is_recording = False
        def get_cleaned_audio(self): print("Mock: Get cleaned audio"); return b"mock_audio_data" # Return mock bytes
        def save_audio(self, data, filename): print(f"Mock: Save audio to {filename}")

    class SarvamSTTIntegration: # Mock STT
        def transcribe_audio(self, audio_data, sample_rate, source_language="hi-IN"):
            print(f"Mock STT: Transcribing with lang {source_language}")
            # Allow dynamic input for testing different scenarios, including symptom queries
            default_query_hi = "मुझे दो दिन से बुखार और खांसी है"
            default_query_en = "I have fever and cough for two days"
            default_query = default_query_hi if source_language == 'hi-IN' else default_query_en

            test_query = input(f"🎤 Enter mock user query (or press Enter for default '{default_query}'): ")
            if test_query.strip():
                print(f"   Using user-provided mock query: '{test_query}'")
                return {"transcription": test_query, "confidence": 0.95}

            if source_language == "hi-IN":
                return {"transcription": default_query_hi, "confidence": 0.9} # Default symptom query
            return {"transcription": default_query_en, "confidence": 0.9} # Default symptom query


from src.nlu_processor import SarvamMNLUProcessor, NLUResult, HealthIntent
from src.response_generator import HealBeeResponseGenerator
from src.symptom_checker import SymptomChecker
import json

def run_healbee_voice_app():
    """
    Main function to run the HealBee Voice Application.
    """
    load_dotenv()
    api_key = os.getenv("SARVAM_API_KEY")

    if not api_key:
        print("❌ SARVAM_API_KEY not found in environment variables. Please set it in your .env file.")
        print("   You can get your API key from: https://dashboard.sarvam.ai")
        return

    print("🚀 Initializing HealBee Voice Application...")
    
    # Initialize components
    # For actual use, ensure CleanAudioCapture and SarvamSTTIntegration are correctly implemented
    audio_capturer = CleanAudioCapture(sample_rate=16000)
    stt_service = SarvamSTTIntegration() # Replace with actual STT client if available
    nlu_processor = SarvamMNLUProcessor(api_key=api_key)
    response_gen = HealBeeResponseGenerator(api_key=api_key)

    try:
        print("\n🎤 Speak your health query now (simulated audio capture)...")
        audio_capturer.start_recording()
        # In a real app, VAD would stop recording or user interaction
        time.sleep(2) # Simulate speaking time
        audio_capturer.stop_recording()

        cleaned_audio_data = audio_capturer.get_cleaned_audio()

        if not cleaned_audio_data:
            print("⚠️ No audio data captured.")
            return

        # --- STT Step ---
        # Determine language for STT - this might come from user preference or auto-detection
        # For now, let's allow choosing or default.
        stt_language = "hi-IN" # or "en-IN", etc.
        print(f"\n🔊 Transcribing audio (Language: {stt_language})...")
        stt_result = stt_service.transcribe_audio(
            cleaned_audio_data,
            sample_rate=audio_capturer.sample_rate,
            source_language=stt_language
        )
        transcribed_text = stt_result.get("transcription")
        if not transcribed_text:
            print("❌ STT failed to transcribe audio.")
            return
        print(f"📝 User Query (Transcribed): \"{transcribed_text}\" (Confidence: {stt_result.get('confidence', 'N/A')})")

        # --- NLU Step ---
        print("\n🧠 Processing NLU...")
        nlu_output: NLUResult = nlu_processor.process_transcription(
            transcribed_text,
            source_language=stt_language # Pass STT language to NLU
        )
        print(f"🔍 NLU Intent: {nlu_output.intent.value}")
        if nlu_output.entities:
            print(f"   Entities: {', '.join([e.text + ' (' + e.entity_type + ')' for e in nlu_output.entities])}")
        else:
            print("   Entities: None found")
        print(f"   Is Emergency (NLU): {nlu_output.is_emergency}")
        print(f"   Detected Language (NLU): {nlu_output.language_detected}")

        # --- Symptom Checker or Standard Response Flow ---
        if nlu_output.intent == HealthIntent.SYMPTOM_QUERY and not nlu_output.is_emergency:
            # Symptom Checker Flow
            print("\n🩺 Activating Symptom Checker...")
            # api_key is available from earlier in the function
            symptom_checker = SymptomChecker(nlu_result=nlu_output, api_key=api_key)
            symptom_checker.prepare_follow_up_questions()

            # Interactive Question-Answering Loop (Simulated for CLI)
            next_question_data = symptom_checker.get_next_question()
            while next_question_data:
                symptom_name_for_prompt = next_question_data['symptom_name']
                question_text_for_prompt = next_question_data['question']

                user_answer = ""
                # Basic validation: ensure answer is not empty
                while not user_answer.strip():
                    prompt_message = f"🎤 HealBee (follow-up for {symptom_name_for_prompt}): {question_text_for_prompt}\nYour answer: "
                    user_answer = input(prompt_message)
                    if not user_answer.strip():
                        print("An answer is required to proceed.")

                symptom_checker.record_answer(
                    symptom_name=symptom_name_for_prompt,
                    question_asked=question_text_for_prompt,
                    user_answer=user_answer
                )
                next_question_data = symptom_checker.get_next_question()

            print("\n🔬 Generating preliminary assessment based on symptoms...")
            assessment_result = symptom_checker.generate_preliminary_assessment()

            final_response_str = json.dumps(assessment_result, indent=2, ensure_ascii=False)

            print("\n\n💡 HealBee Assistant Says (Symptom Assessment):")
            print("--------------------------------------------------")
            print(final_response_str)
            print("--------------------------------------------------")
            # TTS step would need to handle this structured response or a summarized version
            print("\n🗣️ (TTS Placeholder: Speaking assessment summary or key points...)")
            # summary_for_tts = assessment_result.get("assessment_summary", "Please review the detailed assessment.")
            # if "recommended_next_steps" in assessment_result:
            #    summary_for_tts += " Key recommendation: " + assessment_result["recommended_next_steps"].split('\n')[0]
            # print(f"\n🗣️ (TTS Placeholder: Speaking: {summary_for_tts})")
            # # tts_service.speak(summary_for_tts, language=nlu_output.language_detected)

        else:
            # Original flow for non-symptom queries or emergencies
            print("\n💬 Generating response using HealBeeResponseGenerator...")
            # response_gen is initialized from earlier in the function
            final_response_str = response_gen.generate_response(transcribed_text, nlu_output)

            print("\n\n💡 HealBee Assistant Says:")
            print("--------------------------------------------------")
            print(final_response_str)
            print("--------------------------------------------------")

            # --- TTS Step (Placeholder) ---
            # print(f"\n🗣️ (TTS Placeholder: Speaking response: {final_response_str})")
            # # tts_service.speak(final_response_str, language=nlu_output.language_detected)

    except Exception as e:
        print(f"\n❌ An unexpected error occurred in the main application: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Create a .env file if it doesn't exist
    if not os.path.exists(".env"):
        with open(".env", "w") as f:
            f.write("SARVAM_API_KEY=your_sarvam_api_key_here\n")
        print("📝 Created .env file. Please add your SARVAM_API_KEY.")
    
    run_healbee_voice_app()