# Contributing to Game Assistant

Thank you for your interest in contributing to the Game Assistant project!

## Development Setup

1. Fork the repository
2. Clone your fork:
   ```bash
   git clone https://github.com/your-username/game-assistant.git
   cd game-assistant
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Set up environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

## Project Structure

- `src/` - Main source code
  - `main.py` - Application entry point
  - `config.py` - Configuration management
  - `modules/` - Core modules (STT, RAG, LLM, TTS)
- `data/game_info/` - Game knowledge base (text files)
- `tests/` - Test files
- `Dockerfile` - Container configuration
- `requirements.txt` - Python dependencies

## Adding New Features

### Adding New Modules

1. Create a new file in `src/modules/`
2. Follow the existing module pattern
3. Add imports to `src/modules/__init__.py`
4. Document the module with docstrings

### Adding Game Content

1. Create a `.txt` file in `data/game_info/`
2. Use clear, structured text format
3. Include relevant headers and sections
4. Restart the application to re-index

## Code Style

- Follow PEP 8 guidelines
- Use type hints where appropriate
- Add docstrings to classes and functions
- Keep functions focused and modular

## Testing

Run the structure test:
```bash
python test_structure.py
```

## Submitting Changes

1. Create a feature branch
2. Make your changes
3. Test thoroughly
4. Submit a pull request with:
   - Clear description
   - Examples/screenshots if applicable
   - Tests for new features

## Questions?

Open an issue for:
- Bug reports
- Feature requests
- Documentation improvements
- General questions
