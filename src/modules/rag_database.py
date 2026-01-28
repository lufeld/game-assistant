import os
import sys
import uuid
import time
import logging
from pathlib import Path
from typing import List

import chromadb
import chromadb.utils.embedding_functions as embedding_functions

import ollama

# Handle imports for both direct execution and module import
try:
    from ..utils.rag_builder import (
        chunk_text, chunk_markdown_by_sections, list_files,
        setup_recipe_collection, setup_guide_collection
    )
    from ..utils.rag_prompts import QUERY_OPTIMIZER_PROMPT, QUERY_CLASSIFIER_PROMPT
except ImportError:
    # Add src directory to path when running directly
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from utils.rag_builder import (
        chunk_text, chunk_markdown_by_sections, list_files,
        setup_recipe_collection, setup_guide_collection
    )
    from utils.rag_prompts import QUERY_OPTIMIZER_PROMPT, QUERY_CLASSIFIER_PROMPT

GAME_INFO_DIR = Path(__file__).parent.parent.parent / "data" / "game_info"
DB_DIR = Path(__file__).parent.parent.parent / "data" / "chroma_db"
RECIPES_DIR = GAME_INFO_DIR / "recipes" / "text"
GUIDES_DIR = GAME_INFO_DIR / "guides"

MODEL_NAME = "qwen3:4b-instruct"

ef = embedding_functions.ONNXMiniLM_L6_V2(
    #preferred_providers=["CUDAExecutionProvider", "CPUExecutionProvider"]
    preferred_providers=["CPUExecutionProvider"]
)

class Database():

    # Initialize the database and load recipes
    def __init__(self, rebuild_recipes: bool = False, rebuild_guides: bool = False):
        # Initialize ChromaDB client
        self.chroma_client = chromadb.PersistentClient(path=str(DB_DIR))

        # Setup collections using builder functions
        self.recipe_collection = setup_recipe_collection(
            client=self.chroma_client,
            recipes_dir=RECIPES_DIR,
            rebuild=rebuild_recipes,
            embedding_function=ef
        )
        
        self.guide_collection = setup_guide_collection(
            client=self.chroma_client,
            guides_dir=GUIDES_DIR,
            rebuild=rebuild_guides,
            embedding_function=ef
        )


    def query_recipes(self, query_text: str, n_results: int = 3) -> List[str]:
        """Query the database for recipes matching the input text."""
        results = self.recipe_collection.query(
            query_texts=[query_text],
            n_results=n_results,
        )
        # return text of the results
        return results['documents'][0]
    

    def query_guides(self, query_text: str, n_results: int = 3) -> List[str]:
        """Query the database for guides matching the input text."""
        results = self.guide_collection.query(
            query_texts=[query_text],
            n_results=n_results,
        )
        return results['documents'][0]
    

    def _optimize_query_with_llm(self, query_text: str) -> str:
        """Use Ollama to extract key search terms and expand the query."""

        prompt = QUERY_OPTIMIZER_PROMPT.format(query_text=query_text)

        response = ollama.generate(
            model=MODEL_NAME,
            prompt=prompt,
            options={
                "temperature": 0.3,
                "num_predict": 50,
            }
        )
        
        optimized_query = response['response'].strip()
        logging.info(f"Original query: {query_text}")
        logging.info(f"Optimized query: {optimized_query}")
        
        return optimized_query
    

    def _classify_query_intent(self, query_text: str) -> dict:
        """Classify whether the query is about recipes, guides, or both."""
        
        prompt = QUERY_CLASSIFIER_PROMPT.format(query_text=query_text)

        response = ollama.generate(
            model=MODEL_NAME,
            prompt=prompt,
            options={
                "temperature": 0.1,
                "num_predict": 10,
            }
        )
        
        classification = response['response'].strip().upper()
        
        # Parse the classification
        if "RECIPE" in classification and "BOTH" not in classification:
            intent = "recipe"
        elif "GUIDE" in classification and "BOTH" not in classification:
            intent = "guide"
        elif "BOTH" in classification:
            intent = "both"
        else:
            intent = "both"  # Default fallback
        
        logging.info(f"Query intent classified as: {intent}")
        
        return {
            "intent": intent,
            "search_recipes": intent in ["recipe", "both"],
            "search_guides": intent in ["guide", "both"]
        }
    

    # Advanced query method with optional LLM optimization
    def query(self, query_text: str, optimize_processing: bool = True, n_results: int = 3):
        """
        Query both recipes and guides collections.
        
        Args:
            query_text: The user's question
            optimize_processing: Whether to use LLM to optimize the query
            n_results: Number of results to return per collection
            
        Returns:
            dict with 'recipes' and 'guides' results
        """
        # Classify query intent
        intent_info = self._classify_query_intent(query_text) if optimize_processing else {
            "intent": "both",
            "search_recipes": True,
            "search_guides": True
        }
        
        # Optimize query if requested
        search_query = query_text
        if optimize_processing:
            search_query = self._optimize_query_with_llm(query_text)
        
        # Query collections based on intent
        recipe_results = []
        guide_results = []
        
        if intent_info["search_recipes"]:
            recipe_results = self.query_recipes(search_query, n_results=n_results)
        
        if intent_info["search_guides"]:
            guide_results = self.query_guides(search_query, n_results=n_results)
        
        return {
            "recipes": recipe_results,
            "guides": guide_results,
            "optimized_query": search_query if optimize_processing else None,
            "intent": intent_info["intent"]
        }
        

# Example usage
if __name__ == "__main__":
    start_time = time.perf_counter()

    # Rebuild guides with new chunk size
    db = Database(rebuild_guides=True, rebuild_recipes=True)
    
    # Test different query types
    test_queries = [
        "What can I do with an Apple?",  # BOTH
        #"How can I farm food?",  # Should be GUIDE
        #"How do I craft bread?",  # Should be RECIPE
        #"What can I do with wheat and eggs? Where do I get them?",  # Should be BOTH
    ]
    
    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        print('='*60)
        
        results = db.query(query, optimize_processing=True, n_results=2)
        
        print(f"Intent: {results['intent']}")
        print(f"Optimized Query: {results['optimized_query']}\n")
        
        if results['recipes']:
            print("=== Recipe Results ===")
            for i, result in enumerate(results['recipes'], 1):
                print(f"Recipe {i}:")
                print(f"{result[:300]}...\n")
        
        if results['guides']:
            print("=== Guide Results ===")
            for i, result in enumerate(results['guides'], 1):
                print(f"Guide {i}:")
                print(f"{result[:300]}...\n")

    end_time = time.perf_counter()
    print(f"\nTotal elapsed time: {end_time - start_time:.2f} seconds")