import os
import sys
import datetime
import io
from dotenv import load_dotenv
from backend.Utils import UniversalAI
import warnings

# Force UTF-8 encoding
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

warnings.filterwarnings("ignore")

# Load environment variables
load_dotenv(override=True)

DefaultUsername = os.getenv("Username", "User")
Assistantname = os.getenv("Assistantname", "Thing")

def GetSystemMessage(user_name=DefaultUsername):
    return f"""You are {Assistantname}, a highly intelligent, helpful, and professional AI assistant. 
You are currently chatting with {user_name}. Your goal is to provide cheerful, supportive, and helpful responses using real-time information.

*** IDENTITY RULES ***:
- Your name is ALWAYS "{Assistantname}".
- You must NEVER refer to yourself as "Nemo AI" or any previous name.
- If a user asks your name, you respond: "I'm {Assistantname}."
- If a user mentions "Nemo AI", clarify that it was an old name and you are now "{Assistantname}".
- Maintain this identity consistently across all sessions.

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

def Information():
    now = datetime.datetime.now()
    return f"Time: {now.strftime('%H:%M:%S')}\nDate: {now.strftime('%d/%m/%Y')}\nDay: {now.strftime('%A')}\n"

def RealtimeSearchEngine(prompt, provided_messages=None, user_name=None):
    if provided_messages is None:
        provided_messages = []
    if user_name is None:
        user_name = DefaultUsername

    search_query = prompt.lower()
    fillers = [Assistantname.lower(), "hey", "tell me", "what is", "who is", "about", "please", "search for", "find info on", "can you", "search"]
    for word in fillers:
        search_query = search_query.replace(word, "").strip()
    
    if len(search_query) < 2: search_query = prompt

    search_data = GoogleSearch(search_query)
    search_context = f"REAL-TIME SEARCH RESULTS (As of {Information()}):\n{search_data}\n\nIMPORTANT: Use the above search results to provide a current and factual answer."
    
    system_content = GetSystemMessage(user_name)
    combined_system_prompt = system_content + "\n" + search_context
    
    Answer = ""
    for chunk in UniversalAI(prompt, system_prompt=combined_system_prompt, history=provided_messages, temperature=0.2):
        Answer += chunk
        yield Answer

    if Answer:
        provided_messages.append({"role": "user", "content": prompt})
        provided_messages.append({"role": "assistant", "content": Answer})

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
