import os
import sys
import datetime
import io
from json import load, dump
from dotenv import load_dotenv
import os
from groq import Groq
import cohere
import warnings


# Force UTF-8 encoding for standard output to handle symbols like the Rupee sign
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Suppress warnings
warnings.filterwarnings("ignore")

# Load environment variables
load_dotenv()

Username = os.getenv("Username", "User")
Assistantname = os.getenv("Assistantname", "Nemo")
GroqAPIKey = os.getenv("GroqAPIKey")
CohereAPIKey = os.getenv("CohereAPIKey")

# Initialize clients
client = Groq(api_key=GroqAPIKey)
co_client = cohere.Client(api_key=CohereAPIKey)

# Global messages list
messages = []

# System prompt
System = f"""You are {Assistantname}, my advanced, deeply respectful, and high-energy AI assistant. 
You are speaking with {Username}. Your goal is to provide cheerful, supportive, and helpful responses using real-time information.

*** MANDATORY FORMATTING RULE ***:
Whenever you provide CODE, SCRIPTS, or TECHNICAL EXPLANATIONS involving logic, you MUST use Markdown code blocks (e.g., ```python ... ```). 
IMPORTANT: The code MUST be perfectly aligned and indented for direct use in an editor (e.g., Python scripts must use 4-space indentation). Do NOT add extra characters or 'copy-paste' hints inside the backticks.

*** RULES FOR RESPONSE LENGTH & TONE: ***
1. **RESPONSE LENGTH**: 
   - **Default**: Aim for about 2 to 3 lines (30-50 words) for general search topics.
   - **Detailed Request**: If the user asks you to "tell in detail", "explain comprehensively", or provide a "long" answer, provide a thorough, multi-paragraph response using the search data.
   - **Brief Request**: If the user asks for a "brief" or "quick" answer, keep it very short (1 sentence).
2. **GREETINGS**: If the user greets you, respond with a warm, cheerful, and respectful message.
3. **RESPECT & ENERGY**: Treat the user with high respect and positive energy.
4. **INTEGRATION**: Seamlessly blend search data into a natural conversation that matches the user's requested level of detail.
5. **LANGUAGE**: Always respond in English.
"""

# Search Function
def GoogleSearch(query):
    try:
        from duckduckgo_search import DDGS
        results = []
        try:
            with DDGS() as ddgs:
                ddgs_gen = ddgs.text(query, max_results=5)
                if ddgs_gen:
                    for r in ddgs_gen:
                        results.append({
                            'title': r.get('title', 'No Title'),
                            'body': r.get('body', 'No Description'),
                            'href': r.get('href', '#')
                        })
        except Exception as e:
            print(f"DDG Search Error: {e}")

        # Fallback to googlesearch-python if DDGS is empty
        if not results:
            try:
                from googlesearch import search
                google_results = search(query, num_results=5, advanced=True)
                for r in google_results:
                    results.append({
                        'title': r.title,
                        'body': r.description,
                        'href': r.url
                    })
            except Exception as ge:
                print(f"Google Search Fallback Error: {ge}")

        if not results:
            return f"No search results found for '{query}' on any engine. Please try rephrasing."

        Answer = f"The search results for '{query}' are:\n[start]\n"
        for i in results:
            Answer += f"Title: {i.get('title')}\nDescription: {i.get('body')}\nUrl: {i.get('href')}\n\n"
        Answer += "[end]"
        return Answer
    except Exception as e:
        return f"No search results found for '{query}' due to a critical error: {e}"

# Real-time info
def Information():
    now = datetime.datetime.now()
    return f"Time: {now.strftime('%H:%M:%S')}\nDate: {now.strftime('%d/%m/%Y')}\nDay: {now.strftime('%A')}\n"

# Main Engine
def RealtimeSearchEngine(prompt):
    global messages

    Answer = ""
    search_context = ""

    try:
        log_path = os.path.join("Data", "ChatLog.json")
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8") as f:
                try:
                    messages = load(f)
                except:
                    messages = []
        else:
            messages = []

        # Clean search query (remove conversational filler)
        search_query = prompt.lower()
        fillers = [Assistantname.lower(), "hey", "tell me", "what is", "who is", "about", "please", "search for", "find info on", "can you", "search"]
        for word in fillers:
            search_query = search_query.replace(word, "").strip()
        
        if len(search_query) < 2: search_query = prompt

        search_data = GoogleSearch(search_query)
        
        # Format search context prominently
        search_context = f"REAL-TIME SEARCH RESULTS (As of {Information()}):\n{search_data}\n\nIMPORTANT: Use the above search results to provide a current and factual answer."
        
        combined_system_prompt = System + "\n" + search_context
        messages_to_send = [
            {"role": "system", "content": combined_system_prompt},
        ] + messages[-5:] + [
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
                pass
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
                        pass
                        if chunk.choices[0].delta.content:
                            Answer += chunk.choices[0].delta.content
                            yield Answer
                except Exception as e2:
                    # Final Fallback to Cohere if 8B also fails
                    for text in FallbackToCohere(prompt, search_context):
                        Answer = text
                        yield Answer
            else:
                # Fallback to Cohere for other Groq errors
                for text in FallbackToCohere(prompt, search_context):
                    Answer = text
                    yield Answer

    except Exception as e:
        print(f"Critical Error: {e}")
        yield f"Error: {e}"

    # Save interaction
    if Answer:
        try:
            messages.append({"role": "user", "content": prompt})
            messages.append({"role": "assistant", "content": Answer})
            log_path = os.path.join("Data", "ChatLog.json")
            with open(log_path, "w", encoding="utf-8") as f:
                dump(messages, f, indent=4)
        except: pass

def FallbackToCohere(prompt, search_context):
    full_text = ""
    try:
        print(f"Groq Failed, falling back to Cohere...")
        combined_content = f"{System}\n{search_context}"
        stream = co_client.chat_stream(
            model="command-r-plus-08-2024",
            message=prompt,
            preamble=combined_content,
            connectors=[]
        )
        for event in stream:
            pass
            if event.event_type == "text-generation":
                full_text += event.text
                yield full_text
    except Exception as final_e:
        print(f"All Models Failed: {final_e}")
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
