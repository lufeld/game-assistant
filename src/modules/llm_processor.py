import ollama
import sys

# Important: run "ollama pull qwen3:4b-instruct" before running this file.
MODEL_NAME = "qwen3:4b-instruct"

def run_assistant():
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

    while True:
        try:
            # First, we get the user prompt
            print("Please provide your prompt: ")
            user_input = input()

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
                print(content)
                full_assistant_response += content

            # This, we add these messages to the history
            messages.append({'role': 'assistant', 'content': full_assistant_response})

        except KeyboardInterrupt:
            # TODO: remove this once actual STT is implemented (because keyboard interrupts aren't possible any longer then)
            print("Keyboard Interrupt.")
            break
        except Exception as e:
            # TODO: replace this with actual user-friendly errors once the pipeline works.
            print(f"We encountered an error. The following exeception occurred: {e}")
            break
    with open("latest_communication.txt", "w", encoding="utf-8") as f:
        if full_assistant_response != "":
            f.write(full_assistant_response)


# TODO: remove this function once the rest is implemented (once the actual main function is there that calls run_:assistant)
if __name__=="__main__":
    run_assistant()