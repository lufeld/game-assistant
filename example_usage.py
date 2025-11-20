#!/usr/bin/env python3
"""
Example usage script for the Game Assistant.
Demonstrates how to use the modules programmatically.
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Note: This example requires dependencies to be installed
# Run: pip install -r requirements.txt

def example_rag_query():
    """Example: Query the RAG database directly."""
    print("="*60)
    print("Example 1: RAG Database Query")
    print("="*60)
    
    from modules.rag_database import RAGDatabase
    
    # Initialize RAG database
    rag = RAGDatabase(data_path="data/game_info")
    rag.initialize_vectorstore()
    
    # Query for information
    query = "What weapons are available?"
    print(f"\nQuery: {query}")
    
    results = rag.query(query, k=2)
    print(f"\nFound {len(results)} relevant documents:")
    
    for i, result in enumerate(results, 1):
        print(f"\n--- Result {i} ---")
        print(f"Source: {result['metadata'].get('source', 'unknown')}")
        print(f"Content: {result['content'][:200]}...")


def example_llm_query():
    """Example: Generate a response with the LLM."""
    print("\n" + "="*60)
    print("Example 2: LLM Response Generation")
    print("="*60)
    
    from modules.llm_processor import LLMProcessor
    from config import config
    
    if not config.openai_api_key:
        print("\nSkipping - OPENAI_API_KEY not set")
        return
    
    llm = LLMProcessor(
        model=config.llm_model,
        api_key=config.openai_api_key
    )
    
    query = "What is a health potion?"
    context = "Health Potion - Effect: Restores 50 HP instantly, Value: 25 gold"
    
    print(f"\nQuery: {query}")
    print(f"Context: {context}")
    
    response = llm.generate_response(query, context)
    print(f"\nResponse: {response}")


def example_full_pipeline():
    """Example: Full pipeline with RAG + LLM."""
    print("\n" + "="*60)
    print("Example 3: Full Pipeline (RAG + LLM)")
    print("="*60)
    
    from modules.rag_database import RAGDatabase
    from modules.llm_processor import LLMProcessor
    from config import config
    
    if not config.openai_api_key:
        print("\nSkipping - OPENAI_API_KEY not set")
        return
    
    # Initialize components
    rag = RAGDatabase(data_path="data/game_info")
    rag.initialize_vectorstore()
    
    llm = LLMProcessor(
        model=config.llm_model,
        api_key=config.openai_api_key
    )
    
    # Process a query
    query = "How does the combat system work?"
    print(f"\nQuery: {query}")
    
    # Get context from RAG
    context = rag.get_context(query, k=2)
    print(f"\nRetrieved context ({len(context)} chars)")
    
    # Generate response
    response = llm.generate_response(query, context)
    print(f"\nFinal Response:\n{response}")


def main():
    """Run all examples."""
    print("\n" + "="*60)
    print("Game Assistant - Example Usage")
    print("="*60)
    print("\nNote: Requires dependencies installed:")
    print("  pip install -r requirements.txt")
    print("\nAnd OPENAI_API_KEY set for LLM examples:")
    print("  export OPENAI_API_KEY='your-key-here'")
    print()
    
    try:
        # Example 1: RAG only
        example_rag_query()
        
        # Example 2: LLM only
        example_llm_query()
        
        # Example 3: Full pipeline
        example_full_pipeline()
        
        print("\n" + "="*60)
        print("Examples completed!")
        print("="*60)
        
    except ImportError as e:
        print(f"\n✗ Error: {e}")
        print("\nPlease install dependencies:")
        print("  pip install -r requirements.txt")
    except Exception as e:
        print(f"\n✗ Error: {e}")


if __name__ == "__main__":
    main()
