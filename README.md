# Game Assistant - S2S AI Agent

Human AI Interaction (WS25) Project for a Speech-to-Speech (S2S) Gaming Assistant

## Overview

This project implements an AI-powered gaming assistant that uses speech-to-speech technology to help players with game-related questions. The assistant can answer questions about game mechanics, items, quests, locations, and more using a Retrieval-Augmented Generation (RAG) approach combined with large language models.

## Architecture

The system consists of four main modules:

1. **Speech-to-Text (STT)**: Converts user voice input to text using OpenAI Whisper
2. **RAG Database**: Stores and retrieves game information using vector embeddings
3. **LLM Processor**: Generates responses using language models (e.g., GPT-3.5/GPT-4)
4. **Text-to-Speech (TTS)**: Converts text responses back to speech

## Features

- 🎤 Voice input processing with Whisper STT
- 🗄️ Knowledge base with game information (mechanics, items, quests)
- 🤖 Intelligent responses using RAG + LLM
- 🔊 Natural voice output with TTS
- 🐳 Single Docker container deployment
- 💬 Text-only mode for testing without audio hardware

## Project Structure

```
game-assistant/
├── src/
│   ├── main.py                    # Main application entry point
│   ├── config.py                  # Configuration settings
│   └── modules/
│       ├── __init__.py
│       ├── speech_to_text.py      # STT module (Whisper)
│       ├── rag_database.py        # RAG database with vector store
│       ├── llm_processor.py       # LLM integration (OpenAI)
│       └── text_to_speech.py      # TTS module
├── data/
│   └── game_info/                 # Game knowledge base
│       ├── game_mechanics.txt
│       ├── items_database.txt
│       └── quests_and_locations.txt
├── requirements.txt               # Python dependencies
├── Dockerfile                     # Docker configuration
└── README.md                      # This file
```

## Requirements

### System Requirements
- Python 3.10 or higher
- Docker (optional, for containerized deployment)
- Audio input/output devices (for voice mode)
- FFmpeg (for audio processing)

### API Keys
- OpenAI API key (for LLM functionality)

## Installation

### Local Installation

1. Clone the repository:
```bash
git clone https://github.com/lufeld/game-assistant.git
cd game-assistant
```

2. Install system dependencies (Ubuntu/Debian):
```bash
sudo apt-get update
sudo apt-get install -y ffmpeg portaudio19-dev libsndfile1
```

3. Install Python dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
export OPENAI_API_KEY="your-api-key-here"
```

### Docker Installation

1. Build the Docker image:
```bash
docker build -t game-assistant .
```

2. Run the container:
```bash
docker run -it \
  -e OPENAI_API_KEY="your-api-key-here" \
  game-assistant
```

## Usage

### Text Mode (Default)

Run the assistant in text-only mode without voice I/O:

```bash
python src/main.py --mode text
```

This mode is useful for:
- Testing the system without audio hardware
- Debugging RAG and LLM functionality
- Running in environments without audio support

### Interactive Mode (Voice)

Run the assistant with full voice input/output:

```bash
python src/main.py --mode interactive
```

In this mode:
1. The assistant will record audio when prompted (5 seconds)
2. Your speech is transcribed to text
3. The query is processed through RAG + LLM
4. The response is spoken back to you

### Initialize Only

To only initialize models and databases without starting interactive mode:

```bash
python src/main.py --init-only
```

## Configuration

Configuration can be modified in `src/config.py` or via environment variables:

### Speech-to-Text
- `STT_MODEL`: Whisper model size (tiny, base, small, medium, large)
- `STT_LANGUAGE`: Language code (default: en)

### LLM
- `OPENAI_API_KEY`: Your OpenAI API key (required)
- `LLM_MODEL`: Model to use (default: gpt-3.5-turbo)
- `LLM_TEMPERATURE`: Response creativity (0.0-2.0)
- `LLM_MAX_TOKENS`: Maximum response length

### RAG Database
- Game information is stored in `data/game_info/`
- Add new `.txt` files to expand the knowledge base
- The system automatically indexes all text files

## Adding Game Information

To add new game information to the knowledge base:

1. Create a new `.txt` file in `data/game_info/`
2. Write the content in plain text format
3. Restart the application to re-index

Example file structure:
```
data/game_info/
├── game_mechanics.txt      # Combat, leveling, crafting
├── items_database.txt      # Weapons, armor, consumables
├── quests_and_locations.txt # Quests and map locations
└── your_new_file.txt       # Your custom content
```

## Example Queries

- "How does the combat system work?"
- "What is an Iron Sword and what are its stats?"
- "Tell me about the Dragon's Lair quest"
- "How do I level up in the game?"
- "What potions are available?"
- "Where can I find rare materials?"

## Development

### Running Tests

(Tests to be implemented)

```bash
pytest tests/
```

### Logging

Logs are written to:
- Console (stdout)
- `game_assistant.log` file

Log level can be adjusted in `src/main.py`

## Troubleshooting

### No audio input/output
- Use `--mode text` to run without audio
- Check audio device permissions
- Verify FFmpeg installation

### OpenAI API errors
- Verify API key is set correctly
- Check API quota and billing
- Ensure internet connectivity

### RAG database issues
- Check that `data/game_info/` contains `.txt` files
- Verify sufficient disk space for vector database
- Re-initialize with `--init-only`

## Technology Stack

- **Python 3.10**: Core language
- **OpenAI Whisper**: Speech recognition
- **LangChain**: RAG framework
- **ChromaDB**: Vector database
- **Sentence Transformers**: Text embeddings
- **OpenAI API**: LLM (GPT-3.5/4)
- **Coqui TTS**: Text-to-speech
- **Docker**: Containerization

## Future Enhancements

- [ ] Web interface for easier interaction
- [ ] Support for multiple games
- [ ] Voice activity detection (automatic recording)
- [ ] Multi-language support
- [ ] Local LLM support (Llama, Mistral)
- [ ] Real-time game integration
- [ ] Discord/Slack bot integration

## License

This project is developed for educational purposes as part of the Human AI Interaction (WS25) course.

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## Contact

For questions or support, please open an issue on GitHub.
