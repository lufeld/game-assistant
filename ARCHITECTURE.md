# Game Assistant - System Architecture

## Overview

The Game Assistant is a Speech-to-Speech (S2S) AI system designed to help users with game-related questions through voice interaction.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Game Assistant                            │
│                        (main.py)                                 │
└───────┬─────────────────────────────────────────────────────┬───┘
        │                                                      │
        │  1. User speaks question                             │
        ▼                                                      ▼
┌────────────────┐                                    ┌────────────────┐
│  Speech-to-Text│                                    │ Text-to-Speech │
│    (Whisper)   │                                    │   (Coqui TTS)  │
└───────┬────────┘                                    └────────▲───────┘
        │                                                      │
        │  2. Transcribed text                                 │ 5. Synthesized audio
        ▼                                                      │
┌────────────────┐                                             │
│  RAG Database  │                                             │
│   (ChromaDB)   │                                             │
└───────┬────────┘                                             │
        │                                                      │
        │  3. Retrieved context                                │
        ▼                                                      │
┌────────────────┐                                             │
│  LLM Processor │                                             │
│  (OpenAI GPT)  │                                             │
└───────┬────────┘                                             │
        │                                                      │
        │  4. Generated response                               │
        └──────────────────────────────────────────────────────┘
```

## Component Details

### 1. Speech-to-Text Module
- **Technology**: OpenAI Whisper
- **Purpose**: Convert user voice input to text
- **Models**: tiny, base, small, medium, large
- **Features**: 
  - Multi-language support
  - High accuracy
  - Local processing (no external API)

### 2. RAG Database Module
- **Technology**: LangChain + ChromaDB + Sentence Transformers
- **Purpose**: Store and retrieve game information
- **Features**:
  - Vector-based semantic search
  - Document chunking and embedding
  - Persistent storage
  - Context retrieval for LLM

### 3. LLM Processor Module
- **Technology**: OpenAI GPT (3.5/4)
- **Purpose**: Generate intelligent responses
- **Features**:
  - Context-aware responses
  - Conversational AI
  - Customizable system prompts
  - Token management

### 4. Text-to-Speech Module
- **Technology**: Coqui TTS
- **Purpose**: Convert text responses to speech
- **Features**:
  - Natural-sounding voice
  - Multiple voices/languages
  - Adjustable speed
  - Audio output or file saving

## Data Flow

### Text Mode Flow
```
User Input (text) 
  → RAG Query 
  → Retrieve Context 
  → LLM Processing 
  → Text Response
```

### Interactive Mode Flow
```
User Voice 
  → STT (transcribe) 
  → RAG Query 
  → Retrieve Context 
  → LLM Processing 
  → TTS (synthesize) 
  → Voice Output
```

## File Structure

```
game-assistant/
├── src/
│   ├── main.py              # Application orchestrator
│   ├── config.py            # Configuration management
│   └── modules/
│       ├── speech_to_text.py     # STT module
│       ├── rag_database.py       # RAG module
│       ├── llm_processor.py      # LLM module
│       └── text_to_speech.py     # TTS module
├── data/
│   └── game_info/           # Game knowledge base
│       ├── game_mechanics.txt
│       ├── items_database.txt
│       └── quests_and_locations.txt
├── Dockerfile               # Container definition
├── docker-compose.yml       # Deployment config
└── requirements.txt         # Python dependencies
```

## Configuration

Configuration is managed through:
1. **Environment Variables** - API keys, model selection
2. **Config File** (`config.py`) - Default settings
3. **CLI Arguments** - Runtime options

### Key Configuration Options
- `OPENAI_API_KEY` - Required for LLM
- `LLM_MODEL` - GPT model selection
- `STT_MODEL` - Whisper model size
- `RAG_DB_PATH` - Knowledge base location

## Deployment

### Docker Deployment
```bash
docker build -t game-assistant .
docker run -it -e OPENAI_API_KEY="key" game-assistant
```

### Local Deployment
```bash
pip install -r requirements.txt
export OPENAI_API_KEY="key"
python src/main.py --mode text
```

## Extensibility

The modular design allows for easy extension:

### Adding New Game Content
- Add `.txt` files to `data/game_info/`
- Automatic indexing on restart

### Replacing Components
- **STT**: Replace Whisper with Google STT, Azure, etc.
- **LLM**: Use local models (Llama, Mistral) instead of OpenAI
- **TTS**: Use Google TTS, Azure, or other services
- **RAG**: Use Pinecone, Weaviate, or other vector DBs

### Adding New Features
- Web interface (Flask/FastAPI)
- Real-time game integration
- Multi-user support
- Voice activity detection
- Conversation history

## Performance Considerations

### Initialization
- First run: Downloads models (~1-5GB)
- Subsequent runs: Loads from cache
- RAG indexing: ~5-30 seconds depending on data size

### Runtime
- STT: 1-3 seconds for 5-second audio
- RAG: < 1 second for query
- LLM: 2-5 seconds depending on model and response length
- TTS: 2-4 seconds for typical response

### Resource Usage
- Memory: 2-8 GB depending on models
- CPU: Moderate (STT, TTS)
- GPU: Optional but beneficial for STT
- Network: Required for LLM API calls

## Security

### API Keys
- Never commit API keys
- Use environment variables
- Rotate keys regularly

### Data Privacy
- STT/TTS processed locally (Whisper/TTS)
- LLM queries sent to OpenAI (consider data sensitivity)
- Game data stored locally

### Docker Security
- Run as non-root user (can be added)
- Limit container resources
- Use secrets management for production

## Future Enhancements

1. **Real-time Processing**: Stream audio instead of 5-second chunks
2. **Multi-language**: Support multiple game languages
3. **Game Integration**: Direct game state access
4. **Web Interface**: Browser-based interaction
5. **Mobile App**: iOS/Android clients
6. **Voice Commands**: "Pause", "Repeat", "More details"
7. **User Profiles**: Personalized responses
8. **Analytics**: Track common questions

## Troubleshooting

### Common Issues
1. **Import Errors**: Install dependencies
2. **API Errors**: Check API key and quota
3. **Audio Issues**: Verify audio devices or use text mode
4. **Memory Issues**: Reduce model sizes

### Debug Mode
Enable verbose logging in `config.py`:
```python
verbose: bool = True
```

### Logs
Check `game_assistant.log` for detailed information.

## References

- [OpenAI Whisper](https://github.com/openai/whisper)
- [LangChain](https://python.langchain.com/)
- [ChromaDB](https://www.trychroma.com/)
- [Coqui TTS](https://github.com/coqui-ai/TTS)
- [OpenAI API](https://platform.openai.com/)
