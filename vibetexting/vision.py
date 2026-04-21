import os
import json
import base64
import urllib.request
import urllib.error

# Lightweight persistent cache for image descriptions
VISION_CACHE_DIR = os.path.expanduser("~/.vibetexting/vision_cache")
os.makedirs(VISION_CACHE_DIR, exist_ok=True)

OLLAMA_API_URL = "http://localhost:11434/api/generate"
VISION_MODEL = "llava"  # Default Ollama vision model

def _get_cache_path(image_path: str) -> str:
    # Use simple hash of filename for cache
    import hashlib
    name_hash = hashlib.md5(image_path.encode()).hexdigest()
    return os.path.join(VISION_CACHE_DIR, f"{name_hash}.txt")

def _encode_image(image_path: str) -> str:
    """Encode an image to base64 string."""
    try:
        # Resolve tilde just in case, though iMessage uses absolute paths usually
        image_path = os.path.expanduser(image_path)
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        print(f"⚠️ Error reading image {image_path}: {e}")
        return ""

def describe_image(image_path: str) -> str:
    """
    Use a local vision model (LLaVA via Ollama) to describe an image.
    Caches the result to avoid redundant processing.
    """
    if not image_path or not os.path.exists(image_path):
        return "[Image unavailable]"

    # 1. Check Cache
    cache_path = _get_cache_path(image_path)
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            pass

    # 2. Encode Image
    base64_image = _encode_image(image_path)
    if not base64_image:
        return "[Unreadable Image]"

    # 3. Call Vision Model
    prompt = "Briefly describe this image in one short sentence. Do not start with 'This is an image of', just describe the subject."
    payload = {
        "model": VISION_MODEL,
        "prompt": prompt,
        "stream": False,
        "images": [base64_image]
    }
    
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            OLLAMA_API_URL,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            if response.status == 200:
                body = json.loads(response.read().decode("utf-8"))
                description = body.get("response", "").strip()
                
                if description:
                    # Save to cache
                    try:
                        with open(cache_path, "w", encoding="utf-8") as f:
                            f.write(description)
                    except Exception:
                        pass
                    
                    return f"[Image: {description}]"
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return f"[Image: {VISION_MODEL} model missing. Run 'ollama run {VISION_MODEL}']"
    except Exception:
        return "[Image analysis skipped - vision model unreachable]"

    return "[Image analysis failed]"
