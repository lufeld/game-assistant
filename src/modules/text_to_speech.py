import pyttsx3

class TextToSpeech:
    def __init__(self, voice: str = None, rate: int = 180):
        self.target_voice = voice
        self.rate = rate

    def _get_engine(self):
        engine = pyttsx3.init()
        engine.setProperty('rate', self.rate)
        
        # Voice Selection
        voices = engine.getProperty('voices')
        selected_voice = None
        
        # 1. Try requested voice
        if self.target_voice:
            for v in voices:
                if self.target_voice in v.name or self.target_voice in v.id:
                    selected_voice = v.id
                    break
                    
        # 2. Fallback to English
        if not selected_voice:
            for v in voices:
                if "english" in v.name.lower():
                    selected_voice = v.id
                    break
                    
        if selected_voice:
            engine.setProperty('voice', selected_voice)
            
        return engine

    def say(self, text: str, wait: bool = True):
        engine = self._get_engine()
        engine.say(text)
        engine.runAndWait()
        del engine

    def save(self, text: str, filename: str):
        engine = self._get_engine()
        engine.save_to_file(text, filename)
        engine.runAndWait()
        del engine

    def wait(self):
        pass


# Example usage:
# tts = TextToSpeech()
# tts.say('Hello, this is a test!')
