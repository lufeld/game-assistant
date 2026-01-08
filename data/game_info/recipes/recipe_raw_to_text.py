import glob, os
import json
import re
import ollama
from collections import defaultdict

data_dir = os.path.join(os.path.dirname(__file__), 'raw')

if not os.path.exists(data_dir):
    print(f"Data directory {data_dir} does not exist.")
    exit(1)

MODEL_NAME = "qwen3:4b-instruct"

# Global configuration (edit as needed)
OUT_DIR = os.path.join(os.path.dirname(__file__), "text")
LIMIT = None            # e.g., 10 to process only 10 items
DRY_RUN = False         # True = list/prepare only, no LLM calls or writes
DISABLE_LLM = False      # True = skip LLM description generation
SKIP_EXISTING = False   # True = do not overwrite existing item .txt files


def clean_item_name(item_id):
    """Convert minecraft:item_name to readable 'Item Name'"""
    if ':' in item_id:
        item_id = item_id.split(':')[1]
    return item_id.replace('_', ' ').title()


def format_crafting_grid(pattern, key):
    """
    Convert a crafting pattern into a readable text description.
    
    Args:
        pattern: List of strings like ["###", "#X#", "###"]
        key: Dictionary mapping symbols to items like {"#": "minecraft:gold_ingot", "X": "minecraft:apple"}
    
    Returns:
        A clear text description of the crafting grid
    """
    # Create a visual representation
    grid_lines = []
    grid_lines.append("Crafting Grid Layout:")
    
    # Determine grid size
    rows = len(pattern)
    cols = max(len(row) for row in pattern) if pattern else 0
    
    # Build visual grid
    for row in pattern:
        # Pad row to full width
        padded_row = row.ljust(cols, ' ')
        # Convert symbols to item names
        visual_row = []
        for char in padded_row:
            if char == ' ':
                visual_row.append('[Empty]')
            elif char in key:
                item = clean_item_name(key[char])
                visual_row.append(f'[{item}]')
            else:
                visual_row.append(f'[{char}]')
        grid_lines.append('  ' + ' '.join(visual_row))
    
    # Add ingredient list
    grid_lines.append("\nIngredients needed:")
    unique_items = {}
    for symbol, item_id in key.items():
        count = sum(row.count(symbol) for row in pattern)
        item_name = clean_item_name(item_id)
        if item_name in unique_items:
            unique_items[item_name] += count
        else:
            unique_items[item_name] = count
    
    for item_name, count in unique_items.items():
        grid_lines.append(f"  - {count}x {item_name}")
    
    # Add position description
    grid_lines.append("\nStep-by-step placement:")
    position_names = [
        ['top-left', 'top-center', 'top-right'],
        ['middle-left', 'center', 'middle-right'],
        ['bottom-left', 'bottom-center', 'bottom-right']
    ]
    
    for row_idx, row in enumerate(pattern):
        for col_idx, char in enumerate(row):
            if char != ' ' and char in key:
                item = clean_item_name(key[char])
                position = position_names[row_idx][col_idx] if row_idx < 3 and col_idx < 3 else f"row {row_idx+1}, column {col_idx+1}"
                grid_lines.append(f"  {row_idx+1}. Place {item} in {position}")
    
    return '\n'.join(grid_lines)


def convert_recipe_to_text(recipe_data, filename):
    """
    Convert a recipe JSON to structured text that's easier for LLM to process.
    
    Args:
        recipe_data: The parsed JSON recipe data
        filename: The original filename (for extracting result item name)
    
    Returns:
        A structured text representation of the recipe
    """
    # Extract result item
    result_id = recipe_data.get('result', {}).get('id', '')
    result_count = recipe_data.get('result', {}).get('count', 1)
    result_name = clean_item_name(result_id)
    
    # Get recipe type
    recipe_type = recipe_data.get('type', '')
    
    lines = []
    lines.append(f"Recipe: {result_name}")
    lines.append(f"Result: {result_count}x {result_name}")
    lines.append("")
    
    if recipe_type == 'minecraft:crafting_shaped':
        # Shaped recipe with pattern
        pattern = recipe_data.get('pattern', [])
        key = recipe_data.get('key', {})
        
        lines.append("Recipe Type: Shaped Crafting")
        lines.append("")
        lines.append(format_crafting_grid(pattern, key))
        
    elif recipe_type == 'minecraft:crafting_shapeless':
        # Shapeless recipe
        ingredients = recipe_data.get('ingredients', [])
        
        lines.append("Recipe Type: Shapeless Crafting")
        lines.append("")
        lines.append("Ingredients (can be placed in any arrangement):")
        
        # Count ingredients
        ingredient_counts = {}
        for ingredient in ingredients:
            # Handle both string and dict formats
            if isinstance(ingredient, dict):
                item_id = ingredient.get('item', ingredient.get('id', ''))
            else:
                item_id = ingredient
            
            item_name = clean_item_name(item_id)
            ingredient_counts[item_name] = ingredient_counts.get(item_name, 0) + 1
        
        for item_name, count in ingredient_counts.items():
            lines.append(f"  - {count}x {item_name}")
    
    elif recipe_type == 'minecraft:smelting' or recipe_type == 'minecraft:blasting' or recipe_type == 'minecraft:smoking':
        # Smelting recipes
        ingredient = recipe_data.get('ingredient', {})
        if isinstance(ingredient, dict):
            ingredient_id = ingredient.get('item', ingredient.get('id', ''))
        else:
            ingredient_id = ingredient
        
        ingredient_name = clean_item_name(ingredient_id)
        experience = recipe_data.get('experience', 0)
        cooking_time = recipe_data.get('cookingtime', 200)
        
        process_name = {
            'minecraft:smelting': 'Smelting (Furnace)',
            'minecraft:blasting': 'Blasting (Blast Furnace)',
            'minecraft:smoking': 'Smoking (Smoker)'
        }.get(recipe_type, 'Processing')
        
        lines.append(f"Recipe Type: {process_name}")
        lines.append("")
        lines.append(f"Input: 1x {ingredient_name}")
        lines.append(f"Processing time: {cooking_time} ticks ({cooking_time/20:.1f} seconds)")
        lines.append(f"Experience: {experience}")
    
    return '\n'.join(lines)


def generate_llm_description(structured_text, result_name):
    
    prompt = f"""
    You are a Minecraft recipe guide.
    Convert the following structured recipe information into a clear, natural language description that would be helpful for a player.
    Be concise but informative. Avoid emojis.

{structured_text}

Write a helpful description of how to craft {result_name} in Minecraft. Include what ingredients are needed and how to arrange them. Make it conversational and easy to understand."""

    try:
        response = ollama.generate(
            model=MODEL_NAME,
            prompt=prompt
        )
        return response['response'].strip()
    except Exception as e:
        print(f"  ⚠ Error calling LLM: {e}")
        return structured_text  # Fallback to structured text


def process_recipe_file(filepath):
    """
    Process a single recipe JSON file.
    
    Args:
        filepath: Path to the JSON file
    
    Returns:
        Tuple of (success: bool, output_text: str)
    """
    filename = os.path.basename(filepath)
    recipe_name = os.path.splitext(filename)[0]
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            recipe_data = json.load(f)
        
        # Convert to structured text
        structured_text = convert_recipe_to_text(recipe_data, filename)
        
        # Get result name for LLM
        result_id = recipe_data.get('result', {}).get('id', '')
        result_name = clean_item_name(result_id)
        
        # Generate LLM description
        if not DISABLE_LLM:
            llm_description = generate_llm_description(structured_text, result_name)
            
            # Combine structured text with LLM description
            final_text = f"{structured_text}\n\n{'='*60}\n\nDescription:\n{llm_description}"
        else:
            final_text = structured_text
        
        return True, final_text
    
    except Exception as e:
        print(f"  ✗ Error processing {filename}: {e}")
        return False, None


def main():
    all_files = glob.glob(os.path.join(data_dir, '*.json'))
    
    if LIMIT:
        all_files = all_files[:LIMIT]
    
    print(f"Found {len(all_files)} recipe files to process")
    print(f"Output directory: {OUT_DIR}")
    print(f"Model: {MODEL_NAME}")
    print(f"Dry run: {DRY_RUN}")
    print(f"Disable LLM: {DISABLE_LLM}")
    print(f"Skip existing: {SKIP_EXISTING}")
    print()
    
    # Create output directory
    if not DRY_RUN:
        os.makedirs(OUT_DIR, exist_ok=True)
    
    success_count = 0
    skip_count = 0
    error_count = 0
    
    for idx, filepath in enumerate(all_files, 1):
        filename = os.path.basename(filepath)
        recipe_name = os.path.splitext(filename)[0]
        output_path = os.path.join(OUT_DIR, f"{recipe_name}.txt")
        
        # Check if should skip
        if SKIP_EXISTING and os.path.exists(output_path):
            print(f"[{idx}/{len(all_files)}] ⊘ Skipping {filename} (already exists)")
            skip_count += 1
            continue
        
        print(f"[{idx}/{len(all_files)}] Processing {filename}...")
        
        success, output_text = process_recipe_file(filepath)
        
        if success:
            if not DRY_RUN:
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(output_text)
                print(f"  ✓ Saved to {os.path.basename(output_path)}")
            else:
                print(f"  ✓ Would save to {os.path.basename(output_path)}")
                print("  Preview:")
                print("  " + "\n  ".join(output_text.split('\n')[:10]))
                if len(output_text.split('\n')) > 10:
                    print("  ...")
            success_count += 1
        else:
            error_count += 1
    
    print()
    print("="*60)
    print(f"Processing complete!")
    print(f"  Success: {success_count}")
    print(f"  Skipped: {skip_count}")
    print(f"  Errors: {error_count}")
    print(f"  Total: {len(all_files)}")


if __name__ == "__main__":
    main()

    