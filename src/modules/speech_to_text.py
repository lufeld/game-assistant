"""
Speech-to-Text module using OpenAI Whisper for voice input processing.
"""
import numpy as np
import sounddevice as sd
import whisper
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class SpeechToText:
    """Speech-to-Text converter using Whisper model."""
    
    def __init__(self, model_size: str = "base", language: str = "en", sample_rate: int = 16000):
        """
        Initialize the Speech-to-Text module.
        
        Args:
            model_size: Whisper model size (tiny, base, small, medium, large)
            language: Language code for transcription
            sample_rate: Audio sample rate in Hz
        """
        self.model_size = model_size
        self.language = language
        self.sample_rate = sample_rate
        self.model = None
        logger.info(f"Initializing Speech-to-Text with model size: {model_size}")
    
    def load_model(self):
        """Load the Whisper model."""
        if self.model is None:
            logger.info(f"Loading Whisper model: {self.model_size}")
            self.model = whisper.load_model(self.model_size)
            logger.info("Whisper model loaded successfully")
    
    def record_audio(self, duration: int = 5, device: Optional[int] = None) -> np.ndarray:
        """
        Record audio from microphone.
        
        Args:
            duration: Recording duration in seconds
            device: Audio input device ID (None for default)
            
        Returns:
            Audio data as numpy array
        """
        logger.info(f"Recording audio for {duration} seconds...")
        audio = sd.rec(
            int(duration * self.sample_rate),
            samplerate=self.sample_rate,
            channels=1,
            dtype='float32',
            device=device
        )
        sd.wait()
        logger.info("Recording completed")
        return audio.flatten()
    
    def transcribe(self, audio_data: np.ndarray) -> str:
        """
        Transcribe audio data to text.
        
        Args:
            audio_data: Audio data as numpy array
            
        Returns:
            Transcribed text
        """
        if self.model is None:
            self.load_model()
        
        logger.info("Transcribing audio...")
        result = self.model.transcribe(
            audio_data,
            language=self.language,
            fp16=False
        )
        transcribed_text = result["text"].strip()
        logger.info(f"Transcription: {transcribed_text}")
        return transcribed_text
    
    def record_and_transcribe(self, duration: int = 5, device: Optional[int] = None) -> str:
        """
        Record audio and transcribe it to text.
        
        Args:
            duration: Recording duration in seconds
            device: Audio input device ID (None for default)
            
        Returns:
            Transcribed text
        """
        audio = self.record_audio(duration, device)
        return self.transcribe(audio)
