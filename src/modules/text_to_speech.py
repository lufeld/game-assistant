"""
Text-to-Speech module for converting text responses to speech.
"""
import logging
from typing import Optional
import numpy as np
import sounddevice as sd

try:
    from TTS.api import TTS
except ImportError:
    logging.warning("TTS library not installed. Text-to-speech functionality will be limited.")
    TTS = None

logger = logging.getLogger(__name__)


class TextToSpeech:
    """Text-to-Speech converter using TTS models."""
    
    def __init__(
        self,
        model_name: Optional[str] = None,
        sample_rate: int = 22050,
        speed: float = 1.0
    ):
        """
        Initialize the Text-to-Speech module.
        
        Args:
            model_name: TTS model name (None for default)
            sample_rate: Audio sample rate in Hz
            speed: Speech speed multiplier
        """
        self.model_name = model_name or "tts_models/en/ljspeech/tacotron2-DDC"
        self.sample_rate = sample_rate
        self.speed = speed
        self.tts = None
        
        logger.info(f"Initializing Text-to-Speech with model: {self.model_name}")
    
    def load_model(self):
        """Load the TTS model."""
        if self.tts is None and TTS is not None:
            logger.info(f"Loading TTS model: {self.model_name}")
            try:
                self.tts = TTS(model_name=self.model_name, progress_bar=False)
                logger.info("TTS model loaded successfully")
            except Exception as e:
                logger.error(f"Error loading TTS model: {e}")
                logger.info("Falling back to simple TTS")
                self.tts = None
    
    def synthesize(self, text: str) -> Optional[np.ndarray]:
        """
        Synthesize speech from text.
        
        Args:
            text: Text to convert to speech
            
        Returns:
            Audio data as numpy array or None if synthesis fails
        """
        if not text:
            logger.warning("Empty text provided for synthesis")
            return None
        
        if self.tts is None:
            self.load_model()
        
        if self.tts is None:
            logger.warning("TTS model not available, skipping synthesis")
            return None
        
        try:
            logger.info(f"Synthesizing speech: '{text[:50]}...'")
            # Generate speech
            wav = self.tts.tts(text)
            
            # Convert to numpy array if needed
            if not isinstance(wav, np.ndarray):
                wav = np.array(wav)
            
            return wav
            
        except Exception as e:
            logger.error(f"Error synthesizing speech: {e}")
            return None
    
    def speak(self, text: str, device: Optional[int] = None):
        """
        Synthesize and play speech from text.
        
        Args:
            text: Text to speak
            device: Audio output device ID (None for default)
        """
        audio = self.synthesize(text)
        
        if audio is not None:
            logger.info("Playing synthesized speech...")
            try:
                sd.play(audio, self.sample_rate, device=device)
                sd.wait()
                logger.info("Playback completed")
            except Exception as e:
                logger.error(f"Error playing audio: {e}")
        else:
            logger.warning("No audio to play")
    
    def save_audio(self, text: str, output_path: str):
        """
        Synthesize speech and save to file.
        
        Args:
            text: Text to convert to speech
            output_path: Output file path (WAV format)
        """
        audio = self.synthesize(text)
        
        if audio is not None:
            logger.info(f"Saving audio to: {output_path}")
            try:
                import scipy.io.wavfile as wavfile
                wavfile.write(output_path, self.sample_rate, audio)
                logger.info("Audio saved successfully")
            except Exception as e:
                logger.error(f"Error saving audio: {e}")
        else:
            logger.warning("No audio to save")
