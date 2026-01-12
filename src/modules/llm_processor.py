import ollama
import sys
import re

# Important: run "ollama pull qwen3:4b-instruct" before running this file.
MODEL_NAME = "qwen3:4b-instruct"


def run_assistant(stt_engine, tts_engine, rag_db):

    # This function controls the main conversation loop.
    # It takes the initialized STT, TTS, and RAG database as arguments


    # Provide system prompt as start to the conversation history.
    messages = [
        {
            'role': 'system',
            'content': (
                'You are a helpful Minecraft assistant. '
                'Use the provided context to answer questions about crafting and recipes. '
                'Keep answers concise and relevant to the game. Do not use emoji in your answers.'
            )
        }
    ]

    print(f"Starting Local LLM ({MODEL_NAME})... Say 'exit' to quit.")

    while True:
        try:
            # 1. Get Input (STT)
            # This blocks until the user stops speaking
            print("Listening...")
            user_input = stt_engine.transcribe_microphone(duration=4.0)

            # If STT picked up nothing (silence), skip processing
            if not user_input or len(user_input.strip()) < 2:
                continue

            print(f"\nUser: {user_input}")

            if "exit" in user_input.lower() or "quit" in user_input.lower():
                print("Shutting down game assistant. Have a nice day!")
                tts_engine.say("Goodbye!")
                break

            # 2. RAG Retrieval
            # Query the database for relevant game info/recipes
            print("...searching database...")
            # We get a list of matching documents strings
            context_docs = rag_db.query_recipes(user_input, n_results=1)

            # Join the list into a single string if necessary
            if isinstance(context_docs, list):
                context_str = "\n".join(context_docs)
            else:
                context_str = str(context_docs)

            # Construct the prompt with context
            # We add the context temporarily to the user message for the LLM
            rag_prompt = f"Context: {context_str}\n\nQuestion: {user_input}"

            # Add user input to conversation history
            messages.append({'role': 'user', 'content': rag_prompt})

            print("Assistant: ", end="", flush=True)

            # 3. Generate Response (Streamed)
            full_assistant_response = ""
            current_sentence = ""

            stream = ollama.chat(model=MODEL_NAME, messages=messages, stream=True)

            for chunk in stream:
                content = chunk['message']['content']
                print(content, end="", flush=True)

                full_assistant_response += content
                current_sentence += content

                # Buffer logic: Send to TTS only when we hit a punctuation mark
                # This makes the speech sound natural instead of robotic/choppy
                if re.search(r'[.!?\n]', content):
                    tts_engine.say(current_sentence, wait=True)
                    current_sentence = ""

            # Flush any remaining text in the buffer
            if current_sentence.strip():
                tts_engine.say(current_sentence, wait=True)
            
            # Ensure all audio has finished playing before listening again
            tts_engine.wait()

            # 4. Update History
            # We overwrite the last message to just be the user prompt (removing the RAG context to save tokens)
            messages[-1]['content'] = user_input
            messages.append({'role': 'assistant', 'content': full_assistant_response})
            print()  # Newline

        except KeyboardInterrupt:
            print("\nKeyboard Interrupt.")
            break
        except Exception as e:
            print(f"\nWe encountered an error. The following exception occurred: {e}")
            # Continue the loop if it's a non-fatal error
            continue

    # Logging the last conversation
    with open("latest_communication.txt", "w", encoding="utf-8") as f:
        if 'full_assistant_response' in locals() and full_assistant_response != "":
            f.write(full_assistant_response)
