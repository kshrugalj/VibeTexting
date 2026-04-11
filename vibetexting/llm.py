import json
import os
from urllib import error, request

OLLAMA_API_URL = "http://localhost:11434/api/generate"
LM_STUDIO_BASE_URL = os.environ.get("VIBETEXT_LMSTUDIO_URL", "http://localhost:1234")
DEFAULT_LLM_TIMEOUT = float(os.environ.get("VIBETEXT_LLM_TIMEOUT_SECONDS", "90"))
LM_STUDIO_TIMEOUT = float(os.environ.get("VIBETEXT_LMSTUDIO_TIMEOUT_SECONDS", "240"))

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
    payload = {"model": model, "prompt": prompt, "stream": False}
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
        "temperature": 0.7,
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
    if backend == "ollama":
        return call_ollama(prompt, model)
    if backend == "lmstudio":
        return call_lmstudio(prompt, model)

    # auto: prefer LM Studio for Gemma-family models, otherwise Ollama
    if "gemma" in (model or "").lower():
        reply = call_lmstudio(prompt, model)
        if not reply.startswith("Error"):
            return reply
        fallback = call_ollama(prompt, model)
        return fallback if not fallback.startswith("Error") else f"{reply}\n\n{fallback}"

    reply = call_ollama(prompt, model)
    if not reply.startswith("Error"):
        return reply
    fallback = call_lmstudio(prompt, model)
    return fallback if not fallback.startswith("Error") else f"{reply}\n\n{fallback}"
