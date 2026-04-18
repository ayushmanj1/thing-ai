"""
WebMain.py — Flask web server that connects the Nemo AI frontend
to the existing Nemo AI backend (Model, Chatbot, RealtimeSearchEngine, Automation).

Run with:  python WebMain.py
Then open: http://localhost:8000
"""

from flask import Flask, request, jsonify, render_template, send_from_directory, session
from dotenv import load_dotenv
import threading
import sys
import os
import re
import io
import time
import uuid
import traceback

# ── Force UTF-8 ──────────────────────────────────────────────────────────────
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ── Environment ──────────────────────────────────────────────────────────────
load_dotenv(override=True)
DefaultUsername      = os.getenv("Username", "User")
Assistantname = os.getenv("Assistantname", "Nemo")

# ── File-based status helpers (legacy, kept for minimal changes) ──────────────
current_dir = os.getcwd()
TempDirPath = os.path.join(current_dir, "Frontend", "Files")

# Ensure directories exist
os.makedirs(TempDirPath, exist_ok=True)
os.makedirs(os.path.join(current_dir, "Data"), exist_ok=True)

# ── NOW import the backend modules ──────────
from backend.Model import FirstLayerDMM
from backend.RealtimeSearchEngin import RealtimeSearchEngine
from backend.Chatbot import ChatBot, ClearChatHistory
from backend.ImageGeneration import GenerateImages

# ── Session Data Store (RAM-based) ───────────────────────────────────────────
# In a production environment with multiple Render workers, Redis would be better.
# For now, we use a global dictionary keyed by session ID.
SESSION_DATA = {}

def get_session_id():
    if 'uid' not in session:
        session['uid'] = str(uuid.uuid4())
    uid = session['uid']
    if uid not in SESSION_DATA:
        SESSION_DATA[uid] = {
            "history": [],
            "interrupt_flag": threading.Event(),
            "username": DefaultUsername,
            "last_interaction": time.time()
        }
    return uid

# ── Query modifier ───────────────────────────────────────────────────────────
def QueryModifier(Query):
    new_query = Query.lower().strip()
    if not new_query:
        return ""
    query_words = new_query.split()
    question_words = ["how", "what", "who", "where", "when", "why",
                      "which", "whose", "whom", "can you", "what's",
                      "where's", "how's"]
    if any(word + " " in new_query for word in question_words):
        if query_words[-1][-1] in ['.', '?', '!']:
            new_query = new_query[:-1] + "?"
        else:
            new_query += "?"
    else:
        if query_words[-1][-1] in ['.', '?', '!']:
            new_query = new_query[:-1] + "."
        else:
            new_query += "."
    return new_query.capitalize()


# ── Flask app ────────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates")
app.secret_key = os.getenv("SECRET_KEY", "nemo_ai_session_secret_key_9918")
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

@app.route("/")
def index():
    uid = get_session_id()
    # Optional: Clear history only if user explicitly clicks clear
    # ClearChatHistory(SESSION_DATA[uid]["history"])
    
    response = app.make_response(render_template("index.html"))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route("/clear", methods=["POST"])
def clear_chat():
    uid = get_session_id()
    ClearChatHistory(SESSION_DATA[uid]["history"])
    return jsonify(status="success", message="Chat history cleared from RAM"), 200


@app.route("/Data/<path:filename>")
@app.route("/data/<path:filename>")
def serve_data(filename):
    data_folder = os.path.join(current_dir, "Data")
    response = send_from_directory(data_folder, filename)
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response


# ── POST /speak ──────────────────────────────────────────────────────────────
@app.route("/speak", methods=["POST"])
def speak():
    uid = get_session_id()
    user_state = SESSION_DATA[uid]
    interrupt_flag = user_state["interrupt_flag"]
    history = user_state["history"]
    username = user_state["username"]

    data = request.get_json(force=True)
    user_text = (data.get("text") or "").strip()
    if not user_text:
        return jsonify(reply="I didn't catch that.", duration_ms=1500), 200

    # Handle name introduction (AI remembering user identity)
    # Simple heuristic: "my name is Ayush" or "I am Rahul"
    name_match = re.search(r"(?:my name is|i am|call me)\s+([a-zA-Z]+)", user_text.lower())
    if name_match:
        new_name = name_match.group(1).capitalize()
        user_state["username"] = new_name
        username = new_name

    interrupt_flag.clear()

    try:
        print(f"\n{'─'*50}")
        print(f"[WebMain] User ({username}): {user_text}")

        # ── 1. Decision layer ────────────────────────────────────────────
        try:
            Decision = FirstLayerDMM(user_text)
        except Exception as e:
            print(f"[WebMain] Decision error: {e}")
            Decision = ["general " + user_text]

        print(f"[WebMain] Decision: {Decision}")

        full_reply = ""
        action_urls = []

        for task in Decision:
            if interrupt_flag.is_set():
                break

            # ── Image generation ─────────────────────────────────────────
            if "generate image" in task:
                prompt = task.replace("generate image", "").strip()
                full_reply += f"Here are the images for '{prompt}': "
                try:
                    # Direct return value ensures thread-safety for multi-user requests
                    abs_img = GenerateImages(prompt)
                    
                    if abs_img and os.path.exists(abs_img):
                        idx = abs_img.lower().rfind("data\\")
                        if idx == -1: idx = abs_img.lower().rfind("data/")
                        
                        if idx != -1:
                            rel_path = abs_img[idx:].replace("\\", "/") 
                            ts = int(time.time())
                            full_reply += f" I've generated this for you! <br><img src='/{rel_path}?v={ts}' style='max-width:100%; max-height: 450px; border-radius:15px; margin-top:15px; border: 2px solid var(--accent); display:block;' /> "
                        else:
                            filename = os.path.basename(abs_img)
                            ts = int(time.time())
                            full_reply += f" I've generated this for you! <br><img src='/Data/{filename}?v={ts}' style='max-width:100%; max-height: 450px; border-radius:15px; margin-top:15px; border: 2px solid var(--accent); display:block;' /> "
                    else:
                        full_reply += f" I am so sorry, but I ran into a snag while generating your image. "
                except Exception as e:
                    full_reply += f" I am so sorry, {username}, but I ran into a tiny snag while creating your images: {e}. "

            # ── Realtime search, general chat, or content (writing/code) ──────
            elif any(tag in task for tag in ["realtime", "general", "content"]):
                clean_query = task.replace("realtime", "").replace("general", "").replace("content", "").strip()
                modified_query = QueryModifier(clean_query)

                if "realtime" in task:
                    print(f"[WebMain] → RealtimeSearchEngine (User: {username})")
                    generator = RealtimeSearchEngine(modified_query, provided_messages=history, user_name=username)
                else:
                    print(f"[WebMain] → ChatBot (User: {username})")
                    generator = ChatBot(modified_query, provided_messages=history, user_name=username)

                answer = ""
                try:
                    for chunk in generator:
                        if interrupt_flag.is_set():
                            break
                        answer = chunk
                except Exception as e:
                    print(f"[WebMain] Generator error: {e}")
                    if not answer:
                        answer = f"Sorry, I encountered an error: {e}"

                # ── Format Code Blocks ──
                def format_code_blocks(text):
                    code_regex = re.compile(r'```(\w+)?\s*(.*?)\s*```', re.DOTALL)
                    def replace_code(match):
                        lang = (match.group(1) or "code").strip()
                        code = match.group(2).strip().replace('<', '&lt;').replace('>', '&gt;')
                        block_id = f"code-{int(time.time() * 1000)}"
                        return (
                            f'<div class="code-container">'
                            f'<div class="code-header"><span>{lang}</span><button class="copy-btn" onclick="copyCode(this)">Copy</button></div>'
                            f'<pre><code id="{block_id}">{code}</code></pre></div>'
                        )
                    formatted_text = code_regex.sub(replace_code, text)
                    parts = re.split(r'(<div class="code-container">.*?</div>)', formatted_text, flags=re.DOTALL)
                    final_parts = []
                    for p in parts:
                        if not p.startswith('<div class="code-container">'):
                            final_parts.append(p.replace('\n', '<br>'))
                        else:
                            final_parts.append(p)
                    return "".join(final_parts)

                full_reply += format_code_blocks(answer)

            elif "exit" in task:
                full_reply += "Goodbye!"

        if not full_reply:
            full_reply = f"I am so sorry, {username}, but I missed that! I would be absolutely delighted if you could repeat it for me."
        elif "Goodbye" in full_reply and len(full_reply.split()) < 10:
             full_reply = f"{full_reply} It has been a wonderful experience assisting you. I hope you have a fantastic day ahead!"

        duration_ms = max(2000, len(full_reply) * 60)
        print(f"[WebMain] Reply ({len(full_reply)} chars): {full_reply[:100]}...")
        print(f"{'─'*50}")
        return jsonify(reply=full_reply, duration_ms=duration_ms, action_urls=action_urls), 200

    except Exception as e:
        print(f"[WebMain] CRITICAL ERROR: {e}")
        traceback.print_exc()
        return jsonify(reply=f"I'm so sorry, but I encountered a small technical hiccup. Could you please try again?"), 200

# ── POST /interrupt ──────────────────────────────────────────────────────────
@app.route("/interrupt", methods=["POST"])
def interrupt():
    uid = get_session_id()
    print(f"[WebMain] ⚡ Interrupt received for {uid}")
    SESSION_DATA[uid]["interrupt_flag"].set()
    return jsonify(status="interrupted"), 200

# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"Nemo AI — Cloud Web Interface Started on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
