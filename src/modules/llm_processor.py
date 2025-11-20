"""
LLM (Large Language Model) processor module for generating responses.
"""
import logging
from typing import Optional
import openai

logger = logging.getLogger(__name__)


class LLMProcessor:
    """LLM processor for generating game assistant responses."""
    
    def __init__(
        self,
        model: str = "gpt-3.5-turbo",
        api_key: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 500
    ):
        """
        Initialize the LLM processor.
        
        Args:
            model: Model name (e.g., gpt-3.5-turbo, gpt-4)
            api_key: OpenAI API key
            temperature: Sampling temperature (0-2)
            max_tokens: Maximum tokens in response
        """
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        if api_key:
            openai.api_key = api_key
        
        self.system_prompt = """You are a helpful gaming assistant specialized in answering questions about games. 
Your role is to help players understand game mechanics, items, strategies, and any other game-related information.
When provided with context from the game's knowledge base, use it to give accurate and helpful answers.
If you don't have enough information, admit it and suggest what kind of information would be helpful.
Keep your responses concise and friendly, suitable for voice interaction."""
        
        logger.info(f"Initialized LLM processor with model: {model}")
    
    def generate_response(self, user_query: str, context: Optional[str] = None) -> str:
        """
        Generate a response to the user query using the LLM.
        
        Args:
            user_query: User's question or query
            context: Relevant context from RAG database
            
        Returns:
            Generated response text
        """
        logger.info(f"Generating response for query: '{user_query}'")
        
        # Construct the user message with context
        if context:
            user_message = f"""Context from game knowledge base:
{context}

User question: {user_query}

Please answer the user's question based on the provided context. If the context doesn't contain relevant information, use your general gaming knowledge but mention that the specific information wasn't found in the game's knowledge base."""
        else:
            user_message = f"""User question: {user_query}

Please answer the user's question about the game. If you need more specific information, let them know."""
        
        try:
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            
            answer = response.choices[0].message.content.strip()
            logger.info(f"Generated response: {answer[:100]}...")
            return answer
            
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return f"I apologize, but I encountered an error processing your question. Please try again."
    
    def set_system_prompt(self, prompt: str):
        """
        Update the system prompt.
        
        Args:
            prompt: New system prompt
        """
        self.system_prompt = prompt
        logger.info("System prompt updated")
