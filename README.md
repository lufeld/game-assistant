# Game Assistant

A local, voice-driven Minecraft assistant. It answers questions about game
mechanics by reading the [Minecraft Wiki](https://minecraft.wiki) on demand
(cached locally after the first lookup), and answers questions about your
own game state (inventory, position, health, deaths, ...) by reading live
data streamed out of the game by a companion Fabric mod. Everything runs
locally - speech recognition, the LLM (via [Ollama](https://ollama.com)),
and text-to-speech all run on your own machine, with no cloud services
involved.

## Architecture

The live voice loop - listening, handing the question off, speaking the
reply. "orchestrator.py" here is a black box; see the second diagram below
for what's actually inside it.

```mermaid
flowchart LR
    Player(("Player"))
    STT["Speech-to-Text<br/>(Whisper)"]
    TTS["Text-to-Speech<br/>(pyttsx3)"]
    Assistant["orchestrator.py<br/><i>see architecture diagram below</i>"]

    subgraph Voice ["main.py"]
        direction TB
        Loop["voice_loop.py"]
        GUI["assistant_gui.py<br/>(status window)"]
        Loop --- GUI
    end

    Player -- speaks --> STT --> Loop
    Loop --> TTS -- replies --> Player
    Loop -- question --> Assistant -- answer --> Loop

    classDef external fill:#fef7e0,stroke:#f9ab00,color:#1a1a1a
    class Assistant external
```

The assistant itself: a router, not an agent. `route()` and `ask()` are two
separate calls to the *same* model, doing two different jobs - the model
never decides how to retrieve anything, plain Python code in
`gather_context()` does that deterministically.

The two data stores it
reads from - the wiki DB and the player DB - are populated completely
differently:

+ The wiki DB is filled lazily, on demand, by fetching from minecraft.wiki the first time a topic is actually asked about.

+ The player DB is filled continuously, in the background, by the Fabric mod streaming the live game state to `player_ingest.py` while playing.

```mermaid
flowchart TD
    Question(["Question<br/>(from voice_loop.py)"])
    Answer(["Answer<br/>(to voice_loop.py)"])

    Route["route()<br/><i>which topics / player info?</i>"]
    Gather["gather_context()"]
    Ask["ask() / ask_stream()<br/><i>answer from context</i>"]
    Ollama{{"Ollama - qwen3:4b-instruct<br/><i>same model, two separate calls</i>"}}

    subgraph Knowledge ["Wiki DB - src/modules/wiki/"]
        direction TB
        WikiPipe["resolve -> fetch -> parse -> store"]
        Pages[("Pages ledger<br/>(SQLite)")]
        Chroma[("wiki_prose<br/>(Chroma)")]
        WikiPipe -- writes --> Pages
        WikiPipe -- embeds --> Chroma
    end

    subgraph PlayerState ["Player DB - src/modules/player/"]
        direction TB
        Ingest["player_ingest.py<br/>(WebSocket server)"]
        PlayerDB[("player_db.sqlite3")]
        Ingest -- writes --> PlayerDB
    end

    Minecraft["Minecraft + Fabric Mod<br/>(mod/)"]
    WikiSite["minecraft.wiki"]

    Question --> Route --> Gather --> Ask --> Answer

    Route -. "1. route (JSON)" .-> Ollama
    Ask -. "2. answer" .-> Ollama

    Gather -- "if stale" --> WikiPipe
    WikiPipe -- fetches --> WikiSite
    Gather -- search --> Chroma
    Gather -- reads --> PlayerDB

    Minecraft -- streams state --> Ingest

    classDef external fill:#f5f5f5,stroke:#999,color:#333
    classDef store fill:#e8f0fe,stroke:#4285f4,color:#1a1a1a
    classDef llm fill:#fef7e0,stroke:#f9ab00,color:#1a1a1a
    classDef io fill:#e6f4ea,stroke:#34a853,color:#1a1a1a
    class WikiSite,Minecraft external
    class Pages,Chroma,PlayerDB store
    class Ollama llm
    class Question,Answer io
```

The answer streams back sentence-by-sentence as it's generated, not all at
once - the voice loop starts speaking the first sentence while the model is
still generating the rest.

Note that `player_ingest.py` (bottom-left of the second diagram) is a
separate process from the voice assistant - **it does not start
automatically**, see [Running it](#running-it) below.

## Setup

1. **Python 3.10+**, then install dependencies:

   ```
   pip install -r requirements.txt
   ```

2. **[Ollama](https://ollama.com)**, installed and running, with the model
   pulled:

   ```
   ollama pull qwen3:4b-instruct
   ```

3. **The Minecraft mod** (optional - only needed for questions about your
   own game state, not for wiki questions) - see [mod/README.md](mod/README.md)
   for building, installing, and debugging it.

## Running it

Three independent processes, started separately:

```
python src/main.py                      # the voice assistant itself
python src/modules/player/player_ingest.py   # player-state ingest server (optional)
```

...plus Minecraft itself, with the mod installed, if you're running the
ingest server. `main.py` opens a small status window, warms up the model on
startup (so the cold-load delay happens before you start talking, not on
your first question), then listens continuously until you say "exit",
"quit", or "goodbye".

Without a live Minecraft session, you can still exercise the player-state
side end to end using the simulator:

```
python src/modules/player/player_ingest.py &
python src/modules/player/player_simulate.py   # sends src/modules/player/player_events_sample.jsonl
```

## Testing

```
pytest
```

73 tests as of this writing, covering the wiki pipeline (`src/modules/wiki/tests/`)
and the player-state pipeline (`src/modules/player/tests/`) against real I/O
(a tmp SQLite DB, an actual WebSocket connection) rather than mocks.
`orchestrator.py` and the voice loop are exercised manually - see
`src/modules/orchestrator_prompts.txt` for a batch of test questions
(`python src/modules/orchestrator.py --batch src/modules/orchestrator_prompts.txt`).

## Project layout

```
src/
  main.py                    entrypoint: wires GUI + STT + TTS + the voice loop together
  modules/
    orchestrator.py          route -> ensure -> retrieve -> answer pipeline
    orchestrator_prompts.txt batch test questions for orchestrator.py --batch
    voice_loop.py             the live STT -> orchestrator -> TTS loop
    assistant_gui.py          Tkinter status window + conversation log
    speech_to_text.py         Whisper-based listen-until-silence transcription
    text_to_speech.py         pyttsx3 wrapper
    wiki/                     lazy wiki ingestion (resolve/fetch/parse/store) + Chroma
    player/                   player state: player_db.py, player_ingest.py, player_simulate.py
mod/                          the Fabric mod (separate Gradle/Java project - see mod/README.md)
data/                         created at runtime: player_db.sqlite3, game_db.sqlite3,
                              chroma_db/, wiki_cache/ - all gitignored, all rebuildable
```
