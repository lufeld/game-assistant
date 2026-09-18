import pyttsx3


class TextToSpeech:
    """pyttsx3 wrapper - builds a fresh engine per say()/save() call.

    pyttsx3's docs suggest one engine reused across calls, but in practice
    the SAPI5 driver on Windows is known to go silent after the first
    runAndWait() when the same engine instance is reused across repeated
    calls in a loop (confirmed the hard way: switching to a persistent
    engine made every answer after the first render in the GUI but produce
    no audio at all). Recreating it per call costs a bit of latency but is
    the version that actually plays audio reliably.
    """

    def __init__(self, voice: str = None, rate: int = 180):
        self.target_voice = voice
        self.rate = rate

    def _get_engine(self):
        engine = pyttsx3.init()
        engine.setProperty("rate", self.rate)

        voices = engine.getProperty("voices")
        selected_voice = None

        if self.target_voice:
            for v in voices:
                if self.target_voice in v.name or self.target_voice in v.id:
                    selected_voice = v.id
                    break

        if not selected_voice:
            for v in voices:
                if "english" in v.name.lower():
                    selected_voice = v.id
                    break

        if selected_voice:
            engine.setProperty("voice", selected_voice)

        return engine

    def say(self, text: str) -> None:
        """Speak text and block until playback finishes."""
        engine = self._get_engine()
        engine.say(text)
        engine.runAndWait()
        del engine

    def save(self, text: str, filename: str) -> None:
        engine = self._get_engine()
        engine.save_to_file(text, filename)
        engine.runAndWait()
        del engine


# Example usage:
# tts = TextToSpeech()
# tts.say('Hello, this is a test!')
