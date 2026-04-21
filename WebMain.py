"""
WebMain.py — Flask web server that connects the Thing AI frontend
to the existing Thing AI backend (Model, Chatbot, RealtimeSearchEngine, Automation).

Run with:  python WebMain.py
Then open: http://localhost:8000
"""

from flask import Flask, request, jsonify, render_template, send_from_directory, session, Response, stream_with_context
from dotenv import load_dotenv
import threading
import sys
import os
import re
import io
import time
import uuid
import traceback
import razorpay
import hmac
import hashlib


# ── Force UTF-8 ──────────────────────────────────────────────────────────────
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ── Environment ──────────────────────────────────────────────────────────────
load_dotenv(override=True)
DefaultUsername      = os.getenv("Username", "Guest")
Assistantname = os.getenv("Assistantname", "Thing")

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
from backend.DocumentExtraction import get_document_content

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
app.secret_key = os.getenv("SECRET_KEY", "thing_ai_session_secret_key_9918")
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
    # Clear both history and reset username to default
    SESSION_DATA[uid]["history"].clear()
    SESSION_DATA[uid]["username"] = DefaultUsername
    return jsonify(status="success", message="Chat history and identity cleared"), 200


@app.route("/Data/<path:filename>")
@app.route("/data/<path:filename>")
def serve_data(filename):
    data_folder = os.path.join(current_dir, "Data")
    response = send_from_directory(data_folder, filename)
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response


@app.route("/manifest.json")
def serve_manifest():
    return send_from_directory("static", "manifest.json")


@app.route("/sw.js")
def serve_sw():
    response = send_from_directory("static", "sw.js", mimetype='application/javascript')
    response.headers['Service-Worker-Allowed'] = '/'
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


# ── POST /speak (Streaming) ──────────────────────────────────────────────────
import json

@app.route("/speak", methods=["POST"])
def speak():
    uid = get_session_id()
    user_state = SESSION_DATA[uid]
    interrupt_flag = user_state["interrupt_flag"]
    history = user_state["history"]
    username = user_state["username"]

    # --- SAFETY CHECK ---
    bad_phrases = ["supreme leader", "supream leader", "ayushman"]
    if any(phrase in username.lower() for phrase in bad_phrases):
        if DefaultUsername.lower() not in ["supreme leader ayushman", "ayushman"]:
            user_state["username"] = DefaultUsername
            username = DefaultUsername

    if request.is_json:
        data = request.get_json(force=True)
        user_text = (data.get("text") or "").strip()
        files = []
    else:
        user_text = request.form.get("text", "").strip()
        files = request.files.getlist("files")

    if not user_text and not files:
        return jsonify(reply="I didn't catch that."), 200

    document_context = None
    if files:
        allowed_exts = {'.pdf', '.docx', '.txt'}
        valid_files = [f for f in files if os.path.splitext(f.filename.lower())[1] in allowed_exts]
        try:
            document_context = get_document_content(valid_files)
        except Exception as e:
            print(f"Extraction error: {e}")
            document_context = "Error extracting text."

    name_match = re.search(r"(?:my name is|i am|call me)\s+([a-zA-Z]+)", user_text.lower())
    if name_match:
        username = name_match.group(1).capitalize()
        user_state["username"] = username

    interrupt_flag.clear()

    def generate():
        print(f"\n[WebMain] Streaming started for: {user_text}")
        try:
            if document_context:
                Decision = ["general " + user_text]
            else:
                Decision = FirstLayerDMM(user_text)
        except:
            Decision = ["general " + user_text]

        accumulated_reply = ""
        
        # Define the code block formatter locally or move to utils
        def format_code_blocks(text):
            code_regex = re.compile(r'```(\w+)?\s*(.*?)\s*```', re.DOTALL)
            def replace_code(match):
                lang = (match.group(1) or "code").strip()
                code = match.group(2).strip().replace('<', '&lt;').replace('>', '&gt;')
                block_id = f"code-{int(time.time() * 1000)}"
                return f'<div class="code-container"><div class="code-header"><span>{lang}</span><button class="copy-btn" onclick="copyCode(this)">Copy</button></div><pre><code id="{block_id}">{code}</code></pre></div>'
            formatted_text = code_regex.sub(replace_code, text)
            return formatted_text.replace('\n', '<br>') if '<div class="code-container">' not in formatted_text else formatted_text

        for task in Decision:
            if interrupt_flag.is_set(): 
                print(f"[WebMain] Interrupt detected, stopping task: {task}")
                break

            try:
                print(f"[WebMain] 🚀 Executing task: '{task}'")
                if "generate image" in task:
                    prompt = task.replace("generate image", "").strip()
                    yield json.dumps({"reply": f"Generating images for '{prompt}'...", "status": "working"}) + "\n"
                    abs_img = GenerateImages(prompt)
                    if abs_img and os.path.exists(abs_img):
                        filename = os.path.basename(abs_img)
                        img_html = f"<br><img src='/Data/{filename}?v={int(time.time())}' style='max-width:100%; border-radius:15px; margin-top:15px; border:2px solid var(--accent);' />"
                        yield json.dumps({"reply": img_html, "status": "done"}) + "\n"
                    else:
                        yield json.dumps({"reply": "Image generation failed.", "status": "error"}) + "\n"

                elif any(tag in task for tag in ["realtime", "general", "content"]):
                    clean_query = task.replace("realtime", "").replace("general", "").replace("content", "").strip()
                    modified_query = QueryModifier(clean_query)
                    
                    if "realtime" in task:
                        generator = RealtimeSearchEngine(modified_query, provided_messages=history, user_name=username)
                    else:
                        generator = ChatBot(modified_query, provided_messages=history, user_name=username, document_context=document_context)

                    last_sent_len = 0
                    for full_answer in generator:
                        if interrupt_flag.is_set(): break
                        
                        new_chunk = full_answer[last_sent_len:]
                        last_sent_len = len(full_answer)
                        yield json.dumps({"chunk": new_chunk}) + "\n"
            except Exception as e:
                print(f"[WebMain] Loop Error: {e}")
                import traceback
                traceback.print_exc()
                yield json.dumps({"reply": f"An error occurred: {str(e)}", "status": "error"}) + "\n"
        
        yield json.dumps({"done": True}) + "\n"

    return Response(stream_with_context(generate()), mimetype='application/x-ndjson')

# ── Razorpay Integration ─────────────────────────────────────────────────────
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)) if RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET else None

@app.route("/create-order", methods=["POST"])
def create_order():
    if not razorpay_client:
        return jsonify(error="Razorpay not configured"), 500
    try:
        data = request.json
        amount = data.get("amount", 9900) # Default amount in paise
        currency = "INR"
        receipt = str(uuid.uuid4())
        
        order = razorpay_client.order.create({
            "amount": amount,
            "currency": currency,
            "receipt": receipt,
        })
        return jsonify(order_id=order["id"], amount=amount, key=RAZORPAY_KEY_ID)
    except Exception as e:
        return jsonify(error=str(e)), 500

@app.route("/verify-payment", methods=["POST"])
def verify_payment():
    if not razorpay_client:
        return jsonify(error="Razorpay not configured"), 500
    data = request.json
    razorpay_order_id = data.get("razorpay_order_id")
    razorpay_payment_id = data.get("razorpay_payment_id")
    razorpay_signature = data.get("razorpay_signature")
    plan_name = data.get("plan", "Premium")
    
    # Verify signature
    try:
        razorpay_client.utility.verify_payment_signature({
            'razorpay_order_id': razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature': razorpay_signature
        })
        
        uid = get_session_id()
        SESSION_DATA[uid]["is_premium"] = True
        SESSION_DATA[uid]["plan"] = plan_name
        
        return jsonify(status="success", message=f"Payment verified. Welcome to {plan_name}!")
    except razorpay.errors.SignatureVerificationError:
        return jsonify(status="error", message="Invalid payment signature"), 400
    except Exception as e:
        return jsonify(status="error", message=str(e)), 500

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
    print(f"Thing AI — Cloud Web Interface Started on port {port}")
    app.run(host="0.0.0.0", port=port, debug=True, threaded=True)
