"""The live voice loop: STT -> orchestrator -> TTS.

Replaces the old llm_processor.py, which drove the now-deleted rag_database
pipeline directly. Routing, retrieval and answering are all orchestrator's
job now - this module is just the mic-in/speaker-out glue and GUI wiring
around it.

Each turn's answer is streamed straight into TTS sentence-by-sentence via
orchestrator.ask_stream(), the same "speak what's ready, don't wait for the
whole answer" trick the old pipeline used - it lets the player hear the
first sentence while later ones are still being generated.

Stateless per turn, matching orchestrator's own single-turn design - there
is no conversation memory across turns (the router and answer step only
ever see the current question). Adding that would be a real design
decision (what goes into the router's context, how history is bounded,
...), not a small addition, so it's left for later rather than bolted on
here.
"""

from __future__ import annotations

import re
import time

try:
    from modules import orchestrator
except ImportError:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from modules import orchestrator

_EXIT_PHRASES = ("exit", "quit", "goodbye", "good bye")
_SENTENCE_BOUNDARY = re.compile(r"[.!?\n]")


def run_assistant(stt_engine, tts_engine, gui=None) -> None:
    """Listen, route+answer via orchestrator, speak - forever, until an exit phrase."""
    print(f"Starting Local LLM ({orchestrator.MODEL_NAME})... Say 'exit' to quit.")

    while True:
        try:
            if gui and gui.is_muted:
                time.sleep(0.1)  # avoid busy-spinning the CPU while muted
                continue

            if gui:
                gui.update_status("Listening...")
            user_input = stt_engine.listen_with_vad(energy_threshold=0.005)

            if not user_input or len(user_input.strip()) < 2:
                continue

            print(f"\nUser: {user_input}")
            if gui:
                gui.add_message("User", user_input)

            if any(phrase in user_input.lower() for phrase in _EXIT_PHRASES):
                print("Shutting down game assistant. Have a nice day!")
                tts_engine.say("Goodbye!")
                if gui:
                    gui.close()
                break

            if gui:
                gui.update_status("Thinking...")
                gui.add_message_stream("Assistant:\n")
            print("Assistant: ", end="", flush=True)

            full_response = _speak_streamed_answer(user_input, tts_engine, gui)

            if gui:
                gui.add_message_stream("\n\n")
                gui.update_status("Ready")
            print()

            with open("latest_communication.txt", "w", encoding="utf-8") as f:
                f.write(full_response)

        except KeyboardInterrupt:
            print("\nKeyboard Interrupt.")
            if gui:
                gui.close()
            break
        except Exception as exc:  # one bad turn shouldn't kill the whole assistant
            print(f"\nWe encountered an error: {exc}")
            continue


def _speak_streamed_answer(question: str, tts_engine, gui) -> str:
    """Feed orchestrator.ask_stream()'s output to TTS one sentence at a time,
    printing/logging as it arrives. Returns the full answer text."""
    full_response = ""
    sentence = ""

    for chunk in orchestrator.ask_stream(question):
        print(chunk, end="", flush=True)
        full_response += chunk
        sentence += chunk

        if gui:
            gui.add_message_stream(chunk)

        if _SENTENCE_BOUNDARY.search(chunk):
            tts_engine.say(sentence)
            sentence = ""

    if sentence.strip():
        tts_engine.say(sentence)

    return full_response
