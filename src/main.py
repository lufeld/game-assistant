import sys
from modules.llm_processor import run_assistant
from modules.speech_to_text import SpeechToText
from modules.text_to_speech import TextToSpeech
from modules.rag_database import Database


def main():
    print("Initializing Minecraft Assistant modules...")

    try:
        # 1. Initialize Text-to-Speech
        tts = TextToSpeech(rate=170)
        tts.say("Initializing system.", wait=True)

        # 2. Initialize Speech-to-Text
        print("Loading Whisper model...")
        stt = SpeechToText(model_size="base")

        # 3. Initialize RAG Database
        print("Loading Database...")
        db = Database()

        print("\n--- System Ready ---")
        tts.say("System ready. waiting for input.", wait=True)

        # 4. Start the main loop
        run_assistant(stt_engine=stt, tts_engine=tts, rag_db=db)

    except Exception as e:
        print(f"Error during startup: {e}")


if __name__ == "__main__":
    main()