import cohere
from rich import print
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()

# Retrieve API key
CohereAPIKey = os.getenv("CohereAPIKey")

# Create a Cohere client using the provided API key.
if not CohereAPIKey:
    print("Warning: CohereAPIKey is missing from .env")
    co = None
else:
    co = cohere.Client(api_key=CohereAPIKey)

# Define a list of recognized function keywords for task categorization.
funcs = [
    "exit", "general", "realtime", "generate image", "content"
]

# Initialize an empty list to store user messages.
messages = []

# Define the preamble that guides the AI model on how to categorize queries.
preamble = """You are a highly accurate Decision-Making Model. 
Your ONLY task is to categorize the user's query into one or more categories.

*** CATEGORY LIST: ***
-> 'realtime (query)': For ANY factual info, news, weather, prices, or web searches. (PRIORITY)
-> 'general (query)': For greetings, jokes, personal/emotive chat, or general conversation.
-> 'content (topic)': For formal writing, code, essays, or long-form applications ONLY.
-> 'generate image (prompt)': To create images.

*** MANDATORY RULES: ***
1. ONLY respond with the tags mentioned above. 
2. DO NOT engage in conversation. 
3. DO NOT explain your decision. 
4. DO NOT provide any text other than the categorized tags.
5. If the user query is multiple things, separate tags with a comma.
6. If the user query matches NO specific task, always choose 'general (query)'.
"""

# Define a chat history with predefined user-chatbot interactions for context.
ChatHistory = [
    {"role": "User", "message": "hello jarvis"},
    {"role": "Chatbot", "message": "general hello jarvis"},
    {"role": "User", "message": "what is the price of gold in india?"},
    {"role": "Chatbot", "message": "realtime what is the price of gold in india?"},
    {"role": "User", "message": "who is the current prime minister?"},
    {"role": "Chatbot", "message": "realtime who is the current prime minister?"},
    {"role": "User", "message": "tell me a joke"},
    {"role": "Chatbot", "message": "general tell me a joke"},
    {"role": "User", "message": "what is happening in us iran right now?"},
    {"role": "Chatbot", "message": "realtime what is happening in us iran right now?"},
    {"role": "User", "message": "current stock price of nvidia"},
    {"role": "Chatbot", "message": "realtime current stock price of nvidia"},
    {"role": "User", "message": "i love you so much"},
    {"role": "Chatbot", "message": "general i love you so much"},
    {"role": "User", "message": "is it raining in london?"},
    {"role": "Chatbot", "message": "realtime is it raining in london?"},
    {"role": "User", "message": "give me a python code for bubble sort"},
    {"role": "Chatbot", "message": "content give me a python code for bubble sort"},
    {"role": "User", "message": "what is the format of a formal letter?"},
    {"role": "Chatbot", "message": "general what is the format of a formal letter?"},
    {"role": "User", "message": "tell me the format for a notice for school assembly"},
    {"role": "Chatbot", "message": "general tell me the format for a notice for school assembly"},
    {"role": "User", "message": "explain how a convolutional neural network works"},
    {"role": "Chatbot", "message": "content explain how a convolutional neural network works"},
    {"role": "User", "message": "write a leave application for school"},
    {"role": "Chatbot", "message": "content write a leave application for school"}
]

# Define the main function for decision-making on queries.
def FirstLayerDMM(prompt: str = "test"):
    try:
        if not co: return ["general " + prompt]
        
        GroqAPIKey = os.getenv("GroqAPIKey")
        if GroqAPIKey:
            from groq import Groq
            groq_client = Groq(api_key=GroqAPIKey)
            
            # Format history for Groq
            groq_messages = [{"role": "system", "content": preamble}]
            for msg in ChatHistory:
                role = "user" if msg["role"] == "User" else "assistant"
                groq_messages.append({"role": role, "content": msg["message"]})
            groq_messages.append({"role": "user", "content": prompt})

            try:
                completion = groq_client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=groq_messages,
                    temperature=0.1,
                    max_tokens=64
                )
                response = completion.choices[0].message.content.strip()
            except Exception as e:
                print(f"Groq Decision Error: {e}, falling back to Cohere...")
                response = ""
        else:
            response = ""

        # Fallback to Cohere
        if not response and co is not None:
            stream = co.chat_stream(
                model='command-r-plus-08-2024',
                message=prompt,
                temperature=0.1,
                chat_history=ChatHistory,
                prompt_truncation='OFF',
                connectors=[],
                preamble=preamble
            )
            for event in stream:
                if event.event_type == "text-generation":
                    response += event.text
    except Exception as e:
        print(f"Decision Error: {e}")
        return ["general " + prompt]

    if not response:
        return ["general " + prompt]

    # Process response
    response = response.replace("\n", "").split(",")
    response = [i.strip() for i in response]

    # Filter the tasks based on recognized function keywords.
    temp = []
    for task in response:
        matched = False
        for func in funcs:
            if task.lower().startswith(func):
                clean_task = task.lower().replace(func, "").strip()
                if not clean_task:
                    task = f"{func} {prompt}"
                temp.append(task)
                matched = True
                break
    
    # Final Result with Fallback
    if not temp:
        result = ["general " + prompt]
    else:
        result = temp

    return result

# Entry point for the script.
if __name__ == "__main__":
    while True:
        print(FirstLayerDMM(input(">>> ")))