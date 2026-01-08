import os
import uuid
import time
import logging
from pathlib import Path
from typing import List

import chromadb
import chromadb.utils.embedding_functions as embedding_functions

game_info_dir = Path(__file__).parent.parent.parent / "data" / "game_info"
db_dir = Path(__file__).parent.parent.parent / "data" / "chroma_db"
recipes_dir = game_info_dir / "recipes" / "text"

ef = embedding_functions.ONNXMiniLM_L6_V2(
    #preferred_providers=["CUDAExecutionProvider", "CPUExecutionProvider"]
    preferred_providers=["CPUExecutionProvider"]
)

def list_recipe_files() -> List[Path]:
    if not recipes_dir.exists():
        logging.warning("recipes directory not found: %s", recipes_dir)
        return []
    return sorted([p for p in recipes_dir.rglob("*") if p.is_file()])

# chroma_client = chromadb.PersistentClient(path=str(db_dir))

# recipe_collection = chroma_client.get_or_create_collection(
#     name="recipes",
#     embedding_function=ef,
# )

# recipe_files = list_recipe_files()

# for recipe_file in recipe_files:
#     with open(recipe_file, "r", encoding="utf-8") as f:
#         content = f.read()
#     recipe_id = Path(recipe_file).stem
    
#     if not recipe_collection.get(ids=[recipe_id])['ids']:
#         recipe_collection.add(
#             ids=[recipe_id],
#             documents=[content],
#         )


# results = recipe_collection.query(
#     query_texts=["I want to cook something delicious."],
#     n_results=3,
# )

# # Print the results (just the document ids)
# for i, result in enumerate(results['ids'][0]):
#     print(f"Result {i + 1}: {result}")


class Database():

    # Initialize the database and load recipes
    def __init__(self):
        # Initialize ChromaDB client
        self.chroma_client = chromadb.PersistentClient(path=str(db_dir))

        # Initialize recipe collection
        self.recipe_collection = self.chroma_client.get_or_create_collection(
            name="recipes",
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

    # Query the database for recipes matching the input text
    def query_recipes(self, query_text: str, n_results: int = 3):
        results = self.recipe_collection.query(
            query_texts=[query_text],
            n_results=n_results,
        )
        # return text of the results
        return results['documents'][0]
    

# Example usage
if __name__ == "__main__":
    start_time = time.perf_counter()

    db = Database()
    query = "I want to cook something delicious."
    results = db.query_recipes(query, n_results=3)

    for i, result in enumerate(results):
        print(f"Result {i + 1}:\n{result}\n")

    end_time = time.perf_counter()
    print(f"\nElapsed time: {end_time - start_time} seconds")