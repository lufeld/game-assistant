import ollama
import sys

# Important: run "ollama pull qwen3:4b-instruct" before running this file.
MODEL_NAME = "qwen3:4b-instruct"

def run_assistant(prompt: str) -> str:
    """
    This function should be run repeatedly in a loop where it is fed the result of STT.
    It provides the LLM output as a string, which shall then be passed to the TTS section.
    """
    # TODO: maybe this file should import STT and TTS and control the entire conversation loop

    # Provide system prompt as start to the conversation history.
    messages = [
        {
            'role': 'system',
            'content': 'You are a helpful Minecraft assistant. Keep answers concise and relevant to the game.'
        }
    ]


    try:
        # First, we get the user prompt
        user_input = prompt

        if user_input.lower() in ['exit', 'quit']:
            return "Shutting down game assistant. Have a nice day!"


        # Add user input to conversation history
        messages.append({'role': 'user', 'content': user_input})


        # Second, we generate the response.
        # TODO: in the end, this needs to happen in a streamed way such that the TTS can start talking right away
        #  (otherwise, we have a strong delay).
        full_assistant_response = ""
        stream = ollama.chat(model=MODEL_NAME, messages=messages, stream=True)

        for chunk in stream:
            # TODO: probably pass the chunk to STT already here
            content = chunk['message']['content']
            full_assistant_response += content

        # This, we add these messages to the history
        messages.append({'role': 'assistant', 'content': full_assistant_response})
        return full_assistant_response

    except KeyboardInterrupt:
        # TODO: remove this once actual STT is implemented (because keyboard interrupts aren't possible any longer then)
        return "Keyboard Interrupt."
    except Exception as e:
        # TODO: replace this with actual user-friendly errors once the pipeline works.
        return f"We encountered an error. The following exeception occurred: {e}"

