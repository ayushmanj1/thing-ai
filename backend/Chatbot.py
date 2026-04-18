import os
from groq import Groq
import cohere
from json import load, dump
import datetime
from dotenv import dotenv_values


# Load environment variables
env_vars = dotenv_values(".env")

Username = env_vars.get("Username", "User")
Assistantname = env_vars.get("Assistantname", "Nemo")
GroqAPIKey = env_vars.get("GroqAPIKey")
CohereAPIKey = env_vars.get("CohereAPIKey")

# Initialize clients
client = Groq(api_key=GroqAPIKey)
co_client = cohere.Client(api_key=CohereAPIKey)

# Global messages list
messages = []

# System message
System = f"""
Hello, I am {Username}, 
You are {Assistantname}, my advanced, respectful, and high-energy AI assistant. 

*** RULES FOR RESPONSE LENGTH & TONE: ***
1. **RESPONSE LENGTH**: 
   - **Default**: Aim for about 2 to 3 sentences (30-50 words) for general questions.
   - **Detailed Request**: If the user explicitly asks for a "detailed", "long", or "comprehensive" answer, provide a thorough and long explanation.
   - **Brief Request**: If the user asks for a "brief" or "short" answer, keep it to a single sentence or very concise.
2. **GREETINGS**: Give a warm, cheerful, and respectful greeting. Keep it friendly without being excessively wordy.
3. **TONE**: Be cheerful, supportive, and respectful with a high-energy vibe.
4. **COMPREHENSIVENESS**: Match your level of detail to the user's intent. If they just want a quick fact, be direct. If they are asking for an explanation, be helpful but balanced.
5. **RESTRICTIONS**: Reply in English only. Do not mention your training data or AI nature unless asked.
"""

SystemChatBot = [
    {"role": "system", "content": System}
]

# Real-time date & time
def RealtimeInformation():
    now = datetime.datetime.now()
    return f"Day: {now.strftime('%A')}\nDate: {now.strftime('%d/%m/%Y')}\nTime: {now.strftime('%H:%M:%S')}\n"

# Main chatbot function
def ChatBot(Query):
    global messages

    try:
        log_path = os.path.join("Data", "ChatLog.json")
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8") as f:
                messages = load(f)

        combined_system_prompt = SystemChatBot[0]["content"] + "\n" + RealtimeInformation()
        messages_to_send = [{"role": "system", "content": combined_system_prompt}] + messages[-5:] + [{"role": "user", "content": Query}]

        Answer = ""

        # 1. Try Groq (Llama-3.3-70b)
        try:
            completion = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages_to_send,
                max_tokens=1024,
                temperature=0.7,
                stream=True
            )
            for chunk in completion:
                pass
                if chunk.choices[0].delta.content:
                    Answer += chunk.choices[0].delta.content
                    yield Answer

        # 2. Fallback to Groq (Llama-3.1-8b) if 429
        except Exception as e:
            if "429" in str(e):
                print(f"Groq 70B Rate Limit, falling back to 8B...")
                completion = client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=messages_to_send,
                    max_tokens=1024,
                    temperature=0.7,
                    stream=True
                )
                for chunk in completion:
                    pass
                    if chunk.choices[0].delta.content:
                        Answer += chunk.choices[0].delta.content
                        yield Answer
            else: raise e

    except Exception as e:
        # 3. Final Fallback to Cohere
        try:
            print(f"Groq Failed, falling back to Cohere...")
            stream = co_client.chat_stream(
                model="command-r-plus-08-2024",
                message=Query,
                preamble=System + "\n" + RealtimeInformation(),
                connectors=[]
            )
            Answer = ""
            for event in stream:
                pass
                if event.event_type == "text-generation":
                    Answer += event.text
                    yield Answer
        except Exception as final_e:
            print(f"All Models Failed: {final_e}")
            yield f"Error: {final_e}"

    # Save interaction
    if Answer:
        try:
            messages.append({"role": "user", "content": Query})
            messages.append({"role": "assistant", "content": Answer})
            log_path = os.path.join("Data", "ChatLog.json")
            with open(log_path, "w", encoding="utf-8") as f:
                dump(messages, f, indent=4)
        except: pass


# Run program
if __name__ == "__main__":
    while True:
        user_input = input("Enter Your Question: ")
        print("Assistant: ", end="", flush=True)
        full_response = ""
        for chunk in ChatBot(user_input):
            new_chars = chunk[len(full_response):]
            print(new_chars, end="", flush=True)
            full_response = chunk
        print()