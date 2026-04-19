import json
import os
import subprocess
import time
from typing import Optional, List
from urllib import error, request

OLLAMA_API_URL = "http://localhost:11434/api/generate"
LM_STUDIO_BASE_URL = os.environ.get("VIBETEXT_LMSTUDIO_URL", "http://localhost:1234")
DEFAULT_LLM_TIMEOUT = float(os.environ.get("VIBETEXT_LLM_TIMEOUT_SECONDS", "90"))
LM_STUDIO_TIMEOUT = float(os.environ.get("VIBETEXT_LMSTUDIO_TIMEOUT_SECONDS", "240"))

_lmstudio_process = None

def is_lmstudio_running() -> bool:
    """Check if LM Studio server is running."""
    try:
        url = f"{LM_STUDIO_BASE_URL.rstrip('/')}/v1/models"
        with request.urlopen(url, timeout=2) as response:
            return response.status == 200
    except Exception:
        return False

def start_lmstudio_server(model_to_load: Optional[str] = None) -> bool:
    """Start LM Studio server if not already running, and optionally load a model."""
    global _lmstudio_process
    if not is_lmstudio_running():
        try:
            # If we think we have a process but it's actually dead, clean up
            if _lmstudio_process is not None and _lmstudio_process.poll() is not None:
                _lmstudio_process = None

            if _lmstudio_process is None:
                # Start LM Studio in headless server mode
                # Note: 'lms' should be in the user's PATH. 
                # We use a list to avoid shell=True security risks.
                _lmstudio_process = subprocess.Popen(
                    ["lms", "server", "start", "-p", "1234"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                # Wait for server to be ready
                for _ in range(15):  # Wait up to 15 seconds
                    time.sleep(1)
                    if is_lmstudio_running():
                        break
        except Exception:
            pass

    if is_lmstudio_running() and model_to_load:
        # Check if requested model (or similar) is already loaded
        loaded_models = list_lmstudio_models()
        if model_to_load not in loaded_models:
            # Try to find the full identifier from installed models and load it
            try:
                result = subprocess.run(["lms", "ls"], capture_output=True, text=True)
                for line in result.stdout.split('\n'):
                    if model_to_load.lower() in line.lower():
                        full_id = line.split()[0]
                        print(f"Auto-loading model in LM Studio: {full_id}...")
                        subprocess.run(["lms", "load", full_id], stdout=subprocess.DEVNULL)
                        break
            except Exception:
                pass
    return is_lmstudio_running()

def stop_lmstudio_server() -> bool:
    """Stop LM Studio server if we started it."""
    global _lmstudio_process
    try:
        if _lmstudio_process is not None:
            # Try to stop via lms CLI
            subprocess.run(
                ["lms", "server", "stop"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5
            )
            _lmstudio_process = None
            return True
    except Exception:
        pass
    return False

def _post_json(url: str, payload: dict, timeout: float = DEFAULT_LLM_TIMEOUT) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
        return json.loads(response.read().decode("utf-8"))

def call_ollama(prompt: str, model: str = "llama3") -> str:
    """Calls a local Ollama instance for truly local generation."""
    # num_ctx: 8192 allows for more conversation history
    payload = {
        "model": model, 
        "prompt": prompt, 
        "stream": False,
        "options": {
            "num_ctx": 8192,
            "temperature": 0.6,
            "frequency_penalty": 1.2,
            "presence_penalty": 0.5
        }
    }
    try:
        body = _post_json(OLLAMA_API_URL, payload, timeout=DEFAULT_LLM_TIMEOUT)
        return body.get("response", "").strip()
    except error.HTTPError as e:
        return (
            f"Error: Ollama returned {e.code}. "
            f"Make sure model '{model}' is installed (run 'ollama pull {model}')."
        )
    except Exception as e:
        return f"Error connecting to Ollama: {str(e)}\nEnsure Ollama is running (https://ollama.com)."

def list_ollama_models() -> list[str]:
    """Lists available models from the local Ollama instance."""
    try:
        url = OLLAMA_API_URL.replace("/generate", "/tags")
        with request.urlopen(url, timeout=2) as response:
            data = json.loads(response.read().decode("utf-8"))
            return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []

def call_lmstudio(prompt: str, model: str) -> str:
    """Calls LM Studio's OpenAI-compatible local server."""
    api_url = f"{LM_STUDIO_BASE_URL.rstrip('/')}/v1/chat/completions"
    # The prompt is built for text completion. Split it into system instructions
    # and the user message so the chat completions API works correctly.
    chat_prompt = prompt.rstrip()
    if chat_prompt.endswith("Response:"):
        chat_prompt = chat_prompt[: -len("Response:")].rstrip()
    if "\nIncoming message:" in chat_prompt:
        system_part, user_part = chat_prompt.split("\nIncoming message:", 1)
        messages = [
            {"role": "system", "content": system_part.strip()},
            {"role": "user", "content": ("Incoming message:" + user_part).strip()},
        ]
    else:
        messages = [{"role": "user", "content": chat_prompt}]
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.6,
        "frequency_penalty": 1.2,
        "presence_penalty": 0.5,
    }
    try:
        body = _post_json(api_url, payload, timeout=LM_STUDIO_TIMEOUT)
        choices = body.get("choices", [])
        if not choices:
            return "Error: LM Studio returned an empty response."
        return (choices[0].get("message", {}).get("content", "") or "").strip()
    except error.HTTPError as e:
        return (
            f"Error: LM Studio returned {e.code}. "
            "Make sure the Local Server is running and the model is loaded in LM Studio."
        )
    except Exception as e:
        err_text = str(e).lower()
        if "timed out" in err_text or "timeout" in err_text:
            return (
                "Error connecting to LM Studio: timed out waiting for model output.\n"
                "Try increasing timeout with VIBETEXT_LMSTUDIO_TIMEOUT_SECONDS (e.g. 600)."
            )
        return (
            f"Error connecting to LM Studio: {str(e)}\n"
            "Start LM Studio, load a model, and enable the Local Server (default http://localhost:1234)."
        )

def list_lmstudio_models() -> list[str]:
    """Lists available models from the LM Studio Local Server."""
    try:
        url = f"{LM_STUDIO_BASE_URL.rstrip('/')}/v1/models"
        with request.urlopen(url, timeout=2) as response:
            data = json.loads(response.read().decode("utf-8"))
            return [m["id"] for m in data.get("data", [])]
    except Exception:
        return []

def call_local_llm(prompt: str, model: str = "llama3", backend: str = "auto") -> str:
    backend = (backend or "auto").lower()
    model_lower = (model or "").lower()

    # Smart Matching: If user says 'gemma', find the full ID (e.g., google/gemma-4-e4b)
    if "gemma" in model_lower and "google" not in model_lower:
        lms_models = list_lmstudio_models() # Check currently loaded
        found = False
        for m in lms_models:
            if "gemma" in m.lower():
                model = m
                found = True
                break
        
        if not found:
            # Check if it's installed but not loaded
            try:
                result = subprocess.run(["lms", "ls"], capture_output=True, text=True)
                for line in result.stdout.split('\n'):
                    if "gemma" in line.lower():
                        model = line.split()[0]
                        break
            except Exception:
                pass

    if backend == "ollama":
        return call_ollama(prompt, model)
    if backend == "lmstudio":
        start_lmstudio_server(model) # Auto-load if needed
        return call_lmstudio(prompt, model)

    # auto: prefer LM Studio for Gemma-family models, otherwise Ollama
    if "gemma" in model.lower():
        start_lmstudio_server(model)
        reply = call_lmstudio(prompt, model)
        if not reply.startswith("Error"):
            return reply
        fallback = call_ollama(prompt, model)
        return fallback if not fallback.startswith("Error") else f"{reply}\n\n{fallback}"

    reply = call_ollama(prompt, model)
    if not reply.startswith("Error"):
        return reply
    
    start_lmstudio_server(model)
    fallback = call_lmstudio(prompt, model)
    return fallback if not fallback.startswith("Error") else f"{reply}\n\n{fallback}"
