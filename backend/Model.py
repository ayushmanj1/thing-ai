import cohere
from rich import print
from dotenv import dotenv_values

# Load environment variables from the .env file.
env_vars = dotenv_values(".env")

# Retrieve API key.
CohereAPIKey = env_vars.get("CohereAPIKey")

# Create a Cohere client using the provided API key.
if not CohereAPIKey:
    print("Warning: CohereAPIKey is missing from .env")
    co = None
else:
    co = cohere.Client(api_key=CohereAPIKey)

# Define a list of recognized function keywords for task categorization.
funcs = [
    "exit", "general", "realtime", "open", "close", "play",
    "generate image", "system", "content", "google search",
    "youtube search", "reminder"
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
-> 'open (app/site)': To open applications or websites.
-> 'close (app)': To close applications.
-> 'play (song)': To play music on YouTube.
-> 'generate image (prompt)': To create images.
-> 'system (task)': For mute, unmute, volume up/down, wifi on/off, airplane mode on/off, battery saver on/off, night light on/off.
-> 'google search (topic)': For manual Google searches.
-> 'youtube search (topic)': For manual YouTube search.

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
    {"role": "User", "message": "open youtube and search for mr beast"},
    {"role": "Chatbot", "message": "open youtube, youtube search mr beast"},
    {"role": "User", "message": "i love you so much"},
    {"role": "Chatbot", "message": "general i love you so much"},
    {"role": "User", "message": "is it raining in london?"},
    {"role": "Chatbot", "message": "realtime is it raining in london?"},
    {"role": "User", "message": "who is elon musk?"},
    {"role": "Chatbot", "message": "realtime who is elon musk?"},
    {"role": "User", "message": "write a leave application for school"},
    {"role": "Chatbot", "message": "content write a leave application for school"},
    {"role": "User", "message": "turn on the wifi"},
    {"role": "Chatbot", "message": "system wifi on"},
    {"role": "User", "message": "turn off airplane mode"},
    {"role": "Chatbot", "message": "system airplane mode off"},
    {"role": "User", "message": "enable battery saver"},
    {"role": "Chatbot", "message": "system battery saver on"},
    {"role": "User", "message": "turn on night light"},
    {"role": "Chatbot", "message": "system night light on"}
]

# Define the main function for decision-making on queries.
def FirstLayerDMM(prompt: str = "test"):
    try:
        if not co: return ["general " + prompt]
        
        GroqAPIKey = env_vars.get("GroqAPIKey")
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