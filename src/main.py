import sys
import threading
from modules import orchestrator
from modules.voice_loop import run_assistant
from modules.speech_to_text import SpeechToText
from modules.text_to_speech import TextToSpeech
from modules.assistant_gui import AssistantGUI


def main():
    # Model output printed to the console may contain non-ASCII text; avoids
    # a UnicodeEncodeError if the console isn't UTF-8 (this has crashed the
    # process for real before - see orchestrator.py's own __main__ guard).
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("Initializing Minecraft Assistant modules...")

    # Initialize GUI first (must be in main thread)
    gui = AssistantGUI()
    gui.update_status("Initializing system...")

    def initialize_and_run():
        """Initialize components and run assistant in background thread."""
        try:
            # 1. Initialize Text-to-Speech
            print("Initializing TTS...")
            gui.update_status("Initializing TTS...")
            tts = TextToSpeech(rate=170)
            tts.say("Initializing system.")

            # 2. Initialize Speech-to-Text
            print("Loading Whisper model...")
            gui.update_status("Loading Whisper model...")
            stt = SpeechToText(model_size="base")

            # 3. Warm up the LLM so its cold-load cost lands here, not on
            # the user's first real question.
            print("Warming up the LLM...")
            gui.update_status("Warming up the LLM...")
            orchestrator.warm_up_model()

            print("\n--- System Ready ---")
            gui.update_status("System ready")
            gui.add_message("Assistant", "Hello, how can I assist you?")
            tts.say("Hello, how can I assist you?")

            # 4. Start the main loop
            run_assistant(stt_engine=stt, tts_engine=tts, gui=gui)

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