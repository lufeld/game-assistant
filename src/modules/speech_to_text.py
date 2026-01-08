import numpy as np
import warnings

warnings.filterwarnings("ignore", message="FP16 is not supported on CPU")

class SpeechToText:
    def __init__(self, model_size="base", language=None):
        import whisper
        self._model = whisper.load_model(model_size)
        self._language = language

    def transcribe(self, audio):
        if isinstance(audio, np.ndarray):
            arr = audio.astype(np.float32)
            if arr.ndim > 1:
                arr = arr.mean(axis=1)
            audio = arr / np.max(np.abs(arr)) if np.max(np.abs(arr)) > 0 else arr
        result = self._model.transcribe(audio, language=self._language)
        return result["text"].strip()

    def transcribe_file(self, audio_path):
        return self.transcribe(audio_path)

    def transcribe_microphone(self, duration=5.0):
        import sounddevice as sd
        config_sr = 16000
        print(f"Speak now ({duration}s)...")
        audio = sd.rec(int(duration*config_sr), samplerate=config_sr, channels=1, dtype="float32")
        sd.wait()
        audio = audio.flatten()
        return self.transcribe(audio)

if __name__ == "__main__":
    stt = SpeechToText(model_size="base")   
    text = stt.transcribe_microphone(duration=3.0)
    print("You said:", text)