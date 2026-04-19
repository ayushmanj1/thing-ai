import os
import sys
import datetime
import io
from dotenv import load_dotenv
from groq import Groq
import cohere
import warnings

# Force UTF-8 encoding
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

warnings.filterwarnings("ignore")

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
    return f"""You are {Assistantname}, a highly intelligent, helpful, and professional AI assistant. 
You are currently chatting with {user_name}. Your goal is to provide cheerful, supportive, and helpful responses using real-time information.

*** MANDATORY FORMATTING RULE ***:
- ONLY use Markdown code blocks (triple backticks) for COMPUTER PROGRAMMING CODES (e.g., Python, C++, HTML/CSS, etc.). 
- For NON-PROGRAMMING content such as letters, notices, essays, or document formats, use standard plain text without code blocks. 
- Programming code MUST be perfectly aligned and indented for direct editor use (e.g., 4-space indentation for Python).

*** RULES FOR RESPONSE LENGTH & TONE: ***
1. **RESPONSE LENGTH**: 
   - **Default**: Aim for about 2 to 3 lines (30-50 words) for general search topics.
   - **Detailed Request**: If the user asks you to "tell in detail", "explain comprehensively", or provide a "long" answer, provide a thorough, multi-paragraph response using the search data.
   - **Brief Request**: If the user asks for a "brief" or "quick" answer, keep it very short (1 sentence).
2. **GREETINGS**: If the user greets you, respond with a warm and respectful message.
3. **TONE**: Be professional, supportive, and helpful.
4. **INTEGRATION**: Seamlessly blend search data into a natural conversation.
5. **LANGUAGE**: Always respond in English.
"""

# Search Function
def GoogleSearch(query):
    print(f"[GoogleSearch] Searching for: {query}")
    try:
        from duckduckgo_search import DDGS
        results = []
        try:
            with DDGS() as ddgs:
                ddgs_gen = ddgs.text(keywords=query, max_results=5)
                if ddgs_gen:
                    for r in ddgs_gen:
                        results.append({
                            'title': r.get('title', 'No Title'),
                            'body': r.get('body', 'No Description'),
                            'href': r.get('href', '#')
                        })
        except Exception as e:
            print(f"[GoogleSearch] DDG Search Error: {e}")

        if not results:
            print(f"[GoogleSearch] DDG returned no results, trying Google fallback...")
            try:
                from googlesearch import search
                google_results = list(search(query, num_results=5, advanced=True))
                for r in google_results:
                    results.append({
                        'title': r.title,
                        'body': r.description,
                        'href': r.url
                    })
            except Exception as ge:
                print(f"[GoogleSearch] Google Search Fallback Error: {ge}")

        if not results:
            return f"No search results found for '{query}'."

        Answer = f"The search results for '{query}' are:\n[start]\n"
        for i in results:
            Answer += f"Title: {i.get('title')}\nDescription: {i.get('body')}\nUrl: {i.get('href')}\n\n"
        Answer += "[end]"
        return Answer
    except Exception as e:
        return f"I encountered a search error: {e}"

# Real-time info
def Information():
    now = datetime.datetime.now()
    return f"Time: {now.strftime('%H:%M:%S')}\nDate: {now.strftime('%d/%m/%Y')}\nDay: {now.strftime('%A')}\n"

# Main Engine
def RealtimeSearchEngine(prompt, provided_messages=None, user_name=None):
    if provided_messages is None:
        provided_messages = []
    if user_name is None:
        user_name = DefaultUsername

    Answer = ""
    search_context = ""

    try:
        search_query = prompt.lower()
        fillers = [Assistantname.lower(), "hey", "tell me", "what is", "who is", "about", "please", "search for", "find info on", "can you", "search"]
        for word in fillers:
            search_query = search_query.replace(word, "").strip()
        
        if len(search_query) < 2: search_query = prompt

        search_data = GoogleSearch(search_query)
        search_context = f"REAL-TIME SEARCH RESULTS (As of {Information()}):\n{search_data}\n\nIMPORTANT: Use the above search results to provide a current and factual answer."
        
        system_content = GetSystemMessage(user_name)
        combined_system_prompt = system_content + "\n" + search_context
        messages_to_send = [
            {"role": "system", "content": combined_system_prompt},
        ] + provided_messages[-5:] + [
            {"role": "user", "content": prompt}
        ]

        # 1. Try Groq (Llama-3.3-70b)
        try:
            completion = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages_to_send,
                temperature=0.2,
                max_tokens=2048,
                stream=True
            )
            for chunk in completion:
                if chunk.choices[0].delta.content:
                    Answer += chunk.choices[0].delta.content
                    yield Answer

        except Exception as e:
            if "429" in str(e):
                print(f"Groq 70B Rate Limit, falling back to 8B...")
                try:
                    completion = client.chat.completions.create(
                        model="llama-3.1-8b-instant",
                        messages=messages_to_send,
                        temperature=0.2,
                        max_tokens=2048,
                        stream=True
                    )
                    for chunk in completion:
                        if chunk.choices[0].delta.content:
                            Answer += chunk.choices[0].delta.content
                            yield Answer
                except Exception as e2:
                    for text in FallbackToCohere(prompt, search_context, user_name):
                        Answer = text
                        yield Answer
            else:
                for text in FallbackToCohere(prompt, search_context, user_name):
                    Answer = text
                    yield Answer

    except Exception as e:
        print(f"Critical Error: {e}")
        yield f"Error: {e}"

    if Answer:
        provided_messages.append({"role": "user", "content": prompt})
        provided_messages.append({"role": "assistant", "content": Answer})

def FallbackToCohere(prompt, search_context, user_name):
    full_text = ""
    try:
        print(f"Groq Failed, falling back to Cohere...")
        system_content = GetSystemMessage(user_name)
        combined_content = f"{system_content}\n{search_context}"
        stream = co_client.chat_stream(
            model="command-r-plus-08-2024",
            message=prompt,
            preamble=combined_content,
            connectors=[]
        )
        for event in stream:
            if event.event_type == "text-generation":
                full_text += event.text
                yield full_text
    except Exception as final_e:
        yield f"Error: {final_e}"

# Run program
if __name__ == "__main__":
    while True:
        prompt = input("Enter your query: ")
        print("Assistant: ", end="", flush=True)
        full_response = ""
        for chunk in RealtimeSearchEngine(prompt):
            new_chars = chunk[len(full_response):]
            print(new_chars, end="", flush=True)
            full_response = chunk
        print()
