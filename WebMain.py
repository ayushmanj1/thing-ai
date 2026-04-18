"""
WebMain.py — Flask web server that connects the Nemo AI frontend
to the existing Nemo AI backend (Model, Chatbot, RealtimeSearchEngine, Automation).

Run with:  python WebMain.py
Then open: http://localhost:8000
"""

from flask import Flask, request, jsonify, render_template, send_from_directory
from dotenv import load_dotenv
import threading
import sys
import os
import re
import io
import time

import traceback

# ── Force UTF-8 ──────────────────────────────────────────────────────────────
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ── Environment ──────────────────────────────────────────────────────────────
load_dotenv()
Username      = os.getenv("Username", "User")
Assistantname = os.getenv("Assistantname", "Nemo")

# ── File-based status helpers (shared with TTS/backend) ──────────────────────
current_dir = os.getcwd()
TempDirPath = os.path.join(current_dir, "Frontend", "Files")

# Ensure directories exist
os.makedirs(TempDirPath, exist_ok=True)
os.makedirs(os.path.join(current_dir, "Data"), exist_ok=True)

def _write(filename, content):
    """Write content to a file in the TempDir."""
    with open(os.path.join(TempDirPath, filename), "w", encoding="utf-8") as f:
        f.write(content)


def _read(filename, default=""):
    """Read content from a file in the TempDir."""
    try:
        with open(os.path.join(TempDirPath, filename), "r", encoding="utf-8") as f:
            return f.read().strip()
    except (FileNotFoundError, IOError):
        return default


def set_stop_status(s):
    """Update stop status."""
    _write("Stop.data", s)


def get_stop_status():
    """Retrieve stop status."""
    return _read("Stop.data", "False")




# ── Initialize data files ────────────────────────────────────────────────────
for fname, default in [("Stop.data", "False"), ("Responses.data", "")]:
    path = os.path.join(TempDirPath, fname)
    if not os.path.exists(path):
        _write(fname, default)

chatlog = os.path.join(current_dir, "Data", "ChatLog.json")
if not os.path.exists(chatlog):
    with open(chatlog, "w") as f:
        f.write("[]")

# ── Mock keyboard module to prevent crashes in headless/cloud environments ───────
# The backend modules import `keyboard` which requires root on Linux.
# We mock it completely to avoid the import error and handle interrupts cleanly.
class MockKeyboard:
    def __init__(self):
        self._interrupt_flag = threading.Event()
    def is_pressed(self, key):
        if key == 'w':
            return self._interrupt_flag.is_set()
        return False

# Inject the mock into sys.modules BEFORE any backend modules are imported
_mock_kb = MockKeyboard()
sys.modules['keyboard'] = _mock_kb # type: ignore
_interrupt_flag = _mock_kb._interrupt_flag

# ── NOW import the backend modules ──────────
from backend.Model import FirstLayerDMM
from backend.RealtimeSearchEngin import RealtimeSearchEngine

from backend.Chatbot import ChatBot
from backend.ImageGeneration import GenerateImages

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



# Remove lock to prevent "Heavily Processing" errors
# _processing_lock = threading.Lock()

# ── Flask app ────────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates")
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

@app.route("/")
def index():
    # no_cache headers so browser always gets fresh HTML
    response = app.make_response(render_template("index.html"))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route("/Data/<path:filename>")
@app.route("/data/<path:filename>")
def serve_data(filename):
    data_folder = os.path.join(current_dir, "Data")
    response = send_from_directory(data_folder, filename)
    # Prevent caching of images so new generations show up instantly
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response



# ── POST /speak ──────────────────────────────────────────────────────────────
@app.route("/speak", methods=["POST"])
def speak():
    data = request.get_json(force=True)
    user_text = (data.get("text") or "").strip()
    if not user_text:
        return jsonify(reply="I didn't catch that.", duration_ms=1500), 200

    # Clear any previous interrupt and ensure we have a fresh start
    _interrupt_flag.clear()
    set_stop_status("False")



    try:

        print(f"\n{'─'*50}")
        print(f"[WebMain] User: {user_text}")

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
            if _interrupt_flag.is_set():
                break

            # ── Image generation ─────────────────────────────────────────
            if "generate image" in task:
                prompt = task.replace("generate image", "").strip()
                full_reply += f"Here are the images for '{prompt}': "
                try:
                    img_data_path = os.path.join(current_dir, "Frontend", "Files", "ImageGeneration.data")
                    # Clear any old results
                    resp_path = os.path.join(current_dir, "Frontend", "Files", "Responses.data")
                    if os.path.exists(resp_path): os.remove(resp_path)
                    
                    # Direct call is much faster than subprocess
                    GenerateImages(prompt)
                    
                    if os.path.exists(resp_path):
                        with open(resp_path, "r", encoding="utf-8") as rf:
                            resp_content = rf.read().strip()
                        if resp_content.startswith("IMAGE:"):
                            abs_img = resp_content.replace("IMAGE:", "").strip()
                            idx = abs_img.lower().rfind("data\\")
                            if idx == -1: idx = abs_img.lower().rfind("data/")
                            
                            if idx != -1:
                                rel_path = abs_img[idx:].replace("\\", "/") # e.g., "Data/img.jpg"
                                ts = int(time.time())
                                full_reply += f" I've generated this for you! <br><img src='/{rel_path}?v={ts}' style='max-width:100%; max-height: 450px; border-radius:15px; margin-top:15px; border: 2px solid var(--accent); display:block;' /> "
                            else:
                                filename = os.path.basename(abs_img)
                                ts = int(time.time())
                                full_reply += f" I've generated this for you! <br><img src='/Data/{filename}?v={ts}' style='max-width:100%; max-height: 450px; border-radius:15px; margin-top:15px; border: 2px solid var(--accent); display:block;' /> "
                        else:
                            full_reply += f" I've completed the generation for '{prompt}'! "
                    else:
                        full_reply += f" snag while displaying the image. "
                except Exception as e:
                    full_reply += f" I am so sorry, {Username}, but I ran into a tiny snag while creating your images: {e}. "



            # ── Realtime search, general chat, or content (writing/code) ──────
            elif any(tag in task for tag in ["realtime", "general", "content"]):
                clean_query = task.replace("realtime", "").replace("general", "").replace("content", "").strip()
                modified_query = QueryModifier(clean_query)

                if "realtime" in task:
                    print(f"[WebMain] → RealtimeSearchEngine: {modified_query}")
                    generator = RealtimeSearchEngine(modified_query)
                else:
                    # ChatBot handles both general and content/code
                    print(f"[WebMain] → ChatBot: {modified_query}")
                    generator = ChatBot(modified_query)

                # Consume the streaming generator to get the final answer
                answer = ""
                try:
                    for chunk in generator:
                        if _interrupt_flag.is_set():
                            break
                        answer = chunk
                except Exception as e:
                    print(f"[WebMain] Generator error: {e}")
                    traceback.print_exc()
                    if not answer:
                        answer = f"Sorry, I encountered an error: {e}"

                # ── Format Code Blocks for the Web UI ──
                # Convert ```lang ... ``` into a styled div with a copy button
                def format_code_blocks(text):
                    # More flexible regex to catch code blocks even without newlines
                    code_regex = re.compile(r'```(\w+)?\s*(.*?)\s*```', re.DOTALL)
                    
                    def replace_code(match):
                        lang = (match.group(1) or "code").strip()
                        code = match.group(2).strip().replace('<', '&lt;').replace('>', '&gt;')
                        block_id = f"code-{int(time.time() * 1000)}"
                        # Constructing HTML without leading indentation spaces to ensure proper alignment
                        html = (
                            f'<div class="code-container">'
                            f'<div class="code-header">'
                            f'<span>{lang}</span>'
                            f'<button class="copy-btn" onclick="copyCode(this)">'
                            f'<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>'
                            f' Copy</button></div>'
                            f'<pre><code id="{block_id}">{code}</code></pre>'
                            f'</div>'
                        )
                        return html
                    
                    # First, extract and format code blocks
                    formatted_text = code_regex.sub(replace_code, text)
                    
                    # If it's NOT a code block, preserve line breaks for proper alignment
                    # We split by our added tags to avoid double-processing the code content
                    parts = re.split(r'(<div class="code-container">.*?</div>)', formatted_text, flags=re.DOTALL)
                    final_parts = []
                    for p in parts:
                        if not p.startswith('<div class="code-container">'):
                            # Process only the text parts
                            final_parts.append(p.replace('\n', '<br>'))
                        else:
                            final_parts.append(p)
                    
                    return "".join(final_parts)

                full_reply += format_code_blocks(answer)

            # ── Exit ─────────────────────────────────────────────────────
            elif "exit" in task:
                full_reply += "Goodbye!"

        if not full_reply:
            full_reply = f"I am so sorry, {Username}, but I missed that! I would be absolutely delighted if you could repeat it for me."
        elif "Goodbye" in full_reply and len(full_reply.split()) < 10:
             full_reply = f"{full_reply} It has been a wonderful experience assisting you. I hope you have a fantastic day ahead!"

        duration_ms = max(2000, len(full_reply) * 60)

        print(f"[WebMain] Reply ({len(full_reply)} chars): {full_reply[:200]}")
        print(f"{'─'*50}")
        return jsonify(reply=full_reply, duration_ms=duration_ms, action_urls=action_urls), 200

    except Exception as e:
        print(f"[WebMain] CRITICAL ERROR: {e}")
        traceback.print_exc()
        return jsonify(reply=f"I'm so sorry, but I encountered a small technical hiccup while processing your request. Could you please try asking again?", duration_ms=3000), 200

# ── POST /interrupt ──────────────────────────────────────────────────────────
@app.route("/interrupt", methods=["POST"])
def interrupt():
    """Handle user interrupt requests."""
    print("[WebMain] ⚡ Interrupt received")
    _interrupt_flag.set()
    set_stop_status("True")

    return jsonify(status="interrupted"), 200

# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"\n{'='*50}")
    print(f"  Nemo AI — Cloud Web Interface Started")
    print(f"  Running on port {port}")
    print(f"{'='*50}\n")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
