import pyttsx3

class TextToSpeech:
    def __init__(self, voice: str = None, rate: int = 180):
        self.engine = pyttsx3.init()
        if voice:
            # Try set voice by name, language, or id
            for v in self.engine.getProperty('voices'):
                if voice in v.name or voice in v.id or voice in getattr(v, 'languages', [''])[0]:
                    self.engine.setProperty('voice', v.id)
                    break
        self.engine.setProperty('rate', rate)

    def say(self, text: str, wait: bool = True):
        self.engine.say(text)
        if wait:
            self.engine.runAndWait()

    def save(self, text: str, filename: str):
        self.engine.save_to_file(text, filename)
        self.engine.runAndWait()

# Example usage:
# tts = TextToSpeech()
# tts.say('Hello, this is a test!')
