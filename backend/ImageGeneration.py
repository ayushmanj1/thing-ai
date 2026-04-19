import asyncio
import requests
from dotenv import load_dotenv
import os
import json
import random
from PIL import Image

# Define paths
current_dir = os.path.dirname(os.path.abspath(__file__))
base_dir = os.path.dirname(current_dir)
data_dir = os.path.join(base_dir, "Data")

# Load environment variables
load_dotenv()
HuggingFaceAPIKey = os.getenv("HuggingFaceAPIKey")

def is_valid_image_bytes(data: bytes, content_type: str = "") -> bool:
    if not data or len(data) < 100:
        return False
    if 'image/' in content_type and len(data) > 5000:
        return True
    if data[:1] in (b'{', b'['):
        return False
    # Magic numbers
    if data[:2] == b'\xff\xd8': return True # JPEG
    if data[:8] == b'\x89PNG\r\n\x1a\n': return True # PNG
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP': return True # WEBP
    return len(data) > 10000

def pollinations_generate(prompt: str, model: str = "flux", width: int = 1024, height: int = 1024, seed: int = None) -> bytes | None:
    if seed is None: seed = random.randint(1, 999999)
    prompt_encoded = requests.utils.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{prompt_encoded}?width={width}&height={height}&model={model}&seed={seed}&nologo=true"
    
    try:
        resp = requests.get(url, timeout=45)
        if resp.status_code == 200 and is_valid_image_bytes(resp.content, resp.headers.get('content-type', '')):
            return resp.content
    except Exception as e:
        print(f"[ImageGen] Pollinations Error ({model}): {e}")
    return None

async def query_huggingface(model_id: str, prompt: str) -> bytes | None:
    api_url = f"https://router.huggingface.co/hf-inference/models/{model_id}"
    headers = {"Authorization": f"Bearer {HuggingFaceAPIKey}"}
    payload = {"inputs": prompt, "options": {"wait_for_model": True}}
    
    try:
        response = await asyncio.to_thread(requests.post, api_url, headers=headers, json=payload, timeout=60)
        if response.status_code == 200 and is_valid_image_bytes(response.content, response.headers.get('content-type', '')):
            return response.content
    except Exception as e:
        print(f"[ImageGen] HF Error ({model_id}): {e}")
    return None

async def save_image(img_bytes, prompt_safe):
    os.makedirs(data_dir, exist_ok=True)
    filename = f"{prompt_safe}_{random.randint(1000, 9999)}.jpg"
    filepath = os.path.join(data_dir, filename)
    with open(filepath, "wb") as f:
        f.write(img_bytes)
    return filepath

async def generate_images_async(prompt: str) -> str | None:
    prompt_safe = "".join(x for x in prompt if x.isalnum() or x in " _-").strip().replace(" ", "_")[:50]
    
    # Try parallel Pollinations models first
    models = ["flux", "turbo", "flux-realism"]
    tasks = [asyncio.to_thread(pollinations_generate, prompt, m) for m in models]
    
    results = await asyncio.gather(*tasks)
    valid_results = [r for r in results if r]
    
    if valid_results:
        return await save_image(valid_results[0], prompt_safe)

    # Fallback to HuggingFace
    hf_models = ["stabilityai/stable-diffusion-xl-base-1.0", "runwayml/stable-diffusion-v1-5"]
    for model in hf_models:
        img_bytes = await query_huggingface(model, prompt)
        if img_bytes:
            return await save_image(img_bytes, prompt_safe)

    return None

def GenerateImages(prompt: str) -> str | None:
    """Entry point for WebMain.py"""
    try:
        return asyncio.run(generate_images_async(prompt))
    except Exception as e:
        print(f"[ImageGen] Critical Error: {e}")
        return None

if __name__ == "__main__":
    p = input("Enter prompt: ")
    try:
        res = GenerateImages(p)
        print(f"Result: {res}")
    except Exception as e:
        print(f"Error: {e}")