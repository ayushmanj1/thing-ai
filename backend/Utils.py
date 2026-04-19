import os
import time
from groq import Groq
import cohere
from dotenv import load_dotenv

# Load environment variables
load_dotenv(override=True)

# API Keys
GroqAPIKey = os.getenv("GroqAPIKey")
CohereAPIKey = os.getenv("CohereAPIKey")
Assistantname = os.getenv("Assistantname", "Thing")

# Initialize clients (Lazy initialization could be used, but module-level is fine for now)
groq_client = Groq(api_key=GroqAPIKey) if GroqAPIKey else None
co_client = cohere.Client(api_key=CohereAPIKey) if CohereAPIKey else None

def UniversalAI(prompt, system_prompt=None, history=None, stream=True, temperature=0.7, max_tokens=2048):
    """
    A universal wrapper for AI calls with fallback logic.
    Tries Groq (70B), then Groq (8B) if rate limited, then Cohere.
    """
    if history is None:
        history = []
    
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    
    # Add history (last 5 messages)
    for msg in history[-5:]:
        messages.append(msg)
    
    # Add current query
    messages.append({"role": "user", "content": prompt})

    # Strategy 1: Groq 70B
    if groq_client:
        try:
            completion = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=stream
            )
            if stream:
                answer = ""
                for chunk in completion:
                    content = chunk.choices[0].delta.content
                    if content:
                        answer += content
                        yield content
                return
            else:
                return completion.choices[0].message.content
        except Exception as e:
            if "429" in str(e):
                print(f"[Utils] Groq 70B Rate Limit. Trying 8B...")
            else:
                print(f"[Utils] Groq 70B Error: {e}. Trying 8B...")

    # Strategy 2: Groq 8B
    if groq_client:
        try:
            completion = groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=stream
            )
            if stream:
                answer = ""
                for chunk in completion:
                    content = chunk.choices[0].delta.content
                    if content:
                        answer += content
                        yield content
                return
            else:
                return completion.choices[0].message.content
        except Exception as e:
            print(f"[Utils] Groq 8B Error: {e}. Trying Cohere...")

    # Strategy 3: Cohere
    if co_client:
        try:
            if stream:
                stream_resp = co_client.chat_stream(
                    model="command-r-plus-08-2024",
                    message=prompt,
                    preamble=system_prompt,
                    # Cohere handles history differently, but for simplicity we keep it as is or adapt
                    chat_history=[{"role": m["role"].upper() if m["role"] != "system" else "SYSTEM", "message": m["content"]} for m in history[-5:]],
                    connectors=[]
                )
                for event in stream_resp:
                    if event.event_type == "text-generation":
                        yield event.text
                return
            else:
                resp = co_client.chat(
                    model="command-r-plus-08-2024",
                    message=prompt,
                    preamble=system_prompt,
                    chat_history=[{"role": m["role"].upper() if m["role"] != "system" else "SYSTEM", "message": m["content"]} for m in history[-5:]]
                )
                return resp.text
        except Exception as e:
            print(f"[Utils] Cohere Error: {e}")

    yield "I'm sorry, all my thinking modules are currently unavailable. Please check your API keys or try again later."
