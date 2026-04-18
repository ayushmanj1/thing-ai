import os
from groq import Groq
import cohere
import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

DefaultUsername = os.getenv("Username", "User")
Assistantname = os.getenv("Assistantname", "Nemo")
GroqAPIKey = os.getenv("GroqAPIKey")
CohereAPIKey = os.getenv("CohereAPIKey")

# Initialize clients
client = Groq(api_key=GroqAPIKey)
co_client = cohere.Client(api_key=CohereAPIKey)

def GetSystemMessage(user_name=DefaultUsername):
    return f"""
Hello, I am {user_name}, 
You are {Assistantname}, my advanced, respectful, and high-energy AI assistant. 

*** MANDATORY FORMATTING RULE ***:
- ONLY use Markdown code blocks (triple backticks) for COMPUTER PROGRAMMING CODES (e.g., Python, C++, HTML/CSS, etc.). 
- For NON-PROGRAMMING content such as letters, notices, essays, or document formats, use standard plain text without code blocks. 
- Programming code MUST be perfectly aligned and indented for direct editor use (e.g., 4-space indentation for Python).

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

# Real-time date & time
def RealtimeInformation():
    now = datetime.datetime.now()
    return f"Day: {now.strftime('%A')}\nDate: {now.strftime('%d/%m/%Y')}\nTime: {now.strftime('%H:%M:%S')}\n"

# Main chatbot function
def ChatBot(Query, provided_messages=None, user_name=None):
    if provided_messages is None:
        provided_messages = []
    if user_name is None:
        user_name = DefaultUsername

    try:
        system_content = GetSystemMessage(user_name)
        combined_system_prompt = system_content + "\n" + RealtimeInformation()
        messages_to_send = [{"role": "system", "content": combined_system_prompt}] + provided_messages[-5:] + [{"role": "user", "content": Query}]

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
                preamble=GetSystemMessage(user_name) + "\n" + RealtimeInformation(),
                connectors=[]
            )
            Answer = ""
            for event in stream:
                if event.event_type == "text-generation":
                    Answer += event.text
                    yield Answer
        except Exception as final_e:
            print(f"All Models Failed: {final_e}")
            yield f"Error: {final_e}"

    # Save interaction to logic outside this generator if needed, 
    # but for compatibility, we update the passed list.
    if Answer:
        provided_messages.append({"role": "user", "content": Query})
        provided_messages.append({"role": "assistant", "content": Answer})

def ClearChatHistory(provided_messages=None):
    if provided_messages is not None:
        provided_messages.clear()


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