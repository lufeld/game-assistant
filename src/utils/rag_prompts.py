# Prompts for RAG components

QUERY_OPTIMIZER_PROMPT = """You are a search query optimizer for a game guide database.
Given a user question, extract the most important keywords and concepts for semantic search.
Also add relevant synonyms or related terms.

User question: {query_text}

Generate an optimized search query (just the keywords, no explanation):"""

QUERY_CLASSIFIER_PROMPT = """You are a query classifier for a game assistant database.
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