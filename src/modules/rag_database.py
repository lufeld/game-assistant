import os
import uuid
import time
import logging
from pathlib import Path
from typing import List

import chromadb
import chromadb.utils.embedding_functions as embedding_functions

import ollama

GAME_INFO_DIR = Path(__file__).parent.parent.parent / "data" / "game_info"
DB_DIR = Path(__file__).parent.parent.parent / "data" / "chroma_db"
RECIPES_DIR = GAME_INFO_DIR / "recipes" / "text"
GUIDES_DIR = GAME_INFO_DIR / "guides"

MODEL_NAME = "qwen3:4b-instruct"

ef = embedding_functions.ONNXMiniLM_L6_V2(
    #preferred_providers=["CUDAExecutionProvider", "CPUExecutionProvider"]
    preferred_providers=["CPUExecutionProvider"]
)

def list_recipe_files() -> List[Path]:
    if not RECIPES_DIR.exists():
        logging.warning("recipes directory not found: %s", RECIPES_DIR)
        return []
    return sorted([p for p in RECIPES_DIR.rglob("*") if p.is_file()])

def list_guide_files() -> List[Path]:
    if not GUIDES_DIR.exists():
        logging.warning("guides directory not found: %s", GUIDES_DIR)
        return []
    return sorted([p for p in GUIDES_DIR.rglob("*.txt") if p.is_file()])

def chunk_text(text: str, chunk_size: int = 400, overlap: int = 50) -> List[str]:
    """Split text into chunks by paragraphs, respecting max chunk size."""
    paragraphs = text.split('\n\n')
    chunks = []
    current_chunk = []
    current_length = 0
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        
        para_length = len(para.split())
        
        if current_length + para_length > chunk_size and current_chunk:
            chunks.append('\n\n'.join(current_chunk))
            # Keep last part for overlap
            current_chunk = [current_chunk[-1]] if overlap > 0 else []
            current_length = len(current_chunk[0].split()) if current_chunk else 0
        
        current_chunk.append(para)
        current_length += para_length
    
    if current_chunk:
        chunks.append('\n\n'.join(current_chunk))
    
    return chunks


class Database():

    # Initialize the database and load recipes
    def __init__(self, rebuild_recipes: bool = False, rebuild_guides: bool = False):
        # Initialize ChromaDB client
        self.chroma_client = chromadb.PersistentClient(path=str(DB_DIR))

        # Initialize recipe collection
        if rebuild_recipes:
            # Delete and recreate the recipe collection
            try:
                self.chroma_client.delete_collection(name="recipes")
                logging.info("Deleted old recipes collection")
            except:
                pass

        self.recipe_collection = self.chroma_client.get_or_create_collection(
            name="recipes",
            embedding_function=ef,
        )

        # Initialize guide collection
        if rebuild_guides:
            # Delete and recreate the guide collection
            try:
                self.chroma_client.delete_collection(name="guides")
                logging.info("Deleted old guides collection")
            except:
                pass
        
        self.guide_collection = self.chroma_client.get_or_create_collection(
            name="guides",
            embedding_function=ef,
        )

        # Load existing recipes into the database if nor already present
        recipe_files = list_recipe_files()

        for recipe_file in recipe_files:
            with open(recipe_file, "r", encoding="utf-8") as f:
                content = f.read()
            recipe_id = Path(recipe_file).stem
            
            if not self.recipe_collection.get(ids=[recipe_id])['ids']:
                self.recipe_collection.add(
                    ids=[recipe_id],
                    documents=[content],
                )

        # Load existing guides into the database if not already present
        guide_files = list_guide_files()
        
        for guide_file in guide_files:
            with open(guide_file, "r", encoding="utf-8") as f:
                content = f.read()
            
            guide_name = guide_file.stem
            chunks = chunk_text(content, chunk_size=30, overlap=10)
            
            for idx, chunk in enumerate(chunks):
                chunk_id = f"{guide_name}_chunk_{idx}"
                
                if not self.guide_collection.get(ids=[chunk_id])['ids']:
                    self.guide_collection.add(
                        ids=[chunk_id],
                        documents=[chunk],
                        metadatas=[{"source": guide_name, "chunk_index": idx}]
                    )

    def query_recipes(self, query_text: str, n_results: int = 3) -> List[str]:
        """Query the database for recipes matching the input text."""
        results = self.recipe_collection.query(
            query_texts=[query_text],
            n_results=n_results,
        )
        # return text of the results
        return results['documents'][0]
    
    def query_guides(self, query_text: str, n_results: int = 5) -> List[str]:
        """Query the database for guides matching the input text."""
        results = self.guide_collection.query(
            query_texts=[query_text],
            n_results=n_results,
        )
        return results['documents'][0]
    
    def _optimize_query_with_llm(self, query_text: str) -> str:
        """Use Ollama to extract key search terms and expand the query."""

        prompt = f"""You are a search query optimizer for a game guide database.
Given a user question, extract the most important keywords and concepts for semantic search.
Also add relevant synonyms or related terms.

User question: {query_text}

Generate an optimized search query (just the keywords, no explanation):"""

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
        
        prompt = f"""You are a query classifier for a game assistant database.
The database has two types of content:
1. RECIPES: Specific crafting recipes, item creation formulas
2. GUIDES: General gameplay tips, strategies, tutorials, how-to information, item locations

Classify the following user question. Respond with ONLY one of these options:
- "RECIPE" if asking ONLY about crafting recipes with no other context
- "GUIDE" if asking ONLY for general help, strategies, or tutorials with no crafting
- "BOTH" if the query:
  * Asks "what can I do with X" or "what to do with X" or "uses for X"
  * Mentions "where to find/get" items
  * Could involve both crafting AND obtaining/using items

Important: Questions about what you can do with an item should be classified as "BOTH" because they involve both recipes and usage information.

User question: {query_text}

Classification:"""

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
    db = Database(rebuild_guides=True)
    
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