import asyncio
from PIL import Image
import requests
from dotenv import load_dotenv
import os
from time import sleep as _sync_sleep
import json
import random

# Define paths
current_dir = os.path.dirname(os.path.abspath(__file__))
base_dir = os.path.dirname(current_dir)
env_path = os.path.join(base_dir, ".env")
status_file = os.path.join(base_dir, "Frontend", "Files", "Status.data")

# Load environment variables
load_dotenv()
HuggingFaceAPIKey = os.getenv("HuggingFaceAPIKey")

# Pollinations models (free, no key needed)
POLLINATIONS_MODELS = ["flux", "turbo", "flux-realism", "flux-anime"]

def SetAssistantStatus(Status):
    try:
        with open(status_file, "w", encoding='utf-8') as file:
            file.write(Status)
    except:
        pass

def open_images(prompt):
    folder_path = os.path.join(base_dir, "Data")
    prompt_safe = "".join(x for x in prompt if x.isalnum() or x in " _-").strip().replace(" ", "_")
    
    count = 0
    for i in range(1, 10):
        image_path = os.path.join(folder_path, f"{prompt_safe}{i}.jpg")
        if os.path.exists(image_path):
            try:
                img = Image.open(image_path)
                print(f"Opening: {image_path}")
                img.show()
                count += 1
                _sync_sleep(0.5)
            except Exception as e:
                print(f"Could not open {image_path}: {e}")
    return count

def is_valid_image_bytes(data: bytes, content_type: str = "") -> bool:
    """Check that bytes are actually an image, not a JSON error response."""
    if not data or len(data) < 100:
        return False
    # If content-type says image, trust it if it's big enough
    if 'image/' in content_type and len(data) > 5000:
        return True
    # JSON errors start with '{' or '['
    if data[:1] in (b'{', b'['):
        return False
    # JPEG magic
    if data[:2] == b'\xff\xd8':
        return True
    # PNG magic
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return True
    # WEBP magic
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return True
    # Accept any binary data larger than 10KB that doesn't look like JSON
    if len(data) > 10000:
        return True
    return False

def pollinations_generate(prompt: str, model: str = "flux", width: int = 768, height: int = 768, seed: int = None, max_retries: int = 3) -> bytes | None:
    """Generate an image using Pollinations.ai (free, no API key needed)."""
    if seed is None:
        seed = random.randint(1, 99999)
    
    prompt_encoded = requests.utils.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{prompt_encoded}?width={width}&height={height}&model={model}&seed={seed}&nologo=true"
    
    print(f"Pollinations [{model}] {width}x{height}: {url}")
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, timeout=30, allow_redirects=True)
            content_type = resp.headers.get('content-type', '')
            print(f"  -> Attempt {attempt}: Status {resp.status_code}, CT: {content_type}, Size: {len(resp.content)}")
            if resp.status_code == 200 and is_valid_image_bytes(resp.content, content_type):
                return resp.content
            elif resp.status_code == 429:
                wait = 15 * attempt
                print(f"  -> Rate limited, waiting {wait}s before retry...")
                _sync_sleep(wait)
            else:
                print(f"  -> Failed: {resp.content[:200]}")
                break
        except Exception as e:
            print(f"  -> Exception: {e}")
            if attempt < max_retries:
                _sync_sleep(5)
    return None

async def query_huggingface(model_id: str, payload: dict, attempt: int = 1) -> bytes | None:
    """Try HuggingFace router (requires paid tier for most models)."""
    api_url = f"https://router.huggingface.co/hf-inference/models/{model_id}"
    headers = {"Authorization": f"Bearer {HuggingFaceAPIKey}"}
    
    try:
        response = await asyncio.to_thread(
            requests.post, api_url, headers=headers, json=payload, timeout=90
        )
        content_type = response.headers.get('content-type', '')
        if response.status_code == 200:
            data = response.content
            if is_valid_image_bytes(data, content_type):
                return data
            else:
                print(f"HF {model_id}: 200 but invalid image (len={len(data)})")
        elif response.status_code == 503:
            try:
                error_msg = response.json().get('error', '')
            except:
                error_msg = ''
            if attempt < 3:
                wait = 20 * attempt
                print(f"HF {model_id} loading, retry in {wait}s...")
                await asyncio.sleep(wait)
                return await query_huggingface(model_id, payload, attempt + 1)
        elif response.status_code in (401, 402, 403, 410):
            print(f"HF {model_id}: Access denied ({response.status_code}) - skipping")
        else:
            print(f"HF {model_id}: status {response.status_code}")
    except Exception as e:
        print(f"HF {model_id}: Exception: {e}")
    return None

def AppendImageToChat(image_path):
    try:
        responses_file = os.path.join(base_dir, "Frontend", "Files", "Responses.data")
        with open(responses_file, "w", encoding='utf-8') as file:
            file.write(f"IMAGE:{image_path}")
    except:
        pass
async def save_image(img_bytes, prompt_safe, index, data_dir):
    filepath = os.path.join(data_dir, f"{prompt_safe}{index}.jpg")
    with open(filepath, "wb") as f:
        f.write(img_bytes)
    AppendImageToChat(filepath)
    print(f"Saved image to: {filepath}")
    return filepath


async def generate_images(prompt: str) -> str | None:
    SetAssistantStatus("Generating Image...")
    prompt_safe = "".join(x for x in prompt if x.isalnum() or x in " _-").strip().replace(" ", "_")
    data_dir = os.path.join(base_dir, "Data")
    os.makedirs(data_dir, exist_ok=True)
    
    # ── Strategy 1: Pollinations.ai ─────────────────
    model_configs = [
        ("flux", 768, 768, random.randint(1, 100000)),
        ("turbo", 512, 512, random.randint(1, 100000)),
        ("flux-realism", 768, 768, random.randint(1, 100000)),
        ("flux-anime", 768, 768, random.randint(1, 100000))
    ]
    
    tasks = [
        asyncio.to_thread(pollinations_generate, prompt, m, w, h, s)
        for m, w, h, s in model_configs
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    valid_results = [r for r in results if isinstance(r, bytes) and r]
    
    if valid_results:
        # Save only the first successful one for the web response return
        filepath = await save_image(valid_results[0], prompt_safe, random.randint(1, 999), data_dir)
        SetAssistantStatus("Image Generated!")
        return filepath

    # ── Strategy 2: HuggingFace ────────────────────
    hf_models = ["stabilityai/stable-diffusion-xl-base-1.0", "runwayml/stable-diffusion-v1-5"]
    payload = {"inputs": prompt, "options": {"wait_for_model": True}}
    for model in hf_models:
        img_bytes = await query_huggingface(model, payload)
        if img_bytes:
            filepath = await save_image(img_bytes, prompt_safe, random.randint(1, 999), data_dir)
            SetAssistantStatus("Image Generated!")
            return filepath

    SetAssistantStatus("Generation Failed.")
    return None

def GenerateImages(prompt: str) -> str | None:
    return asyncio.run(generate_images(prompt))

if __name__ == "__main__":
    trigger_file = os.path.join(base_dir, "Frontend", "Files", "ImageGeneration.data")
    try:
        if os.path.exists(trigger_file):
            with open(trigger_file, "r") as f:
                Data = f.read().strip()
            if "," in Data:
                last_comma = Data.rfind(",")
                Prompt = Data[:last_comma].strip()
                Status = Data[last_comma + 1:].strip()
                if Status == "True":
                    GenerateImages(prompt=Prompt)
                    # Reset trigger file
                    with open(trigger_file, "w") as f:
                        f.write("False,False")
    except Exception as e:
        print(f"Error: {e}")
        SetAssistantStatus("System Error.")