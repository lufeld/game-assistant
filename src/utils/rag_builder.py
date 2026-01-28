from pathlib import Path
from typing import List, Any
import logging


def setup_recipe_collection(client: Any, recipes_dir: Path, rebuild: bool = False, embedding_function: Any = None):
    """Set up and populate the recipe collection in ChromaDB."""
    # Delete and recreate if requested
    if rebuild:
        try:
            client.delete_collection(name="recipes")
            logging.info("Deleted old recipes collection")
        except:
            pass
    
    # Get or create collection
    recipe_collection = client.get_or_create_collection(
        name="recipes",
        embedding_function=embedding_function,
    )
    
    # Load recipe files
    recipe_files = list_files(recipes_dir, extension="txt")
    
    for recipe_file in recipe_files:
        with open(recipe_file, "r", encoding="utf-8") as f:
            content = f.read()
        recipe_id = Path(recipe_file).stem
        
        if not recipe_collection.get(ids=[recipe_id])['ids']:
            recipe_collection.add(
                ids=[recipe_id],
                documents=[content],
            )
    
    return recipe_collection


def setup_guide_collection(client: Any, guides_dir: Path, rebuild: bool = False, embedding_function: Any = None):
    """Set up and populate the guide collection in ChromaDB."""
    # Delete and recreate if requested
    if rebuild:
        try:
            client.delete_collection(name="guides")
            logging.info("Deleted old guides collection")
        except:
            pass
    
    # Get or create collection
    guide_collection = client.get_or_create_collection(
        name="guides",
        embedding_function=embedding_function,
    )
    
    # Load guide files
    guide_files = list_files(guides_dir, extension="md")
    
    for guide_file in guide_files:
        with open(guide_file, "r", encoding="utf-8") as f:
            content = f.read()
        
        chunks = chunk_markdown_by_sections(content)
        
        for idx, chunk in enumerate(chunks):
            guide_name = chunk['guide_name'] if chunk['guide_name'] else Path(guide_file).stem
            source = chunk['source'] if chunk['source'] else guide_name
            section = chunk['section'] if chunk['section'] else ""
            chunk_id = f"{guide_name}_chunk_{idx}"
            
            if not guide_collection.get(ids=[chunk_id])['ids']:
                guide_collection.add(
                    ids=[chunk_id],
                    documents=[chunk['text']],
                    metadatas=[{"source": source, "guide": guide_name, "section": section, "chunk_index": idx}]
                )
    
    return guide_collection


def list_files(path: Path, extension: str = "*") -> List[Path]:
    """List all files with the given extension in the specified directory and its subdirectories."""
    if not path.exists():
        logging.warning(f"directory not found: {path}")
        return []
    return sorted([p for p in path.rglob(f"*.{extension}") if p.is_file()])


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


def chunk_markdown_by_sections(text: str, max_chunk_size: int = 500) -> List[dict]:
    """
    Chunk markdown by headers, preserving semantic context.
    Each chunk includes the section header for context.
    Returns dict with 'text', 'section', 'guide_name', and 'source'.
    """
    import re
    
    # Extract source (first line if it starts with "Source:")
    source = ""
    lines = text.split('\n')
    if lines and lines[0].strip().startswith('Source:'):
        source = lines[0].strip()
    
    # Extract guide name (# main title)
    guide_name = ""
    title_match = re.search(r'^#\s+(.+)$', text, re.MULTILINE)
    if title_match:
        guide_name = title_match.group(1).strip()
    
    # Split by ## headers (subsections)
    sections = re.split(r'\n(##\s+.+)', text)
    
    chunks = []
    current_title = ""
    
    for i, part in enumerate(sections):
        if part.startswith('##'):
            current_title = part.strip()
        elif part.strip() and current_title:
            content = f"{current_title}\n{part.strip()}"
            
            # If section is too large, split further by paragraphs
            if len(content.split()) > max_chunk_size:
                sub_chunks = chunk_text(part, chunk_size=max_chunk_size, overlap=50)
                for sub in sub_chunks:
                    chunks.append({
                        'text': f"{current_title}\n{sub}",
                        'section': current_title.replace('##', '').strip(),
                        'guide_name': guide_name,
                        'source': source
                    })
            else:
                chunks.append({
                    'text': content,
                    'section': current_title.replace('##', '').strip(),
                    'guide_name': guide_name,
                    'source': source
                })
    
    return chunks