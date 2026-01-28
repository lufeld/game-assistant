import sys
import threading
from modules.llm_processor import run_assistant
from modules.speech_to_text import SpeechToText
from modules.text_to_speech import TextToSpeech
from modules.rag_database import Database
from modules.assistant_gui import AssistantGUI


def main():
    print("Initializing Minecraft Assistant modules...")

    # Initialize GUI first (must be in main thread)
    gui = AssistantGUI()
    gui.update_status("Initializing system...")

    def initialize_and_run():
        """Initialize components and run assistant in background thread."""
        try:
            # 1. Initialize Text-to-Speech
            print("DEBUG: Initializing TTS...")
            gui.update_status("Initializing TTS...")
            tts = TextToSpeech(rate=170)
            tts.say("Initializing system.", wait=True)

            # 2. Initialize Speech-to-Text
            print("Loading Whisper model...")
            gui.update_status("Loading Whisper model...")
            stt = SpeechToText(model_size="base")

            # 3. Initialize RAG Database
            print("Loading Database...")
            gui.update_status("Loading database...")
            db = Database()

            print("\n--- System Ready ---")
            gui.update_status("System ready")
            gui.add_message("Assistant", "Hello, how can I assist you?")
            tts.say("Hello, how can I assist you?", wait=True)

            # 4. Start the main loop
            run_assistant(stt_engine=stt, tts_engine=tts, rag_db=db, gui=gui)

        except Exception as e:
            print(f"Error during startup: {e}")
            gui.update_status(f"Error: {e}")

    # Start assistant in background thread
    assistant_thread = threading.Thread(target=initialize_and_run, daemon=True)
    assistant_thread.start()

    # Run GUI in main thread (required for tkinter)
    gui.run()


if __name__ == "__main__":
    main()