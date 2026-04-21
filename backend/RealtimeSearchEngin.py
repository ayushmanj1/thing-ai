import os
import sys
import re
import datetime
import io
import json
import requests
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus
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

# --- Keywords that signal time-sensitive queries ---
TEMPORAL_KEYWORDS = [
    "current", "latest", "today", "now", "present", "recent",
    "new", "currently", "2025", "2026", "right now", "as of",
    "who is the", "who's the"
]

FINANCIAL_KEYWORDS = [
    "price", "stock", "share", "gold", "silver", "bitcoin", "btc",
    "ethereum", "eth", "crypto", "nifty", "sensex", "market",
    "forex", "crude oil", "commodity"
]

WEATHER_KEYWORDS = ["weather", "temperature", "forecast", "rain", "raining"]

CURRENT_AFFAIRS_KEYWORDS = [
    "president", "prime minister", "pm", "cm", "chief minister",
    "governor", "ceo", "chairman", "leader", "minister",
    "election", "war", "news", "happening"
]


def GetSystemMessage(user_name=DefaultUsername):
    now = datetime.datetime.now()
    current_date = now.strftime("%B %d, %Y")
    current_year = now.strftime("%Y")

    return f"""You are {Assistantname}, a highly intelligent, helpful, and professional AI assistant. 
You are currently chatting with {user_name}. Your goal is to provide cheerful, supportive, and helpful responses using real-time information.

*** CRITICAL: TODAY'S DATE IS {current_date} (Year: {current_year}) ***

*** IDENTITY RULES ***:
- Your name is ALWAYS "{Assistantname}".
- Your creator/designer is ALWAYS "Ayushman Jha".
- You must NEVER refer to yourself as "Nemo AI" or any previous name.
- If a user asks your name, you respond: "I'm {Assistantname}."
- If a user asks who created or designed you, respond: "I was designed and created by Ayushman Jha."
- If a user mentions "Nemo AI", clarify that it was an old name and you are now "{Assistantname}".
- Maintain this identity consistently across all sessions.

*** REAL-TIME DATA RULES (ABSOLUTELY CRITICAL — READ CAREFULLY) ***:
- You DO have access to real-time data via the search results provided below.
- NEVER say "I cannot access real-time data" or "I don't have real-time information."
- For ANY factual question (who is the current leader, what is the price, what is the score, etc.):
  → You MUST answer ONLY based on the provided search results.
  → DO NOT use your training data or internal knowledge for factual/current answers.
  → If the search results contain the answer, USE IT — even if it contradicts your training data.
  → Your training data is OUTDATED. The search results are LIVE and CURRENT as of {current_date}.
- If search results don't contain enough info, say "Based on the latest available data..." and give what you can.
- NEVER give an answer from your training data and present it as current fact.

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


def clean_search_query(prompt):
    """Clean the user prompt into a good search query using whole-word matching
    so that substrings inside real words are NOT removed."""
    search_query = prompt.lower().strip()

    # Remove trailing punctuation
    while search_query and search_query[-1] in '?!.':
        search_query = search_query[:-1].strip()

    # Filler words/phrases to remove — use word-boundary regex so
    # "hi" does NOT match inside "delhi", "search" does NOT match inside "research", etc.
    fillers = [
        "hlo", "hi", "hello", Assistantname.lower(), "hey",
        "tell me", "please", "search for", "find info on",
        "can you", "ok", "yo", "bro", "dude"
    ]
    # Sort by length descending so longer phrases are removed first
    fillers.sort(key=len, reverse=True)

    for word in fillers:
        # \b = word boundary — prevents partial-word matches
        search_query = re.sub(r'\b' + re.escape(word) + r'\b', '', search_query, flags=re.IGNORECASE)

    # Collapse multiple spaces and strip
    search_query = re.sub(r'\s+', ' ', search_query).strip()

    # If cleaning removed everything, fall back to the original prompt
    if len(search_query) < 2:
        search_query = prompt.strip()
        while search_query and search_query[-1] in '?!.':
            search_query = search_query[:-1].strip()

    return search_query


def enhance_query_for_recency(query):
    """For time-sensitive queries, append the current year/month to force
    search engines to return recent results instead of old Wikipedia pages."""
    query_lower = query.lower()
    now = datetime.datetime.now()
    year = now.strftime("%Y")
    month = now.strftime("%B")  # e.g. "April"

    is_temporal = any(kw in query_lower for kw in TEMPORAL_KEYWORDS)
    is_current_affairs = any(kw in query_lower for kw in CURRENT_AFFAIRS_KEYWORDS)

    # Already has a year in it? Don't add another
    if re.search(r'\b20\d{2}\b', query):
        return query

    if is_temporal or is_current_affairs:
        enhanced = f"{query} {year}"
        print(f"[QueryEnhancer] 📅 Enhanced: '{query}' → '{enhanced}'")
        return enhanced

    return query


def detect_query_type(query):
    """Detect what kind of real-time query this is."""
    query_lower = query.lower()
    types = set()
    if any(kw in query_lower for kw in WEATHER_KEYWORDS):
        types.add("weather")
    if any(kw in query_lower for kw in FINANCIAL_KEYWORDS):
        types.add("financial")
    if any(kw in query_lower for kw in CURRENT_AFFAIRS_KEYWORDS):
        types.add("current_affairs")
    if any(kw in query_lower for kw in TEMPORAL_KEYWORDS):
        types.add("temporal")
    if not types:
        types.add("general")
    return types


# =====================================================================
# DEDICATED REAL-TIME DATA SOURCES
# =====================================================================

def fetch_weather(query):
    """Get live weather data from wttr.in (free, no API key needed)."""
    location = query.lower()
    for w in ["weather", "temperature", "forecast", "in", "of", "for", "the", "current", "today", "right now", "what is", "what's", "how's", "how is"]:
        location = re.sub(r'\b' + re.escape(w) + r'\b', '', location, flags=re.IGNORECASE)
    location = re.sub(r'\s+', ' ', location).strip()
    if not location:
        return None
    try:
        print(f"[WeatherAPI] 🌤️ Fetching weather for: '{location}'")
        resp = requests.get(
            f"https://wttr.in/{location}?format=j1",
            headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"},
            timeout=6
        )
        if resp.status_code == 200:
            data = resp.json()
            current = data.get("current_condition", [{}])[0]
            area = data.get("nearest_area", [{}])[0]
            area_name = area.get("areaName", [{}])[0].get("value", location)
            country = area.get("country", [{}])[0].get("value", "")
            desc = current.get("weatherDesc", [{}])[0].get("value", "N/A")
            temp_c = current.get("temp_C", "N/A")
            temp_f = current.get("temp_F", "N/A")
            feels_c = current.get("FeelsLikeC", "N/A")
            humidity = current.get("humidity", "N/A")
            wind_kmph = current.get("windspeedKmph", "N/A")
            wind_dir = current.get("winddir16Point", "")
            precip = current.get("precipMM", "0")
            uv = current.get("uvIndex", "N/A")
            visibility = current.get("visibility", "N/A")

            weather_text = (
                f"Title: [LIVE WEATHER] Current Weather in {area_name}, {country}\n"
                f"Description: Condition: {desc}. Temperature: {temp_c}°C ({temp_f}°F). "
                f"Feels Like: {feels_c}°C. Humidity: {humidity}%. "
                f"Wind: {wind_kmph} km/h {wind_dir}. Precipitation: {precip} mm. "
                f"UV Index: {uv}. Visibility: {visibility} km.\n"
                f"Url: https://wttr.in/{location}\n"
            )
            print(f"[WeatherAPI] ✅ Got weather data for {area_name}")
            return weather_text
    except Exception as e:
        print(f"[WeatherAPI] ❌ Error: {e}")
    return None


def fetch_financial_data(query):
    """Fetch live financial data from free APIs (no API key needed)."""
    results = []
    query_lower = query.lower()

    # --- Gold / Silver / Commodity prices ---
    if any(w in query_lower for w in ["gold", "silver", "platinum", "commodity"]):
        try:
            print(f"[FinanceAPI] 💰 Fetching metal prices...")
            resp = requests.get(
                "https://api.metals.dev/v1/latest?api_key=demo&currency=USD&unit=gram",
                timeout=6
            )
            if resp.status_code == 200:
                data = resp.json()
                metals = data.get("metals", {})
                if metals:
                    metal_info = []
                    for metal, price in metals.items():
                        if metal.lower() in query_lower or "gold" in metal.lower() or len(metals) <= 5:
                            metal_info.append(f"{metal}: ${price}/gram")
                    if metal_info:
                        results.append({
                            'title': '[LIVE PRICE] Metal/Commodity Prices (USD)',
                            'body': "Current prices: " + ", ".join(metal_info[:5]),
                            'href': '#'
                        })
                        print(f"[FinanceAPI] ✅ Got metal prices")
        except Exception as e:
            print(f"[FinanceAPI] Metal price error: {e}")

    # --- Crypto prices (CoinGecko — free, no API key) ---
    crypto_map = {
        "bitcoin": "bitcoin", "btc": "bitcoin",
        "ethereum": "ethereum", "eth": "ethereum",
        "dogecoin": "dogecoin", "doge": "dogecoin",
        "solana": "solana", "sol": "solana",
        "xrp": "ripple", "ripple": "ripple",
        "cardano": "cardano", "ada": "cardano",
    }
    detected_crypto = None
    for keyword, coin_id in crypto_map.items():
        if keyword in query_lower:
            detected_crypto = coin_id
            break

    if detected_crypto:
        try:
            print(f"[FinanceAPI] 🪙 Fetching crypto price for: {detected_crypto}")
            resp = requests.get(
                f"https://api.coingecko.com/api/v3/simple/price?ids={detected_crypto}&vs_currencies=usd,inr&include_24hr_change=true",
                timeout=6
            )
            if resp.status_code == 200:
                data = resp.json()
                coin_data = data.get(detected_crypto, {})
                if coin_data:
                    usd = coin_data.get("usd", "N/A")
                    inr = coin_data.get("inr", "N/A")
                    change = coin_data.get("usd_24h_change", 0)
                    change_str = f"+{change:.2f}%" if change >= 0 else f"{change:.2f}%"
                    results.append({
                        'title': f'[LIVE PRICE] {detected_crypto.capitalize()} Price',
                        'body': f"Current {detected_crypto.capitalize()} price: ${usd:,.2f} USD (₹{inr:,.2f} INR). 24hr change: {change_str}",
                        'href': f'https://www.coingecko.com/en/coins/{detected_crypto}'
                    })
                    print(f"[FinanceAPI] ✅ Got {detected_crypto} price: ${usd}")
        except Exception as e:
            print(f"[FinanceAPI] Crypto price error: {e}")

    # --- Stock prices (Yahoo Finance summary — unofficial) ---
    stock_patterns = re.findall(r'\b([A-Z]{2,5})\b', query)  # Detect tickers like AAPL, NVDA
    common_stocks = {
        "nvidia": "NVDA", "apple": "AAPL", "google": "GOOGL", "alphabet": "GOOGL",
        "microsoft": "MSFT", "amazon": "AMZN", "meta": "META", "facebook": "META",
        "tesla": "TSLA", "reliance": "RELIANCE.NS", "tata": "TCS.NS", "infosys": "INFY.NS",
        "nifty": "%5ENSEI", "sensex": "%5EBSESN"
    }
    detected_ticker = None
    for name, ticker in common_stocks.items():
        if name in query_lower:
            detected_ticker = ticker
            break
    if not detected_ticker and stock_patterns:
        detected_ticker = stock_patterns[0]

    if detected_ticker and any(w in query_lower for w in ["stock", "share", "price", "nifty", "sensex"]):
        try:
            print(f"[FinanceAPI] 📈 Fetching stock data for: {detected_ticker}")
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{detected_ticker}?interval=1d&range=1d",
                headers=headers, timeout=6
            )
            if resp.status_code == 200:
                data = resp.json()
                result_data = data.get("chart", {}).get("result", [{}])[0]
                meta = result_data.get("meta", {})
                price = meta.get("regularMarketPrice", "N/A")
                prev_close = meta.get("previousClose", 0)
                currency = meta.get("currency", "USD")
                symbol = meta.get("symbol", detected_ticker)
                if price != "N/A" and prev_close:
                    change = ((price - prev_close) / prev_close) * 100
                    change_str = f"+{change:.2f}%" if change >= 0 else f"{change:.2f}%"
                else:
                    change_str = "N/A"
                results.append({
                    'title': f'[LIVE STOCK] {symbol} Stock Price',
                    'body': f"Current {symbol} price: {price} {currency}. Change from previous close: {change_str}",
                    'href': f'https://finance.yahoo.com/quote/{detected_ticker}'
                })
                print(f"[FinanceAPI] ✅ Got stock price for {symbol}: {price}")
        except Exception as e:
            print(f"[FinanceAPI] Stock price error: {e}")

    return results


def fetch_google_news_rss(query):
    """Fetch fresh news from Google News RSS feed (free, no API key, always current)."""
    results = []
    try:
        encoded_query = quote_plus(query)
        url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en"
        print(f"[GoogleNewsRSS] 📰 Fetching news for: '{query}'")
        resp = requests.get(url, timeout=6, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            root = ET.fromstring(resp.content)
            items = root.findall('.//item')
            for item in items[:5]:
                title = item.findtext('title', 'No Title')
                desc = item.findtext('description', 'No Description')
                link = item.findtext('link', '#')
                pub_date = item.findtext('pubDate', '')
                # Clean HTML from description
                desc = re.sub(r'<[^>]+>', '', desc)
                results.append({
                    'title': f"[LATEST NEWS] {title}",
                    'body': f"{desc} (Published: {pub_date})" if pub_date else desc,
                    'href': link
                })
            if results:
                print(f"[GoogleNewsRSS] ✅ Got {len(results)} news articles")
            else:
                print(f"[GoogleNewsRSS] ⚠️ No news results found")
    except Exception as e:
        print(f"[GoogleNewsRSS] ❌ Error: {e}")
    return results


# =====================================================================
# MAIN SEARCH FUNCTION
# =====================================================================

def GoogleSearch(query, query_types=None):
    """Multi-source search function that prioritizes the right sources
    based on query type."""
    query = query.strip()
    while query and query[-1] in '?!.':
        query = query[:-1].strip()

    if query_types is None:
        query_types = detect_query_type(query)

    print(f"[GoogleSearch] 🔍 Searching for: \"{query}\" (types: {query_types})")
    results = []

    # --- DEDICATED APIs FIRST (most accurate for specific data) ---

    # Weather API
    if "weather" in query_types:
        weather_result = fetch_weather(query)
        if weather_result:
            results.append({
                'title': '[LIVE WEATHER] Weather Data',
                'body': weather_result,
                'href': f'https://wttr.in/{query}'
            })

    # Financial APIs
    if "financial" in query_types:
        fin_results = fetch_financial_data(query)
        results.extend(fin_results)

    # --- GOOGLE NEWS RSS (best for current affairs, always fresh) ---
    if "current_affairs" in query_types or "temporal" in query_types:
        # For current affairs, enhance query with the year
        news_query = enhance_query_for_recency(query)
        news_results = fetch_google_news_rss(news_query)
        results.extend(news_results)

    # --- DDGS SEARCH (general web search) ---
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            # For current affairs / temporal, prioritize news over text
            if "current_affairs" in query_types or "temporal" in query_types:
                enhanced_query = enhance_query_for_recency(query)

                # Try DDGS news first
                try:
                    print(f"[GoogleSearch] Trying DDGS News: '{enhanced_query}'")
                    news = list(ddgs.news(enhanced_query, max_results=5))
                    for r in news:
                        results.append({
                            'title': "[NEWS] " + r.get('title', 'No Title'),
                            'body': r.get('body', 'No Description'),
                            'href': r.get('url', '#')
                        })
                except Exception as e:
                    print(f"[GoogleSearch] DDGS News Error: {e}")

                # Then text search with year
                if len(results) < 5:
                    try:
                        print(f"[GoogleSearch] Trying DDGS Text: '{enhanced_query}'")
                        text = list(ddgs.text(enhanced_query, max_results=5))
                        for r in text:
                            results.append({
                                'title': r.get('title', 'No Title'),
                                'body': r.get('body', 'No Description'),
                                'href': r.get('href', '#')
                            })
                    except Exception as e:
                        print(f"[GoogleSearch] DDGS Text Error: {e}")
            else:
                # General queries — text search first
                try:
                    print(f"[GoogleSearch] Trying DDGS Text Search...")
                    text_results = list(ddgs.text(query, max_results=5))
                    for r in text_results:
                        results.append({
                            'title': r.get('title', 'No Title'),
                            'body': r.get('body', 'No Description'),
                            'href': r.get('href', '#')
                        })
                except Exception as e:
                    print(f"[GoogleSearch] DDGS Text Error: {e}")

                # Also try news if we don't have enough
                if len(results) < 3:
                    try:
                        print(f"[GoogleSearch] Trying DDGS News...")
                        news_results = list(ddgs.news(query, max_results=3))
                        for r in news_results:
                            results.append({
                                'title': "[NEWS] " + r.get('title', 'No Title'),
                                'body': r.get('body', 'No Description'),
                                'href': r.get('url', '#')
                            })
                    except Exception as e:
                        print(f"[GoogleSearch] DDGS News Error: {e}")
    except ImportError:
        print("[GoogleSearch] ⚠️ ddgs package not found, trying legacy...")
        try:
            from duckduckgo_search import DDGS
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
            print(f"[GoogleSearch] Legacy DDG Error: {e}")
    except Exception as e:
        print(f"[GoogleSearch] DDGS Error: {e}")

    # --- DDG Instant Answer API (stable, good for definitions) ---
    if len(results) < 3 and "general" in query_types:
        try:
            print(f"[GoogleSearch] Trying DuckDuckGo Instant Answer API...")
            api_url = f"https://api.duckduckgo.com/?q={query}&format=json"
            resp = requests.get(api_url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('AbstractText'):
                    results.append({
                        'title': "[API] " + data.get('Heading', 'Summary'),
                        'body': data.get('AbstractText'),
                        'href': data.get('AbstractURL', '#')
                    })
                for r in data.get('RelatedTopics', [])[:2]:
                    if 'Text' in r:
                        results.append({
                            'title': "[Related] " + query,
                            'body': r.get('Text'),
                            'href': r.get('FirstURL', '#')
                        })
        except Exception as e:
            print(f"[GoogleSearch] DDG API Error: {e}")

    # --- Google Search Fallback ---
    if not results:
        print(f"[GoogleSearch] ⚠️ Attempting Google Search Fallback...")
        try:
            from googlesearch import search
            g_query = enhance_query_for_recency(query) if ("current_affairs" in query_types or "temporal" in query_types) else query
            google_results = list(search(g_query, num_results=5, advanced=True))
            for r in google_results:
                results.append({
                    'title': "[GOOGLE] " + getattr(r, 'title', 'No Title'),
                    'body': getattr(r, 'description', 'No Description'),
                    'href': getattr(r, 'url', '#')
                })
        except Exception as ge:
            print(f"[GoogleSearch] Google Search Error: {ge}")

    # --- Also try Google News RSS as last resort if we still have nothing ---
    if not results:
        news_results = fetch_google_news_rss(query)
        results.extend(news_results)

    if not results:
        return f"No search results found for '{query}'."

    Answer = f"The real-time search results for '{query}' are:\n[start]\n"
    for i in results:
        Answer += f"Title: {i.get('title')}\nDescription: {i.get('body')}\nUrl: {i.get('href')}\n\n"
    Answer += "[end]"
    return Answer


def Information():
    now = datetime.datetime.now()
    return f"Time: {now.strftime('%H:%M:%S')}\nDate: {now.strftime('%d/%m/%Y')}\nDay: {now.strftime('%A')}\nYear: {now.strftime('%Y')}\n"


def RealtimeSearchEngine(prompt, provided_messages=None, user_name=None):
    if provided_messages is None:
        provided_messages = []
    if user_name is None:
        user_name = DefaultUsername

    print(f"[RealtimeSearchEngine] 🔍 Query: '{prompt}'")

    # Clean and detect query type
    search_query = clean_search_query(prompt)
    query_types = detect_query_type(search_query)

    print(f"[RealtimeSearchEngine] 🌐 Searching for: '{search_query}' (types: {query_types})")
    search_data = GoogleSearch(search_query, query_types)

    now = datetime.datetime.now()
    date_info = Information()

    # --- KEY FIX: Inject search data into the USER message, not just system prompt ---
    # LLMs (especially Llama) pay much more attention to user messages than system prompts.
    # This RAG-style approach forces the model to read and use the live search data.

    system_content = GetSystemMessage(user_name)

    # Build a RAG-style user message with search context embedded
    rag_user_message = f"""### REAL-TIME SEARCH RESULTS (As of {now.strftime('%B %d, %Y')}) ###
{search_data}
----------------------------------

### INSTRUCTIONS ###
1. Answer the question using ONLY the provided search results.
2. The search results above are LIVE and CORRECT. If they contradict your knowledge (e.g., about leaders, prices, dates), TRUST THE SEARCH RESULTS.
3. Your training data is OUTDATED. Do NOT use it.
4. If the results say Rekha Gupta is CM, she is CM. If they say gold is $2k, it is $2k.

Question: {prompt}
"""

    print(f"[RealtimeSearchEngine] 🤖 Calling LLM with AGGRESSIVE RAG prompt...")

    # We use a very low temperature for factual accuracy
    # We pass a shorter history to prevent old answers from biasing the model
    Answer = ""
    chunk_count = 0
    for chunk in UniversalAI(rag_user_message, system_prompt=system_content, history=provided_messages[-2:], temperature=0.0):
        Answer += chunk
        chunk_count += 1
        yield Answer

    print(f"[RealtimeSearchEngine] 🏁 Done. Chunks: {chunk_count}")

    if Answer:
        # Store the original prompt in history (not the RAG wrapper)
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
