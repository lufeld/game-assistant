"""
Main application file for the Game Assistant S2S AI Agent.
Orchestrates all modules: STT, RAG, LLM, and TTS.
"""
import argparse
import logging
import sys
from pathlib import Path

from config import Config, config
from modules import SpeechToText, RAGDatabase, LLMProcessor, TextToSpeech


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('game_assistant.log')
    ]
)
logger = logging.getLogger(__name__)


class GameAssistant:
    """Main Game Assistant S2S AI Agent."""
    
    def __init__(self, config: Config):
        """
        Initialize the Game Assistant.
        
        Args:
            config: Configuration object
        """
        self.config = config
        logger.info("Initializing Game Assistant S2S AI Agent")
        
        # Initialize modules
        self.stt = SpeechToText(
            model_size=config.stt_model,
            language=config.stt_language,
            sample_rate=config.audio_sample_rate
        )
        
        self.rag = RAGDatabase(
            data_path=config.rag_db_path,
            embedding_model=config.embedding_model,
            chunk_size=config.rag_chunk_size,
            chunk_overlap=config.rag_chunk_overlap
        )
        
        self.llm = LLMProcessor(
            model=config.llm_model,
            api_key=config.openai_api_key,
            temperature=config.llm_temperature,
            max_tokens=config.llm_max_tokens
        )
        
        self.tts = TextToSpeech(
            sample_rate=config.audio_sample_rate,
            speed=config.tts_speed
        )
        
        logger.info("Game Assistant initialized successfully")
    
    def initialize(self):
        """Initialize all modules (load models, databases, etc.)."""
        logger.info("Loading models and initializing databases...")
        
        # Load STT model
        self.stt.load_model()
        
        # Initialize RAG database
        self.rag.initialize_vectorstore()
        
        # Load TTS model
        self.tts.load_model()
        
        logger.info("All modules initialized successfully")
    
    def process_query(self, query_text: str) -> str:
        """
        Process a text query through the RAG and LLM.
        
        Args:
            query_text: User's query text
            
        Returns:
            Generated response
        """
        logger.info(f"Processing query: '{query_text}'")
        
        # Get relevant context from RAG database
        context = self.rag.get_context(query_text)
        
        # Generate response using LLM
        response = self.llm.generate_response(query_text, context)
        
        return response
    
    def run_interactive(self):
        """Run the assistant in interactive mode with voice input/output."""
        logger.info("Starting interactive mode")
        print("\n" + "="*60)
        print("Game Assistant S2S AI Agent - Interactive Mode")
        print("="*60)
        print("\nPress Ctrl+C to exit\n")
        
        try:
            while True:
                print("\n--- Ready to listen ---")
                print("Speak your question (recording for 5 seconds)...")
                
                try:
                    # Record and transcribe user input
                    user_query = self.stt.record_and_transcribe(
                        duration=5,
                        device=self.config.audio_input_device
                    )
                    
                    if not user_query or len(user_query.strip()) < 3:
                        print("No speech detected or query too short. Please try again.")
                        continue
                    
                    print(f"\nYou asked: {user_query}")
                    
                    # Process the query
                    response = self.process_query(user_query)
                    print(f"\nAssistant: {response}")
                    
                    # Speak the response
                    print("\n--- Speaking response ---")
                    self.tts.speak(response, device=self.config.audio_output_device)
                    
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    logger.error(f"Error in interactive loop: {e}")
                    print(f"\nError: {e}")
                    print("Please try again.")
        
        except KeyboardInterrupt:
            print("\n\nShutting down Game Assistant...")
            logger.info("Game Assistant stopped by user")
    
    def run_text_mode(self):
        """Run the assistant in text-only mode (no voice I/O)."""
        logger.info("Starting text-only mode")
        print("\n" + "="*60)
        print("Game Assistant - Text Mode")
        print("="*60)
        print("\nType 'exit' or 'quit' to stop\n")
        
        try:
            while True:
                user_query = input("\nYour question: ").strip()
                
                if user_query.lower() in ['exit', 'quit', 'q']:
                    break
                
                if not user_query:
                    continue
                
                # Process the query
                response = self.process_query(user_query)
                print(f"\nAssistant: {response}")
        
        except KeyboardInterrupt:
            pass
        
        print("\n\nShutting down Game Assistant...")
        logger.info("Game Assistant stopped")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Game Assistant S2S AI Agent"
    )
    parser.add_argument(
        '--mode',
        choices=['interactive', 'text'],
        default='text',
        help='Interaction mode (interactive: voice I/O, text: text-only)'
    )
    parser.add_argument(
        '--init-only',
        action='store_true',
        help='Only initialize models and databases, then exit'
    )
    
    args = parser.parse_args()
    
    try:
        # Create and initialize assistant
        assistant = GameAssistant(config)
        assistant.initialize()
        
        if args.init_only:
            logger.info("Initialization complete. Exiting.")
            return
        
        # Run in selected mode
        if args.mode == 'interactive':
            assistant.run_interactive()
        else:
            assistant.run_text_mode()
    
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        print(f"\nFatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
