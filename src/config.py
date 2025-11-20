"""
Configuration settings for the Game Assistant S2S AI Agent.
"""
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Config:
    """Configuration class for the game assistant."""
    
    # Speech-to-Text settings
    stt_model: str = "base"  # Whisper model size: tiny, base, small, medium, large
    stt_language: str = "en"
    
    # RAG Database settings
    rag_db_path: str = "data/game_info"
    rag_chunk_size: int = 500
    rag_chunk_overlap: int = 50
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    
    # LLM settings
    llm_model: str = os.getenv("LLM_MODEL", "gpt-3.5-turbo")
    llm_temperature: float = 0.7
    llm_max_tokens: int = 500
    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
    
    # Text-to-Speech settings
    tts_model: str = "tts_models/en/ljspeech/tacotron2-DDC"
    tts_speed: float = 1.0
    
    # General settings
    audio_sample_rate: int = 16000
    audio_input_device: Optional[int] = None
    audio_output_device: Optional[int] = None
    verbose: bool = True
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        if not self.openai_api_key and "gpt" in self.llm_model.lower():
            print("Warning: OPENAI_API_KEY not set. LLM functionality may be limited.")


# Global configuration instance
config = Config()
