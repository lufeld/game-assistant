# game-assistant
Human AI Interaction (WS25) Project for a S2S (Speech to Speech) Gaming Assistant

## Overview

This project implements an AI-powered gaming assistant that uses speech-to-speech technology to help players with game-related questions. The assistant can answer questions about game mechanics, items, quests, locations, and more using a Retrieval-Augmented Generation (RAG) approach combined with large language models.

## Architecture

See also [Detailed Architecture](./ARCHITECTURE.md).

The system consists of four main modules:

1. **Speech-to-Text (STT)**: Converts user voice input to text using OpenAI Whisper
2. **RAG Database**: Stores and retrieves game information using vector embeddings
3. **LLM Processor**: Generates responses using language models (e.g., GPT-3.5/GPT-4)
4. **Text-to-Speech (TTS)**: Converts text responses back to speech

## Installation
1. Install Ollama on the machine: https://ollama.com/download
2. Run `ollama pull qwen3:4b-instruct`  (under Windows: `.\ollama pull qwen3:4b-instruct`)
3. Set up a python virtual environment (either manually or using conda).
   1. Install Anaconda
   2. Activate the environment
      - If the environment already exists on this machine: Activate environment with `conda activate game-assistant` and update it with `conda env update --file environment.yml --prune`
      - If the environment doesn't yet exist on this machine, install using `conda env create --name game-assistant --file=environment.yml`


Note: if the environment has been updated, export conda environment as .yml using `conda env export -n game-assistant -c conda-forge -c defaults --no-builds > environment.yml`

## Usage
TODO

## Configuration
TODO

## Example Queries