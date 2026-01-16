import numpy as np
import warnings
import sounddevice as sd
import time

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

    def listen_with_vad(self, energy_threshold=0.02, silence_duration_ms=900, max_duration=30):        
        """Listens and auto-stops when you stop speaking using energy-based detection."""
        config_sr = 16000
        frame_duration_ms = 100
        frame_size = int(config_sr * frame_duration_ms / 1000)
        
        print("\n Speak now...")
        
        audio_buffer = []
        silence_frames = 0
        silence_threshold = int(silence_duration_ms / frame_duration_ms)
        speech_detected = False
        start_time = time.time()
        
        def audio_callback(indata, frames, time_info, status):
            audio_buffer.append(indata.copy())
        
        with sd.InputStream(samplerate=config_sr, channels=1, dtype='float32',
                           blocksize=frame_size, callback=audio_callback):
            
            while True:
                if time.time() - start_time > max_duration:
                    print("\n[Timeout] ")
                    break
                
                if len(audio_buffer) == 0:
                    time.sleep(0.01)
                    continue
                
                # Calculate energy (RMS) of latest frame
                frame = audio_buffer[-1]
                energy = np.sqrt(np.mean(frame**2))
                
                # Check if speech based on energy
                if energy > energy_threshold:
                    if not speech_detected:
                        speech_detected = True
                        print("Recording...")
                    silence_frames = 0
                else:
                    if speech_detected:
                        silence_frames += 1
                        if silence_frames > silence_threshold:
                            print("Silence detected")
                            break
                
                time.sleep(frame_duration_ms / 1000)
        
        if not audio_buffer:
            return ""
        
        # Concatenate and normalize
        audio_np = np.concatenate(audio_buffer, axis=0).flatten()
        
        print("Transcribing...")
        return self.transcribe(audio_np)

if __name__ == "__main__":
    stt = SpeechToText(model_size="base")   
    print("Testing VAD - speak and it will auto-stop when you finish\n")
    print("Tip: Speak normally into your microphone. If it doesn't detect, try speaking louder.\n")
    
    while True:
        # Lower threshold to 0.005 for better sensitivity
        text = stt.listen_with_vad(energy_threshold=0.005)
        print(f"\n You said: '{text}'\n")
        
        if "exit" in text.lower() or "quit" in text.lower():
            break