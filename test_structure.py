#!/usr/bin/env python3
"""
Simple test script to verify the project structure and imports.
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_imports():
    """Test that all modules can be imported."""
    print("Testing imports...")
    
    try:
        import config
        print("✓ config module imported")
    except Exception as e:
        print(f"✗ Error importing config: {e}")
        return False
    
    try:
        from modules.speech_to_text import SpeechToText
        print("✓ SpeechToText module imported")
    except Exception as e:
        print(f"✗ Error importing SpeechToText: {e}")
        # Expected to fail without dependencies
    
    try:
        from modules.rag_database import RAGDatabase
        print("✓ RAGDatabase module imported")
    except Exception as e:
        print(f"✗ Error importing RAGDatabase: {e}")
        # Expected to fail without dependencies
    
    try:
        from modules.llm_processor import LLMProcessor
        print("✓ LLMProcessor module imported")
    except Exception as e:
        print(f"✗ Error importing LLMProcessor: {e}")
        # Expected to fail without dependencies
    
    try:
        from modules.text_to_speech import TextToSpeech
        print("✓ TextToSpeech module imported")
    except Exception as e:
        print(f"✗ Error importing TextToSpeech: {e}")
        # Expected to fail without dependencies
    
    return True

def test_structure():
    """Test that the directory structure is correct."""
    print("\nTesting directory structure...")
    
    base_path = Path(__file__).parent
    
    required_files = [
        "README.md",
        "requirements.txt",
        "Dockerfile",
        "docker-compose.yml",
        ".gitignore",
        ".env.example",
        "src/main.py",
        "src/config.py",
        "src/modules/__init__.py",
        "src/modules/speech_to_text.py",
        "src/modules/rag_database.py",
        "src/modules/llm_processor.py",
        "src/modules/text_to_speech.py",
        "data/game_info/game_mechanics.txt",
        "data/game_info/items_database.txt",
        "data/game_info/quests_and_locations.txt"
    ]
    
    all_exist = True
    for file_path in required_files:
        full_path = base_path / file_path
        if full_path.exists():
            print(f"✓ {file_path}")
        else:
            print(f"✗ {file_path} - MISSING")
            all_exist = False
    
    return all_exist

def main():
    """Run all tests."""
    print("="*60)
    print("Game Assistant - Project Structure Test")
    print("="*60)
    
    structure_ok = test_structure()
    imports_ok = test_imports()
    
    print("\n" + "="*60)
    if structure_ok:
        print("✓ Project structure is correct")
    else:
        print("✗ Project structure has issues")
    
    print("="*60)
    print("\nNote: Import errors are expected without dependencies installed.")
    print("Run 'pip install -r requirements.txt' to install dependencies.")

if __name__ == "__main__":
    main()
